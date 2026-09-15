"""Verify a v8 package before extraction; does not execute code or contact services."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

PREFIX='jilian-assistant'
REQUIRED={'START_HERE.md','.env.example','requirements.txt','setup_local.ps1','start_local.ps1','run_backend.ps1',
          'scripts/release_smoke.py','scripts/check_local_runtime.py','app/assistant_version.py','app/main.py',
          'app/assistant_ui/index.html','app/assistant_ui/cooling-warning.js',
          'app/assistant_ui/vendor/echarts/echarts.min.js','app/assistant_ui/vendor/echarts/LICENSE',
          'app/assistant_ui/vendor/echarts/NOTICE','app/assistant_ui/vendor/echarts/SOURCE.json',
          'data/cooling_warning_v1/model.json','data/cooling_warning_v1/manifest.json',
          'data/cooling_warning_v1/runtime.json','data/cooling_warning_v1/evaluation.json',
          'data/work_state_v1/model.json','data/work_state_v1/evaluation.json','extension/manifest.json',
          'docs/RELEASE_V8_GUIDE.md','docs/RELEASE_V8_NOTES.md','docs/COOLING_WARNING.md'}
PRIVATE={'.env','.git','.venv','.tmp','__pycache__','node_modules','local','cache'}


def safe_path(name):
    path=PurePosixPath(name)
    return (bool(path.parts) and not path.is_absolute() and str(path)==name
            and not any(p in {'.','..'} or ':' in p or p.casefold() in PRIVATE
                        or p.casefold().startswith('.env.') and p.casefold()!='.env.example' for p in path.parts)
            and '\\' not in name and '\x00' not in name)


def verify_contents(manifest,read,*,release='v8',required=REQUIRED):
    if manifest.get('schema_version')!=2 or manifest.get('release')!=release or manifest.get('root')!=PREFIX:
        raise ValueError('Unexpected release manifest version')
    files=manifest['files']
    if not required<=set(files):raise ValueError('Required release resource missing')
    if len({name.casefold() for name in files})!=len(files):raise ValueError('Case-colliding release paths')
    for name,digest in files.items():
        if not safe_path(name) or not re.fullmatch(r'[0-9a-f]{64}',digest):raise ValueError('Unsafe manifest entry')
        if hashlib.sha256(read(name)).hexdigest()!=digest:raise ValueError('Release file hash mismatch: '+name)
    config=dict(line.split('=',1) for line in read('.env.example').decode().splitlines() if '=' in line and not line.startswith('#'))
    expected={'AI_PROVIDER':'gemini','GEMINI_API_KEY':'','GEMINI_MODEL':'gemini-flash-latest','DATA_SOURCE':'mock',
              'GEMINI_BASE_URL':'https://generativelanguage.googleapis.com/v1beta',
              'TRACKUNIT_AUTO_SYNC_ENABLED':'false','TRACKUNIT_AUTO_SYNC_RUN_ON_START':'false'}
    if any(config.get(k)!=v for k,v in expected.items()) or any(k.startswith('OLLAMA_') for k in config):
        raise ValueError('Release must default to uncredentialed Gemini and local synthetic data')
    if manifest.get('llm_provider')!='gemini' or manifest.get('requires_local_llm') is not False:
        raise ValueError('Release architecture mismatch')
    version=read('app/assistant_version.py').decode()
    if not re.search(r"ASSISTANT_BUILD\s*=\s*['\"]"+re.escape(manifest['backend_build'])+r"['\"]",version):
        raise ValueError('Backend build mismatch')
    cooling=json.loads(read('data/cooling_warning_v1/manifest.json'))
    runtime=json.loads(read('data/cooling_warning_v1/runtime.json'))
    for kind in ('model','manifest'):
        if hashlib.sha256(read(f'data/cooling_warning_v1/{kind}.json')).hexdigest()!=runtime[kind+'_sha256']:
            raise ValueError('Cooling artifact mismatch')
    counts={split:sum(e['split']==split for e in cooling['episodes']) for split in ('train','validation','test')}
    if counts!={'train':72,'validation':24,'test':24}:raise ValueError('Cooling experiment incomplete')
    for entry in cooling['episodes']:
        name=f'data/cooling_warning_v1/observations/{entry["split"]}/{entry["episode_id"]}.csv.gz'
        if files.get(name)!=entry['sensor_sha256']:raise ValueError('Cooling observation missing or mismatched')
        private=f'data/cooling_warning_v1/evaluator_only/{entry["split"]}/{entry["episode_id"]}/'
        if not {private+'event.json',private+'thermal_truth.csv.gz'}<=set(files):raise ValueError('Cooling evaluator data missing')
    work=json.loads(read('data/work_state_v1/evaluation.json'))
    if hashlib.sha256(read('data/work_state_v1/model.json')).hexdigest()!=work['model_sha256']:
        raise ValueError('Work-state model mismatch')
    if sum(n.startswith('data/work_state_v1/observations/test/') for n in files)!=7:
        raise ValueError('Work-state replay inputs missing')
    machines=json.loads(read('app/mock_data/machines.json'))
    identities={m['id'] for m in machines}
    if len(identities)!=len(machines) or not all(re.fullmatch(r'SIM-FLEET-\d{3}',m['id']) and m['serialNumber']==m['id']
        and m.get('latitude') is None and m.get('longitude') is None and m['customer']=='模拟客户' and m['location']=='模拟工地' for m in machines):
        raise ValueError('Mock identities must be explicitly synthetic')
    for name in ('telemetry_snapshots.json','fault_codes.json'):
        if any(r['assetId'] not in identities for r in json.loads(read('app/mock_data/'+name))):
            raise ValueError('Broken mock identity join')
    html=read('app/assistant_ui/index.html').decode()
    for filename,digest in re.findall(r'(?:src|href)="([^"?]+\.(?:js|css))\?v=([0-9a-f]+)"',html):
        name='app/assistant_ui/'+filename
        if name not in files or not files[name].startswith(digest):raise ValueError('UI asset version mismatch')
    return manifest


def verify_archive(path,*,release='v8',required=REQUIRED):
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist(); names=[i.filename for i in infos]
        if len(names)!=len(set(n.casefold() for n in names)):raise ValueError('Duplicate archive names')
        if len(infos)>5000 or sum(i.file_size for i in infos)>200_000_000:raise ValueError('Unexpected archive size')
        for info in infos:
            if (not safe_path(info.filename) or PurePosixPath(info.filename).parts[0]!=PREFIX
                    or stat.S_ISLNK(info.external_attr>>16) or info.file_size>50_000_000):
                raise ValueError('Unsafe archive path or entry')
        manifest=json.loads(archive.read(PREFIX+'/MANIFEST.json'))
        if set(names)!={PREFIX+'/'+name for name in manifest['files']}|{PREFIX+'/MANIFEST.json'}:
            raise ValueError('Manifest file set mismatch')
        return verify_contents(manifest,lambda name:archive.read(PREFIX+'/'+name),release=release,required=required)


def verify_folder(folder,*,release='v8',required=REQUIRED):
    folder=Path(folder).resolve();manifest=json.loads((folder/'MANIFEST.json').read_text(encoding='utf-8'))
    def read(name):
        if not safe_path(name):raise ValueError('Unsafe extracted path')
        path=folder/name
        if path.is_symlink() or not path.resolve().is_relative_to(folder):raise ValueError('Extracted source escapes folder')
        return path.read_bytes()
    return verify_contents(manifest,read,release=release,required=required)


def extract_release(archive,destination,*,release='v8',required=REQUIRED):
    verify_archive(archive,release=release,required=required)
    destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as package:package.extractall(destination)
    return destination/PREFIX


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive',type=Path);group.add_argument('--folder',type=Path)
    args=parser.parse_args()
    result=verify_archive(args.archive) if args.archive else verify_folder(args.folder)
    print(json.dumps({'verified':True,'release':result['release'],'backend_build':result['backend_build'],
                      'files':len(result['files'])},ensure_ascii=False))
