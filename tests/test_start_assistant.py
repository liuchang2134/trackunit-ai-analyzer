"""Launcher checks never install, terminate services or make external requests."""
from contextlib import nullcontext
import io
from urllib.error import HTTPError

import pytest

from scripts import start_assistant as launcher


@pytest.fixture(autouse=True)
def no_real_processes_or_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('The startup test must not start processes or contact services')
    monkeypatch.setattr(launcher.subprocess, 'call', forbidden)
    monkeypatch.setattr(launcher.socket, 'create_connection', forbidden)
    monkeypatch.setattr(launcher, 'read_local_json', forbidden)


@pytest.fixture
def local_ready(monkeypatch):
    value = {'local_ready': True, 'missing_dependencies': [], 'provider': 'gemini',
             'api_key_configured': False, 'official_endpoint': True, 'ai_ready': False}
    def check(*, demo_only):
        assert demo_only is True
        return value
    monkeypatch.setattr(launcher, 'check', check)
    monkeypatch.setattr(launcher, 'existing_service', lambda _: False)
    return value


def test_check_only_supports_local_features_without_gemini(local_ready, capsys):
    assert launcher.main(['--port', '8892', '--check-only']) == 0
    text = capsys.readouterr().out
    assert 'Gemini key is not configured' in text
    assert 'No server started' in text and 'http://127.0.0.1:8892/assistant-ui/' in text


def test_start_uses_current_python_and_loopback_only(local_ready, monkeypatch):
    calls = []
    monkeypatch.setattr(launcher.subprocess, 'call', lambda command, **options: calls.append((command, options)) or 0)
    assert launcher.main([]) == 0
    assert calls == [([launcher.sys.executable, '-m', 'uvicorn', 'app.main:app',
                      '--host', '127.0.0.1', '--port', '8890'], {'cwd': launcher.ROOT})]


def test_deepseek_check_displays_current_provider_without_network(local_ready, capsys):
    local_ready.update(provider='deepseek', api_key_configured=True)
    assert launcher.main(['--port', '8892', '--check-only']) == 0
    output = capsys.readouterr().out
    assert 'DeepSeek is configured locally' in output
    assert 'were not tested' in output and 'Gemini' not in output


def test_missing_local_dependencies_never_start(local_ready, capsys):
    local_ready.update(local_ready=False, missing_dependencies=['uvicorn'])
    assert launcher.main([]) == 1
    assert 'uvicorn' in capsys.readouterr().err


def occupied(monkeypatch, *, title='Trackunit AI Analyzer', build=launcher.ASSISTANT_BUILD):
    monkeypatch.setattr(launcher.socket, 'create_connection', lambda address, timeout: nullcontext())
    paths = []
    def read(port, path):
        paths.append((port, path))
        return {'info': {'title': title}} if path == '/openapi.json' else {'backend_build': build}
    monkeypatch.setattr(launcher, 'read_local_json', read)
    return paths


def test_existing_current_service_reports_url_without_start_or_model_check(monkeypatch, capsys):
    paths = occupied(monkeypatch)
    monkeypatch.setattr(launcher, 'check', lambda **kwargs: pytest.fail('Existing service needs no AI prerequisite probe'))
    assert launcher.main(['--port', '8892']) == 0
    assert paths == [(8892, '/openapi.json'), (8892, '/assistant/runtime')]
    assert 'Assistant already running: http://127.0.0.1:8892/assistant-ui/' in capsys.readouterr().out


@pytest.mark.parametrize('title,build,error', [
    ('Another app', launcher.ASSISTANT_BUILD, 'another application'),
    ('Trackunit AI Analyzer', 'old-build', 'older or different build'),
])
def test_other_or_old_service_is_not_restarted(monkeypatch, capsys, title, build, error):
    occupied(monkeypatch, title=title, build=build)
    assert launcher.main(['--port', '8892']) == 1
    assert error in capsys.readouterr().err


def test_non_http_occupied_port_is_an_error_not_a_free_port(monkeypatch, capsys):
    occupied(monkeypatch)
    def unreadable(*args):
        raise ValueError('not JSON')
    monkeypatch.setattr(launcher, 'read_local_json', unreadable)
    assert launcher.main([]) == 1
    assert 'occupied' in capsys.readouterr().err


def test_connection_refusal_only_is_treated_as_available(monkeypatch):
    def refused(*args, **kwargs):
        raise ConnectionRefusedError()
    monkeypatch.setattr(launcher.socket, 'create_connection', refused)
    assert launcher.existing_service(8890) is False
    def timeout(*args, **kwargs):
        raise TimeoutError()
    monkeypatch.setattr(launcher.socket, 'create_connection', timeout)
    with pytest.raises(launcher.StartupError, match='Cannot verify'):
        launcher.existing_service(8890)


@pytest.mark.parametrize('port', ['0', '1023', '65536', 'not-a-number'])
def test_invalid_port_is_rejected_before_any_probe(port):
    with pytest.raises(SystemExit) as error:
        launcher.main(['--port', port])
    assert error.value.code == 2


def test_redirects_are_not_followed_and_proxy_is_disabled(monkeypatch):
    # Exercise the stdlib handlers with a fake HTTP response; no socket is opened.
    from urllib.request import BaseHandler, build_opener, ProxyHandler
    seen = []
    class RedirectReply(BaseHandler):
        handler_order = 400
        def http_open(self, request):
            seen.append(request.full_url)
            response = io.BytesIO(b'')
            response.code = 302
            response.msg = 'Found'
            response.headers = {'Location': 'https://external.invalid/never-follow'}
            response.info = lambda: response.headers
            return response
    opener = build_opener(ProxyHandler({}), launcher.NoRedirect(), RedirectReply())
    with pytest.raises(HTTPError):
        opener.open('http://127.0.0.1:8892/openapi.json')
    assert seen == ['http://127.0.0.1:8892/openapi.json']
