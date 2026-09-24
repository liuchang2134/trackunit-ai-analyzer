import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app import can_replay, can_demo_ai
from app.api.routes_can_replay import router


def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize('payload', [
    {'scenario': 'recorded', 'at': 390},
    {'scenario': 'synthetic', 'at': 390, 'vin': 'PRIVATE'},
    {'scenario': 'synthetic', 'at': 390, 'telemetry': [100]},
    {'scenario': 'synthetic', 'at': 481},
    {'scenario': 'synthetic', 'at': -1},
    {'scenario': 'synthetic', 'at': '390'},
])
def test_analysis_cannot_accept_real_context_or_invalid_cursor(payload):
    with pytest.raises(ValidationError):
        can_demo_ai.SyntheticAnalysisRequest.model_validate(payload)
    assert client().post('/assistant/can-replay/synthetic-analysis', json=payload).status_code == 422


def test_simulation_never_loads_capture(monkeypatch):
    def forbidden():
        raise AssertionError('Real capture must not enter synthetic AI')
    monkeypatch.setattr(can_replay, 'recorded_replay', forbidden)
    data = can_replay.synthetic_replay()
    assert data['source_kind'] == 'synthetic'
    assert data['vin'] is None
    assert all(p['raw'] is None and p['line'] is None for s in data['signals'] for p in s['points'])
    evidence = can_replay.synthetic_evidence(390)
    assert all(row['start_s'] == 270 and row['end_s'] == 390 for row in evidence['evidence'])
    assert evidence['evidence'][0]['last'] == 105
    assert all(row['end_s'] == 0 and row['samples'] == 1 for row in can_replay.synthetic_evidence(0)['evidence'])


def answer(ref='S1'):
    return json.dumps({'summary': '模拟温升需核查', 'hypotheses': [{'component': '散热系统',
        'reasoning': '温度上升，不能确诊。', 'evidence_ids': [ref], 'inspection': '冷却后检查外观。',
        'search_terms': ['散热器']}], 'missing_evidence': ['风扇状态']})


def test_cloud_boundary_contains_only_generated_values(monkeypatch):
    sent = []
    def model(messages, schema, timeout_seconds):
        sent.extend(messages)
        return answer()
    monkeypatch.setattr(can_demo_ai, 'generate_structured_with_deepseek', model)
    request = can_demo_ai.SyntheticAnalysisRequest(scenario='synthetic', at=390)
    result = can_demo_ai.analyze_synthetic(request)
    wire = json.loads(sent[-1]['content'])
    assert wire == can_replay.synthetic_evidence(390)
    assert result['source_kind'] == 'synthetic'
    assert 'XC948U' not in json.dumps(sent)
    assert result['catalog_status'] == 'awaiting_same_vin_verification'


def test_invented_citations_rejected(monkeypatch):
    monkeypatch.setattr(can_demo_ai, 'generate_structured_with_deepseek', lambda *a, **kw: answer('S999'))
    with pytest.raises(ValueError):
        can_demo_ai.analyze_synthetic(can_demo_ai.SyntheticAnalysisRequest(scenario='synthetic', at=390))


def test_stream_delivers_validated_model_response(monkeypatch):
    monkeypatch.setattr(can_demo_ai, 'generate_structured_with_deepseek', lambda *a, **kw: answer())
    response = client().post('/assistant/can-replay/synthetic-analysis', json={'scenario': 'synthetic', 'at': 390})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[0]['stage'] == 'model_decision'
    assert events[-1]['type'] == 'result'
    assert events[-1]['report']['input']['at'] == 390


def test_no_local_capture_has_actionable_fallback(monkeypatch):
    from app.api import routes_can_replay
    def missing():
        raise FileNotFoundError()
    monkeypatch.setattr(routes_can_replay, 'recorded_replay', missing)
    response = client().get('/assistant/can-replay')
    assert response.status_code == 404
    assert '模拟' in response.json()['detail']
    simulated = client().get('/assistant/can-replay?scenario=synthetic')
    assert simulated.status_code == 200
    assert simulated.headers['cache-control'] == 'no-store'
