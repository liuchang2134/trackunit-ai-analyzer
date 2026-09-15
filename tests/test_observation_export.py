import csv
from datetime import timedelta
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from app import device_overview as overview_module
from app import observation_export as export_module
from app.device_overview import build_overview
from app.main import app
from app.models import TelemetrySnapshot
from scripts.prepare_parts_demo import build_demo


def make_overview(**changes):
    data = build_demo()
    machine = data.machine.model_copy(update=changes)
    samples = [TelemetrySnapshot(machine_id=machine.machine_id,
        recorded_at=(data.replay_at - timedelta(hours=hours)).isoformat(),
        operating_hours=100 + 7 - hours,
        idle_hours=None if hours == 1 else 10,
        fuel_remaining_percent=50) for hours in [7, 6, 1, 0]]
    return build_overview(machine, samples, [], source='imported_synthetic',
                          cutoff=data.replay_at, dataset_id='a' * 64)


def rows(content):
    assert content.startswith(b'\xef\xbb\xbf')
    assert b'\r\n' in content
    return list(csv.DictReader(StringIO(content.decode('utf-8-sig'), newline='')))


def test_csv_preserves_evidence_identity_and_missing_values(monkeypatch):
    evidence = make_overview(model='挖掘机,"甲"\n二型')
    monkeypatch.setattr(export_module, 'device_overview', lambda *a: evidence)
    content, filename = export_module.export_observations(evidence['machine_id'], 'a' * 64, 'idle_hours')
    records = rows(content)
    assert len(records) == 4
    assert records[2]['value'] == '' and records[3]['value'] == '10.0'
    assert {r['model'] for r in records} == {'挖掘机,"甲"\n二型'}
    assert {r['source'] for r in records} == {'imported_synthetic'}
    assert {r['dataset_id'] for r in records} == {'a' * 64}
    assert {r['plot_revision'] for r in records} == {evidence['plot_revision']}
    assert {r['metric'] for r in records} == {'idle_hours'}
    assert {r['unit'] for r in records} == {'h'}
    assert {r['sampled_for_display'] for r in records} == {'false'}
    assert filename.endswith('-idle_hours-all.csv') and '/' not in filename


@pytest.mark.parametrize('window,count', [('all', 4), ('6', 3), ('1', 2)])
def test_export_uses_chart_window_and_includes_exact_boundary(monkeypatch, window, count):
    evidence = make_overview()
    monkeypatch.setattr(export_module, 'device_overview', lambda *a: evidence)
    content, _ = export_module.export_observations(evidence['machine_id'], metric='fuel_remaining_percent', window=window)
    records = rows(content)
    assert len(records) == count
    assert records[-1]['recorded_at'] == evidence['series'][-1]['recorded_at']
    assert records[0]['recorded_at'] == evidence['series'][-count]['recorded_at']
    assert all(r['unit'] == '%' and r['window_hours'] == window for r in records)


def test_formula_like_metadata_is_inert_and_filename_is_safe(monkeypatch):
    evidence = make_overview(machine_id='=SUM(1,2)', model='  +1', serial_number='\t@cmd')
    monkeypatch.setattr(export_module, 'device_overview', lambda *a: evidence)
    content, filename = export_module.export_observations(evidence['machine_id'])
    record = rows(content)[0]
    assert record['machine_id'] == "'=SUM(1,2)"
    assert record['model'] == "'  +1" and record['serial_number'] == "'\t@cmd"
    assert all(c.isalnum() or c in '-_.' for c in filename)


def test_revision_ignores_clock_but_tracks_device_source_and_plotted_measurements():
    data = build_demo()
    first = build_overview(data.machine, data.telemetry, data.faults, source='mock', cutoff=data.replay_at)
    later = build_overview(data.machine, data.telemetry, data.faults, source='mock', cutoff=data.replay_at + timedelta(seconds=1))
    assert first['as_of'] != later['as_of'] and first['plot_revision'] == later['plot_revision']
    other_source = build_overview(data.machine, data.telemetry, [], source='trackunit', cutoff=data.replay_at)
    assert first['plot_revision'] != other_source['plot_revision']
    other_version = build_overview(data.machine, data.telemetry, [], source='mock', cutoff=data.replay_at, dataset_id='b' * 64)
    assert first['plot_revision'] != other_version['plot_revision']
    sample = TelemetrySnapshot(machine_id=data.machine.machine_id, recorded_at=data.replay_at.isoformat(), operating_hours=9000)
    updated = build_overview(data.machine, [*data.telemetry, sample], [], source='mock', cutoff=data.replay_at)
    assert first['plot_revision'] != updated['plot_revision']


def test_download_response_and_changed_evidence_rejection(monkeypatch):
    evidence = make_overview()
    monkeypatch.setattr(export_module, 'device_overview', lambda *a: evidence)
    client = TestClient(app)
    params = {'machine_id': evidence['machine_id'], 'expected_revision': evidence['plot_revision']}
    response = client.get('/assistant/device-overview.csv', params=params)
    assert response.status_code == 200 and len(rows(response.content)) == 4
    assert response.headers['content-type'] == 'text/csv; charset=utf-8'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['content-disposition'].startswith('attachment; filename="jilian-observations-')
    params['expected_revision'] = 'f' * 64
    response = client.get('/assistant/device-overview.csv', params=params)
    assert response.status_code == 409 and '数据已更新' in response.json()['detail']


@pytest.mark.parametrize('bad', [{'metric': 'pressure'}, {'window': '24'}, {'expected_revision': 'not-a-hash'},
                                {'dataset_id': '../private'}, {'machine_id': ''}])
def test_invalid_export_inputs_are_rejected(bad):
    response = TestClient(app).get('/assistant/device-overview.csv', params={'machine_id': 'x', **bad})
    assert response.status_code == 422


def test_wrong_device_and_unreadable_dataset_are_not_exported(monkeypatch):
    data = build_demo()
    monkeypatch.setattr(overview_module, 'load_dataset', lambda *a: data)
    client = TestClient(app)
    response = client.get('/assistant/device-overview.csv', params={'machine_id': 'OTHER', 'dataset_id': 'a' * 64})
    assert response.status_code == 404
    def unavailable(*a):
        raise OSError('unreadable')
    monkeypatch.setattr(overview_module, 'load_dataset', unavailable)
    response = client.get('/assistant/device-overview.csv', params={'machine_id': 'OTHER', 'dataset_id': 'a' * 64})
    assert response.status_code == 503


def test_empty_series_still_has_headers(monkeypatch):
    evidence = make_overview()
    evidence['series'] = []
    monkeypatch.setattr(export_module, 'device_overview', lambda *a: evidence)
    content, _ = export_module.export_observations(evidence['machine_id'], window='1')
    assert rows(content) == []
    assert content.decode('utf-8-sig').startswith('machine_id,model,serial_number,')


def test_real_dataset_download_does_not_call_external_services(monkeypatch):
    import httpx
    data = build_demo().model_copy(update={'provenance': 'user_supplied', 'replay_at': None})
    monkeypatch.setattr(overview_module, 'load_dataset', lambda *a: data)
    for method in ('get', 'post'):
        monkeypatch.setattr(httpx, method, lambda *a, **k: pytest.fail('Export must stay local'))
    response = TestClient(app).get('/assistant/device-overview.csv', params={
        'machine_id': data.machine.machine_id, 'dataset_id': 'a' * 64})
    assert response.status_code == 200
    assert {r['source'] for r in rows(response.content)} == {'imported_user_supplied'}
