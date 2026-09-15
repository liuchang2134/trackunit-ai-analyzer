import hashlib
import json
import zipfile
import pytest
from scripts import build_release_v8 as builder
from scripts.verify_release_v8 import verify_archive,verify_contents,safe_path,extract_release
from tests.historical_assets import require_release_history


@pytest.fixture(scope='module')
def actual_entries():
    require_release_history(builder.ROOT, 8)
    return builder.collect_entries(builder.ROOT)


def test_current_recipe_contains_models_not_private_state(actual_entries):
    config=actual_entries['.env.example'].decode()
    assert 'AI_PROVIDER=gemini' in config and 'GEMINI_API_KEY=\n' in config and 'OLLAMA_' not in config
    assert all('/local/' not in n and '/cache/' not in n and n!='.env' for n in actual_entries)
    assert 'app/assistant_ui/vendor/echarts/LICENSE' in actual_entries
    assert 'app/assistant_ui/vendor/echarts/NOTICE' in actual_entries
    assert sum(n.startswith('data/cooling_warning_v1/evaluator_only/') for n in actual_entries)==240
    assert sum(n.startswith('data/cooling_warning_v1/observations/') for n in actual_entries)==120
    assert b'](docs/RELEASE_V8_NOTES.md)' in actual_entries['START_HERE.md']


def test_all_mock_identity_joins_remain_valid_after_anonymization(actual_entries):
    machines=json.loads(actual_entries['app/mock_data/machines.json']); ids={m['id'] for m in machines}
    assert len(ids)==5 and all(m['serialNumber']==m['id'] for m in machines)
    assert all(m['customer']=='模拟客户' and m['latitude'] is None for m in machines)
    for name in ('telemetry_snapshots.json','fault_codes.json'):
        assert all(r['assetId'] in ids for r in json.loads(actual_entries['app/mock_data/'+name]))
    assert b'SIM-M-1001' not in actual_entries['app/mock_data/machines.json']


def test_configured_secrets_abort_without_echoing_them():
    secret=b'private-unit-key-472381'
    with pytest.raises(ValueError,match='credential') as caught:
        builder.validate_credentials({'app/example.py':b'prefix '+secret},[secret])
    assert secret.decode() not in str(caught.value)


def test_current_archive_and_file_integrity_are_verified(actual_entries,tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'collect_entries',lambda _:actual_entries)
    path,count=builder.build_release(tmp_path)
    manifest=verify_archive(path)
    assert count==len(manifest['files'])+1 and manifest['requires_local_llm'] is False
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):builder.build_release(tmp_path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    damaged={**actual_entries,'app/main.py':b'# changed'}
    with pytest.raises(ValueError,match='hash mismatch'):verify_contents(manifest,damaged.__getitem__)
    missing={**manifest,'files':{k:v for k,v in manifest['files'].items() if not k.endswith('/NOTICE')}}
    with pytest.raises(ValueError,match='resource missing'):verify_contents(missing,actual_entries.__getitem__)


@pytest.mark.parametrize('name',['../escape','C:/escape','a/../b','a\\b','a//b','.env','a/.env.secret','data/local/data.json'])
def test_unsafe_package_paths_are_not_allowed(name):
    assert not safe_path(name)


def test_case_collision_and_path_escape_rejected_before_writes(tmp_path):
    path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('jilian-assistant/A.txt','one');archive.writestr('jilian-assistant/a.txt','two')
    target=tmp_path/'extract'
    with pytest.raises(ValueError,match='Duplicate'):extract_release(path,target)
    assert not target.exists()
