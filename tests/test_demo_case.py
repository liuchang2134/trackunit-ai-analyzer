import copy
import json
import socket
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import demo_case
from app.api.routes_demo import router


@pytest.fixture
def client():
    application = FastAPI()
    application.include_router(router)
    return TestClient(application)


def test_demo_is_standalone_offline_and_read_only(client, monkeypatch, tmp_path):
    source = demo_case.DEMO_PATH
    before = source.read_bytes()
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: pytest.fail('Demo attempted a network connection'))
    monkeypatch.setenv('TV12U_FAULT_REFERENCE_PATH', str(tmp_path / 'not-installed.json'))
    response = client.get('/assistant/demo-case')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    result = response.json()
    assert result['is_simulation'] is True and result['source']['external_calls'] is False
    assert result['machine']['machine_id'].startswith('SIM-') and result['machine']['vin'] is None
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == []
    assert 'source_path' not in response.text
    assert client.post('/assistant/demo-case', json={}).status_code == 405


def test_case_has_traceable_five_stages_and_no_pretend_part_numbers():
    result = demo_case.load_demo()
    assert [stage['id'] for stage in result['stages']] == demo_case.STAGES
    definition = next(item for item in result['evidence'] if item['id'] == 'protocol-h10101')
    assert '左泵前进比例阀短路' in definition['text'] and '第 66 行' in definition['source_note']
    assert '未调用 Gemini' in result['stages'][2]['summary']
    assert all(part['part_number'] is None and part['stock'] is None for part in result['parts'])
    assert all('模拟' in check['action'] or '演示' in check['action'] for check in result['checks'])
    assert '未经验证' in result['conclusion']['status']


def test_telemetry_depicts_stop_inspection_and_retest_not_training_data():
    points = demo_case.load_demo()['telemetry']['points']
    assert points[2]['fault_code'] == 'H10101' and points[2]['left_travel_response_percent'] == 0
    assert any(point['engine_rpm'] == 0 for point in points)
    assert points[-1]['fault_code'] is None
    assert points[-1]['left_travel_command_percent'] == points[-1]['left_travel_response_percent'] > 0


@pytest.mark.parametrize('change', [
    lambda d: d.update(is_simulation=False),
    lambda d: d['source'].update(external_calls=True),
    lambda d: d['machine'].update(vin='PRETEND_REAL_VIN'),
    lambda d: d['parts'][0].update(part_number='PRETEND_PART'),
    lambda d: d['stages'][1].update(evidence_ids=['unknown']),
    lambda d: d['telemetry']['points'][4].update(left_travel_command_percent=20),
    lambda d: d['telemetry']['points'][2].update(minute=1),
    lambda d: d['telemetry']['points'][2].update(engine_rpm=float('nan')),
    lambda d: d['stages'][2].update(details='missing list'),
    lambda d: d['checks'][1].update(simulated_result=''),
])
def test_corrupt_demo_does_not_look_like_verified_case(change):
    data = copy.deepcopy(demo_case.load_demo())
    change(data)
    with pytest.raises(demo_case.DemoUnavailable):
        demo_case.validate_demo(data)


def test_missing_corrupt_or_mislabeled_data_returns_path_free_503(client, monkeypatch, tmp_path):
    path = tmp_path / 'private-example.json'
    monkeypatch.setattr(demo_case, 'DEMO_PATH', path)
    assert client.get('/assistant/demo-case').status_code == 503
    for value in ('{bad JSON', json.dumps({'is_simulation': False})):
        path.write_text(value, encoding='utf-8')
        response = client.get('/assistant/demo-case')
        assert response.status_code == 503 and str(path) not in response.text


def test_markdown_download_is_utf8_complete_and_deterministic(client):
    case = client.get('/assistant/demo-case').json()
    response = client.get('/assistant/demo-case/report.md')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'text/markdown; charset=utf-8'
    assert response.headers['content-disposition'] == 'attachment; filename="tv12u-h10101-simulated-case.md"'
    assert response.headers['cache-control'] == 'no-store'
    report = response.content.decode('utf-8')
    assert case['disclaimer'] in report and case['source']['label'] in report
    assert 'SIM-TV12U-DEMO-001' in report and '未调用 Gemini' in report
    assert '压缩演示时间，不能当作实际维修工时' in report
    for stage in case['stages']:
        assert stage['title'] in report and stage['summary'] in report
        assert all(detail in report for detail in stage['details'])
    for check in case['checks']:
        assert check['action'] in report and check['simulated_result'] in report
    for part in case['parts']:
        assert part['name'] in report and part['status'] in report
    assert report.count('- 料号：未提供') == len(case['parts'])
    assert report.count('- 库存：未提供') == len(case['parts'])
    for evidence in case['evidence']:
        assert evidence['id'] in report and evidence['source_note'] in report
    assert all(item in report for item in case['conclusion']['limitations'])
    assert client.get('/assistant/demo-case/report.md').content == response.content


def test_report_export_never_writes_records_or_uses_external_services(client, monkeypatch):
    original_open = Path.open
    def read_only_open(path, mode='r', *args, **kwargs):
        assert not set(mode).intersection('wax+'), 'Report export attempted a file write'
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', read_only_open)
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: pytest.fail('Report attempted network I/O'))
    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **kw: pytest.fail('Report attempted database access'))
    assert client.get('/assistant/demo-case/report.md').status_code == 200
    assert client.post('/assistant/demo-case/report.md', json={}).status_code == 405


def test_report_uses_validated_case_and_does_not_mutate_it(client, monkeypatch, tmp_path):
    case = demo_case.load_demo()
    before = copy.deepcopy(case)
    demo_case.render_demo_report(case)
    assert case == before
    case['is_simulation'] = False
    with pytest.raises(demo_case.DemoUnavailable):
        demo_case.render_demo_report(case)
    path = tmp_path / 'private-case.json'
    monkeypatch.setattr(demo_case, 'DEMO_PATH', path)
    for content in (None, '{broken json', json.dumps(case)):
        if content is not None:
            path.write_text(content, encoding='utf-8')
        response = client.get('/assistant/demo-case/report.md')
        assert response.status_code == 503 and response.headers['cache-control'] == 'no-store'
        assert 'content-disposition' not in response.headers
        assert str(path) not in response.text
