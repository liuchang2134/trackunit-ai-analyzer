import csv
import gzip
import hashlib
import json
from pathlib import Path
import pytest

from app.cooling_warning import predict_prefix
from scripts.calibrate_cooling_alarm import measure, prepare, deployment_checks
from scripts.generate_cooling_dataset import episode, write_csv, OBS_FIELDS
from tests.test_cooling_warning import constant_model, rows
from tests.historical_assets import require_historical_files

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('confirmation', [2, 3, 4])
def test_confirmation_requires_uninterrupted_valid_history(confirmation):
    model = constant_model()
    model['alarm_consecutive_minutes'] = confirmation
    data = rows(40)
    result = predict_prefix(model, data)
    assert all(r['status'] == 'watch' for r in result[10:9+confirmation])
    assert result[9+confirmation]['status'] == 'warning'
    data[15]['coolant_c'] = None
    result = predict_prefix(model, data)
    assert result[15]['status'] == 'unknown'
    assert result[26]['status'] == 'watch'
    assert result[25+confirmation]['status'] == 'warning'
    # Future changes cannot affect any prefix decision.
    expected = result[:29]
    data[30]['coolant_c'] = 110
    assert predict_prefix(model, data)[:29] == expected


@pytest.mark.parametrize('confirmation', [True, False, None, 1, 5, 2.0, '3'])
def test_bad_policy_contract_rejected(confirmation):
    model = constant_model()
    model['alarm_consecutive_minutes'] = confirmation
    with pytest.raises(ValueError):
        predict_prefix(model, rows())


def test_false_alarm_segments_minutes_and_censoring_are_distinct():
    item = dict(episode_id='example', group='test', scenario='manual', event=20,
                scores=[.9, .9, .9, 0, .9, .9, .9, .9],
                eligible=[True, True, False, True, True, True, True, True])
    report = measure([item], .8, 2)['overall']
    # Confirmed false alarm at index 1; index 2 ineligible; index 5 begins
    # the positive 15-minute horizon. Only indices 5,6,7 are true positives.
    assert report['false_alert_episodes'] == 1
    assert report['false_alert_minutes'] == 1
    assert report['window_counts'] == dict(tp=3, fp=1, tn=3, fn=0)
    assert report['eligible_hours'] == pytest.approx(7/60)
    assert report['median_lead_minutes'] == 15


def test_never_alarm_does_not_pass_release_gate():
    base = dict(event_recall=1, detected_events=4, median_lead_minutes=12,
                false_alert_episodes_per_eligible_hour=.3, false_alert_minutes=30)
    candidate = dict(base, event_recall=0, detected_events=0, median_lead_minutes=None,
                     false_alert_episodes_per_eligible_hour=0, false_alert_minutes=0)
    checks = deployment_checks({'groups':{'nominal':candidate}}, {'groups':{'nominal':base}},
                               {'groups':{'nominal':base}})['nominal']
    assert not checks['recall_at_least_90_percent']
    assert not checks['no_additional_missed_events']
    assert not checks['median_lead_at_least_10_minutes']


@pytest.mark.parametrize('split', ['train', 'validation', 'test'])
def test_nominal_generator_preserves_frozen_v1_bytes(split, tmp_path):
    private_files = sorted((ROOT/'data/cooling_warning_v1/evaluator_only'/split).glob('*/event.json'))
    if not private_files:
        pytest.skip(f'Frozen v1 {split} truth is local historical acceptance data not distributed with Git')
    private = private_files[0]
    original = ROOT/'data/cooling_warning_v1/observations'/split/(private.parent.name+'.csv.gz')
    require_historical_files(ROOT, [original.relative_to(ROOT).as_posix()], 'Frozen v1 generator comparison')
    meta = json.loads(private.read_text(encoding='utf-8'))
    observed, truth, regenerated_meta = episode(meta['seed'], meta['scenario'])
    output = tmp_path/'nominal.csv.gz'
    write_csv(output, OBS_FIELDS, observed)
    assert output.read_bytes() == original.read_bytes()
    assert regenerated_meta == meta


def test_shifted_profile_is_reproducible_and_differs_from_nominal():
    nominal, _, _ = episode(2026102001, 'gradual_loss')
    shifted, truth, meta = episode(2026102001, 'gradual_loss', 'shifted')
    repeat, _, repeated_meta = episode(2026102001, 'gradual_loss', 'shifted')
    assert shifted == repeat and meta == repeated_meta
    assert shifted != nominal
    assert len(shifted) == 480 and len(truth) == 5760
    assert meta['profile'] == 'shifted'
    assert meta['fuel_conservation_error_l'] < 1e-8


def test_new_statistics_match_existing_v1_validation():
    from scripts.calibrate_cooling_alarm import original_validation
    manifest = json.loads((ROOT/'data/cooling_warning_v1/manifest.json').read_text(encoding='utf-8'))
    validation = [item['episode_id'] for item in manifest['episodes'] if item['split'] == 'validation']
    assert validation, 'Distributed v1 manifest must describe validation episodes'
    required = [name for eid in validation for name in (
        f'data/cooling_warning_v1/observations/validation/{eid}.csv.gz',
        f'data/cooling_warning_v1/evaluator_only/validation/{eid}/event.json')]
    require_historical_files(ROOT, required, 'Frozen v1 validation statistics')
    model = json.loads((ROOT/'data/cooling_warning_v1/model.json').read_text())
    original = json.loads((ROOT/'data/cooling_warning_v1/evaluation.json').read_text())['validation']['random_forest']
    actual = measure(original_validation(model), model['alarm_threshold'], 2)['overall']
    for key in ('events', 'detected_events', 'false_alert_episodes', 'window_counts', 'median_lead_minutes'):
        assert actual[key] == original[key]
    assert actual['eligible_hours'] == pytest.approx(original['eligible_hours'])
