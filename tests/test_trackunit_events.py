"""Official-schema-shaped synthetic fixtures; never authenticate or call a model."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import trackunit_events as events
from app import xgss_research_handoff as handoff, xgss_research_ai as ai, xgss_research_store as store
from app.api import routes_fault_events as routes, routes_xgss_research as research_routes

NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
ASSET = '00000000-0000-0000-0000-000000000001'
OTHER = '00000000-0000-0000-0000-000000000002'
SOURCE = '10000000-0000-0000-0000-000000000001'
IDENTITY = {'machine_id': ASSET, 'trackunit_asset_id': ASSET, 'dataset_id': 'a'*64,
            'vin': 'XUGTEST000000001', 'model': 'XE55U'}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(events, 'STORE', tmp_path/'events')
    monkeypatch.setattr(store, 'STORE', tmp_path/'research')
    monkeypatch.setattr(events, 'utcnow', lambda: NOW)
    monkeypatch.setattr(events.TrackunitClient, 'get_token', lambda *a, **k: pytest.fail('Unexpected authentication'))
    monkeypatch.setattr(ai, 'generate_structured_with_deepseek', lambda *a, **k: pytest.fail('Unexpected model call'))
    machine = SimpleNamespace(machine_id=ASSET, trackunit_asset_id=ASSET,
                              serial_number=IDENTITY['vin'], model='XE55U')
    dataset = SimpleNamespace(machine=machine, provenance='user_supplied', telemetry=[], faults=[])
    def loaded(dataset_id):
        if dataset_id != 'a'*64:
            raise ValueError('fixture dataset missing')
        return dataset
    monkeypatch.setattr(events, 'load_dataset', loaded)
    monkeypatch.setattr(events, 'list_datasets', lambda: [{'dataset_id': 'a'*64, 'provenance': dataset.provenance,
                                                          'machine': {'machine_id': ASSET}}])
    monkeypatch.setattr(events, 'get_data_source', lambda: 'demo')
    return dataset


def raw(**changes):
    row = {'id': SOURCE, 'assetId': ASSET, 'type': 'MACHINE_FAULT', 'status': 'OPEN',
           'eventTime': '2026-09-22T10:01:00Z', 'timeOn': '2026-09-22T10:00:00Z', 'timeOff': None,
           'criticality': 'CRITICAL', 'assetEventDomainDetails': {'eventTypeName': 'AssetEventMachineFaultDetails',
               'faultCode': 'E4030', 'description': '测试夹具中的故障描述', 'j1939': None}}
    row.update(changes)
    return row


def page(rows, number=0, total_pages=1, total=None):
    return {'content': rows, 'number': number, 'size': 1000, 'numberOfElements': len(rows),
            'totalPages': total_pages, 'totalElements': len(rows) if total is None else total}


class FakeClient:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def request(self, method, endpoint, **kwargs):
        self.calls.append((method, endpoint, kwargs))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_official_post_query_normalizes_allowlisted_fields_and_event_lifecycle():
    row = raw(status='RESOLVED', timeOff='2026-09-22T10:30:00Z', secret='DO_NOT_KEEP')
    fake = FakeClient(page([row]))
    state = events.refresh(IDENTITY, client=fake, now=NOW)
    assert state['status'] == 'data' and state['coverage'] == 'queried_window'
    event = state['events'][0]
    assert event['source_event_id'] == SOURCE and event['code'] == 'E4030'
    assert event['status'] == 'RESOLVED' and event['cleared_at'] == '2026-09-22T10:30:00+00:00'
    assert event['occurred_at'] == '2026-09-22T10:00:00+00:00'
    assert 'DO_NOT_KEEP' not in json.dumps(state)
    method, endpoint, kwargs = fake.calls[0]
    assert method == 'POST' and endpoint == events.ENDPOINT and kwargs['follow_redirects'] is False
    assert kwargs['json'] == {'assetIds': [ASSET], 'type': ['MACHINE_FAULT'],
                             'fromTime': (NOW-timedelta(days=7)).isoformat(), 'toTime': NOW.isoformat()}
    assert kwargs['params'] == {'page': 0, 'size': 1000}
    assert events.read_state(IDENTITY)['events'] == [event]


def test_j1939_is_preserved_without_inventing_an_oem_code():
    data = raw(assetEventDomainDetails={'eventTypeName': 'AssetEventMachineFaultDetails',
               'j1939': {'spn': 2664, 'fmi': 3, 'sa': 0}, 'description': 'fixture'})
    state = events.refresh(IDENTITY, client=FakeClient(page([data])), now=NOW)
    event = state['events'][0]
    assert (event['code'], event['code_system'], event['spn'], event['fmi'], event['sa']) == (None, 'j1939', 2664, 3, 0)


@pytest.mark.parametrize('status, expected', [(401, 'unauthorized'), (403, 'forbidden'), (429, 'rate_limited'), (500, 'unavailable')])
def test_failure_is_not_empty_and_keeps_existing_events(status, expected):
    first = events.refresh(IDENTITY, client=FakeClient(page([raw()])), now=NOW)
    fake = FakeClient(events.TrackunitError('PRIVATE_PROVIDER_TEXT', status))
    failed = events.refresh(IDENTITY, client=fake, now=NOW+timedelta(seconds=1))
    assert failed['status'] == expected and failed['http_status'] == status
    assert failed['coverage'] == 'unknown' and failed['events'] == first['events']
    assert len(fake.calls) == 1 and len(events._ledger()) == 2
    assert 'PRIVATE_PROVIDER_TEXT' not in json.dumps(failed)


def test_empty_window_does_not_delete_history_or_claim_no_fault():
    first = events.refresh(IDENTITY, client=FakeClient(page([raw()])), now=NOW)
    empty = events.refresh(IDENTITY, client=FakeClient(page([], total_pages=0)), now=NOW+timedelta(seconds=1))
    assert empty['status'] == 'empty' and empty['coverage'] == 'queried_window'
    assert empty['events'] == first['events'] and '不能据此' in empty['message']


def test_global_failed_request_quota_applies_across_devices_and_recovers():
    fake = FakeClient(events.TrackunitError('blocked', 401), events.TrackunitError('blocked', 401))
    events.refresh(IDENTITY, client=fake, now=NOW)
    other = {**IDENTITY, 'machine_id': OTHER, 'trackunit_asset_id': OTHER, 'vin': 'XUGTEST000000002'}
    events.refresh(other, client=fake, now=NOW+timedelta(seconds=1))
    blocked = events.refresh(IDENTITY, client=fake, now=NOW+timedelta(seconds=2))
    assert blocked['status'] == 'rate_limited' and len(fake.calls) == 2
    assert blocked['retry_after'] == (NOW+timedelta(seconds=1800)).isoformat()
    later = FakeClient(page([], total_pages=0))
    assert events.refresh(IDENTITY, client=later, now=NOW+timedelta(seconds=1800))['status'] == 'empty'


def test_pagination_uses_global_quota_and_marks_partial_instead_of_finishing():
    events.refresh(IDENTITY, client=FakeClient(events.TrackunitError('blocked', 401)), now=NOW)
    fake = FakeClient(page([raw()], total_pages=3, total=2001))
    result = events.refresh(IDENTITY, client=fake, now=NOW+timedelta(seconds=1))
    assert len(fake.calls) == 1 and result['pages_read'] == 1
    assert result['status'] == 'partial' and result['coverage'] == 'partial_window'
    assert len(result['events']) == 1 and result['retry_after']


def test_pagination_never_requests_a_third_page_and_incomplete_count_is_visible():
    second = raw(id='10000000-0000-0000-0000-000000000002')
    fake = FakeClient(page([raw()], total_pages=3, total=2001),
                      page([second], number=1, total_pages=3, total=2001))
    result = events.refresh(IDENTITY, client=fake, now=NOW)
    assert len(fake.calls) == 2 and result['pages_read'] == 2
    assert result['status'] == 'partial' and len(result['events']) == 2
    assert [call[2]['params']['page'] for call in fake.calls] == [0, 1]


def test_duplicates_deduplicate_and_newer_status_replaces_same_source_event():
    fake = FakeClient(page([raw(), raw()]))
    first = events.refresh(IDENTITY, client=fake, now=NOW)
    assert len(first['events']) == 1
    closed = raw(status='CLOSED', timeOff='2026-09-22T11:00:00Z')
    second = events.refresh(IDENTITY, client=FakeClient(page([closed])), now=NOW+timedelta(seconds=1))
    assert len(second['events']) == 1 and second['events'][0]['status'] == 'CLOSED'
    assert second['events'][0]['event_id'] == first['events'][0]['event_id']


@pytest.mark.parametrize('bad', [page([raw(assetId=OTHER)]), page([raw(type='ALERT')]),
    page([raw(timeOff='2026-09-20T00:00:00Z')]), {'content': []},
    page([raw(assetEventDomainDetails={'j1939': {'spn': 12, 'fmi': 99}})])])
def test_invalid_or_cross_device_response_is_not_saved_as_success(bad):
    result = events.refresh(IDENTITY, client=FakeClient(bad), now=NOW)
    assert result['status'] == 'schema_error' and result['coverage'] == 'unknown' and result['events'] == []


def test_probe_import_requires_actual_uuid_and_is_idempotent():
    summary = {'model': 'XE55U', 'checked_at': NOW.isoformat(), 'window_start': (NOW-timedelta(days=7)).isoformat(),
               'window_end': NOW.isoformat(), 'data_requests': [{'name': 'machine_fault_events', 'method': 'POST', 'http_status': 401}]}
    with pytest.raises(ValueError):
        events.import_probe(IDENTITY, summary, verified_asset_id=OTHER)
    for _ in range(2):
        imported = events.import_probe(IDENTITY, summary, verified_asset_id=ASSET)
    assert imported['status'] == 'unauthorized' and imported['events'] == []
    assert len(events._ledger()) == 1


def test_unexpected_failure_releases_os_lock_and_existing_lock_file_is_reusable():
    fake = FakeClient(RuntimeError('simulated process work failure'))
    with pytest.raises(RuntimeError):
        events.refresh(IDENTITY, client=fake, now=NOW)
    assert (events.STORE/'refresh.lock').exists()
    # A retained lock file is harmless: ownership is kernel-managed, not existence.
    result = events.refresh(IDENTITY, client=FakeClient(page([], total_pages=0)), now=NOW+timedelta(seconds=1))
    assert result['status'] == 'empty'


def test_registration_rejects_synthetic_wrong_vin_and_unknown_uuid(isolated):
    assert events.registered_machine(ASSET)['trackunit_asset_id'] == ASSET
    with pytest.raises(ValueError):
        events.registered_machine(OTHER)
    with pytest.raises(ValueError):
        events.registered_machine(ASSET, 'a'*64, 'XUGTEST000000009')
    isolated.provenance = 'synthetic'
    with pytest.raises(ValueError):
        events.registered_machine(ASSET, 'a'*64, IDENTITY['vin'])


def test_get_is_local_and_refresh_is_explicit_and_device_validated(monkeypatch):
    app = FastAPI(); app.include_router(routes.router)
    client = TestClient(app)
    calls = []
    monkeypatch.setattr(events, 'refresh', lambda identity: calls.append(identity) or events.read_state(identity))
    response = client.get('/assistant/fault-events', params={'machine_id': ASSET})
    assert response.status_code == 200 and response.json()['status'] == 'not_checked' and calls == []
    assert response.headers['cache-control'] == 'no-store'
    body = {key: IDENTITY[key] for key in ('machine_id', 'dataset_id', 'vin')}
    assert client.post('/assistant/fault-events/refresh', json={**body, 'vin': 'XUGTEST000000009'}).status_code == 422
    assert calls == []
    assert client.post('/assistant/fault-events/refresh', json=body).status_code == 200 and len(calls) == 1


def test_research_reloads_event_and_preserves_frozen_context_through_both_model_passes(monkeypatch):
    event = events.refresh(IDENTITY, client=FakeClient(page([raw()])), now=NOW)['events'][0]
    body = research_routes.PlanRequest(**{key: IDENTITY[key] for key in ('machine_id', 'dataset_id', 'vin')},
        fault_event_id=event['event_id'], symptom_source='trackunit_event', symptom='驾驶员额外报告间歇异常。')
    continuation = handoff.plan_context(body, 'XE55U')
    assert continuation['catalog_fault_code'] == 'E4030'
    assert continuation['fault_context']['operator_supplement'] == body.symptom
    assert body.symptom not in continuation['symptom']
    sent = []
    plan = {'summary': '先核对连接器与电源线路。', 'directions': [{'component': '连接器', 'reason': '需要检查连接状态。',
            'search_terms': ['连接器']}], 'missing_evidence': ['实际检查结果']}
    def model(messages, schema, **kwargs):
        sent.append(json.loads(messages[1]['content']))
        if len(sent) == 1:
            return json.dumps(plan, ensure_ascii=False)
        return json.dumps({'summary': 'E4030 需要核对连接状态。', 'parts': [],
            'repair_steps': [{'instruction': '请由服务人员核对适用资料。', 'basis': 'ai_inspection_suggestion'}],
            'missing_evidence': ['现场检查结果']}, ensure_ascii=False)
    monkeypatch.setattr(ai, 'generate_structured_with_deepseek', model)
    symptom = ai.Symptom(**{key: continuation[key] for key in ('symptom', 'symptom_source')})
    record = ai.plan(ASSET, 'a'*64, IDENTITY['vin'], 'XE55U', symptom,
                     **{key: value for key, value in continuation.items() if key not in ('symptom', 'symptom_source')})
    events.refresh(IDENTITY, client=FakeClient(page([raw(status='RESOLVED', timeOff='2026-09-22T11:00:00Z')])), now=NOW+timedelta(seconds=1))
    store.append(record['research_id'], store.PageCapture(source='xgss_rendered_page', source_url='https://xgss.xcmg.com/',
        vin=IDENTITY['vin'], title='测试图册', items=[{'name': '连接器', 'part_number': 'FIXTURE-001'}], coverage='rendered_content_only'))
    result = ai.analyze(record['research_id'])
    assert result['fault_context']['trackunit_event']['status'] == 'OPEN'
    assert result['fault_event_id'] == event['event_id']
    assert sent[0]['fault_context'] == sent[1]['fault_context']
    assert IDENTITY['vin'] not in json.dumps(sent) and ASSET not in json.dumps(sent)
    assert SOURCE not in json.dumps(sent) and event['event_id'] not in json.dumps(sent)
    for key in ('source_event_id','event_id','trackunit_asset_id','machine_id','vin'):
        assert key not in sent[0]['fault_context']['trackunit_event']
    assert result['advice']['parts'] == []


def test_spn_only_research_uses_generic_catalog_and_missing_or_cross_machine_id_is_rejected():
    row = raw(assetEventDomainDetails={'j1939': {'spn': 2664, 'fmi': 3}, 'description': 'fixture'})
    event = events.refresh(IDENTITY, client=FakeClient(page([row])), now=NOW)['events'][0]
    body = research_routes.PlanRequest(**{key: IDENTITY[key] for key in ('machine_id', 'dataset_id', 'vin')},
        fault_event_id=event['event_id'], symptom_source='trackunit_event')
    context = handoff.plan_context(body, 'XE55U')
    assert context['catalog_fault_code'] is None and 'SPN 2664 / FMI 3' in context['symptom']
    draft=ai.Advice(summary='该 SPN/FMI 需按适用 ECU 资料核实。',parts=[],
        repair_steps=[{'instruction':'核对适用资料。','basis':'ai_inspection_suggestion'}],missing_evidence=[])
    assert ai.validate_advice(draft,[],[],symptom=context['symptom'],fault_context=context['fault_context'])['parts']==[]
    for changed in ({'fault_event_id': 'f'*64}, {'machine_id': OTHER}, {'fault_event_id': None}):
        with pytest.raises(ValueError):
            handoff.plan_context(body.model_copy(update=changed), 'XE55U')
