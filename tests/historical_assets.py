"""Availability checks for optional, locally archived acceptance evidence."""
import json
from pathlib import Path

import pytest


def require_historical_files(root, names, label):
    root = Path(root)
    missing = [name for name in names if not (root / name).exists()]
    if missing:
        pytest.skip(
            f'{label}: local historical acceptance assets are not distributed with Git; '
            f'missing {missing[0]} ({len(missing)} missing files)'
        )


def require_release_history(root, version):
    """Skip only absent archive inputs, never malformed inputs or app failures."""
    from scripts import build_release_v9, build_release_v10

    names = [
        'docs/RELEASE_V8_GUIDE.md', 'docs/RELEASE_V8_NOTES.md',
        'docs/EXTENSION.md', 'docs/SYNTHETIC_DATA_GUIDE.md',
        'docs/evaluation/2026-09-14-work-state-stress.md',
        'docs/examples/excavator-parts-demo.json',
        'docs/examples/synthetic-profile-and-assumptions.json',
        'data/cooling_warning_v1/README.md',
    ]
    for recipe in ([build_release_v9] if version == 9 else
                   [build_release_v9, build_release_v10] if version == 10 else []):
        names.extend(name for name in recipe.ADDITIONS
                     if name.startswith(('docs/RELEASE_', 'docs/evaluation/', 'docs/superpowers/')))
    require_historical_files(root, names, f'v{version} archive acceptance')

    # The manifest is a distributed runtime input: missing/corrupt core files
    # still fail normally. Only undistributed training and truth files may skip.
    root = Path(root)
    manifest = json.loads((root / 'data/cooling_warning_v1/manifest.json').read_text(encoding='utf-8'))
    names = []
    for item in manifest['episodes']:
        base = f"data/cooling_warning_v1/evaluator_only/{item['split']}/{item['episode_id']}"
        names.extend((base + '/event.json', base + '/thermal_truth.csv.gz'))
        if item['split'] != 'test':
            names.append(f"data/cooling_warning_v1/observations/{item['split']}/{item['episode_id']}.csv.gz")
    work_state = json.loads((root / 'data/work_state_v1/evaluation.json').read_text(encoding='utf-8'))
    for source in work_state['input_hashes']:
        parts = source.replace('\\', '/').split('/')
        if parts[-3] in ('train', 'validation'):
            names.append(f'data/work_state_v1/observations/{parts[-3]}/{parts[-2]}.csv.gz')
    if version == 10:
        names.extend('data/cooling_alarm_calibration_v2/' + name for name in (
            'protocol.json', 'selection.json', 'candidate-model.json',
            'validation-manifest.json', 'test-manifest.json',
            'audit/original.csv.gz', 'audit/candidate.csv.gz', 'audit/temperature_95c.csv.gz'))
    require_historical_files(root, names, f'v{version} archive acceptance')
    if version == 10:
        names = []
        for split in ('validation', 'test'):
            base = 'data/cooling_alarm_calibration_v2'
            manifest = json.loads((root / base / f'{split}-manifest.json').read_text(encoding='utf-8'))
            for item in manifest['episodes']:
                eid = item['episode_id']
                names.extend((f'{base}/observations/{split}/{eid}.csv.gz',
                              f'{base}/evaluator_only/{split}/{eid}/event.json',
                              f'{base}/evaluator_only/{split}/{eid}/thermal_truth.csv.gz'))
        require_historical_files(root, names, 'v10 archive acceptance')
