"""Verify our built release, then smoke-test it in a fresh private directory."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sys
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_release import RELEASE_FILENAME


def verify_archive(archive):
    with zipfile.ZipFile(archive) as package:
        names=package.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate archive names')
        for name in names:
            parts=PurePosixPath(name).parts
            if not parts or parts[0]!='jilian-local' or '..' in parts or '\\' in name:
                raise ValueError('Unsafe archive path')
            if any(part in {'.env','.git','.venv','.tmp','__pycache__','node_modules','local','cache'} for part in parts):
                raise ValueError('Private or runtime directory in release')
        manifest=json.loads(package.read('jilian-local/MANIFEST.json'))
        expected={'jilian-local/'+name for name in manifest['files']}|{'jilian-local/MANIFEST.json'}
        if set(names)!=expected:raise ValueError('Manifest file set mismatch')
        for name,digest in manifest['files'].items():
            if hashlib.sha256(package.read('jilian-local/'+name)).hexdigest()!=digest:raise ValueError('File hash mismatch')
        return manifest


def smoke():
    archive=ROOT/'dist'/RELEASE_FILENAME;manifest=verify_archive(archive)
    directory=ROOT/'.tmp'/('release-smoke-'+uuid.uuid4().hex);directory.mkdir(parents=True)
    with zipfile.ZipFile(archive) as package:package.extractall(directory)
    checkout=directory/'jilian-local'
    (checkout/'.env').write_bytes((checkout/'.env.example').read_bytes())
    env={k:v for k,v in os.environ.items() if not k.startswith(('TRACKUNIT_','OLLAMA_','GEMINI_','PYTHONPATH')) and k not in {'DATABASE_URL','SQLITE_DB_PATH','DATA_SOURCE','AI_PROVIDER'}}
    prepared=subprocess.run([sys.executable,'scripts/prepare_parts_demo.py','--install'],cwd=checkout,env=env,capture_output=True,text=True)
    if prepared.returncode:raise RuntimeError('Extracted demo preparation failed')
    code='''
from pathlib import Path
import json
from fastapi.testclient import TestClient
from app.main import app
from app import normalizer
from app.core.config import settings
from app import local_assistant as agent
decisions=[]
original_step=agent.model_step
def capture_step(messages,allowed=None):
    decision=original_step(messages,allowed)
    decisions.append({'decision':decision.model_dump(),'control':messages[-1]['content']})
    Path('smoke-model-decisions.json').write_text(json.dumps(decisions,ensure_ascii=False,indent=2),encoding='utf-8')
    return decision
agent.model_step=capture_step
assert Path(normalizer.__file__).resolve().is_relative_to(Path.cwd())
assert settings.sqlite_db_path.is_relative_to(Path.cwd())
with TestClient(app) as client:
    assert client.get('/health').json()['data_source']=='mock'
    machines=client.get('/machines').json()
    assert len(machines)==5 and all(m['serial_number'].startswith('SIM-FLEET-') for m in machines)
    datasets=client.get('/assistant/datasets').json()
    assert len(datasets)==1 and datasets[0]['provenance']=='synthetic'
    assert client.get('/assistant/catalog').json()['demo']==1
    episodes=client.get('/assistant/work-state/episodes').json()
    assert len(episodes)==7
    replay=client.get('/assistant/work-state/replay',params={'episode_id':episodes[0]['episode_id'],'count':12})
    assert replay.status_code==200,replay.text[:200]
    response=client.post('/assistant/investigate',json={'machine_id':datasets[0]['machine']['machine_id'],
        'dataset_id':datasets[0]['dataset_id'],'task':'parts','question':'读取故障并匹配备件，说明仍需核实的事项。'})
    assert response.status_code==200,response.text[:200]
    report=response.json()
    assert report['history_saved'] and report['model']=='qwen3.5:9b'
    assert report['summary_status']=='ai_interpretation_requires_review'
    assert len(report['data_facts'])>=4 and any(f['fact_id']=='parts-result' for f in report['data_facts'])
    assert all(set(f['evidence_ids'])<=set(report['evidence']) for f in report['data_facts'])
    assert report['parts_candidates'] and all(p['part_number'].startswith('DEMO-') for p in report['parts_candidates'])
    print(json.dumps({'health':'ok','machines':len(machines),'datasets':len(datasets),'test_episodes':len(episodes),
        'replay_status':replay.status_code,'local_model':report['model'],'history_saved':report['history_saved'],
        'tool_queries':len(report['tool_trace']),'demo_candidates':len(report['parts_candidates']),
        'data_facts':len(report['data_facts'])}))
'''
    result=subprocess.run([sys.executable,'-c',code],cwd=checkout,env=env,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Extracted application smoke failed in '+str(checkout)+': '+result.stderr[-1600:])
    data=json.loads(result.stdout)
    return {'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'manifest_files':len(manifest['files']),
            'isolated_checkout':str(checkout),'checks':data,'scope':'existing Python dependencies; no clean-machine or offline claim'}


if __name__=='__main__':print(json.dumps(smoke(),ensure_ascii=False,indent=2))
