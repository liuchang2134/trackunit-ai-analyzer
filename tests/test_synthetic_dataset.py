import gzip
import hashlib
import math
from datetime import datetime

import pytest

from scripts.generate_diagnostic_dataset import CLASSES, DT, PUBLIC_FIELDS, simulate, validate, write_csv


@pytest.mark.parametrize('scenario', CLASSES)
def test_complete_shift_physical_and_time_constraints(scenario):
    ep = simulate(81379526, scenario)
    validate(ep)
    physical = ep['physical']
    total = sum(r['fuel_lph'] * DT / 3600 for r in physical)
    assert ep['initial_fuel_l'] - physical[-1]['fuel_l'] == pytest.approx(total)
    assert any(r['work_state'] == 'dig' for r in physical)
    assert any(r['work_state'] == 'travel' for r in physical)
    assert any(r['work_state'] == 'off' for r in physical)
    for prev, row in zip(physical, physical[1:]):
        assert row['operating_hours'] >= prev['operating_hours']
        assert row['idle_hours'] >= prev['idle_hours']
        assert row['fuel_l'] <= prev['fuel_l']
        assert row['shaft_kw'] <= 90
        assert abs(row['coolant_c'] - prev['coolant_c']) < 1
        if row['engine_rpm']:
            torque = row['shaft_kw'] * 1000 * 60 / (row['engine_rpm'] * 2 * math.pi)
            assert torque <= 500
    for row in ep['observations']:
        assert not set(('scenario','seed','work_state','terminal_power')).intersection(row)
        if row['recorded_at']:
            age = (datetime.fromisoformat(row['observed_at'])-datetime.fromisoformat(row['recorded_at'])).total_seconds()
            assert row['age_seconds'] == age >= 0


@pytest.mark.parametrize('scenario', ['network_outage','terminal_power_loss'])
def test_telematics_loss_does_not_stop_machine(scenario):
    ep = simulate(54137829, scenario)
    during = [r for r in ep['physical'] if ep['onset_s'] <= r['elapsed_s'] < ep['end_s']]
    assert all(r['engine_on'] for r in during)
    assert during[-1]['fuel_l'] < during[0]['fuel_l']
    assert during[-1]['operating_hours'] > during[0]['operating_hours']
    stale = [r for r in ep['observations'] if ep['onset_s'] + 120 <= r['elapsed_s'] < ep['end_s']]
    assert all(r['age_seconds'] >= 60 for r in stale)
    recovered = [r for r in ep['observations'] if ep['end_s'] + 180 <= r['elapsed_s'] < ep['end_s'] + 360]
    assert min(r['age_seconds'] for r in recovered) <= 60


def test_cache_staleness_has_fresh_cloud_and_sensor_freeze_has_live_engine_hours():
    ep = simulate(54137829, 'cache_stale')
    during = [r for r in ep['layers'] if ep['onset_s']+180 <= r['elapsed_s'] < ep['end_s']]
    assert all(r['cloud_sample_s'] > r['cache_sample_s'] for r in during)
    ep = simulate(54137829, 'fuel_sensor_freeze')
    during = [r for r in ep['observations'] if ep['onset_s']+180 <= r['elapsed_s'] < ep['end_s']]
    assert len({r['fuel_percent'] for r in during}) == 1
    assert during[-1]['operating_hours'] > during[0]['operating_hours']
    true = [r for r in ep['physical'] if ep['onset_s'] <= r['elapsed_s'] < ep['end_s']]
    assert true[-1]['fuel_l'] < true[0]['fuel_l']


def test_determinism_and_gzip_bytes(tmp_path):
    first = simulate(54137829, 'healthy')
    second = simulate(54137829, 'healthy')
    assert first == second
    write_csv(tmp_path/'a.csv.gz', PUBLIC_FIELDS, first['observations'])
    write_csv(tmp_path/'b.csv.gz', PUBLIC_FIELDS, second['observations'])
    assert hashlib.sha256((tmp_path/'a.csv.gz').read_bytes()).digest() == hashlib.sha256((tmp_path/'b.csv.gz').read_bytes()).digest()
    with gzip.open(tmp_path/'a.csv.gz', 'rt') as f:
        assert len(f.readlines()) == 481


def test_checks_are_timestamped_and_missing_is_not_zero():
    ep = simulate(54137829, 'network_outage')
    assert ep['observations'][0]['fuel_percent'] is None
    assert ep['onset_s'] < ep['decision_s'] < ep['end_s']
    for action in ep['actions'].values():
        assert action['as_of_s'] == ep['decision_s']
        assert action['cost_units'] > 0
        assert action['result'] is not None or not action['available']


def test_paired_link_faults_preserve_underlying_workload():
    reference = simulate(54137829, 'healthy')['physical']
    fields = ['work_state','engine_rpm','fuel_l','coolant_c','x_m','y_m']
    for scenario in ['network_outage','terminal_power_loss','fuel_sensor_freeze','cache_stale','cloud_batch_delay']:
        candidate = simulate(54137829, scenario)['physical']
        assert [[r[f] for f in fields] for r in candidate] == [[r[f] for f in fields] for r in reference]
