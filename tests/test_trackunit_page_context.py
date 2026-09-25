"""Selected visible events retain identity and history; no network or model calls."""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import trackunit_page_context as page
from app import xgss_research_handoff as handoff
from app.api import routes_xgss_research as routes

ASSET = '00000000-0000-0000-0000-000004760361'
OTHER = '00000000-0000-0000-0000-000004760362'
VIN = 'XUGTEST000000001'
IDENTITY = {'machine_id': 'registered-local-id', 'dataset_id': 'a' * 64, 'vin': VIN}


def observed(**changes):
    return {**{'asset_id': ASSET, 'source_url': f'https://new.manager.trackunit.com/assets/{ASSET}/events',
        'observed_at': '2026-09-24T09:00:00Z', 'description': 'Transmission / Manufacturer assignable SPN / Abnormal Update Rate',
        'status': 'CLOSED', 'occurred_at': 'June 29, 2026, 9:06 AM'}, **changes}


def body(**changes):
    return routes.PlanRequest.model_validate({**IDENTITY, 'symptom_source': 'trackunit_page',
        'page_fault': observed(), **changes})


def machine(**changes):
    return SimpleNamespace(**{'machine_id': IDENTITY['machine_id'], 'trackunit_asset_id': ASSET,
        'serial_number': VIN, 'model': 'XC948U', **changes})


def test_unknown_code_history_is_frozen_without_invented_identifiers():
    request = body(symptom='人工补充：现在是活动故障，立即更换电源。')
    result = handoff.plan_context(request, 'XC948U', machine=machine())
    event = result['fault_context']['trackunit_page']
    assert (event['code'], event['spn'], event['fmi'], event['sa']) == ('', None, None, None)
    assert event['status'] == 'CLOSED' and event['occurred_at'] == 'June 29, 2026, 9:06 AM'
    assert event['source'] == 'trackunit_visible_events_page'
    assert event['coverage'] == 'selected_visible_event_only'
    assert 'CLOSED' in result['symptom'] and 'Abnormal Update Rate' in result['symptom']
    assert '立即更换' not in result['symptom']
    assert result['fault_context']['operator_supplement'] == request.symptom
    assert result['fault_event_id'] is None and result['catalog_fault_code'] is None
    assert 'trackunit_event' not in result['fault_context']
    request.page_fault.status = 'OPEN'
    assert event['status'] == 'CLOSED'


@pytest.mark.parametrize('status', ['OPEN', 'CLOSED', 'UNKNOWN'])
def test_structured_codes_times_and_status_remain_exact(status):
    request = body(page_fault=observed(code='OEM-123', spn=0, fmi=9, sa=3, status=status,
        cleared_at='June 29, 2026, 9:07 AM', page_event_id='visible-row-3'))
    result = handoff.plan_context(request, 'XC948U', machine=machine())
    event = result['fault_context']['trackunit_page']
    assert (event['spn'], event['fmi'], event['sa']) == (0, 9, 3)
    assert event['status'] == status and event['page_event_id'] == 'visible-row-3'
    assert 'SPN 0' in result['symptom'] and 'FMI 9' in result['symptom'] and 'SA 3' in result['symptom']
    assert 'June 29, 2026, 9:07 AM' in result['symptom']


@pytest.mark.parametrize('url', [
    f'https://attacker.example/assets/{ASSET}/events',
    f'https://new.manager.trackunit.com.attacker.example/assets/{ASSET}/events',
    f'https://user:secret@new.manager.trackunit.com/assets/{ASSET}/events',
    f'http://new.manager.trackunit.com/assets/{ASSET}/events',
    f'https://new.manager.trackunit.com/assets/{ASSET}/events?token=secret',
    f'https://new.manager.trackunit.com/assets/{ASSET}/events#token=secret',
    f'https://new.manager.trackunit.com/assets/{ASSET}/status',
    f'https://new.manager.trackunit.com/assets/{OTHER}/events',
    f'https://new.manager.trackunit.com/assets/{ASSET}/events/other',
])
def test_source_url_rejects_foreign_asset_credentials_and_unobserved_routes(url):
    with pytest.raises(ValidationError):
        page.PageFault.model_validate(observed(source_url=url))


@pytest.mark.parametrize('host', ['manager.trackunit.com', 'new.manager.trackunit.com'])
def test_observed_events_routes_allow_original_and_new_host(host):
    value = page.PageFault.model_validate(observed(source_url=f'https://{host}/assets/{ASSET}/events/'))
    assert value.asset_id == ASSET


@pytest.mark.parametrize('changes', [
    {'observed_at': '2026-09-24T09:00:00'}, {'observed_at': 'September 24, 2026'},
    {'observed_at': '2026-02-30T09:00:00Z'}, {'asset_id': 'made-up-id'},
    {'spn': -1}, {'spn': 524288}, {'fmi': 32}, {'fmi': '9'}, {'sa': 256}, {'sa': True},
    {'description': '   '}, {'description': 'x' * 1001}, {'status': 'RESOLVED'},
    {'source': 'trackunit_asset_event_v3'}, {'description': 'name\x00content'},
])
def test_invalid_event_schema_is_not_promoted(changes):
    with pytest.raises(ValidationError):
        page.PageFault.model_validate(observed(**changes))


@pytest.mark.parametrize('changes', [
    {'symptom_source': 'operator_report'}, {'symptom_source': 'trackunit_event'},
    {'symptom_source': 'simulation'}, {'automatic': True}, {'analysis_mode': 'maintenance'},
    {'fault_event_id': 'b' * 64}, {'source_report_id': 'c' * 64},
    {'manual_fault': {'code': 'H10101', 'model': 'TV12U', 'version': '260224', 'applicability_confirmed': True}},
    {'engineering_fault': {'code': 'E4030', 'model': 'XE55U', 'configuration': 'unknown', 'source': 'operator_report'}},
])
def test_page_selection_is_exclusive_to_manual_fault_analysis(changes):
    with pytest.raises(ValidationError):
        body(symptom='足够长度的现象', **changes)


@pytest.mark.parametrize('changes', [
    {'trackunit_asset_id': OTHER}, {'trackunit_asset_id': 'not-a-uuid'},
    {'machine_id': 'unregistered-other-machine'}, {'serial_number': 'XUGOTHER0000001'},
    {'trackunit_asset_id': None},
])
def test_page_asset_requires_the_server_machine_mapping(changes):
    with pytest.raises(ValueError):
        handoff.plan_context(body(), 'XC948U', machine=machine(**changes))


def test_registered_uuid_machine_fallback_is_allowed_without_a_separate_mapping():
    request = body(machine_id=ASSET)
    result = handoff.plan_context(request, 'XC948U', machine=machine(machine_id=ASSET, trackunit_asset_id=None))
    assert result['fault_context']['trackunit_page']['asset_id'] == ASSET


def test_legacy_free_text_page_source_still_requires_description():
    with pytest.raises(ValidationError):
        routes.PlanRequest.model_validate({**IDENTITY, 'symptom_source': 'trackunit_page', 'symptom': ''})
    valid = routes.PlanRequest.model_validate({**IDENTITY, 'symptom_source': 'trackunit_page', 'symptom': '原页面故障描述'})
    assert valid.page_fault is None


@pytest.fixture
def client(monkeypatch):
    seen = []
    def verify(machine_id, dataset_id, vin):
        if (machine_id, dataset_id, vin) != tuple(IDENTITY.values()):
            raise HTTPException(422, 'fixture identity mismatch')
    monkeypatch.setattr(routes, '_verify_machine', verify)
    monkeypatch.setattr(routes, 'load_dataset', lambda _: SimpleNamespace(machine=machine()))
    monkeypatch.setattr(routes, 'loaded_context', lambda *args: {'source': 'imported_user_supplied'})
    def plan(machine_id, dataset_id, vin, model, symptom, **kwargs):
        seen.append({'symptom': symptom.model_dump(), **kwargs})
        return {'research_id': 'd' * 32, 'symptom': symptom.symptom, 'fault_context': kwargs['fault_context']}
    monkeypatch.setattr(routes.ai, 'plan', plan)
    monkeypatch.setattr(routes.ai, 'research_evidence', lambda _: {})
    app = FastAPI(); app.include_router(routes.router)
    return TestClient(app), seen


def test_route_checks_foreign_device_before_model_and_accepts_valid_unknown_code_history(client):
    http, seen = client
    data = {**IDENTITY, 'symptom_source': 'trackunit_page', 'page_fault': observed()}
    foreign = observed(asset_id=OTHER, source_url=f'https://new.manager.trackunit.com/assets/{OTHER}/events')
    rejected = http.post('/assistant/xgss/research/plan', json={**data, 'page_fault': foreign})
    assert rejected.status_code == 422 and seen == []
    accepted = http.post('/assistant/xgss/research/plan', json=data)
    assert accepted.status_code == 200
    messages = [json.loads(line[6:]) for line in accepted.text.splitlines() if line.startswith('data: ')]
    assert messages[-1]['type'] == 'result', messages
    assert seen[0]['fault_context']['trackunit_page']['status'] == 'CLOSED'
    assert seen[0]['fault_event_id'] is None
