import json

import httpx
import pytest

from app import deepseek_client as deepseek
from app.deepseek_client import DeepSeekError, generate_structured_with_deepseek, generate_with_deepseek


@pytest.fixture(autouse=True)
def configured_deepseek(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-deepseek-key')
    monkeypatch.setenv('DEEPSEEK_MODEL', 'deepseek-flash')
    monkeypatch.setenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')


def response(status=200, content='answer', finish='stop', headers=None):
    return httpx.Response(status, json={'choices': [{'finish_reason': finish, 'message': {
        'content': content, 'reasoning_content': 'private reasoning is not returned'}}]}, headers=headers)


@pytest.mark.parametrize('base', ['https://api.deepseek.com', 'https://api.deepseek.com/v1/'])
def test_official_endpoint_nonthinking_and_authorization(monkeypatch, base):
    monkeypatch.setenv('DEEPSEEK_BASE_URL', base)

    def post(url, **kwargs):
        assert url == base.rstrip('/') + '/chat/completions'
        assert kwargs['headers'] == {'Content-Type': 'application/json', 'Authorization': 'Bearer test-deepseek-key'}
        assert 'test-deepseek-key' not in url
        assert kwargs['follow_redirects'] is False
        assert 0 < kwargs['timeout'] <= 45
        assert kwargs['json'] == {
            'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': 'prompt'}],
            'max_tokens': 4096, 'thinking': {'type': 'disabled'}, 'temperature': 0, 'stream': False,
        }
        return response(content=' final answer ')

    monkeypatch.setattr(httpx, 'post', post)
    assert generate_with_deepseek('prompt') == 'final answer'


def test_default_model_is_flash(monkeypatch):
    monkeypatch.delenv('DEEPSEEK_MODEL')
    assert deepseek.get_deepseek_model() == 'deepseek-flash'


def test_structured_messages_keep_history_and_schema_without_metadata(monkeypatch):
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['action', 'evidence_ids'],
              'properties': {'action': {'type': 'string', 'enum': ['snapshot'], 'default': ''},
                             'evidence_ids': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 0}}}
    messages = [{'role': 'system', 'content': 'application instructions'},
                {'role': 'user', 'content': 'question'}, {'role': 'assistant', 'content': 'previous decision'},
                {'role': 'user', 'content': 'evidence', '_decision_options': {'private': 'local metadata'}}]

    def post(url, **kwargs):
        body = kwargs['json']
        assert body['response_format'] == {'type': 'json_object'}
        assert body['thinking'] == {'type': 'disabled'} and body['max_tokens'] == 2048
        assert body['messages'][1:] == [{k: v for k, v in item.items() if k in {'role', 'content'}} for item in messages]
        assert 'local metadata' not in json.dumps(body)
        instruction = body['messages'][0]['content']
        serialized_schema = instruction.split('JSON Schema: ')[1].split('\nExample JSON format:')[0]
        assert json.loads(serialized_schema) == schema
        assert json.loads(instruction.split('Example JSON format: ')[1]) == {'action': 'snapshot', 'evidence_ids': []}
        return response(content='{"action":"snapshot","evidence_ids":[]}')

    monkeypatch.setattr(httpx, 'post', post)
    assert json.loads(generate_structured_with_deepseek(messages, schema))['action'] == 'snapshot'
    assert '_decision_options' in messages[-1]  # Caller-owned history is not mutated.


def test_empty_structured_history_has_json_user_instruction(monkeypatch):
    def post(url, **kwargs):
        assert kwargs['json']['messages'][-1]['role'] == 'user'
        assert 'JSON' in kwargs['json']['messages'][-1]['content']
        return response(content='{}')
    monkeypatch.setattr(httpx, 'post', post)
    assert generate_structured_with_deepseek([], {'type': 'object'}) == '{}'


@pytest.mark.parametrize('base', ['https://example.com', 'http://api.deepseek.com',
                                'https://api.deepseek.com.evil.test', 'https://api.deepseek.com@evil.test',
                                'https://api.deepseek.com:444', 'https://api.deepseek.com/beta',
                                'https://api.deepseek.com/?target=secret'])
def test_no_key_transmission_to_nonofficial_endpoint(monkeypatch, base):
    monkeypatch.setenv('DEEPSEEK_BASE_URL', base)
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: pytest.fail('Must not transmit key'))
    with pytest.raises(DeepSeekError) as caught:
        generate_with_deepseek('prompt')
    assert caught.value.kind == 'configuration_invalid' and caught.value.attempts == 0


@pytest.mark.parametrize('model', ['', '../model', 'model?api_key=secret', 'model\r\nsecret'])
def test_invalid_model_rejected_before_request(monkeypatch, model):
    monkeypatch.setenv('DEEPSEEK_MODEL', model)
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: pytest.fail('Must not transmit key'))
    with pytest.raises(DeepSeekError) as caught:
        generate_with_deepseek('prompt')
    assert caught.value.kind == 'configuration_invalid'


def test_missing_key(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', '   ')
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: pytest.fail('Must not make request'))
    with pytest.raises(DeepSeekError, match='DEEPSEEK_API_KEY') as caught:
        generate_with_deepseek('prompt')
    assert caught.value.kind == 'configuration_missing'


@pytest.mark.parametrize('status,kind', [(302, 'configuration_invalid'), (400, 'configuration_invalid'),
                                     (401, 'authentication'), (402, 'insufficient_balance'),
                                     (403, 'authentication'), (404, 'configuration_invalid'),
                                     (422, 'configuration_invalid'), (429, 'rate_limit')])
def test_nonretryable_http_errors_are_specific_and_sanitized(monkeypatch, status, kind):
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        return httpx.Response(status, json={'error': {'message': 'private test-deepseek-key'}},
                              headers={'Location': 'https://evil.test'})
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(deepseek.time, 'sleep', lambda _: pytest.fail('Must not retry'))
    with pytest.raises(DeepSeekError) as caught:
        generate_with_deepseek('prompt')
    assert len(calls) == 1 and caught.value.attempts == 1 and caught.value.kind == kind
    assert 'private' not in str(caught.value) and 'test-deepseek-key' not in str(caught.value)


@pytest.mark.parametrize('status', [500, 502, 503, 504])
def test_transient_errors_stop_after_three_identical_requests(monkeypatch, status):
    calls, delays = [], []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return response(status=status)
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(deepseek.time, 'sleep', delays.append)
    monkeypatch.setattr(deepseek.random, 'uniform', lambda *a: 0)
    with pytest.raises(DeepSeekError) as caught:
        generate_with_deepseek('same evidence')
    assert len(calls) == 3 and caught.value.attempts == 3
    assert calls[0] == calls[1] == calls[2] and delays == [2, 4]
    assert caught.value.kind == 'service_unavailable'


def test_transient_error_can_recover_and_honors_retry_after(monkeypatch):
    calls, delays = [], []
    def post(url, **kwargs):
        calls.append(kwargs)
        return response(status=503, headers={'Retry-After': '7'}) if len(calls) == 1 else response(content='recovered')
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(deepseek.time, 'sleep', delays.append)
    assert generate_with_deepseek('prompt') == 'recovered'
    assert len(calls) == 2 and delays == [7]


@pytest.mark.parametrize('retry_after', ['NaN', 'inf', '-1', 'Tue, 15 Sep 2026 10:00:00 GMT'])
def test_unknown_retry_after_does_not_retry_early(monkeypatch, retry_after):
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: response(status=503, headers={'Retry-After': retry_after}))
    monkeypatch.setattr(deepseek.time, 'sleep', lambda _: pytest.fail('Must not retry early'))
    with pytest.raises(DeepSeekError) as caught:
        generate_with_deepseek('prompt')
    assert caught.value.attempts == 1


@pytest.mark.parametrize('error,kind', [(httpx.ConnectError('private test-deepseek-key'), 'network'),
                                    (httpx.ReadTimeout('private test-deepseek-key'), 'timeout'),
                                    (httpx.RemoteProtocolError('private test-deepseek-key'), 'network')])
def test_transport_errors_do_not_retry_or_expose_details(monkeypatch, error, kind):
    def post(*a, **k):
        raise error
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(deepseek.time, 'sleep', lambda _: pytest.fail('Must not retry'))
    with pytest.raises(DeepSeekError) as caught:
        generate_with_deepseek('prompt')
    assert caught.value.kind == kind and caught.value.attempts == 1
    assert 'private' not in str(caught.value) and 'test-deepseek-key' not in str(caught.value)


@pytest.mark.parametrize('payload', [None, [], {}, {'choices': []}, {'choices': [None]},
                                  {'choices': [{'finish_reason': 'stop', 'message': {'content': []}}]},
                                  {'choices': [{'finish_reason': 'stop', 'message': {'content': ' '}}]},
                                  {'choices': [{'finish_reason': 'length', 'message': {'content': 'partial'}}]},
                                  {'choices': [{'finish_reason': 'content_filter', 'message': {'content': 'partial'}}]},
                                  {'choices': [{'message': {'content': 'missing finish'}}]}])
def test_malformed_empty_and_incomplete_responses_are_rejected(monkeypatch, payload):
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: httpx.Response(200, json=payload))
    with pytest.raises(DeepSeekError) as caught:
        generate_with_deepseek('prompt')
    assert caught.value.kind == 'invalid_response' and caught.value.attempts == 1


def test_non_json_http_body_is_rejected(monkeypatch):
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: httpx.Response(200, text='private test-deepseek-key'))
    with pytest.raises(DeepSeekError) as caught:
        generate_with_deepseek('prompt')
    assert caught.value.kind == 'invalid_response'
    assert 'test-deepseek-key' not in str(caught.value)


def test_retry_cannot_exceed_remaining_deadline(monkeypatch):
    clock, calls = [0.0], []
    def post(*args, **kwargs):
        calls.append(kwargs['timeout'])
        clock[0] += 4
        return response(status=503, headers={'Retry-After': '10'})
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(deepseek.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(deepseek.time, 'sleep', lambda _: pytest.fail('No time for retry'))
    with pytest.raises(DeepSeekError, match='Time limit reached') as caught:
        generate_with_deepseek('prompt', timeout_seconds=5)
    assert calls == [5] and caught.value.attempts == 1


def test_late_response_is_not_accepted(monkeypatch):
    clock = [0.0]
    def post(*args, **kwargs):
        clock[0] = 6
        return response()
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(deepseek.time, 'monotonic', lambda: clock[0])
    with pytest.raises(DeepSeekError) as caught:
        generate_with_deepseek('prompt', timeout_seconds=5)
    assert caught.value.kind == 'timeout' and caught.value.attempts == 1


@pytest.mark.parametrize('budget', [0, -1, float('inf'), float('nan')])
def test_invalid_time_budget_sends_no_request(monkeypatch, budget):
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: pytest.fail('Must not make request'))
    with pytest.raises(DeepSeekError) as caught:
        generate_with_deepseek('prompt', timeout_seconds=budget)
    assert caught.value.kind == 'timeout' and caught.value.attempts == 0
