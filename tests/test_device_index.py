from datetime import timedelta

from scripts.prepare_parts_demo import build_demo
from app.device_index import summarize_faults, device_index
from app import device_index as module


def test_latest_status_supersedes_open_and_duplicates_are_not_failures():
    data = build_demo(); now = data.replay_at
    event = data.faults[0].model_copy(update={'occurred_at': (now-timedelta(minutes=2)).isoformat(), 'status': 'open'})
    fixed = event.model_copy(update={'occurred_at': now.isoformat(), 'status': 'resolved'})
    result = summarize_faults(data.machine.machine_id, [event, event, fixed], now)
    assert result['state'] == 'resolved_records' and result['unresolved_codes'] == 0
    assert result['highest_severity'] is None and result['valid_records'] == 3


def test_conflicts_are_explicit_and_do_not_choose_the_worst_as_truth():
    data = build_demo(); event = data.faults[0]
    other = event.model_copy(update={'status': 'resolved'})
    result = summarize_faults(data.machine.machine_id, [event, other], data.replay_at)
    assert result['state'] == 'conflicting' and result['conflicting_codes'] == 1
    assert result['highest_severity'] is None
    other = event.model_copy(update={'severity': 'critical' if event.severity != 'critical' else 'low'})
    assert summarize_faults(data.machine.machine_id, [event, other], data.replay_at)['conflicting_codes'] == 1


def test_summary_excludes_invalid_future_and_other_device_and_keeps_all_codes():
    data = build_demo(); event = data.faults[0]; now = data.replay_at
    rows = [event.model_copy(update={'machine_id': 'OTHER'}),
            event.model_copy(update={'occurred_at': 'invalid'}),
            event.model_copy(update={'occurred_at': (now+timedelta(seconds=1)).isoformat()})]
    result = summarize_faults(data.machine.machine_id, rows, now)
    assert result['state'] == 'no_records'
    assert result['excluded_records'] == {'other_machine': 1, 'invalid_timestamp': 1, 'after_cutoff': 1}
    rows = [event.model_copy(update={'fault_code': str(i), 'status': 'open', 'severity': 'high'}) for i in range(30)]
    result = summarize_faults(data.machine.machine_id, rows, now)
    assert result['unresolved_codes'] == 30 and result['highest_severity'] == 'high'


def test_index_loads_fleet_once_and_keeps_dataset_versions_and_partial_errors(monkeypatch, tmp_path):
    data = build_demo(); calls = []
    monkeypatch.setattr(module.data_store, 'get_data_source', lambda: 'mock')
    monkeypatch.setattr(module.data_store, 'load_machines', lambda: calls.append('machines') or [data.machine])
    monkeypatch.setattr(module.data_store, 'load_faults', lambda: calls.append('faults') or [])
    monkeypatch.setattr(module.local_datasets, 'DATASETS', tmp_path)
    for prefix in ('a', 'b', 'c'):
        (tmp_path / (prefix*64+'.json')).write_text(data.model_dump_json() if prefix != 'c' else '{}')
    result = device_index()
    assert calls == ['machines', 'faults']
    assert len(result['devices']) == 3 and len({d['selection_id'] for d in result['devices']}) == 3
    assert result['devices'][0]['fault_summary']['state'] == 'no_records'
    assert result['devices'][1]['fault_summary']['as_of'] == data.replay_at.isoformat()
    assert result['warnings'] == ['1 份导入数据无法读取，未列入结果；请核对导入文件。']
    assert result['ai_used'] is False and result['upstream_sync_performed'] is False


def test_unreadable_fault_cache_is_not_empty_or_fatal(monkeypatch, tmp_path):
    data = build_demo()
    monkeypatch.setattr(module.data_store, 'load_machines', lambda: [data.machine])
    def broken(): raise ValueError('private path')
    monkeypatch.setattr(module.data_store, 'load_faults', broken)
    monkeypatch.setattr(module.local_datasets, 'DATASETS', tmp_path)
    result = device_index()
    assert result['devices'][0]['fault_summary']['state'] == 'unavailable'
    assert 'private path' not in str(result)


def test_index_route_no_store_and_no_network(monkeypatch, tmp_path):
    import socket
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(module.local_datasets, 'DATASETS', tmp_path)
    def forbidden(*args, **kwargs): raise AssertionError('Unexpected external lookup')
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    response = TestClient(app).get('/assistant/device-index')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.json()['upstream_sync_performed'] is False
