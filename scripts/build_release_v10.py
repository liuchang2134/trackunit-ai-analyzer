"""Package the .16 web app, extension 0.4.0 and frozen synthetic evidence without runtime state."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import build_release_v9 as previous
from scripts import build_release_v8 as base
from scripts.verify_release_v10 import BUILD,EXTENSION_VERSION

RELEASE_FILENAME='jilian-assistant-web-chrome-20260914-v10.zip'
ADDITIONS=[
 'scripts/verify_release_v10.py','scripts/release_smoke_v10.py',
 'scripts/calibrate_cooling_alarm.py','scripts/verify_cooling_calibration.py',
 'docs/RELEASE_V10_GUIDE.md','docs/RELEASE_V10_NOTES.md',
 'docs/LOCAL_INVESTIGATION_DRAFTS.md','docs/MAINTENANCE_WORKLIST.md',
 'docs/examples/xgss-config.example.json','docs/examples/xgss-page-routing-cases.json',
 'docs/superpowers/plans/2026-09-14-cooling-alarm-calibration.md',
 'docs/evaluation/2026-09-14-cooling-calibration-independent.json',
 'docs/evaluation/2026-09-14-cooling-evidence.md','docs/evaluation/2026-09-14-cooling-evidence-browser.json',
 'docs/evaluation/ux-20260914/cooling-evidence/evaluation-390.png',
 'docs/evaluation/ux-20260914/cooling-evidence/evaluation-1280.png','extension/README.md',
]


def collect_entries(root=ROOT):
 root=Path(root).resolve();entries=previous.collect_entries(root)
 for name in ('docs/RELEASE_V9_GUIDE.md','docs/RELEASE_V9_NOTES.md'):
  del entries[name]
 additions=list(ADDITIONS)
 directory=root/'data/cooling_alarm_calibration_v2'
 allowed=r'(?:protocol|selection|candidate-model|evaluation|validation-manifest|test-manifest)\.json|observations/(?:validation|test)/CA-[0-9a-f]{12}\.csv\.gz|evaluator_only/(?:validation|test)/CA-[0-9a-f]{12}/(?:event\.json|thermal_truth\.csv\.gz)|audit/(?:original|candidate|temperature_95c)\.csv\.gz'
 additions += [path.relative_to(root).as_posix() for path in directory.rglob('*')
               if path.is_file() and re.fullmatch(allowed,path.relative_to(directory).as_posix())]
 for name in additions:
  path=root/name
  if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('Release source escapes workspace')
  entries[name]=path.read_bytes()
 # Keep the package self-contained; development screenshot collections are not distributed.
 for name in ('docs/OPEN_SOURCE_REFERENCES.md','docs/LOCAL_INVESTIGATION_DRAFTS.md','docs/MAINTENANCE_WORKLIST.md'):
  text=entries[name].decode('utf-8')
  text=re.sub(r'\]\((?:evaluation/2026-09-14-(?:local-drafts|maintenance-worklist)\.md|RELEASE_V9_NOTES\.md)\)','](RELEASE_V10_NOTES.md)',text)
  entries[name]=text.encode()
 entries['docs/EXTENSION.md']=b'# Chrome extension\n\n'+ '[安装与使用说明](../extension/README.md)。本包包含 0.4.0 源码；实际 Chrome 安装验收仍待完成。\n'.encode()
 guide=entries['docs/RELEASE_V10_GUIDE.md'].decode('utf-8')
 entries['START_HERE.md']=re.sub(r'\]\(([^:)]+)\)',lambda m:']('+('extension/README.md' if m[1]=='../extension/README.md' else 'docs/'+m[1])+')',guide).encode()
 entries['README.md']=entries['START_HERE.md']
 base.validate_credentials(entries,base.credential_values(root))
 return entries


def build_release(root=ROOT,output_dir=None):
 root=Path(root).resolve();entries=collect_entries(root)
 build=re.search(r"ASSISTANT_BUILD\s*=\s*['\"]([^'\"]+)",entries['app/assistant_version.py'].decode()).group(1)
 if build!=BUILD or json.loads(entries['extension/manifest.json'])['version']!=EXTENSION_VERSION:
  raise ValueError('Recipe does not match current web/extension build')
 manifest={'schema_version':2,'release':'v10','backend_build':build,'extension_version':EXTENSION_VERSION,'root':base.PREFIX,
  'label':'Web and Chrome software prototype; external integrations and field prediction not fully verified',
  'llm_provider':'gemini','llm_model':'gemini-flash-latest','requires_local_llm':False,
  'included_data':'Synthetic mock fixtures, work-state model and frozen v1/v2 cooling experiments; no user runtime state',
  'updated_features':['Local investigation drafts','Maintenance task history and export','Configured XGSS page handoff',
                      'Chrome device-context acknowledgment','Expanded cooling evaluation'],
  'not_verified':['Real Gemini successful investigation and feedback','XGSS production integration',
                  'Installed Chrome extension on Trackunit','Real-machine prediction','Another physical computer'],
  'files':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(entries.items())}}
 entries['MANIFEST.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
 destination=Path(output_dir).resolve() if output_dir else root/'dist'
 if not destination.is_relative_to(root):raise ValueError('Release output must stay within workspace')
 destination.mkdir(parents=True,exist_ok=True);target=destination/RELEASE_FILENAME
 with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
  for name,data in sorted(entries.items()):
   info=zipfile.ZipInfo(base.PREFIX+'/'+name,date_time=(2026,9,14,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
   archive.writestr(info,data)
 return target,len(entries)


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path)
 path,count=build_release(output_dir=parser.parse_args().output_dir)
 print(json.dumps({'path':str(path),'files':count,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
