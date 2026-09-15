import json

import pytest
from fastapi.testclient import TestClient

from app import local_assistant as agent
from app import ai_request_status as status
from app.deepseek_client import DeepSeekError
from app.main import app


@pytest.fixture
def deepseek(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'deepseek')
    monkeypatch.setenv('DEEPSEEK_MODEL', 'deepseek-flash')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'private-deepseek-test-key')
    monkeypatch.setattr(agent, 'generate_structured_with_gemini', lambda *a, **k: pytest.fail('No Gemini fallback'))
    monkeypatch.setattr(agent.httpx, 'post', lambda *a, **k: pytest.fail('No Ollama or live request'))


def test_runtime_reports_configured_cloud_model_without_credentials(deepseek, monkeypatch):
    client = TestClient(app)
    result = client.get('/assistant/runtime')
    runtime = result.json()
    assert runtime['provider'] == 'deepseek' and runtime['model'] == 'deepseek-flash'
    assert runtime['inference_location'] == 'cloud' and runtime['cloud_credentials_configured']
    assert runtime['automatic_fallback'] is False and runtime['thinking_mode'] == 'disabled'
    assert runtime['investigation_timeout_seconds'] == 120 and runtime['transient_attempt_limit'] == 3
    assert 'private-deepseek-test-key' not in result.text
    monkeypatch.delenv('DEEPSEEK_API_KEY')
    assert client.get('/assistant/runtime').json()['cloud_credentials_configured'] is False


def test_structured_decision_uses_cloud_policy_and_source_allowlists(deepseek, monkeypatch):
    def generate(messages, schema, timeout_seconds):
        assert schema['properties']['action']['enum'] == ['finish']
        assert schema['properties']['evidence_ids']['items']['enum'] == ['tool:1:snapshot']
        assert schema['properties']['next_check_ids']['maxItems'] == 0
        assert set(schema['required']) == set(schema['properties'])
        assert all(set(message) == {'role', 'content'} for message in messages)
        assert 'JSON' in messages[0]['content']
        assert timeout_seconds == 12.5
        return json.dumps({'action': 'finish', 'component': '', 'summary': '模拟记录，尚不能确认故障。',
                           'evidence_ids': ['tool:1:snapshot'], 'next_check_ids': []})
    monkeypatch.setattr(agent, 'generate_structured_with_deepseek', generate)
    decision = agent.model_step([
        {'role': 'system', 'content': 'rules'},
        {'role': 'user', 'content': 'synthetic evidence', '_decision_options': {
            'evidence_ids': ['tool:1:snapshot'], 'next_check_ids': []}}
    ], ['finish'], timeout_seconds=12.5)
    assert decision.evidence_ids == ['tool:1:snapshot']


@pytest.mark.parametrize('output,match', [
    ('not JSON', 'invalid structured'),
    ('{"action":"parts"}', 'unavailable action'),
    ('{"action":"snapshot","evidence_ids":["invented"]}', 'unavailable evidence'),
    ('{"action":"snapshot","next_check_ids":["invented-check"]}', 'unavailable evidence'),
])
def test_generated_decisions_must_pass_local_validation(deepseek, monkeypatch, output, match):
    monkeypatch.setattr(agent, 'generate_structured_with_deepseek', lambda *a, **k: output)
    with pytest.raises(DeepSeekError, match=match) as failure:
        agent.model_step([{'role': 'user', 'content': 'read source', '_decision_options': {
            'evidence_ids': [], 'next_check_ids': []}}], ['snapshot'])
    assert failure.value.kind == 'invalid_response'


@pytest.mark.parametrize('kind', ['insufficient_balance', 'rate_limit', 'authentication', 'timeout'])
def test_cloud_failure_is_actionable_503_and_persisted_without_raw_message(deepseek, monkeypatch, kind):
    from app.api import routes_assistant as routes
    def fail(request):
        raise DeepSeekError('DeepSeek request could not complete.', kind=kind)
    monkeypatch.setattr(routes, 'investigate', fail)
    response = TestClient(app).post('/assistant/investigate', json={'machine_id': 'SIM-TEST', 'question': 'check'})
    assert response.status_code == 503 and response.headers['cache-control'] == 'no-store'
    assert response.json()['provider_error'] == {'kind': kind}
    assert response.json()['ai_status']['last_attempt']['failure'] == {'kind': kind, 'limits': []}
    record = status.STATUS_PATH.read_text(encoding='utf-8')
    assert 'private-deepseek-test-key' not in record and 'request could not complete' not in record


def test_status_follows_deepseek_config_and_hides_old_gemini_attempts(deepseek, monkeypatch):
    context = status.capture_context()
    assert context['configured'] is True
    status.record_outcome(context, 'failed', error=DeepSeekError('balance', kind='insufficient_balance'))
    monkeypatch.setenv('GEMINI_API_KEY', 'different-unused-key')
    assert status.request_status()['last_attempt']['failure']['kind'] == 'insufficient_balance'
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'different-deepseek-key')
    assert status.request_status()['record_state'] == 'other_configuration'
    assert status.request_status()['last_attempt'] is None
    monkeypatch.setenv('AI_PROVIDER', 'gemini')
    status.record_outcome(status.capture_context(), 'report_saved')
    monkeypatch.setenv('AI_PROVIDER', 'deepseek')
    result = status.request_status()
    assert result['provider'] == 'deepseek' and result['record_state'] == 'other_configuration'
    assert result['last_attempt'] is None
