"""Source-bound snapshot triage; no manufactured failure date or threshold."""
import json

from fastapi.testclient import TestClient
import pytest

from app import local_datasets, sensor_risk
from app.local_datasets import LocalDataset, save_dataset
from app.models import Machine, TelemetrySnapshot

ASSET = '00000000-0000-0000-0000-000000009991'


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(local_datasets, 'DATASETS', tmp_path / 'datasets')
    monkeypatch.setattr(sensor_risk, 'STORE', tmp_path / 'risk')
    machine = Machine(machine_id=ASSET, model='TEST-LOADER', serial_number='TEST-PIN', machine_type='Wheel loader', customer='Test', location='Test site', last_seen_at='2026-01-01T10:00:00Z')
    data = LocalDataset(name='Test Trackunit snapshot', source_document='Trackunit AEMP single-equipment snapshot',
        provenance='user_supplied', machine=machine,
        telemetry=[TelemetrySnapshot(machine_id=ASSET, recorded_at='2026-01-01T10:00:00Z', operating_hours=100.0)],
        sensors=[
            {'key':'coolant_c','value':86.0,'recorded_at':'2026-01-01T09:57:00Z'},
            {'key':'engine_rpm','value':1487.5,'recorded_at':'2026-01-01T09:58:00Z'},
            {'key':'engine_running','value':False,'recorded_at':'2026-01-01T10:00:00Z'},
            {'key':'oil_pressure_kpa','value':0.0,'recorded_at':'2026-01-01T10:00:00Z'},
            {'key':'red_stop_lamp','value':True,'recorded_at':'2026-01-01T09:59:00Z'}])
    return save_dataset(data)['dataset_id']


def test_risk_overview_preserves_times_and_refuses_future_window(snapshot):
    report = sensor_risk.overview(ASSET, snapshot)
    observations = {row['key']:row for row in report['observations']}
    assert observations['coolant_c']['recorded_at'] != observations['engine_rpm']['recorded_at']
    assert observations['engine_running']['value'] is False
    assert report['prediction_window'] is None
    assert report['ai_priorities'] is None
    assert '同一时点' in next(row['detail'] for row in report['checks'] if row['id']=='verify_oil_pressure_context')
    with pytest.raises(ValueError):
        sensor_risk.overview('another asset', snapshot)


def test_ai_can_only_rank_derived_checks_without_identifiers(snapshot, monkeypatch):
    calls=[]
    def ai(messages, schema, timeout_seconds):
        calls.append((messages,schema))
        return json.dumps({'priority_ids':['verify_warning_event','verify_oil_pressure_context']})
    monkeypatch.setattr(sensor_risk, 'generate_structured_with_deepseek', ai)
    report = sensor_risk.analyze(ASSET, snapshot)
    assert report['ai_priorities']['priority_ids']==['verify_warning_event','verify_oil_pressure_context']
    assert ASSET not in str(calls) and 'TEST-PIN' not in str(calls)
    assert sensor_risk.overview(ASSET, snapshot)['ai_priorities']['priority_ids']==report['ai_priorities']['priority_ids']
    assert len(calls)==1


def test_risk_routes_are_scoped_and_no_store(snapshot):
    from app.main import app
    client=TestClient(app)
    params={'machine_id':ASSET,'dataset_id':snapshot}
    response=client.get('/assistant/risk-overview',params=params)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert client.get('/assistant/risk-overview',params={**params,'machine_id':'wrong'}).status_code==404
