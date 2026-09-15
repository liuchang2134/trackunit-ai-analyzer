import json
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from fastapi.testclient import TestClient

from app import ai_request_status as status
from app.gemini_client import GeminiError
from app.main import app


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-flash-latest')
    monkeypatch.setenv('GEMINI_API_KEY', 'private-configured-key')
    return status.capture_context()


def test_status_has_no_live_probe_or_private_configuration(context, monkeypatch):
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: pytest.fail('No provider probe'))
    response = TestClient(app).get('/assistant/ai-status')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.json()['last_attempt'] is None and response.json()['current_availability'] == 'not_verified'
    assert 'private-configured-key' not in response.text and 'context_id' not in response.text


def test_daily_failure_persists_and_does_not_assert_recovery(context, monkeypatch):
    error = GeminiError('private prompt and upstream response', provider_error={'kind':'daily_quota', 'private':'secret',
        'limits':[{'window':'day','measure':'requests','limit':20,'subject':'private project'}]})
    saved = status.record_outcome(context, 'failed', error=error)
    assert saved['recording_saved'] and saved['last_attempt']['failure']['limits'][0]['limit'] == 20
    raw = status.STATUS_PATH.read_text(encoding='utf-8')
    assert 'private' not in raw and 'secret' not in raw
    later = datetime.fromisoformat(saved['last_attempt']['finished_at']) + timedelta(days=2)
    monkeypatch.setattr(status, 'now_utc', lambda: later)
    result = status.request_status()
    assert result['last_attempt']['older_than_24h']
    assert result['last_attempt']['failure']['kind'] == 'daily_quota'
    assert result['current_availability'] == 'not_verified'


@pytest.mark.parametrize('field,value', [('GEMINI_API_KEY','changed-secret'), ('GEMINI_MODEL','another-model')])
def test_changed_configuration_does_not_inherit_failure(context, monkeypatch, field, value):
    status.record_outcome(context, 'failed', error=GeminiError('quota'))
    monkeypatch.setenv(field, value)
    result = status.request_status()
    assert result['last_attempt'] is None and result['record_state'] == 'other_configuration'


@pytest.mark.parametrize('body', ['not-json', '{"outcome":"report_saved"}'])
def test_corrupt_record_is_unknown_not_healthy(context, body):
    status.STATUS_PATH.write_text(body, encoding='utf-8')
    assert status.request_status()['record_state'] == 'invalid'
    assert status.request_status()['last_attempt'] is None


def test_prior_verification_is_explicit_and_future_record_rejected(context):
    record = status.Attempt(provider='gemini', finished_at=datetime.now(timezone.utc)-timedelta(hours=2),
        outcome='failed', failure=status.Failure(kind='daily_quota'), source='prior_verification')
    status.STATUS_PATH.write_text(record.model_dump_json(), encoding='utf-8')
    old = status.request_status()['last_attempt']
    assert old['source'] == 'prior_verification' and old['configuration_match'] is False
    record.finished_at = datetime.now(timezone.utc)+timedelta(days=1)
    status.STATUS_PATH.write_text(record.model_dump_json(), encoding='utf-8')
    assert status.request_status()['record_state'] == 'invalid'


def test_storage_failure_keeps_unsaved_report_outcome_in_response(context, monkeypatch):
    monkeypatch.setattr(status.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('disk unavailable')))
    result = status.record_outcome(context, 'report_unsaved')
    assert result['recording_saved'] is False
    assert result['last_attempt']['outcome'] == 'report_unsaved'
    assert not list(status.STATUS_PATH.parent.glob('.ai-status-*.tmp'))


def test_failure_route_records_only_category_and_invalid_input_does_not_replace_it(context, monkeypatch):
    from app.api import routes_assistant as routes
    from app import investigation_history
    monkeypatch.setattr(investigation_history, 'save_investigation', lambda *a: pytest.fail('No report'))
    def fail(request):
        raise GeminiError('provider unavailable', kind='service_unavailable')
    monkeypatch.setattr(routes, 'investigate', fail)
    client=TestClient(app)
    response=client.post('/assistant/investigate',json={'machine_id':'SIM-TEST','question':'check'})
    assert response.status_code == 503
    assert response.json()['ai_status']['last_attempt']['failure']['kind'] == 'service_unavailable'
    before=status.STATUS_PATH.read_bytes()
    monkeypatch.setattr(routes, 'investigate', lambda r: (_ for _ in ()).throw(ValueError('missing device')))
    assert client.post('/assistant/investigate',json={'machine_id':'missing','question':'check'}).status_code == 404
    assert status.STATUS_PATH.read_bytes() == before


@pytest.mark.parametrize('save_fails', [False, True])
def test_route_distinguishes_report_and_history_save(context, monkeypatch, save_fails):
    from app.api import routes_assistant as routes
    from app import investigation_history
    monkeypatch.setattr(routes, 'investigate', lambda r: {'status':'completed','summary':'simulated transport'})
    def save(*args):
        if save_fails: raise OSError('disk unavailable')
        return {'record_id':'a'*64}
    monkeypatch.setattr(investigation_history, 'save_investigation', save)
    response=TestClient(app).post('/assistant/investigate',json={'machine_id':'SIM-TEST','question':'check'})
    assert response.status_code == 200
    assert response.json()['history_saved'] is not save_fails
    assert response.json()['ai_status']['last_attempt']['outcome'] == ('report_unsaved' if save_fails else 'report_saved')
