"""The explicit UI source choice cannot fall through to demo fixtures."""
from fastapi.testclient import TestClient

from app.data_store import get_data_source, load_machines
from app.main import app
from app.request_data_mode import set_mode, reset_mode


def test_request_mode_is_isolated_and_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv('DATA_SOURCE', 'demo')
    client = TestClient(app)
    assert client.get('/health').json()['data_source'] == 'demo'
    assert client.get('/health', headers={'X-Jilian-Data-Mode': 'live'}).json()['data_source'] == 'trackunit_cache'
    assert client.get('/health', headers={'X-Jilian-Data-Mode': 'demo'}).json()['data_source'] == 'demo'
    assert client.get('/health', headers={'X-Jilian-Data-Mode': 'other'}).status_code == 400
    assert client.get('/health').json()['data_source'] == 'demo'


def test_live_mode_never_uses_demo_when_cache_is_empty(monkeypatch, tmp_path):
    from app import data_store
    monkeypatch.setattr(data_store, 'MACHINES_CACHE', tmp_path / 'missing-machines.json')
    token = set_mode('live')
    try:
        assert get_data_source() == 'trackunit_cache'
        assert load_machines() == []
    finally:
        reset_mode(token)


def test_live_mode_excludes_sample_cache_and_its_evidence(monkeypatch, tmp_path):
    import json
    from app import data_store

    machines = tmp_path / 'machines.json'
    telemetry = tmp_path / 'telemetry.json'
    faults = tmp_path / 'faults.json'
    machine = dict(model='XE55U', machine_type='excavator', customer='XCMG',
                   location='Site', last_seen_at='2026-09-01T00:00:00Z')
    machines.write_text(json.dumps([
        {**machine, 'machine_id': 'sample', 'serial_number': 'SIM-M-1001'},
        {**machine, 'machine_id': 'actual', 'serial_number': 'XUGC055UARKA02003'},
    ]), encoding='utf-8')
    telemetry.write_text(json.dumps([{'machine_id': machine_id, 'recorded_at': '2026-09-01T00:00:00Z'}
                                     for machine_id in ('sample', 'actual')]), encoding='utf-8')
    faults.write_text(json.dumps([{'machine_id': machine_id, 'fault_code': 'E4030',
                                   'description': 'Fault', 'severity': 'medium',
                                   'occurred_at': '2026-09-01T00:00:00Z', 'status': 'open'}
                                  for machine_id in ('sample', 'actual')]), encoding='utf-8')
    monkeypatch.setattr(data_store, 'MACHINES_CACHE', machines)
    monkeypatch.setattr(data_store, 'TELEMETRY_CACHE', telemetry)
    monkeypatch.setattr(data_store, 'FAULTS_CACHE', faults)
    token = set_mode('live')
    try:
        assert [row.machine_id for row in data_store.load_machines()] == ['actual']
        assert [row.machine_id for row in data_store.load_telemetry()] == ['actual']
        assert [row.machine_id for row in data_store.load_faults()] == ['actual']
    finally:
        reset_mode(token)
