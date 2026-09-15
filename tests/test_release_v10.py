import hashlib
import json
import posixpath
import re
from urllib.parse import unquote
import pytest
from scripts import build_release_v10 as builder,verify_release_v10 as verifier
from tests.historical_assets import require_release_history


@pytest.fixture(scope='module')
def entries():
 require_release_history(builder.ROOT, 10)
 return builder.collect_entries()


@pytest.fixture(scope='module')
def sealed_version_entries(entries):
 # Controlled serialization fixture, not a reconstruction of the sealed artifact.
 # The actual recipe must continue rejecting newer development under the v10 name.
 return {**entries,'app/assistant_version.py':f"ASSISTANT_BUILD = '{verifier.BUILD}'\n".encode()}


def test_current_release_includes_both_deliverables_without_runtime_data(entries):
 assert verifier.REQUIRED<=set(entries)
 assert not any('/local/' in n or '/cache/' in n or n=='.env' or n.endswith('.sqlite3') for n in entries)
 assert json.loads(entries['extension/manifest.json'])['version']=='0.4.0'
 assert b'GEMINI_API_KEY=\n' in entries['.env.example']
 for name,content in entries.items():
  if not name.endswith('.md'):continue
  for target in re.findall(r'\]\(([^)]+)\)',content.decode('utf-8')):
   if target.startswith(('https://','http://','#')):continue
   relative=unquote(target.split('#',1)[0])
   assert posixpath.normpath(posixpath.join(posixpath.dirname(name),relative)) in entries,(name,target)


@pytest.mark.parametrize('drift', ['application','extension'])
def test_sealed_recipe_rejects_version_drift(sealed_version_entries,tmp_path,monkeypatch,drift):
 changed=dict(sealed_version_entries)
 if drift=='application':
  changed['app/assistant_version.py']=b"ASSISTANT_BUILD = 'unreleased-development'\n"
 else:
  extension=json.loads(changed['extension/manifest.json']);extension['version']='9.9.9'
  changed['extension/manifest.json']=json.dumps(extension).encode()
 monkeypatch.setattr(builder,'collect_entries',lambda _:dict(changed))
 with pytest.raises(ValueError,match='Recipe does not match'):
  builder.build_release(tmp_path)
 assert not list(tmp_path.rglob('*.zip'))


def test_sealed_release_fixture_verifies_and_cannot_overwrite(sealed_version_entries,tmp_path,monkeypatch):
 entries=sealed_version_entries
 monkeypatch.setattr(builder,'collect_entries',lambda _:dict(entries))
 path,count=builder.build_release(tmp_path)
 manifest=verifier.verify_archive(path)
 assert count==len(manifest['files'])+1
 before=hashlib.sha256(path.read_bytes()).hexdigest()
 with pytest.raises(FileExistsError):builder.build_release(tmp_path)
 assert hashlib.sha256(path.read_bytes()).hexdigest()==before
 changed={**entries,'data/cooling_alarm_calibration_v2/evaluation.json':b'{}'}
 with pytest.raises(ValueError,match='Expanded evaluation mismatch'):
  verifier.verify_extras(manifest,changed.__getitem__)
 extension=json.loads(entries['extension/manifest.json']);extension['host_permissions']=['<all_urls>']
 changed={**entries,'extension/manifest.json':json.dumps(extension).encode()}
 with pytest.raises(ValueError,match='permission scope'):
  verifier.verify_extras(manifest,changed.__getitem__)
