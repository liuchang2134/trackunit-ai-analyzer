"""Build an explicit-source demo release, never the developer workspace wholesale."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RELEASE_FILENAME='jilian-local-prototype-20260914-v6.zip'
CONFIG='''DATA_SOURCE=mock
TRACKUNIT_AUTO_SYNC_ENABLED=false
TRACKUNIT_AUTO_SYNC_RUN_ON_START=false
AI_PROVIDER=ollama_local
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:9b
'''
DOCS=['LOCAL_ASSISTANT.md','PARTS_DEMO.md','WORK_STATE_MODEL.md','INSPECTION_FEEDBACK.md',
      'EXTENSION.md','TRACKUNIT_NORMALIZATION.md','OPEN_SOURCE_REFERENCES.md',
      '机联智检_完整参赛Proposal.md','机联智检_完整参赛Proposal.docx','机联智检_完整参赛Proposal.pdf',
      'evaluation/2026-09-14-model-comparison.md','evaluation/2026-09-14-work-state-stress.md',
      'evaluation/work-state-stress-20260914T051436Z.json',
      'evaluation/local-assistant-20260914T045945Z.json','evaluation/local-assistant-20260914T050151Z.json',
      'evaluation/local-assistant-20260914T050243Z.json']
DOCS += ['机联智检_答辩演示稿_v4.pptx','机联智检_答辩演示稿_v4.pdf','机联智检_答辩讲稿.md',
         'examples/browser-export-demo.md','examples/browser-export-demo.json',
         'evaluation/2026-09-14-clean-venv-install.md','evaluation/2026-09-14-browser-report-export.md',
         'evaluation/2026-09-14-summary-regression.md','evaluation/2026-09-14-metric-availability.md',
         'evaluation/2026-09-14-parts-search-reasons.md','evaluation/2026-09-14-health-claim-guard.md']
DOCS += ['evaluation/local-assistant-'+stamp+'.json' for stamp in [
    '20260914T054940Z','20260914T055028Z','20260914T055124Z','20260914T055210Z',
    '20260914T055334Z','20260914T055416Z','20260914T055617Z','20260914T055806Z']]
DOCS += ['TRACKUNIT_HISTORY_SYNC.md','SYNTHETIC_DATA_GUIDE.md','examples/synthetic-profile-and-assumptions.json',
         'evaluation/2026-09-14-ui-history-sync-success.md']
DOCS += ['机联智检_模拟功能演示_v1.mp4','DEMO_VIDEO.md','RELEASE_V4_NOTES.md',
         'examples/browser-export-facts-demo.md','examples/browser-export-facts-demo.json',
         'evaluation/2026-09-14-data-facts-report.md','evaluation/2026-09-14-model-reload.md',
         'evaluation/2026-09-14-startup-scripts.md','evaluation/2026-09-14-local-network-boundary.md',
         'evaluation/2026-09-14-ui-parts-no-match.md','evaluation/2026-09-14-bilingual-review.md',
         'evaluation/BILINGUAL_REVIEW_CRITERIA.md','evaluation/2026-09-14-summary-context-experiment.md']
DOCS += ['evaluation/local-assistant-'+stamp+'.json' for stamp in [
    '20260914T062036Z','20260914T062139Z','20260914T062254Z','20260914T062553Z','20260914T062701Z']]
SCRIPTS=['sync_trackunit_history.py','check_local_runtime.py','prepare_parts_demo.py','generate_diagnostic_dataset.py',
         'export_demo_dataset.py','train_work_state.py','stress_work_state.py','evaluate_local_assistant.py']
DOCS += ['RELEASE_V5_NOTES.md','机联智检_检查反馈演示_v1.mp4',
         'examples/browser-export-feedback-demo.md','examples/browser-feedback-facts.png',
         'evaluation/2026-09-14-catalog-gap-followup.md','evaluation/2026-09-14-summary-time-equality.md',
         'evaluation/2026-09-14-feedback-workflow-video.md','evaluation/2026-09-14-feedback-summary.md',
         'evaluation/2026-09-14-feedback-summary-first-pass.json','evaluation/2026-09-14-feedback-summary-recheck.json',
         'evaluation/2026-09-14-feedback-facts.md','evaluation/2026-09-14-feedback-facts-live.json',
         'evaluation/2026-09-14-feedback-guard.md','evaluation/2026-09-14-feedback-guard-live.json',
         'evaluation/2026-09-14-history-report-view.md']
DOCS += ['evaluation/local-assistant-'+stamp+'.json' for stamp in [
    '20260914T063825Z','20260914T063858Z','20260914T064111Z']]
DOCS += ['RELEASE_V6_NOTES.md','XGSS_INTEGRATION.md',
         'evaluation/2026-09-14-qwen35-feedback.json','evaluation/2026-09-14-qwen35-feedback-review.md',
         'evaluation/2026-09-14-qwen35-bilingual-review.md','evaluation/2026-09-14-trend-followup.md',
         'evaluation/2026-09-14-summary-source-scope.md','evaluation/2026-09-14-qwen35-local-backend.json']
DOCS += ['evaluation/local-assistant-'+stamp+'.json' for stamp in [
    '20260914T071328Z','20260914T071733Z','20260914T072112Z','20260914T072841Z',
    '20260914T072933Z','20260914T073019Z','20260914T073058Z']]


def secret_values(root):
    path=root/'.env'
    if not path.exists():return []
    values=[]
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if '=' not in line or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1);value=value.strip().strip('\"\'')
        if re.search(r'SECRET|PASSWORD|API_KEY|CLIENT_ID|TOKEN',key,re.I) and len(value)>=8:values.append(value.encode())
    return values


def build_release(root=ROOT):
    root=Path(root).resolve();entries={}
    paths=[]
    for directory,suffixes in [('app',{'.py','.json','.js','.css','.html'}),('extension',{'.json','.js','.css','.html'})]:
        paths.extend(p for p in (root/directory).rglob('*') if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts)
    paths.extend(root/name for name in ['requirements.txt','requirements-training.txt','requirements-xgss.txt','run_backend.ps1','start_local.ps1','setup_local.ps1'])
    paths.extend(root/'scripts'/name for name in SCRIPTS)
    paths.extend(root/'docs'/name for name in DOCS)
    paths.extend(root/'docs/examples'/name for name in ['excavator-shift.json','excavator-parts-demo.json','demo-parts-catalog.json'])
    paths.extend(root/'data/work_state_v1'/name for name in ['model.json','evaluation.json'])
    paths.extend((root/'data/work_state_v1/observations/test').glob('*.csv.gz'))
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('Release source escapes workspace')
        entries[path.relative_to(root).as_posix()]=path.read_bytes()
    entries['START_HERE.md']=(root/'docs/RELEASE_GUIDE.md').read_bytes()
    entries['.env.example']=CONFIG.encode()
    # Public fixture copies use artificial identities and no geographic coordinates.
    key='app/mock_data/machines.json'
    if key in entries:
        fixtures=json.loads(entries[key])
        for index,item in enumerate(fixtures,1):
            item.update(serialNumber=f'SIM-FLEET-{index:03d}',customer='演示客户',location='模拟工地',latitude=None,longitude=None)
        entries[key]=json.dumps(fixtures,ensure_ascii=False,indent=2).encode()
    key='app/mock_data/telemetry_snapshots.json'
    if key in entries:
        fixtures=json.loads(entries[key])
        for item in fixtures:item['Location']={'Latitude':None,'Longitude':None}
        entries[key]=json.dumps(fixtures,ensure_ascii=False,indent=2).encode()
    secrets=secret_values(root)
    for content in entries.values():
        if any(secret in content for secret in secrets):raise ValueError('Configured credential detected; release aborted')
    manifest={'schema_version':1,'label':'local prototype, not field validated',
              'files':{name:hashlib.sha256(content).hexdigest() for name,content in sorted(entries.items())}}
    entries['MANIFEST.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
    target=root/'dist'/RELEASE_FILENAME;target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,content in sorted(entries.items()):archive.writestr('jilian-local/'+name,content)
    return target,len(entries)


if __name__=='__main__':
    target,count=build_release()
    print(json.dumps({'path':str(target),'files':count,'bytes':target.stat().st_size,
                      'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},ensure_ascii=False))
