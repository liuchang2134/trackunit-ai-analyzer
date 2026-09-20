import json
import zipfile
import pytest
from scripts import build_release as builder
from scripts.verify_release import verify_archive


@pytest.fixture
def release_root(tmp_path):
    names=['requirements.txt','requirements-training.txt','requirements-xgss.txt','run_backend.ps1','start_local.ps1','setup_local.ps1',
           'docs/RELEASE_GUIDE.md','data/work_state_v1/model.json','data/work_state_v1/evaluation.json',
           'docs/examples/excavator-shift.json','docs/examples/excavator-parts-demo.json','docs/examples/demo-parts-catalog.json']
    names+=['docs/'+name for name in builder.DOCS]+['scripts/'+name for name in builder.SCRIPTS]
    for name in names:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture',encoding='utf-8')
    for name,content in {'app/main.py':'# fixture','app/mock_data/machines.json':json.dumps([{'serialNumber':'private-serial','customer':'private-name'}]),
                         'app/mock_data/telemetry_snapshots.json':json.dumps([{'Location':{'Latitude':12,'Longitude':34}}]),
                         '.env':'TRACKUNIT_CLIENT_SECRET=release-secret-test-123',
                         'data/local/private.json':'release-secret-test-123','data/cache/cache.json':'private'}.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
    return tmp_path


def test_package_excludes_private_data_and_replaces_fixture_identity(release_root):
    path,count=builder.build_release(release_root);verify_archive(path)
    with zipfile.ZipFile(path) as archive:
        assert not any('/local/' in name or '/cache/' in name or name.endswith('/.env') for name in archive.namelist())
        machine=json.loads(archive.read('jilian-local/app/mock_data/machines.json'))[0]
        assert machine['serialNumber']=='SIM-FLEET-001' and machine['latitude'] is None
        assert b'private-serial' not in archive.read('jilian-local/app/mock_data/machines.json')
        assert b'AI_PROVIDER=ollama_local' in archive.read('jilian-local/.env.example')
        assert b'OLLAMA_MODEL=qwen3.5:9b' in archive.read('jilian-local/.env.example')
        assert 'jilian-local/requirements-xgss.txt' in archive.namelist()
        assert 'jilian-local/docs/XGSS_INTEGRATION.md' in archive.namelist()
        for name in ['机联智检_答辩演示稿_v4.pptx','examples/browser-export-facts-demo.json','evaluation/2026-09-14-health-claim-guard.md']:
            assert 'jilian-local/docs/'+name in archive.namelist()
        assert 'jilian-local/scripts/sync_trackunit_history.py' in archive.namelist()
        assert 'jilian-local/docs/SYNTHETIC_DATA_GUIDE.md' in archive.namelist()


def test_release_aborts_if_configured_secret_appears_in_source(release_root):
    (release_root/'app/main.py').write_text('release-secret-test-123')
    with pytest.raises(ValueError,match='credential'):builder.build_release(release_root)
    assert not (release_root/'dist'/builder.RELEASE_FILENAME).exists()


def test_existing_release_cannot_be_overwritten(release_root):
    path,_=builder.build_release(release_root)
    original=path.read_bytes()
    with pytest.raises(FileExistsError):builder.build_release(release_root)
    assert path.read_bytes()==original


def test_reject_path_escape_before_extraction(tmp_path):
    path=tmp_path/'unsafe.zip'
    with zipfile.ZipFile(path,'w') as archive:archive.writestr('jilian-local/../../escape','bad')
    with pytest.raises(ValueError,match='Unsafe'):verify_archive(path)
