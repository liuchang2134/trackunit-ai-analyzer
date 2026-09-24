"""Automatic claims use synthetic local events and fake plans; no network/model."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import trackunit_events as events
from app import xgss_auto_fault as automatic
from app import xgss_research_ai as ai, xgss_research_store as store
from app.api import routes_xgss_research as routes


NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
ASSET = '00000000-0000-0000-0000-000000000001'
SOURCE = '10000000-0000-0000-0000-000000000001'
IDENTITY = {'machine_id': ASSET, 'dataset_id': 'a' * 64, 'vin': 'XUGTEST000000001'}
EVENT_ID = events.event_key(ASSET, SOURCE)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(events, 'STORE', tmp_path / 'events')
    monkeypatch.setattr(store, 'STORE', tmp_path / 'research')
    monkeypatch.setattr(events, 'utcnow', lambda: NOW)
    def registered(machine_id, dataset_id=None, vin=None):
        if (machine_id, dataset_id, vin) != tuple(IDENTITY.values()):
            raise ValueError('fixture identity mismatch')
        return {**IDENTITY, 'trackunit_asset_id': ASSET, 'model': 'XE55U'}
    monkeypatch.setattr(events, 'registered_machine', registered)
    monkeypatch.setattr(events.TrackunitClient, 'get_token', lambda *a, **k: pytest.fail('Unexpected authentication'))
    monkeypatch.setattr(ai, 'generate_structured_with_deepseek', lambda *a, **k: pytest.fail('Unexpected model transport'))
    write_state()


def event(**changes):
    return {**{'event_id': EVENT_ID, 'source_event_id': SOURCE, 'machine_id': ASSET,
        'trackunit_asset_id': ASSET, 'vin': IDENTITY['vin'], 'code': 'E4030',
        'code_system': 'oem_unspecified', 'spn': None, 'fmi': None, 'sa': None,
        'description': '合成夹具故障', 'occurred_at': (NOW-timedelta(minutes=5)).isoformat(),
        'event_time': (NOW-timedelta(minutes=5)).isoformat(), 'cleared_at': None,
        'status': 'OPEN', 'severity': None, 'source': 'trackunit_asset_event_v3',
        'observed_at': NOW.isoformat()}, **changes}


def write_state(**changes):
    state = {**IDENTITY, 'trackunit_asset_id': ASSET, 'status': 'data', 'http_status': 200,
        'coverage': 'queried_window', 'checked_at': NOW.isoformat(), 'events': [event()], **changes}
    events._write(events._path(ASSET), state)
    return state


def body(**changes):
    return routes.PlanRequest(**{**IDENTITY, 'automatic': True, 'analysis_mode': 'fault',
        'symptom': '', 'symptom_source': 'trackunit_event', 'fault_event_id': EVENT_ID, **changes})


def planned(**changes):
    record = store.create(**IDENTITY)
    record.update(analysis_mode='fault', symptom_source='trackunit_event', symptom='测试故障',
        fault_event_id=EVENT_ID, plan={'summary': '合成计划', 'directions': []},
        fault_context={'operator_supplement': '', 'trackunit_event': event()})
    record.update(changes)
    store._write(record)
    return record


def rejected(request, kind):
    with pytest.raises(automatic.AutoFaultError) as failure:
        automatic.plan(request, lambda: pytest.fail('Rejected request called the model'))
    assert failure.value.kind == kind


def test_concurrent_windows_claim_before_model_and_refresh_reuses_completed_record():
    started, finish = Event(), Event()
    calls = []
    def model():
        calls.append('plan')
        started.set()
        assert finish.wait(timeout=5)
        return planned()
    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(automatic.plan, body(), model)
        assert started.wait(timeout=5)
        other = pool.submit(rejected, body(), 'auto_fault_pending')
        other.result(timeout=5)
        assert calls == ['plan']
        finish.set()
        record = winner.result(timeout=5)
    again = automatic.plan(body(), lambda: pytest.fail('Refresh repeated model call'))
    assert again == record
    store.activate(record['research_id'], None)
    assert automatic.plan(body(), lambda: pytest.fail('Active refresh repeated model call')) == record
    assert len(list(store.STORE.glob('*.json'))) == 1


@pytest.mark.parametrize('failure', [RuntimeError('fixture failure'), KeyboardInterrupt()])
def test_failure_or_cancellation_is_terminal_for_automatic_retry(failure):
    def failing():
        raise failure
    with pytest.raises(type(failure)):
        automatic.plan(body(), failing)
    rejected(body(), 'auto_fault_failed')
    claim = json.loads(automatic._claim_path(automatic._scope(body())).read_text(encoding='utf-8'))
    assert claim['status'] == 'failed'


@pytest.mark.parametrize('claim', [None, '{', {'status': 'planning'}, {'status': 'failed'}])
def test_existing_interrupted_or_corrupt_claim_never_retries(claim):
    request = body()
    path = automatic._claim_path(automatic._scope(request))
    path.parent.mkdir(parents=True)
    if isinstance(claim, dict):
        claim = json.dumps({**claim, 'scope': automatic._scope(request)})
    path.write_text('' if claim is None else claim, encoding='utf-8')
    expected = 'auto_fault_pending' if 'planning' in (claim or '') else 'auto_fault_failed' if 'failed' in (claim or '') else 'auto_fault_corrupt'
    rejected(request, expected)


@pytest.mark.parametrize('changes', [
    {'status': 'unauthorized', 'http_status': 401}, {'status': 'partial'},
    {'coverage': 'partial_window'}, {'http_status': 401},
    {'checked_at': (NOW-timedelta(seconds=1801)).isoformat()},
    {'checked_at': (NOW+timedelta(seconds=1)).isoformat()},
    {'checked_at': 'unparseable'}, {'events': [event(status='CLOSED')]},
    {'events': [event(cleared_at=NOW.isoformat())]},
    {'events': [event(observed_at=(NOW-timedelta(seconds=1)).isoformat())]},
    {'events': [event(code=None, spn=100, fmi=None)]},
    {'events': [event(event_id='b'*64)]},
    {'events': [event(trackunit_asset_id='00000000-0000-0000-0000-000000000002')]},
    {'events': [event(), event(source_event_id='10000000-0000-0000-0000-000000000002',
         event_id=events.event_key(ASSET, '10000000-0000-0000-0000-000000000002'))]},
])
def test_only_current_complete_unique_open_official_event_is_eligible(changes):
    write_state(**changes)
    rejected(body(), 'auto_fault_ineligible')
    assert not (store.STORE / 'automatic-faults').exists()


@pytest.mark.parametrize('changes', [
    {'symptom': '人工补充'}, {'symptom_source': 'operator_report', 'symptom': '现场人工故障描述'},
    {'analysis_mode': 'maintenance', 'symptom_source': 'user_question'},
    {'fault_event_id': None, 'symptom_source': 'user_question', 'symptom': '问题'},
    {'source_report_id': 'f'*64},
    {'engineering_fault': {'model': 'XE55U', 'code': 'E4030', 'configuration': 'unknown', 'source': 'test'}},
])
def test_automatic_request_cannot_mix_manual_problem_or_old_context(changes):
    rejected(body(**changes), 'auto_fault_invalid')


@pytest.mark.parametrize('changes', [{'machine_id': 'another-machine'}, {'dataset_id': 'b'*64}, {'vin': 'XUGOTHER000000001'}])
def test_automatic_request_verifies_exact_registered_identity(changes):
    rejected(body(**changes), 'auto_fault_ineligible')


def test_other_active_research_blocks_new_claim_and_reuse():
    existing = planned(fault_event_id=None, symptom_source='user_question', symptom='人工问题')
    store.activate(existing['research_id'], None)
    rejected(body(), 'auto_fault_active')
    assert not automatic._claim_path(automatic._scope(body())).exists()
    # A completed automatic record must not displace a later manual investigation.
    completed = planned()
    store._write_json(automatic._claim_path(automatic._scope(body())),
        {'scope': automatic._scope(body()), 'status': 'completed', 'research_id': completed['research_id']})
    rejected(body(), 'auto_fault_active')
    assert store.active(**IDENTITY)['research_id'] == existing['research_id']


def test_concurrent_manual_activation_keeps_original_cas_protection():
    manual = planned(fault_event_id=None, symptom_source='user_question')
    def model():
        store.activate(manual['research_id'], None)
        return planned()
    automatic_record = automatic.plan(body(), model)
    with pytest.raises(store.ActiveResearchConflict):
        store.activate(automatic_record['research_id'], None)
    assert store.active(**IDENTITY)['research_id'] == manual['research_id']


@pytest.mark.parametrize('changes', [
    {'fault_event_id': 'b'*64}, {'dataset_id': 'b'*64}, {'plan': None},
    {'fault_context': {'operator_supplement': '后来补充的人工问题'}},
])
def test_completed_claim_with_mismatched_record_never_repeats_model(changes):
    record = automatic.plan(body(), planned)
    record.update(changes)
    store._write(record)
    rejected(body(), 'auto_fault_corrupt')


def test_j1939_with_complete_spn_fmi_can_start_automatically():
    write_state(events=[event(code=None, code_system='j1939', spn=2664, fmi=3)])
    assert automatic.plan(body(), planned)['fault_event_id'] == EVENT_ID


@pytest.fixture
def client(monkeypatch):
    machine = SimpleNamespace(model='XE55U', machine_type='excavator')
    monkeypatch.setattr(routes, '_verify_machine', lambda *args: None)
    monkeypatch.setattr(routes, 'load_dataset', lambda *args: SimpleNamespace(machine=machine, telemetry=[], faults=[]))
    monkeypatch.setattr(routes, 'find_machine', lambda *args: machine)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def last_event(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')][-1]


def test_route_returns_specific_auto_error_and_manual_request_still_works(client, monkeypatch):
    write_state(status='unauthorized', http_status=401)
    error = last_event(client.post('/assistant/xgss/research/plan', json=body().model_dump()))
    assert error['type'] == 'error' and error['kind'] == 'auto_fault_ineligible'
    calls = []
    def fake_plan(*args, **kwargs):
        calls.append(kwargs)
        return planned()
    monkeypatch.setattr(ai, 'plan', fake_plan)
    manual = body(automatic=False).model_dump()
    assert last_event(client.post('/assistant/xgss/research/plan', json=manual))['type'] == 'result'
    manual.pop('automatic')
    assert last_event(client.post('/assistant/xgss/research/plan', json=manual))['type'] == 'result'
    assert len(calls) == 2
    assert not (store.STORE / 'automatic-faults').exists()


def test_route_automatic_result_is_reused_after_failed_claim_manual_retry_remains_available(client, monkeypatch):
    calls = []
    monkeypatch.setattr(ai, 'plan', lambda *a, **k: (calls.append('plan'), planned())[1])
    first = last_event(client.post('/assistant/xgss/research/plan', json=body().model_dump()))
    second = last_event(client.post('/assistant/xgss/research/plan', json=body().model_dump()))
    assert first['type'] == second['type'] == 'result'
    assert first['record']['research_id'] == second['record']['research_id']
    assert calls == ['plan']
    store._write_json(automatic._claim_path(automatic._scope(body())),
        {'scope': automatic._scope(body()), 'status': 'failed'})
    error = last_event(client.post('/assistant/xgss/research/plan', json=body().model_dump()))
    assert error['kind'] == 'auto_fault_failed'
    assert last_event(client.post('/assistant/xgss/research/plan', json=body(automatic=False).model_dump()))['type'] == 'result'
    assert calls == ['plan', 'plan']


@pytest.mark.parametrize('invented', [False, True])
def test_route_reused_auto_plan_validates_cached_advice_against_sources(client, monkeypatch, invented):
    calls = []
    monkeypatch.setattr(ai, 'plan', lambda *a, **k: (calls.append('plan'), planned())[1])
    first = last_event(client.post('/assistant/xgss/research/plan', json=body().model_dump()))['record']
    current = store.append(first['research_id'], store.PageCapture(source='xgss_rendered_page',
        source_url='https://xgss.xcmg.com/', vin=IDENTITY['vin'], title='合成来源',
        items=[{'name': '线束', 'part_number': 'TEST-001'}], manual_sections=[], coverage='rendered_content_only'))
    reference = store.evidence(current)['parts'][0]['source_id']
    current.update(analysis_revision=current['revision'], advice={
        'summary': '线束为待检查候选，尚未确认损坏。',
        'parts': [{'source_id': reference, 'part_number': 'FAKE-999',
            'reason': '订购料号 FAKE-999。' if invented else '故障相关部件，待现场核实。',
            'replacement_condition': '检查确认损坏后再核对配置。'}],
        'repair_steps': [{'instruction': '停机后核对故障信息。', 'basis': 'ai_inspection_suggestion'}],
        'missing_evidence': ['现场检查结果'],
    })
    store._write(current)
    result = last_event(client.post('/assistant/xgss/research/plan', json=body().model_dump()))
    if invented:
        assert result['type'] == 'error' and result['kind'] == 'auto_fault_cached_advice_invalid'
    else:
        assert result['type'] == 'result'
        assert result['record']['advice']['parts'][0]['part_number'] == 'TEST-001'
    assert 'FAKE-999' not in json.dumps(result)
    assert calls == ['plan'], 'Cache validation cannot cause another billed model request'
    assert store.read(first['research_id'])['advice']['parts'][0]['part_number'] == 'FAKE-999'
