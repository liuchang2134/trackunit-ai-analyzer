import json
import httpx
import pytest
from fastapi.testclient import TestClient

from app.gemini_client import GeminiError, generate_with_gemini
from app.gemini_quota import quota_failure
from app.main import app


def response_for(quota_id, value='20', delay='44s'):
    return httpx.Response(429, json={'error': {'message': 'private response and private-key',
        'details': [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{
            'quotaId': quota_id, 'quotaValue': value, 'subject': 'projects/private-project',
            'quotaDimensions': {'model': 'gemini-3.8-flash', 'project': 'private-project'}}]},
            {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': delay}]}})


def test_observed_daily_request_quota_does_not_inherit_short_retry_hint():
    # Fixed, redacted Google error contract; no local account response required.
    response = response_for('GenerateRequestsPerDayPerProjectPerModel-FreeTier', '20', '44s')
    result = quota_failure(response)
    assert result == {'kind': 'daily_quota', 'limits': [{'window': 'day', 'measure': 'requests', 'limit': 20}]}
    assert 'retry_after_seconds' not in result
    assert 'private' not in json.dumps(result)


def test_minute_limit_rounds_up_provider_retry_delay():
    result = quota_failure(response_for('GenerateContentInputTokensPerModelPerMinute-FreeTier', '250000', '4.1s'))
    assert result['kind'] == 'minute_quota' and result['retry_after_seconds'] == 5
    assert result['limits'] == [{'window': 'minute', 'measure': 'tokens', 'limit': 250000}]


def test_zero_quota_is_unavailable_and_daily_tokens_are_not_called_requests():
    assert quota_failure(response_for('GenerateRequestsPerDayPerProjectPerModel-FreeTier', '0'))['kind'] == 'quota_unavailable'
    tokens = quota_failure(response_for('GenerateContentInputTokensPerModelPerDay-FreeTier', '100000'))
    assert tokens['kind'] == 'daily_quota' and tokens['limits'][0]['measure'] == 'tokens'


@pytest.mark.parametrize('body', [None, [], {'error': []}, {'error': {'details': 'private'}},
                                 {'error': {'details': [None, [], {'@type': 'unrecognized'}]}}])
def test_missing_or_malformed_details_do_not_invent_a_daily_quota(body):
    assert quota_failure(httpx.Response(429, json=body)) == {'kind': 'quota_unknown', 'limits': []}


def test_invalid_fields_are_not_reflected_and_nonquota_errors_ignored():
    assert quota_failure(response_for('GeneratePrivate<iframe>PerDay'))['kind'] == 'quota_unknown'
    assert quota_failure(response_for('GenerateUnrecognizedResourcePerDay'))['kind'] == 'quota_unknown'
    result = quota_failure(response_for('GenerateRequestsPerMinute', 'private-key', 'NaNs'))
    assert result == {'kind': 'minute_quota', 'limits': [{'window': 'minute', 'measure': 'requests'}]}
    assert quota_failure(httpx.Response(503, json={'error': {'message': 'private'}})) is None


def test_daily_quota_is_propagated_once_and_never_retried(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'private-key')
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        return response_for('GenerateRequestsPerDayPerProjectPerModel-FreeTier')
    monkeypatch.setattr(httpx, 'post', post)
    with pytest.raises(GeminiError) as error:
        generate_with_gemini('synthetic test')
    assert len(calls) == 1 and error.value.attempts == 1
    assert error.value.provider_error['kind'] == 'daily_quota'
    assert 'private-key' not in str(error.value)


def test_api_preserves_detail_and_structured_quota_without_saving_report(monkeypatch):
    from app.api import routes_assistant
    from app import investigation_history
    def fail(request):
        raise GeminiError('Gemini API quota exceeded', attempts=1,
            provider_error=quota_failure(response_for('GenerateRequestsPerDayPerProjectPerModel-FreeTier')))
    monkeypatch.setattr(routes_assistant, 'investigate', fail)
    monkeypatch.setattr(investigation_history, 'save_investigation', lambda *a: pytest.fail('No report to save'))
    response = TestClient(app).post('/assistant/investigate', json={'machine_id': 'SIM-TEST', 'question': 'overview'})
    assert response.status_code == 503
    assert response.json()['provider_error']['kind'] == 'daily_quota'
    assert response.json()['detail'] == 'Gemini API quota exceeded'
    assert response.headers['cache-control'] == 'no-store'
