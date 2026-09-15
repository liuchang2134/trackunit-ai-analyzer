"""Self-test a fresh extracted prototype without making a provider request."""
from datetime import datetime,timezone
import csv
import importlib.metadata
import io
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.verify_release_v8 import verify_folder


def run(verifier=verify_folder):
    manifest=verifier(ROOT)
    # Require the packaged blank config, not a user credential. No key is printed.
    config=(ROOT/'.env').read_bytes()
    if config!=(ROOT/'.env.example').read_bytes():
        raise RuntimeError('Run release smoke in a fresh extracted copy with the unchanged blank .env.example configuration')
    for key in list(os.environ):
        if key.startswith(('TRACKUNIT_','GEMINI_','OLLAMA_')) or key in {'AI_PROVIDER','DATA_SOURCE','SQLITE_DB_PATH','DATABASE_URL'}:
            os.environ.pop(key,None)
    attempts=[]
    original_connect=socket.socket.connect;original_resolve=socket.getaddrinfo
    def local(host):
        if host=='localhost':return True
        try:return ipaddress.ip_address(host).is_loopback
        except ValueError:return False
    def connect(sock,address):
        if isinstance(address,tuple) and not local(address[0]):
            attempts.append('nonlocal socket');raise RuntimeError('Provider network disabled during release verification')
        return original_connect(sock,address)
    def resolve(host,*args,**kwargs):
        if host is not None and not local(host):
            attempts.append('nonlocal DNS');raise RuntimeError('Provider network disabled during release verification')
        return original_resolve(host,*args,**kwargs)
    socket.socket.connect=connect;socket.getaddrinfo=resolve
    try:
        from fastapi.testclient import TestClient
        from app.main import app
        from app import normalizer
        from app.core.config import settings
        from scripts.check_local_runtime import check
        assert Path(normalizer.__file__).resolve().is_relative_to(ROOT)
        assert settings.sqlite_db_path.is_relative_to(ROOT)
        assert not settings.trackunit_auto_sync_enabled and not settings.trackunit_auto_sync_run_on_start
        ready=check(demo_only=True)
        assert ready['ready'] and ready['local_ready'] and not ready['ai_ready']
        assert not check()['ready']
        with TestClient(app) as client:
            assert client.get('/health').json()['data_source']=='mock'
            runtime=client.get('/assistant/runtime').json()
            assert runtime['backend_build']==manifest['backend_build'] and runtime['provider']=='gemini'
            assert runtime['cloud_credentials_configured'] is False
            assert client.get('/assistant-ui/').status_code==200
            for asset in ('cooling-warning.js','device-finder.js','ai-request-status.js',
                          'fault-context.js','vendor/echarts/echarts.min.js','vendor/echarts/LICENSE'):
                assert client.get('/assistant-ui/'+asset).status_code==200
            machines=client.get('/machines').json()
            assert len(machines)==5 and all(m['serial_number'].startswith('SIM-FLEET-') for m in machines)
            datasets=client.get('/assistant/datasets').json()
            assert len(datasets)==1 and datasets[0]['provenance']=='synthetic'
            parts=datasets[0]; identity={'machine_id':parts['machine']['machine_id'],'dataset_id':parts['dataset_id']}
            initial_status=client.get('/assistant/ai-status')
            assert initial_status.headers['cache-control']=='no-store'
            assert initial_status.json()['record_state']=='missing' and initial_status.json()['last_attempt'] is None
            assert not initial_status.json()['configured'] and not initial_status.json()['is_live_check']
            finder=client.get('/assistant/device-index').json()
            assert len(finder['devices'])==6 and not finder['ai_used'] and not finder['upstream_sync_performed']
            selected=[entry for entry in finder['devices'] if entry.get('dataset_id')==identity['dataset_id']]
            assert len(selected)==1 and selected[0]['machine_id']==identity['machine_id']
            assert selected[0]['source']=='imported_synthetic' and selected[0]['fault_summary']['unresolved_codes']==1
            overview=client.get('/assistant/device-overview',params=identity).json()
            context=client.get('/assistant/fault-context',params={**identity,'fault_code':'ENG-BOOST-102-3'})
            assert context.status_code==200 and 'DEMO-BOOST-SENSOR' in context.text
            assert client.get('/assistant/catalog').json()['demo']==1
            csv_result=client.get('/assistant/device-overview.csv',params={**identity,'metric':'operating_hours','window':'1'})
            assert csv_result.status_code==200 and csv_result.content.startswith(b'\xef\xbb\xbf')
            exported=list(csv.DictReader(io.StringIO(csv_result.content.decode('utf-8-sig'))))
            assert exported and all(r['machine_id']==identity['machine_id'] for r in exported)
            episodes=client.get('/assistant/work-state/episodes').json();assert len(episodes)==7
            work=client.get('/assistant/work-state/replay',params={'episode_id':episodes[0]['episode_id'],'count':12})
            assert work.status_code==200 and len(work.json()['samples'])==12
            assert len(client.get('/assistant/cooling/episodes').json())==24
            warning=client.get('/assistant/cooling/replay',params={'episode_id':'CW-1b1941610c93','cursor':135})
            assert warning.status_code==200 and warning.json()['prediction']['status']=='warning'
            assert 'event_index' not in warning.text
            prepared=client.post('/assistant/cooling/prepare',json={'episode_id':'CW-1b1941610c93','cursor':135}).json()
            assert prepared['sample_count']==136 and prepared['provenance']=='synthetic'
            bound=client.get('/assistant/cooling/context',params={'dataset_id':prepared['dataset_id']}).json()
            assert bound['machine_id']==prepared['machine']['machine_id'] and bound['cutoff']==prepared['replay_at']
            history_before=client.get('/assistant/history').json()
            failure=client.post('/assistant/investigate',json={**identity,'task':'parts','question':'检查模拟故障与目录'})
            assert failure.status_code==503 and 'GEMINI_API_KEY is not configured' in failure.json()['detail']
            assert client.get('/assistant/history').json()==history_before
            final_status=client.get('/assistant/ai-status').json()
            assert final_status['last_attempt']['outcome']=='failed'
            assert final_status['last_attempt']['failure']['kind']=='configuration_missing'
            assert final_status['last_attempt']['source']=='application' and final_status['last_attempt']['configuration_match']
            assert not final_status['is_live_check'] and final_status['current_availability']=='not_verified'
        assert not attempts
        verifier(ROOT)  # startup and seeding must not change packaged source/docs
        return {'verified_at':datetime.now(timezone.utc).isoformat(),'python':sys.version.split()[0],
            'backend_build':manifest['backend_build'],'manifest_files':len(manifest['files']),
            'application_import_root_verified':True,'application_lifespan':'startup_and_shutdown_passed',
            'provider_network_attempts':len(attempts),'gemini_success_claimed':False,
            'demo_ready_without_key':True,'cloud_ready_without_key':False,
            'synthetic_machines':len(machines),'initial_synthetic_datasets':len(datasets),
            'finder_entries':len(finder['devices']),'finder_exact_dataset_selection':True,
            'initial_ai_status':'missing','missing_key_status_persisted':True,
            'fault_catalog_candidate':'DEMO-BOOST-SENSOR','csv_rows':len(exported),
            'work_state_episodes':len(episodes),'cooling_episodes':24,'cooling_handoff_samples':prepared['sample_count'],
            'missing_key_status':failure.status_code,'failed_ai_creates_no_history':True,
            'source_files_unchanged_after_setup_and_smoke':True,
            'packages':{name:importlib.metadata.version(name) for name in ('fastapi','uvicorn','pydantic','httpx','python-dotenv','openpyxl','reportlab')},
            'scope':'Fresh extracted checkout. In-process ASGI startup; no listening service, external API, installed-extension or different-computer claim.'}
    finally:
        socket.socket.connect=original_connect;socket.getaddrinfo=original_resolve


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))
