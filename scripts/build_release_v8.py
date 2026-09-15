"""Current Gemini release recipe. Prior release recipes and archives remain unchanged."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RELEASE_FILENAME='jilian-assistant-gemini-prototype-20260914-v8.zip'
PREFIX='jilian-assistant'
CONFIG='''# Local synthetic demonstration; add your own Gemini credentials for AI analysis.
DATA_SOURCE=mock
TRACKUNIT_AUTO_SYNC_ENABLED=false
TRACKUNIT_AUTO_SYNC_RUN_ON_START=false
AI_PROVIDER=gemini
GEMINI_MODEL=gemini-flash-latest
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
GEMINI_API_KEY=
'''
DOCS=['RELEASE_V8_GUIDE.md','RELEASE_V8_NOTES.md','COOLING_WARNING.md','WORK_STATE_MODEL.md',
      'OPEN_SOURCE_REFERENCES.md','XGSS_INTEGRATION.md','PARTS_DEMO.md','INSPECTION_FEEDBACK.md',
      'EXTENSION.md','TRACKUNIT_NORMALIZATION.md','TRACKUNIT_HISTORY_SYNC.md','SYNTHETIC_DATA_GUIDE.md',
      'evaluation/2026-09-14-work-state-stress.md',
      'examples/excavator-shift.json','examples/excavator-parts-demo.json','examples/demo-parts-catalog.json',
      'examples/synthetic-profile-and-assumptions.json']
SCRIPTS=['check_local_runtime.py','prepare_parts_demo.py','generate_diagnostic_dataset.py',
         'export_demo_dataset.py','train_work_state.py','stress_work_state.py','generate_cooling_dataset.py',
         'train_cooling_warning.py','sync_trackunit_history.py','release_smoke.py','verify_release_v8.py']
ROOT_FILES=['requirements.txt','requirements-training.txt','requirements-xgss.txt','setup_local.ps1',
            'start_local.ps1','run_backend.ps1','.gitignore']
MODEL_FILES={
    'work_state_v1':['model.json','evaluation.json'],
    'cooling_warning_v1':['model.json','manifest.json','runtime.json','evaluation.json','README.md']}


def credential_values(root):
    path=root/'.env'
    if not path.is_file(): return []
    values=[]
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if '=' not in line or line.lstrip().startswith('#'): continue
        key,value=line.split('=',1);value=value.strip().strip('\"\'')
        if re.search(r'SECRET|PASSWORD|API_KEY|CLIENT_ID|TOKEN',key,re.I) and len(value)>=8:
            values.append(value.encode())
    return values


def sanitize_mock(entries):
    machines=json.loads(entries['app/mock_data/machines.json'])
    identities={str(m['id']):f'SIM-FLEET-{i:03d}' for i,m in enumerate(machines,1)}
    sanitized=[]
    for raw in machines:
        # Explicit fields prevent retained owner/account or terminal identifiers.
        identity=identities[str(raw['id'])]
        sanitized.append(dict(id=identity,serialNumber=identity,model=raw.get('model','SIM-EXC'),
            type=raw.get('type','excavator'),customer='模拟客户',location='模拟工地',
            latitude=None,longitude=None,lastSeenAt=raw['lastSeenAt']))
    entries['app/mock_data/machines.json']=json.dumps(sanitized,ensure_ascii=False,indent=2).encode()
    keep={
        'telemetry_snapshots.json':('CumulativeOperatingHours','CumulativeIdleHours','FuelRemaining','EngineStatus','recordedAt'),
        'fault_codes.json':('SPN','FMI','code','text','severity','occurredAt','status')}
    for name,fields in keep.items():
        rows=[]
        for raw in json.loads(entries['app/mock_data/'+name]):
            if str(raw['assetId']) not in identities: raise ValueError('Unmatched mock device identity')
            row={key:raw[key] for key in fields if key in raw}
            row['assetId']=identities[str(raw['assetId'])]
            if name=='telemetry_snapshots.json':row['Location']={'Latitude':None,'Longitude':None}
            rows.append(row)
        entries['app/mock_data/'+name]=json.dumps(rows,ensure_ascii=False,indent=2).encode()


def collect_entries(root):
    root=Path(root).resolve(); paths=[]
    for directory in ('app','extension'):
        for path in (root/directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and (path.suffix in {'.py','.json','.js','.css','.html'} or path.name in {'LICENSE','NOTICE'}):
                paths.append(path)
    paths += [root/name for name in ROOT_FILES]
    paths += [root/'docs'/name for name in DOCS]
    paths += [root/'scripts'/name for name in SCRIPTS]
    for dataset,names in MODEL_FILES.items():
        paths += [root/'data'/dataset/name for name in names]
        pattern=r'^EP-[0-9a-f]{12}\.csv\.gz$' if dataset=='work_state_v1' else r'^CW-[0-9a-f]{12}\.csv\.gz$'
        for split in ('train','validation','test'):
            paths += [p for p in (root/'data'/dataset/'observations'/split).glob('*.csv.gz') if re.fullmatch(pattern,p.name)]
    for split in ('train','validation','test'):
        for directory in (root/'data/cooling_warning_v1/evaluator_only'/split).glob('CW-*'):
            if directory.is_dir() and re.fullmatch(r'CW-[0-9a-f]{12}',directory.name):
                paths += [directory/'event.json',directory/'thermal_truth.csv.gz']
    entries={}; folded=set()
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root): raise ValueError('Release source escapes workspace')
        name=path.relative_to(root).as_posix()
        if name.casefold() in folded: raise ValueError('Duplicate or case-colliding release source')
        folded.add(name.casefold());entries[name]=path.read_bytes()
    guide=entries['docs/RELEASE_V8_GUIDE.md'].decode('utf-8')
    entries['START_HERE.md']=re.sub(r'\]\(([A-Za-z0-9_]+\.md)\)',r'](docs/\1)',guide).encode()
    entries['.env.example']=CONFIG.encode()
    sanitize_mock(entries)
    # Cache versions describe the bytes actually included in this package.
    html=entries['app/assistant_ui/index.html'].decode('utf-8')
    html=re.sub(r'(src|href)="([^"?]+\.(?:js|css))(?:\?v=[^"]*)?"',
        lambda m:m[1]+'="'+m[2]+'?v='+hashlib.sha256(entries['app/assistant_ui/'+m[2]]).hexdigest()[:12]+'"',html)
    entries['app/assistant_ui/index.html']=html.encode()
    validate_credentials(entries,credential_values(root))
    for name,content in entries.items():
        if name.endswith('.json'):
            json.loads(content)  # reject corrupt or accidentally non-JSON source files
    return entries


def validate_credentials(entries,secrets):
    if any(secret in content for content in entries.values() for secret in secrets):
        raise ValueError('Configured credential detected; release aborted')


def build_release(root=ROOT,output_dir=None):
    root=Path(root).resolve();entries=collect_entries(root)
    build=re.search(r"ASSISTANT_BUILD\s*=\s*['\"]([^'\"]+)",entries['app/assistant_version.py'].decode()).group(1)
    manifest={'schema_version':2,'release':'v8','backend_build':build,'root':PREFIX,
        'label':'Gemini assistant software prototype; synthetic experiments, not field validated',
        'llm_provider':'gemini','llm_model':'gemini-flash-latest','requires_local_llm':False,
        'included_data':'Synthetic mock fixtures, work-state sensor observations and complete cooling_warning_v1 experiment',
        'not_verified':['Gemini full successful investigation','XGSS online manual and official parts API',
                        'installed browser extension','real-machine prediction','another physical computer'],
        'files':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(entries.items())}}
    entries['MANIFEST.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
    destination=Path(output_dir).resolve() if output_dir else root/'dist'
    if not destination.is_relative_to(root):raise ValueError('Release output must stay within workspace')
    target=destination/RELEASE_FILENAME;target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(entries.items()):
            info=zipfile.ZipInfo(PREFIX+'/'+name,date_time=(2026,9,14,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    return target,len(entries)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,help='Optional new candidate directory within the workspace')
    path,count=build_release(output_dir=parser.parse_args().output_dir)
    print(json.dumps({'path':str(path),'files':count,'bytes':path.stat().st_size,
                      'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},ensure_ascii=False))
