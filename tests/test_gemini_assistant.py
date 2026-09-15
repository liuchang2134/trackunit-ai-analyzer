import pytest
from fastapi.testclient import TestClient
from app import local_assistant as agent
from app.gemini_client import GeminiError
from app.main import app


def test_gemini_step_uses_dynamic_schema_and_never_ollama(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('OLLAMA_BASE_URL','https://unused.example.com')
    def generate(messages,schema):
        assert schema['properties']['action']['enum']==['snapshot']
        assert schema['properties']['evidence_ids']['maxItems']==0
        assert '_decision_options' not in messages[-1]
        return '{"action":"snapshot","component":"","summary":"","evidence_ids":[],"next_check_ids":[]}'
    monkeypatch.setattr(agent,'generate_structured_with_gemini',generate)
    assert agent.model_step([{'role':'system','content':'rules','_decision_options':{'evidence_ids':[]}}],['snapshot']).action=='snapshot'
    def fail(*args):raise GeminiError('Quota unavailable')
    monkeypatch.setattr(agent,'generate_structured_with_gemini',fail)
    monkeypatch.setattr(agent.httpx,'post',lambda *a,**k:pytest.fail('No fallback allowed'))
    with pytest.raises(GeminiError,match='Quota'):agent.model_step([],['snapshot'])


def test_runtime_does_not_return_api_key_and_cloud_error_is_503(monkeypatch):
    from app.api import routes_assistant
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('GEMINI_API_KEY','private-test-key')
    monkeypatch.setenv('GEMINI_MODEL','gemini-flash-latest')
    client=TestClient(app)
    runtime=client.get('/assistant/runtime')
    assert runtime.json()['inference_location']=='cloud'
    assert runtime.json()['model']=='gemini-flash-latest'
    assert 'private-test-key' not in runtime.text
    def fail(request):raise GeminiError('Gemini API quota exceeded')
    monkeypatch.setattr(routes_assistant,'investigate',fail)
    response=client.post('/assistant/investigate',json={'machine_id':'SIM-TEST','question':'overview'})
    assert response.status_code==503 and 'quota' in response.json()['detail']


def test_empty_dynamic_allowlist_is_enforced_after_generation(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setattr(agent,'generate_structured_with_gemini',lambda *args:
        '{"action":"snapshot","evidence_ids":["invented"],"next_check_ids":[]}')
    with pytest.raises(GeminiError,match='unavailable evidence'):
        agent.model_step([{'role':'user','content':'check',
                           '_decision_options':{'evidence_ids':[]}}],['snapshot'])


def test_cloud_startup_requires_key_but_never_checks_ollama(monkeypatch):
    from scripts import check_local_runtime as runtime
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setattr(runtime,'urlopen',lambda *a,**k:pytest.fail('Ollama is not required'))
    assert runtime.check()['ready'] is False
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    result=runtime.check()
    assert result['ready'] and result['ollama']=='not_required'
    assert result['authentication_verified'] is False
