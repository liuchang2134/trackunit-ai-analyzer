import hashlib
import json
import posixpath
import re
from urllib.parse import unquote
import pytest

from scripts import build_release_v9 as builder
from scripts import verify_release_v8 as base
from scripts import verify_release_v9 as verifier
from tests.historical_assets import require_release_history


@pytest.fixture(scope='module')
def entries():
    require_release_history(builder.ROOT, 9)
    return builder.collect_entries()


def test_current_package_has_no_runtime_status_and_all_document_links_resolve(entries):
    assert verifier.REQUIRED <= set(entries)
    assert not any('/local/' in name or '/cache/' in name or name == '.env' for name in entries)
    assert b'GEMINI_API_KEY=\n' in entries['.env.example']
    example = json.loads(entries['docs/examples/xgss-config.example.json'])
    assert example['query_mode_confirmed'] is False
    assert not any(example['identity'].values()) and not example['public_key_path']
    assert 'docs/examples/xgss-page-routing-cases.json' in entries
    assert b'docs/RELEASE_V9_NOTES.md' in entries['START_HERE.md']
    assert 'docs/RELEASE_V8_NOTES.md' not in entries
    for name, content in entries.items():
        if not name.endswith('.md'):
            continue
        for target in re.findall(r'\]\(([^)]+)\)', content.decode('utf-8')):
            if target.startswith(('https://', 'http://', '#')):
                continue
            relative = unquote(target.split('#', 1)[0])
            assert posixpath.normpath(posixpath.join(posixpath.dirname(name), relative)) in entries, (name, target)


def test_v9_archive_checks_version_required_features_and_cannot_overwrite(entries, tmp_path, monkeypatch):
    # v9 is sealed at .11. New development must not be packaged under its name.
    monkeypatch.setattr(builder, 'collect_entries', lambda _: entries)
    with pytest.raises(ValueError, match='Recipe does not match'):
        builder.build_release(tmp_path)
    # This controlled fixture exercises v9 serialization and integrity checks;
    # it is not a claim that the current development tree is the v9 artifact.
    fixture_entries={**entries,'app/assistant_version.py':f"ASSISTANT_BUILD = '{verifier.BUILD}'\n".encode()}
    monkeypatch.setattr(builder, 'collect_entries', lambda _: fixture_entries)
    path, count = builder.build_release(tmp_path)
    manifest = verifier.verify_archive(path)
    assert manifest['backend_build'] == verifier.BUILD and count == len(manifest['files']) + 1
    with pytest.raises(ValueError, match='manifest version'):
        base.verify_archive(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        builder.build_release(tmp_path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    missing = {**manifest, 'files': {k: v for k, v in manifest['files'].items() if k != 'app/ai_request_status.py'}}
    with pytest.raises(ValueError, match='resource missing'):
        base.verify_contents(missing, entries.__getitem__, release='v9', required=verifier.REQUIRED)
    with pytest.raises(ValueError, match='application build'):
        verifier.current({**manifest, 'backend_build': 'old-build'})
