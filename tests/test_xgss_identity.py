import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app import local_datasets, platform_asset_loader as loader, xgss_handoff as xgss, xgss_identity as identity
from app.api import routes_xgss
from app.local_datasets import LocalDataset
from app.main import app
from app.models import Machine, TelemetrySnapshot

ASSET = '00000000-0000-0000-0000-000000009881'
OTHER = '00000000-0000-0000-0000-000000009882'
ORIGINAL = '10000988'
VIN = 'XUGTEST00000098811'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(local_datasets, 'DATASETS', tmp_path / 'datasets')
    monkeypatch.setattr(identity, 'STATE_DIR', tmp_path / 'identities')
    monkeypatch.setattr(loader, 'STATE_DIR', tmp_path / 'platform')
    machine = Machine(machine_id=ASSET, trackunit_asset_id=ASSET, equipment_id=ORIGINAL,
                      serial_number=ORIGINAL, model='XE80U', machine_type='excavator',
                      customer='test', location='test', last_seen_at='2026-01-01T10:00:00Z')
    dataset = LocalDataset(name='identity fixture', source_document='AEMP fixture', provenance='user_supplied',
                           machine=machine, telemetry=[TelemetrySnapshot(machine_id=ASSET, operating_hours=9,
                           recorded_at='2026-01-01T10:00:00Z')])
    saved = local_datasets.save_dataset(dataset)
    calls = []
    monkeypatch.setattr(xgss, 'request_page', lambda *args, **kwargs: calls.append((args, kwargs)) or {'url':'https://xgss.xcmg.com/test'})
    return TestClient(app), dataset, saved, calls


def body(saved, **changes):
    return dict(machine_id=ASSET, dataset_id=saved['dataset_id'], current_vin=ORIGINAL,
                new_vin=VIN, confirmed=True, **changes)


def test_numeric_equipment_collision_is_reported_and_never_sent_to_xgss(setup):
    client, dataset, saved, calls = setup
    fields = dict(machine_id=ASSET, dataset_id=saved['dataset_id'], vin=ORIGINAL)
    status = client.post('/assistant/xgss/identity', json=fields)
    assert status.status_code == 200 and status.json()['needs_verification']
    response = client.post('/assistant/xgss/open', json={**fields, 'vin_confirmed':True})
    assert response.status_code == 422 and response.json()['detail']['code'] == 'vin_required'
    assert not calls


@pytest.mark.parametrize('serial,equipment,pending', [
    ('12345678901234567','12345678901234567',False),
    ('12345678','DIFFERENT',False),
    ('XUGTEST00000098811','XUGTEST00000098811',False),
    ('未提供',ORIGINAL,True),
])
def test_identity_guard_is_not_a_blanket_numeric_pin_rejection(setup, serial, equipment, pending):
    machine = setup[1].machine.model_copy(update={'serial_number':serial,'equipment_id':equipment})
    assert identity.needs_verification(machine) is pending


def test_correction_verifies_before_save_preserves_old_data_and_refreshes_exact_cache(setup):
    client, dataset, saved, calls = setup
    original_bytes = (local_datasets.DATASETS / (saved['dataset_id']+'.json')).read_bytes()
    loader.STATE_DIR.mkdir()
    cache = {'authorization_context':'test-context','expires_at':99,'result':{
        'asset_id':ASSET,'dataset_id':saved['dataset_id'],'machine':dataset.machine.model_dump(),'fetched_at':'original-time'}}
    (loader.STATE_DIR / (ASSET+'.json')).write_text(json.dumps(cache), encoding='utf-8')
    response = client.post('/assistant/xgss/identity/correct', json={**body(saved),'new_vin':' '+VIN.lower()+' '})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'corrected' and result['dataset_id'] != saved['dataset_id']
    assert calls == [((VIN,), {'language':'zh'})]
    updated = local_datasets.load_dataset(result['dataset_id'])
    assert updated.machine.serial_number == VIN and updated.machine.machine_id == ASSET
    assert updated.telemetry == dataset.telemetry and updated.faults == dataset.faults
    assert updated.machine.equipment_id == ORIGINAL
    assert identity.SOURCE_NOTE in updated.source_document
    assert (local_datasets.DATASETS / (saved['dataset_id']+'.json')).read_bytes() == original_bytes
    assert 'url' not in result
    cache2 = json.loads((loader.STATE_DIR / (ASSET+'.json')).read_text())
    assert cache2['result']['dataset_id'] == result['dataset_id']
    assert cache2['result']['fetched_at'] == 'original-time'
    status = client.post('/assistant/xgss/identity', json=dict(machine_id=ASSET,dataset_id=saved['dataset_id'],vin=ORIGINAL)).json()
    assert status['replacement_dataset_id'] == result['dataset_id']
    assert identity.apply_binding(dataset.machine).serial_number == VIN
    for changes in ({'machine_id':OTHER},{'model':'XE55U'},{'equipment_id':'OTHER'},{'serial_number':'10009999'}):
        foreign = dataset.machine.model_copy(update=changes)
        assert identity.apply_binding(foreign).serial_number == foreign.serial_number


@pytest.mark.parametrize('changes', [
    {'machine_id':OTHER}, {'current_vin':'10009999'}, {'new_vin':' '},
    {'confirmed':False}, {'new_vin':'NOT A VIN'}, {'dataset_id':'f'*64},
])
def test_invalid_or_stale_correction_never_calls_upstream_or_saves(setup, changes):
    client, dataset, saved, calls = setup
    before = set(local_datasets.DATASETS.glob('*.json'))
    response = client.post('/assistant/xgss/identity/correct', json={**body(saved),**changes})
    assert response.status_code in (404,422)
    assert not calls and set(local_datasets.DATASETS.glob('*.json')) == before
    assert not identity.STATE_DIR.exists()


def test_simulated_correction_never_calls_xgss(setup):
    client, dataset, saved, calls = setup
    simulated = dataset.model_copy(update={'provenance':'synthetic'})
    saved = local_datasets.save_dataset(simulated)
    assert client.post('/assistant/xgss/identity/correct', json=body(saved)).status_code == 422
    assert not calls and not identity.STATE_DIR.exists()


@pytest.mark.parametrize('error,status', [(xgss.XGSSUpstreamError('XGSS拒绝该编号'),502),
                                         (xgss.XGSSUnavailable('尚未配置'),503)])
def test_upstream_failure_keeps_original_identity_and_no_binding(setup, monkeypatch, error, status):
    client, dataset, saved, calls = setup
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(xgss, 'request_page', fail)
    response = client.post('/assistant/xgss/identity/correct', json=body(saved))
    assert response.status_code == status
    assert len(list(local_datasets.DATASETS.glob('*.json'))) == 1
    assert not identity.STATE_DIR.exists()
    assert local_datasets.load_dataset(saved['dataset_id']).machine.serial_number == ORIGINAL


def test_future_snapshot_keeps_verified_vin_without_changing_readings(setup):
    client, dataset, saved, calls = setup
    corrected = client.post('/assistant/xgss/identity/correct', json=body(saved)).json()
    snapshot = {'metadata':{'assetId':ASSET}, 'EquipmentHeader':{'EquipmentID':ORIGINAL,'Model':'XE80U','PIN':ORIGINAL},
                'CumulativeOperatingHours':{'Hour':10,'datetime':'2026-01-02T10:00:00Z'}}
    new = loader._save_snapshot(ASSET, snapshot, loader._snapshot_metadata(snapshot,ASSET), 'AEMP fixture')
    assert new['machine']['serial_number'] == VIN
    assert new['dataset_id'] != corrected['dataset_id']
    imported = local_datasets.load_dataset(new['dataset_id'])
    assert imported.telemetry[0].operating_hours == 10
    assert identity.SOURCE_NOTE in imported.source_document


def test_correction_does_not_redirect_other_historical_versions(setup):
    client, dataset, saved, calls = setup
    client.post('/assistant/xgss/identity/correct', json=body(saved))
    older = dataset.model_copy(deep=True)
    older.telemetry[0].operating_hours = 1
    older_saved = local_datasets.save_dataset(older)
    assert 'replacement_dataset_id' not in identity.status(older.machine, older_saved['dataset_id'])


def test_same_numeric_manufacturer_pin_can_be_explicitly_verified_with_distinct_provenance(setup):
    client, dataset, saved, calls = setup
    dataset.source_document = 'AEMP fixture ' + 'x' * 287
    saved = local_datasets.save_dataset(dataset)
    response = client.post('/assistant/xgss/identity/correct', json={**body(saved), 'new_vin':ORIGINAL})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['dataset_id'] != saved['dataset_id']
    corrected = local_datasets.load_dataset(result['dataset_id'])
    assert corrected.machine.serial_number == ORIGINAL and corrected.telemetry == dataset.telemetry
    assert len(corrected.source_document) <= 300 and corrected.source_document.endswith(identity.SOURCE_NOTE)
    assert local_datasets.load_dataset(saved['dataset_id']).source_document == dataset.source_document
    assert calls == [((ORIGINAL,), {'language':'zh'})]
    assert not identity.needs_verification(corrected.machine)
    status = client.post('/assistant/xgss/identity', json=dict(machine_id=ASSET,dataset_id=saved['dataset_id'],vin=ORIGINAL)).json()
    assert status['replacement_dataset_id'] == result['dataset_id']


def test_same_numeric_pin_rejected_by_xgss_never_creates_confirmation_or_dataset(setup, monkeypatch):
    client, dataset, saved, calls = setup
    def fail(*args, **kwargs):
        calls.append(args)
        raise xgss.XGSSUpstreamError('XGSS拒绝该编号')
    monkeypatch.setattr(xgss, 'request_page', fail)
    response = client.post('/assistant/xgss/identity/correct', json={**body(saved),'new_vin':ORIGINAL})
    assert response.status_code == 502 and calls == [(ORIGINAL,)]
    assert len(list(local_datasets.DATASETS.glob('*.json'))) == 1
    assert not identity.STATE_DIR.exists() and identity.needs_verification(dataset.machine)


def test_same_already_usable_vin_cannot_be_reconfirmed_as_a_new_correction(setup):
    client, dataset, saved, calls = setup
    dataset.machine.serial_number = VIN
    saved = local_datasets.save_dataset(dataset)
    response = client.post('/assistant/xgss/identity/correct', json={**body(saved),'current_vin':VIN})
    assert response.status_code == 422 and not calls
