import httpx
import pytest

from app.gemini_client import GeminiError, generate_with_gemini
from app.gemini_client import generate_structured_with_gemini


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_generate_with_gemini_returns_text(monkeypatch):
    def fake_post(url, headers, json, timeout):
        assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
        assert headers["X-goog-api-key"] == "test-key"
        assert json["contents"][0]["parts"][0]["text"] == "prompt"
        return DummyResponse(payload={
            "candidates": [
                {"content": {"parts": [{"text": "Gemini answer"}]}}
            ]
        })

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-flash-latest")
    monkeypatch.setattr(httpx, "post", fake_post)

    assert generate_with_gemini("prompt") == "Gemini answer"


def test_generate_with_gemini_requires_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(GeminiError, match="GEMINI_API_KEY"):
        generate_with_gemini("prompt")


def test_generate_with_gemini_invalid_key(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return DummyResponse(status_code=403, payload={"error": {"message": "API key not valid"}})

    monkeypatch.setenv("GEMINI_API_KEY", "bad-key")
    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(GeminiError, match="API key is invalid"):
        generate_with_gemini("prompt")


def test_structured_decision_keeps_system_and_enum_constraints(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    def post(url, headers, json, timeout):
        assert headers['X-goog-api-key'] == 'test-key'
        assert 'test-key' not in url
        assert json['systemInstruction']['parts'] == [{'text':'rules'}, {'text':'choose from options'}]
        assert [v['role'] for v in json['contents']] == ['user','model','user']
        assert '_decision_options' not in str(json)
        schema=json['generationConfig']['responseJsonSchema']
        assert schema['properties']['action']['enum'] == ['snapshot']
        assert 'default' not in schema['properties']['action']
        assert 'maxItems' not in schema['properties']['empty_ids']
        return DummyResponse(payload={'candidates':[{'finishReason':'STOP','content':{'parts':[{'thought':True,'text':'hidden'},{'text':'{"action":"snapshot"}'}]}}]})
    monkeypatch.setattr(httpx, 'post', post)
    result=generate_structured_with_gemini([
        {'role':'system','content':'rules'}, {'role':'user','content':'question'},
        {'role':'assistant','content':'decision'}, {'role':'user','content':'evidence'},
        {'role':'system','content':'choose from options','_decision_options':{'secret':'internal'}}
    ], {'type':'object','properties':{'action':{'type':'string','enum':['snapshot'],'default':''},
                                    'empty_ids':{'type':'array','items':{'type':'string'},'maxItems':0}}})
    assert result == '{"action":"snapshot"}'


def test_gemini_rejects_nonofficial_endpoint_before_transmitting_key(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    monkeypatch.setenv('GEMINI_BASE_URL','https://example.com/v1beta')
    monkeypatch.setattr(httpx,'post',lambda *a,**k:pytest.fail('Must not send key'))
    with pytest.raises(GeminiError,match='official HTTPS'):
        generate_with_gemini('prompt')


@pytest.mark.parametrize('status,finish',[(429,None),(400,None),(200,'MAX_TOKENS')])
def test_cloud_errors_do_not_expose_raw_response(monkeypatch,status,finish):
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    monkeypatch.setattr(httpx,'post',lambda *a,**k:DummyResponse(status_code=status,payload={
        'error':{'message':'sensitive-debug test-key'},
        'candidates':[{'finishReason':finish,'content':{'parts':[{'text':'partial'}]}}]}))
    with pytest.raises(GeminiError) as error:generate_with_gemini('prompt')
    assert 'test-key' not in str(error.value) and 'sensitive-debug' not in str(error.value)


def test_transient_failure_recovers_with_same_request(monkeypatch):
    from app import gemini_client as gemini
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    calls, delays = [], []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return DummyResponse(status_code=503, payload={'error':{'message':'capacity'}}) if len(calls)==1 else DummyResponse(
            payload={'candidates':[{'content':{'parts':[{'text':'recovered'}]}}]})
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(gemini.time, 'sleep', delays.append)
    monkeypatch.setattr(gemini.random, 'uniform', lambda *args: 0)
    assert generate_with_gemini('same evidence') == 'recovered'
    assert len(calls)==2 and calls[0][0]==calls[1][0]
    assert calls[0][1]['json']==calls[1][1]['json']
    assert calls[0][1]['headers']==calls[1][1]['headers']
    assert delays == [2]


@pytest.mark.parametrize('status,expected_calls',[(400,1),(403,1),(429,1),(503,3)])
def test_retry_limit_and_nonretryable_errors(monkeypatch,status,expected_calls):
    from app import gemini_client as gemini
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    calls=[]
    def post(*args, **kwargs):
        calls.append(kwargs)
        return DummyResponse(status_code=status,payload={'error':{'message':'private test-key'}})
    monkeypatch.setattr(httpx,'post',post)
    monkeypatch.setattr(gemini.time,'sleep',lambda _:None)
    with pytest.raises(GeminiError) as error:
        generate_with_gemini('evidence')
    assert len(calls)==expected_calls
    assert error.value.attempts==expected_calls
    assert 'test-key' not in str(error.value) and 'private' not in str(error.value)


def test_retry_stops_at_time_budget_and_respects_retry_after(monkeypatch):
    from app import gemini_client as gemini
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    clock=[0.0]
    calls=[]
    def post(*args, **kwargs):
        calls.append(kwargs['timeout'])
        clock[0]+=4
        response=DummyResponse(status_code=503)
        response.headers={'Retry-After':'10'}
        return response
    monkeypatch.setattr(httpx,'post',post)
    monkeypatch.setattr(gemini.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(gemini.time,'sleep',lambda _:pytest.fail('No time for requested delay'))
    with pytest.raises(GeminiError):
        generate_with_gemini('evidence',timeout_seconds=5)
    assert calls==[5]
