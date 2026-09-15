"""Build a new current-workflow ZIP; never overwrite an earlier release."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import build_release_v8 as base
from scripts.verify_release_v9 import BUILD

RELEASE_FILENAME = 'jilian-assistant-gemini-prototype-20260914-v9.zip'
ADDITIONS = [
    'scripts/verify_release_v9.py', 'scripts/release_smoke_v9.py',
    'docs/RELEASE_V9_GUIDE.md', 'docs/RELEASE_V9_NOTES.md', 'docs/AI_REQUEST_STATUS.md',
    # Public examples linked by XGSS_INTEGRATION.md; never include data/local config.
    'docs/examples/xgss-config.example.json', 'docs/examples/xgss-page-routing-cases.json',
    'docs/evaluation/2026-09-14-ai-request-status.md',
    'docs/evaluation/2026-09-14-ai-request-status.json',
] + ['docs/evaluation/ux-20260914/request-status/' + name for name in (
    '01-fault-action-narrow.jpg', '02-handoff-status-narrow.jpg',
    '03-status-desktop.jpg', '04-handoff-390.jpg')]


def collect_entries(root=ROOT):
    root = Path(root).resolve()
    entries = base.collect_entries(root)
    for name in ('docs/RELEASE_V8_GUIDE.md', 'docs/RELEASE_V8_NOTES.md'):
        del entries[name]
    for name in ADDITIONS:
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Release source escapes workspace')
        entries[name] = path.read_bytes()
    guide = entries['docs/RELEASE_V9_GUIDE.md'].decode('utf-8')
    entries['START_HERE.md'] = re.sub(r'\]\(([A-Za-z0-9_]+\.md)\)', r'](docs/\1)', guide).encode()
    # The development-only finder audit includes real-device screenshots and is not distributed.
    references = entries['docs/OPEN_SOURCE_REFERENCES.md'].decode('utf-8')
    references = references.replace('实际验收见 [设备查找](evaluation/2026-09-14-device-finder.md)。',
                                    '本包功能与验证范围见 [本版说明](RELEASE_V9_NOTES.md)。')
    entries['docs/OPEN_SOURCE_REFERENCES.md'] = references.encode()
    base.validate_credentials(entries, base.credential_values(root))
    return entries


def build_release(root=ROOT, output_dir=None):
    root = Path(root).resolve()
    entries = collect_entries(root)
    build = re.search(r"ASSISTANT_BUILD\s*=\s*['\"]([^'\"]+)", entries['app/assistant_version.py'].decode()).group(1)
    if build != BUILD:
        raise ValueError('Recipe does not match current application build')
    manifest = {
        'schema_version': 2, 'release': 'v9', 'backend_build': build, 'root': base.PREFIX,
        'label': 'Gemini assistant software prototype; synthetic experiments, not field validated',
        'llm_provider': 'gemini', 'llm_model': 'gemini-flash-latest', 'requires_local_llm': False,
        'included_data': 'Synthetic mock fixtures and numerical-model experiments; no user runtime state',
        'updated_features': ['Device and data-version finder', 'Persistent last AI investigation status',
                             'Shorter fault-to-investigation handoff'],
        'not_verified': ['Real Gemini successful investigation and feedback', 'XGSS online manual and official parts API',
                         'Installed browser extension', 'Real-machine prediction', 'Another physical computer'],
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(entries.items())},
    }
    entries['MANIFEST.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    destination = Path(output_dir).resolve() if output_dir else root / 'dist'
    if not destination.is_relative_to(root):
        raise ValueError('Release output must stay within workspace')
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / RELEASE_FILENAME
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(base.PREFIX + '/' + name, date_time=(2026, 9, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return target, len(entries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    path, count = build_release(output_dir=parser.parse_args().output_dir)
    print(json.dumps({'path': str(path), 'files': count, 'bytes': path.stat().st_size,
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}, ensure_ascii=False))
