"""Synthetic single-asset API fixtures, never a production VIN or response."""
from copy import deepcopy
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import platform_asset_loader as loader, local_datasets, data_store
from app.trackunit_client import TrackunitError

ASSET = '00000000-0000-0000-0000-000000009991'
OTHER = '00000000-0000-0000-0000-000000009992'
META = {'id': ASSET, 'model': 'XC948U', 'name': 'TEST-ASSET', 'serialNumber': 'TEST-PIN',
        'type': 'Wheel loader', 'telematicsDevices': [{'serialNumber': 'TEST-DEVICE'}]}
SNAPSHOT = {'metadata': {'assetId': ASSET}, 'EquipmentHeader': {'Model': 'XC948U', 'PIN': 'TEST-PIN'},
            'CumulativeOperatingHours': {'Hour': 419.5, 'datetime': '2026-01-01T10:00:00Z'},
            'CumulativeIdleHours': {'Hour': 50.0, 'datetime': '2026-01-01T09:30:00Z'}}


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, 'STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr(local_datasets, 'DATASETS', tmp_path / 'datasets')
    monkeypatch.setenv('TRACKUNIT_FLEET_SNAPSHOT_ENDPOINT', loader.FLEET_PATH + '{page}')
    for method in ('save_machines', 'save_telemetry', 'save_faults'):
        monkeypatch.setattr(data_store, method, lambda *a: pytest.fail('Must not overwrite fleet caches'))
    return tmp_path


def mock_client(monkeypatch, responses):
    calls = []
    class Client:
        def __init__(self, timeout_seconds, retries):
            assert retries == 0
            self.timeout_seconds = timeout_seconds
        def request(self, method, endpoint, **kwargs):
            assert method == 'GET'
            assert 0 < self.timeout_seconds <= 8
            calls.append((endpoint, kwargs))
            result = responses[len(calls)-1]
            if isinstance(result, Exception):
                raise result
            return deepcopy(result)
    monkeypatch.setattr(loader, 'BoundedAssetClient', Client)
    return calls


def test_asset_snapshot_import_is_isolated_and_independently_timestamped(fixture, monkeypatch):
    calls = mock_client(monkeypatch, [META, {'equipment': [SNAPSHOT]}])
    result = loader.load_platform_asset(ASSET)
    assert result['state'] == 'loaded'
    assert result['fault_status'] == 'not_checked'
    assert result['sample_count'] == 2
    dataset = local_datasets.load_dataset(result['dataset_id'])
    assert dataset.provenance == 'user_supplied'
    assert dataset.machine.machine_id == ASSET
    assert dataset.machine.serial_number == 'TEST-PIN'
    assert dataset.faults == []
    assert all(row.raw_payload is None and row.trackunit_asset_id == ASSET for row in dataset.telemetry)
    assert dataset.telemetry[0].operating_hours is None
    assert dataset.telemetry[1].idle_hours is None
    assert all('/fault' not in endpoint.lower() for endpoint, _ in calls)
    assert calls[1][1]['params'] == {'addMetadata': 'true', 'addExtendedData': 'true'}
    again = loader.load_platform_asset(ASSET)
    assert again['dataset_id'] == result['dataset_id'] and again['cache_hit']
    assert len(calls) == 2


@pytest.mark.parametrize('change', [
    {'metadata': {'assetId': OTHER}},
    {'id': OTHER},
    {'assetId': OTHER},
    {'metadata': {}},
])
def test_snapshot_missing_or_conflicting_uuid_never_imports(fixture, monkeypatch, change):
    mock_client(monkeypatch, [META, {'equipment': [{**SNAPSHOT, **change}]}])
    result = loader.load_platform_asset(ASSET)
    assert result['state'] == 'unavailable' and result['status'] == 'invalid_response'
    assert not list(local_datasets.DATASETS.glob('*.json'))


def test_metadata_uuid_mismatch_stops_before_snapshot_request(fixture, monkeypatch):
    calls = mock_client(monkeypatch, [{**META, 'id': OTHER}])
    result = loader.load_platform_asset(ASSET)
    assert result['status'] == 'invalid_response'
    assert len(calls) == 1


@pytest.mark.parametrize('channel', [
    {},
    {'CumulativeOperatingHours': {'Hour': True, 'datetime': '2026-01-01T10:00:00Z'}},
    {'CumulativeOperatingHours': {'Hour': 123}},
    {'CumulativeOperatingHours': {'Hour': 123, 'datetime': '2099-01-01T10:00:00Z'}},
    {'Location': {'Latitude': 1000, 'datetime': '2026-01-01T10:00:00Z'}},
])
def test_missing_invalid_or_future_telemetry_is_metadata_only(fixture, monkeypatch, channel):
    snapshot = {'metadata': {'assetId': ASSET}, 'EquipmentHeader': {'Model': 'XC948U'}, **channel}
    mock_client(monkeypatch, [META, {'equipment': [snapshot]}])
    result = loader.load_platform_asset(ASSET)
    assert result['state'] == 'unavailable' and result['status'] == 'metadata_only'
    assert result['sample_count'] == 0 and result['dataset_id'] is None
    assert result['machine']['model'] == 'XC948U'
    assert not list(local_datasets.DATASETS.glob('*.json'))


@pytest.mark.parametrize('status', [401, 403, 429])
def test_provider_failure_has_backoff_and_never_retries_faults(fixture, monkeypatch, status):
    calls = mock_client(monkeypatch, [TrackunitError('Provider detail must not escape', status)] * 2)
    first = loader.load_platform_asset(ASSET)
    second = loader.load_platform_asset(ASSET)
    assert first['state'] == 'unavailable' and first['http_status'] == status
    assert second['cache_hit'] and second['retry_after_seconds'] > 0
    assert len(calls) == (2 if status in {401, 403} else 1)
    assert 'Provider detail' not in json.dumps(first)


def test_only_snapshot_404_tries_one_associated_device_identifier(fixture, monkeypatch):
    calls = mock_client(monkeypatch, [META, TrackunitError('not found', 404), {'equipment': [SNAPSHOT]}])
    result = loader.load_platform_asset(ASSET)
    assert result['state'] == 'loaded'
    assert calls[1][0].endswith('/TEST-PIN')
    assert calls[2][0].endswith('/TEST-DEVICE')
    assert len(calls) == 3


def test_snapshot_unauthorized_preserves_metadata_without_trying_other_id(fixture, monkeypatch):
    calls = mock_client(monkeypatch, [META, TrackunitError('unauthorized', 401)])
    result = loader.load_platform_asset(ASSET)
    assert result['status'] == 'metadata_only'
    assert result['telemetry_status'] == 'unauthorized'
    assert result['fault_status'] == 'not_checked'
    assert len(calls) == 2


def test_busy_asset_and_invalid_path_do_not_send_requests(fixture, monkeypatch):
    mock_client(monkeypatch, [])
    loader.STATE_DIR.mkdir()
    (loader.STATE_DIR / (ASSET + '.lock')).write_text('busy', encoding='utf-8')
    assert loader.load_platform_asset(ASSET)['status'] == 'busy'
    with pytest.raises(ValueError):
        loader.load_platform_asset('../invalid')


def test_api_route_returns_scoped_dataset_and_no_store(fixture, monkeypatch):
    from app.main import app
    mock_client(monkeypatch, [META, {'equipment': [SNAPSHOT]}])
    client = TestClient(app)
    response = client.post('/assistant/platform-asset/' + ASSET + '/load')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['state'] == 'loaded'
    assert client.post('/assistant/platform-asset/not-a-uuid/load').status_code == 422


def page(items, next_page=None, pages_total=None):
    links = [] if next_page is None else [
        {'rel': 'next', 'href': 'https://iris.trackunit.com' + loader.FLEET_PATH + str(next_page)}]
    if pages_total is not None:
        links.append({'rel': 'last', 'href': 'https://iris.trackunit.com' + loader.FLEET_PATH + str(pages_total)})
    return {'equipment': items, 'Links': links}


def test_fleet_fallback_skips_other_assets_and_stores_only_exact_match(fixture, monkeypatch):
    unrelated = {**SNAPSHOT, 'metadata': {'assetId': OTHER}}
    malformed_other = {**SNAPSHOT, 'metadata': {'assetId': 'not-an-asset'}}
    calls = mock_client(monkeypatch, [TrackunitError('denied', 401),
            page([unrelated, malformed_other], 2), page([unrelated, SNAPSHOT], 3)])
    result = loader.load_platform_asset(ASSET)
    assert result['state'] == 'loaded' and result['sample_count'] == 2
    assert result['api_request_count'] == 3 and result['searched_pages'] == 2
    assert result['identity_matches'] == 1 and result['lookup_route'] == 'aemp_fleet'
    saved = local_datasets.load_dataset(result['dataset_id'])
    assert saved.machine.machine_id == ASSET and saved.machine.serial_number == 'TEST-PIN'
    assert 'AEMP Fleet' in saved.source_document and 'single-equipment' not in saved.source_document
    files = list(local_datasets.DATASETS.glob('*.json'))
    assert len(files) == 1 and OTHER not in files[0].read_text(encoding='utf-8')
    assert all(kwargs['params'] == {'addMetadata': 'true', 'addExtendedData': 'true'} for _, kwargs in calls[1:])


def test_fleet_search_has_three_page_limit_and_never_claims_no_faults(fixture, monkeypatch):
    unrelated = {**SNAPSHOT, 'metadata': {'assetId': OTHER}}
    calls = mock_client(monkeypatch, [TrackunitError('denied', 403)] + [page([unrelated], i + 1) for i in (1, 2, 3)])
    result = loader.load_platform_asset(ASSET)
    # Hitting the page cap is not a conclusion about the device, so it is reported
    # as its own status: a caller must not present it as "not found" or as a
    # temporary failure that a retry would fix.
    assert result['status'] == 'search_incomplete' and result['search_complete'] is False
    assert result['searched_pages'] == 3 and result['identity_matches'] == 0
    assert '前 3 页' in result['message'] and '未关联其他设备' in result['message']
    assert result['fault_status'] == 'not_checked' and len(calls) == 4
    assert not list(local_datasets.DATASETS.glob('*.json'))


def test_fleet_page_cap_reports_how_much_of_the_fleet_was_covered(fixture, monkeypatch):
    unrelated = {**SNAPSHOT, 'metadata': {'assetId': OTHER}}
    mock_client(monkeypatch, [TrackunitError('denied', 401)] + [page([unrelated], i + 1, pages_total=11) for i in (1, 2, 3)])
    result = loader.load_platform_asset(ASSET)
    assert result['status'] == 'search_incomplete'
    assert result['searched_pages'] == 3 and result['pages_total'] == 11
    assert '共 11 页' in result['message']
    # The device stays unassociated; nothing about it is asserted from a partial scan.
    assert result['dataset_id'] is None and result.get('machine') is None


def test_an_unusable_equipment_hint_still_allows_the_fleet_search(fixture, monkeypatch):
    # A tab title is only a hint. If that endpoint rejects the account or the
    # value is not a real equipment ID, the device must still be reachable
    # through the bounded fleet search instead of the import being abandoned.
    # The 401 sequence below is the one this account really produces: the hint
    # endpoint and the single-asset endpoint both refuse, and only AEMP answers.
    calls = mock_client(monkeypatch, [TrackunitError('denied', 401), TrackunitError('denied', 401),
                                      page([SNAPSHOT])])
    result = loader.load_platform_asset(ASSET, equipment_id_hint='TEST-10001')
    assert result['state'] == 'loaded' and result['lookup_route'] == 'aemp_fleet'
    assert result['hint_status'] == 'unusable' and result['hint_http_status'] == 401
    assert len(calls) == 3 and calls[0][0].endswith('TEST-10001')


@pytest.mark.parametrize('items', [[SNAPSHOT, SNAPSHOT], [{**SNAPSHOT, 'assetId': OTHER}]])
def test_fleet_duplicate_or_conflicting_target_rejected(fixture, monkeypatch, items):
    mock_client(monkeypatch, [TrackunitError('denied', 401), page(items)])
    result = loader.load_platform_asset(ASSET)
    assert result['status'] == 'invalid_response' and result['dataset_id'] is None


def test_fleet_metadata_without_actual_measurement_never_invents_hours(fixture, monkeypatch):
    item = {'metadata': {'assetId': ASSET}, 'EquipmentHeader': {'Model': 'XC948U', 'PIN': 'TEST-PIN'}}
    mock_client(monkeypatch, [TrackunitError('denied', 401), page([item])])
    result = loader.load_platform_asset(ASSET)
    assert result['status'] == 'metadata_only' and result['sample_count'] == 0
    assert result['machine']['model'] == 'XC948U'


def test_fleet_does_not_follow_foreign_next_url(fixture, monkeypatch):
    payload = page([], 2)
    payload['Links'][0]['href'] = 'https://example.test' + loader.FLEET_PATH + '2'
    calls = mock_client(monkeypatch, [TrackunitError('denied', 401), payload])
    assert loader.load_platform_asset(ASSET)['status'] == 'invalid_response'
    assert len(calls) == 2


def test_version_upgrade_skips_previously_denied_asset_call_once(fixture, monkeypatch):
    loader.STATE_DIR.mkdir()
    path = loader.STATE_DIR / (ASSET + '.json')
    path.write_text(json.dumps({'expires_at': time.time() - 30,
        'result': loader._unavailable(ASSET, 'upstream_unauthorized', 'old', http_status=401)}), encoding='utf-8')
    calls = mock_client(monkeypatch, [page([SNAPSHOT])])
    result = loader.load_platform_asset(ASSET)
    assert result['state'] == 'loaded' and result['asset_endpoint_skipped']
    assert len(calls) == 1 and '/Fleet/1' in calls[0][0]
    assert loader.load_platform_asset(ASSET)['cache_hit']
    record = json.loads(path.read_text(encoding='utf-8'))
    assert record['cache_version'] == loader.CACHE_VERSION


def test_auth_failure_does_not_attempt_fleet_with_invalid_credentials(fixture, monkeypatch):
    error = TrackunitError('authentication denied', 401)
    error.phase = 'authentication'
    calls = mock_client(monkeypatch, [error])
    result = loader.load_platform_asset(ASSET)
    assert result['failure_phase'] == 'authentication' and len(calls) == 1


def test_cache_not_shared_after_authorization_context_changes(fixture, monkeypatch):
    calls = mock_client(monkeypatch, [META, page([SNAPSHOT]), META, page([SNAPSHOT])])
    loader.load_platform_asset(ASSET)
    monkeypatch.setenv('TRACKUNIT_SCOPE', 'different-test-scope')
    assert not loader.load_platform_asset(ASSET)['cache_hit']
    assert len(calls) == 4


def test_equipment_hint_uses_single_read_and_checks_authoritative_uuid(fixture, monkeypatch):
    calls = mock_client(monkeypatch, [page([SNAPSHOT])])
    result = loader.load_platform_asset(ASSET, 'TEST-10001')
    assert result['state'] == 'loaded' and result['identity_matches'] == 1
    assert result['lookup_route'] == 'aemp_equipment_hint' and result['api_request_count'] == 1
    assert calls[0][0] == loader.SNAPSHOT_ENDPOINT + 'TEST-10001'
    assert loader.load_platform_asset(ASSET, 'TEST-10001')['cache_hit']


def test_stale_hint_matching_other_machine_never_imports_or_falls_back(fixture, monkeypatch):
    calls = mock_client(monkeypatch, [page([{**SNAPSHOT, 'metadata': {'assetId': OTHER}}])])
    result = loader.load_platform_asset(ASSET, 'TEST-OTHER')
    assert result['status'] == 'invalid_response' and result['dataset_id'] is None
    assert len(calls) == 1


def test_late_hint_bypasses_prior_no_hint_failure_cache(fixture, monkeypatch):
    calls = mock_client(monkeypatch, [TrackunitError('denied', 401), page([]), page([SNAPSHOT])])
    first = loader.load_platform_asset(ASSET)
    assert first['status'] == 'limited_search'
    second = loader.load_platform_asset(ASSET, 'TEST-10001')
    assert second['state'] == 'loaded' and not second['cache_hit'] and len(calls) == 3


def test_hint_404_can_use_metadata_lookup(fixture, monkeypatch):
    calls = mock_client(monkeypatch, [TrackunitError('not found', 404), META, page([SNAPSHOT])])
    result = loader.load_platform_asset(ASSET, 'TEST-10001')
    assert result['state'] == 'loaded' and result['hint_status'] == 'not_found'
    assert len(calls) == 3


def test_hint_route_accepts_optional_body_but_rejects_url_and_nonstring(fixture, monkeypatch):
    from app.main import app
    calls = mock_client(monkeypatch, [page([SNAPSHOT])])
    client = TestClient(app)
    url = '/assistant/platform-asset/' + ASSET + '/load'
    assert client.post(url, json={'equipment_id_hint': 'TEST-10001'}).json()['state'] == 'loaded'
    for hint in ('https://example.test', '../other', '   ', '', 123):
        assert client.post(url, json={'equipment_id_hint': hint}).status_code == 422
    assert len(calls) == 1


def test_equipment_hint_encodes_internal_spaces_and_trims_outer_spaces(fixture, monkeypatch):
    calls = mock_client(monkeypatch, [page([SNAPSHOT])])
    assert loader.load_platform_asset(ASSET, ' TEST MACHINE ')['state'] == 'loaded'
    assert calls[0][0].endswith('/TEST%20MACHINE')


def test_extended_snapshot_import_keeps_each_sensor_timestamp(fixture, monkeypatch):
    snapshot = {**SNAPSHOT,
        'engineCoolantTemperature': {'temperature': 86.0, 'datetime': '2026-01-01T09:57:00Z'},
        'engineSpeed': {'speed': 1487.5, 'datetime': '2026-01-01T09:58:00Z'},
        'engineOilPressure': {'pressure': 0.0, 'datetime': '2026-01-01T10:00:00Z'},
        'EngineStatus': {'Running': False, 'datetime': '2026-01-01T10:00:00Z'},
        'redStopLamp': {'state': 'true', 'datetime': '2026-01-01T09:59:00Z'}}
    mock_client(monkeypatch, [META, {'equipment': [snapshot]}])
    result = loader.load_platform_asset(ASSET)
    assert result['state'] == 'loaded'
    sensors = {row.key: row for row in local_datasets.load_dataset(result['dataset_id']).sensors}
    assert len(sensors) == 5
    assert sensors['coolant_c'].value == 86.0
    assert sensors['engine_rpm'].value == 1487.5
    assert sensors['engine_running'].value is False
    assert sensors['red_stop_lamp'].value is True
    assert sensors['coolant_c'].recorded_at != sensors['engine_rpm'].recorded_at
    assert sensors['oil_pressure_kpa'].recorded_at == sensors['engine_running'].recorded_at
