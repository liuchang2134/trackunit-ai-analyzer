"""Verify the current v9 package without executing it or contacting services."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import verify_release_v8 as base

BUILD = '20260914.11-ai-request-status'
REQUIRED = (base.REQUIRED - {'docs/RELEASE_V8_GUIDE.md', 'docs/RELEASE_V8_NOTES.md'}) | {
    'docs/RELEASE_V9_GUIDE.md', 'docs/RELEASE_V9_NOTES.md', 'docs/AI_REQUEST_STATUS.md',
    'scripts/verify_release_v9.py', 'scripts/release_smoke_v9.py',
    'app/device_index.py', 'app/ai_request_status.py',
    'app/assistant_ui/device-finder.js', 'app/assistant_ui/ai-request-status.js',
    'app/assistant_ui/fault-context.js',
}


def current(manifest):
    if manifest['backend_build'] != BUILD:
        raise ValueError('Unexpected v9 application build')
    return manifest


def verify_archive(path):
    return current(base.verify_archive(path, release='v9', required=REQUIRED))


def verify_folder(folder):
    return current(base.verify_folder(folder, release='v9', required=REQUIRED))


def extract_release(archive, destination):
    verify_archive(archive)
    return base.extract_release(archive, destination, release='v9', required=REQUIRED)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive', type=Path)
    group.add_argument('--folder', type=Path)
    args = parser.parse_args()
    result = verify_archive(args.archive) if args.archive else verify_folder(args.folder)
    print(json.dumps({'verified': True, 'release': result['release'],
                      'backend_build': result['backend_build'], 'files': len(result['files'])}))
