from concurrent.futures import ThreadPoolExecutor
import sqlite3
import socket

import pytest
from fastapi.testclient import TestClient
from app import maintenance_cases as cases
from app.main import app


@pytest.fixture
def client(monkeypatch):
    def device(machine, source='mock', dataset=None):
        return {'machine_id': machine, 'serial_number': machine, 'model': 'SIM-EXC',
                'source': source, 'dataset_id': dataset,
                'selection_id': 'dataset:'+dataset if dataset else 'fleet:'+machine,
                'fault_summary': {'state': 'unresolved', 'unresolved_codes': 1}}
    index = {'devices': [device('SIM-A'), device('SIM-B'),
             device('SIM-A', 'imported_synthetic', 'a'*64),
             device('SIM-A', 'imported_synthetic', 'b'*64)]}
    monkeypatch.setattr(cases, 'device_index', lambda: index)
    def forbidden(*args, **kwargs):
        pytest.fail('Case tracking must not call an external service')
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    return TestClient(app)


def create(client, **extra):
    return client.post('/assistant/cases', json={'machine_id': 'SIM-A', 'source': 'mock',
        'title': '模拟增压信号排查', 'note': '原始观察，尚未检查。', **extra})


def update(client, case, state='in_progress', note='已查看接头，尚未测量压力。', **extra):
    return client.post(f'/assistant/cases/{case["case_id"]}/events', json={
        'expected_revision': case['revision'], 'state': state, 'note': note, **extra})


def test_lifecycle_history_export_and_reopen_without_ai(client):
    created = create(client)
    assert created.status_code == 200 and created.json()['created']
    initial = created.json()['case']
    case = initial
    for state in ('in_progress', 'waiting', 'archived'):
        response = update(client, case, state=state, note='  现场原文\n等待进一步验证。  ')
        assert response.status_code == 200
        case = response.json()['case']
    assert case['revision'] == 4 and case['source_kind'] == 'unverified_operator_case'
    assert case['events'][0] == initial['events'][0]
    assert case['events'][-1]['note'] == '  现场原文\n等待进一步验证。  '
    assert client.get('/assistant/cases').json()['total'] == 0
    assert client.get('/assistant/cases?state=archived').json()['total'] == 1
    assert client.get('/assistant/cases/current', params={'machine_id': 'SIM-A', 'source': 'mock'}).json()['case'] is None
    exported = client.get(f'/assistant/cases/{case["case_id"]}/export.md')
    assert exported.status_code == 200 and exported.headers['content-disposition'].startswith('attachment;')
    assert '  现场原文\n等待进一步验证。  ' in exported.text
    assert '不代表设备已修复' in exported.text and '已归档' in exported.text
    assert update(client, case, note='新线索，重新排查。').json()['case']['state'] == 'in_progress'
    assert client.get('/assistant/cases').json()['total'] == 1


def test_scope_and_duplicate_creation_preserve_existing_content(client):
    one = create(client).json()['case']
    duplicate = create(client, title='不得覆盖现有标题', note='不得悄悄追加').json()
    assert duplicate['created'] is False and duplicate['case'] == one
    a = create(client, dataset_id='a'*64, source='imported_synthetic').json()['case']
    b = create(client, dataset_id='b'*64, source='imported_synthetic').json()['case']
    assert len({one['case_id'], a['case_id'], b['case_id']}) == 3
    assert create(client, machine_id='SIM-B', dataset_id='a'*64, source='imported_synthetic').status_code == 404
    assert create(client, source='trackunit_cache').status_code == 404
    assert client.get('/assistant/cases/current', params={'machine_id':'SIM-A','source':'imported_synthetic','dataset_id':'a'*64}).json()['case'] == a


def test_concurrent_updates_are_atomic_and_stale_note_is_not_written(client):
    first = create(client).json()['case']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda note: update(client, first, note=note), ['first', 'second']))
    assert sorted(r.status_code for r in results) == [200, 409]
    saved = client.get('/assistant/cases/'+first['case_id']).json()['case']
    assert saved['revision'] == 2 and len(saved['events']) == 2
    assert update(client, first, note='stale').status_code == 409
    assert client.get('/assistant/cases/'+first['case_id']).json()['case'] == saved


def test_concurrent_creation_returns_one_task(client):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(client), range(2)))
    assert all(r.status_code == 200 for r in results)
    assert len({r.json()['case']['case_id'] for r in results}) == 1
    assert sorted(r.json()['created'] for r in results) == [False, True]


def test_archived_task_cannot_reopen_over_another_active_task(client):
    first = create(client).json()['case']
    archived = update(client, first, 'archived', '本次结束，原因尚未确定。').json()['case']
    new = create(client).json()['case']
    assert new['case_id'] != first['case_id']
    assert update(client, archived, 'in_progress', '重开').status_code == 409
    assert client.get('/assistant/cases/current', params={'machine_id':'SIM-A','source':'mock'}).json()['case']['case_id'] == new['case_id']


def test_report_link_requires_same_device_source_and_version(client, monkeypatch):
    first = create(client).json()['case']
    report = {'report':{'machine_id':'SIM-B','source':'mock'},'request':{'dataset_id':None}}
    monkeypatch.setattr(cases, 'read_investigation', lambda _: report)
    assert update(client, first, report_id='f'*64).status_code == 404
    report['report']['machine_id'] = 'SIM-A'
    report['request']['dataset_id'] = 'a'*64
    assert update(client, first, report_id='f'*64).status_code == 404
    report['request']['dataset_id'] = None
    result = update(client, first, report_id='f'*64)
    assert result.status_code == 200
    assert result.json()['case']['events'][-1]['report_id'] == 'f'*64


def test_scope_disappears_but_saved_task_remains_readable(client, monkeypatch):
    first = create(client).json()['case']
    monkeypatch.setattr(cases, 'device_index', lambda:{'devices':[]})
    assert client.get('/assistant/cases/current', params={'machine_id':'SIM-A','source':'mock'}).status_code == 404
    assert client.get('/assistant/cases/'+first['case_id']).json()['case'] == first
    assert update(client, first, 'waiting', '设备资料暂不可用。').status_code == 200


def test_manual_fault_and_checks_persist_when_ai_reports_are_unavailable(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError('AI report service unavailable')
    monkeypatch.setattr(cases, 'read_investigation', unavailable)
    initial_note = '机手报告 H10101，低速动作异常；代码及现象未经现场核实。'
    response = create(client, title='TV12U 人工故障排查', note=initial_note)
    assert response.status_code == 200 and response.json()['ai_used'] is False
    initial = response.json()['case']
    check_note = '已检查接头，无松脱；尚未测量线圈电阻。AI 暂不可用，继续保留记录。'
    saved = update(client, initial, state='waiting', note=check_note)
    assert saved.status_code == 200 and saved.json()['ai_used'] is False
    case = client.get('/assistant/cases/'+initial['case_id']).json()['case']
    assert [event['note'] for event in case['events']] == [initial_note, check_note]
    assert all(event['report_id'] is None for event in case['events'])
    exported = client.get(f'/assistant/cases/{initial["case_id"]}/export.md')
    assert exported.status_code == 200
    assert initial_note in exported.text and check_note in exported.text


def test_pagination_filters_and_invalid_inputs(client):
    create(client)
    create(client, machine_id='SIM-B')
    assert client.get('/assistant/cases?limit=1').json()['total'] == 2
    assert len(client.get('/assistant/cases?limit=1&offset=1').json()['cases']) == 1
    assert client.get('/assistant/cases?machine_id=SIM-B').json()['total'] == 1
    assert client.get('/assistant/cases?real_only=true').json()['total'] == 0
    first = client.get('/assistant/cases').json()['cases'][0]
    assert update(client, first, 'archived', '   ').status_code == 422
    assert update(client, first, 'unknown').status_code == 422
    assert create(client, title='  ').status_code == 422
    assert client.get('/assistant/cases?limit=101').status_code == 422
    assert client.get('/assistant/cases/not-a-case').status_code == 404


def test_incomplete_history_and_storage_error_are_explicit(client, monkeypatch, tmp_path):
    first = create(client).json()['case']
    with sqlite3.connect(cases.CASE_DB) as db:
        db.execute('DELETE FROM case_events')
    result = client.get('/assistant/cases/'+first['case_id'])
    assert result.status_code == 503 and 'no-store' in result.headers['cache-control']
    monkeypatch.setattr(cases, 'CASE_DB', tmp_path)
    assert client.get('/assistant/cases').status_code == 503
