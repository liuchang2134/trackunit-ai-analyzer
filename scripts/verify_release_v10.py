"""Verify .16 web, extension 0.4.0 and frozen expanded evaluation before execution."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import verify_release_v8 as base

BUILD='20260914.16-cooling-evidence'
EXTENSION_VERSION='0.4.0'
EVALUATION_SHA256='1a3cde3c2437005a3828751b7eb3a23c12367b03da6a56151b2eb8689efbb607'
REQUIRED=(base.REQUIRED-{'docs/RELEASE_V8_GUIDE.md','docs/RELEASE_V8_NOTES.md'})|{
 'scripts/verify_release_v10.py','scripts/release_smoke_v10.py','docs/RELEASE_V10_GUIDE.md','docs/RELEASE_V10_NOTES.md',
 'app/maintenance_cases.py','app/investigation_drafts.py','app/xgss_handoff.py',
 'app/assistant_ui/maintenance-cases.js','app/assistant_ui/local-drafts.js','app/assistant_ui/xgss-viewer.js',
 'app/assistant_ui/platform-context.js','extension/README.md','extension/context.js','extension/panel.js',
 'docs/examples/xgss-config.example.json','data/cooling_alarm_calibration_v2/evaluation.json',
 'scripts/verify_cooling_calibration.py','data/cooling_alarm_calibration_v2/selection.json',
 'data/cooling_alarm_calibration_v2/protocol.json','data/cooling_alarm_calibration_v2/test-manifest.json',
 'data/cooling_alarm_calibration_v2/validation-manifest.json','data/cooling_alarm_calibration_v2/candidate-model.json',
}


def verify_extras(manifest,read):
 if manifest.get('backend_build')!=BUILD or manifest.get('extension_version')!=EXTENSION_VERSION:
  raise ValueError('Unexpected v10 web/extension build')
 extension=json.loads(read('extension/manifest.json'))
 if extension['version']!=EXTENSION_VERSION or extension.get('manifest_version')!=3:
  raise ValueError('Extension package version mismatch')
 if set(extension.get('permissions',[]))!={'sidePanel','activeTab'} or extension.get('host_permissions'):
  raise ValueError('Unexpected extension permission scope')
 directory='data/cooling_alarm_calibration_v2/'
 raw=read(directory+'evaluation.json')
 if hashlib.sha256(raw).hexdigest()!=EVALUATION_SHA256:raise ValueError('Expanded evaluation mismatch')
 evaluation=json.loads(raw)
 if evaluation['deployable_under_protocol'] is not False:raise ValueError('Failed candidate must not be promoted')
 for split,count in [('validation',48),('test',96)]:
  entries=json.loads(read(directory+split+'-manifest.json'))['episodes']
  if len(entries)!=count:raise ValueError('Expanded experiment incomplete')
  for entry in entries:
   for name,digest in [(f'observations/{split}/{entry["episode_id"]}.csv.gz',entry['sensor_sha256']),
                       (f'evaluator_only/{split}/{entry["episode_id"]}/event.json',entry['event_sha256']),
                       (f'evaluator_only/{split}/{entry["episode_id"]}/thermal_truth.csv.gz',entry['truth_sha256'])]:
    if manifest['files'].get(directory+name)!=digest:raise ValueError('Expanded evidence missing or mismatched')
 config=json.loads(read('docs/examples/xgss-config.example.json'))
 if config['query_mode_confirmed'] is not False or any(config['identity'].values()):
  raise ValueError('XGSS example must remain unconfigured')
 return manifest


def verify_archive(path):
 manifest=base.verify_archive(path,release='v10',required=REQUIRED)
 with zipfile.ZipFile(path) as archive:
  return verify_extras(manifest,lambda name:archive.read(base.PREFIX+'/'+name))


def verify_folder(folder):
 folder=Path(folder).resolve()
 return verify_extras(base.verify_folder(folder,release='v10',required=REQUIRED),lambda name:(folder/name).read_bytes())


def extract_release(archive,destination):
 verify_archive(archive)
 return base.extract_release(archive,destination,release='v10',required=REQUIRED)


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
 group.add_argument('--archive',type=Path);group.add_argument('--folder',type=Path);args=parser.parse_args()
 result=verify_archive(args.archive) if args.archive else verify_folder(args.folder)
 print(json.dumps({'verified':True,'release':result['release'],'backend_build':result['backend_build'],
                   'extension_version':result['extension_version'],'files':len(result['files'])}))
