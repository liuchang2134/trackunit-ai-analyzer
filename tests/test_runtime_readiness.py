import pytest
from scripts import check_local_runtime as runtime


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(runtime.importlib.util,'find_spec',lambda _:object())
    for key in ('GEMINI_API_KEY','GEMINI_BASE_URL','GEMINI_MODEL','OLLAMA_BASE_URL','OLLAMA_MODEL',
                'DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL','DEEPSEEK_MODEL'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setattr(runtime,'urlopen',lambda *args,**kw:pytest.fail('Readiness must not contact a provider'))


def test_blank_key_keeps_cloud_unready_but_explicit_demo_can_start():
    result=runtime.check()
    assert result['local_ready'] and not result['ai_ready'] and not result['ready']
    demo=runtime.check(demo_only=True)
    assert demo['ready'] and not demo['ai_ready']
    assert demo['mode']=='local_demo' and demo['authentication_verified'] is False


def test_configured_key_is_not_claimed_as_authenticated(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','unit-test-placeholder')
    result=runtime.check()
    assert result['ready'] and result['api_key_configured']
    assert result['authentication_verified'] is False
    assert 'unit-test-placeholder' not in str(result)


def test_missing_dependencies_blocks_demo(monkeypatch):
    monkeypatch.setattr(runtime.importlib.util,'find_spec',lambda name:None if name=='httpx' else object())
    result=runtime.check(demo_only=True)
    assert not result['ready'] and not result['local_ready']
    assert result['missing_dependencies']==['httpx']


@pytest.mark.parametrize('version',[(3,10,9),(3,14,0)])
def test_unsupported_python_is_explicit(version,monkeypatch):
    monkeypatch.setattr(runtime.sys,'version_info',version)
    assert runtime.check(demo_only=True)['python_supported'] is False
    assert runtime.check(demo_only=True)['ready'] is False


def test_invalid_endpoint_and_provider_do_not_become_demo_ready(monkeypatch):
    monkeypatch.setenv('GEMINI_BASE_URL','https://unapproved.example')
    assert runtime.check(demo_only=True)['ready'] is False
    monkeypatch.setenv('AI_PROVIDER','unknown')
    assert runtime.check(demo_only=True)['ready'] is False


def test_explicit_local_demo_does_not_query_legacy_ollama(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','ollama_local')
    report=runtime.check(demo_only=True)
    assert report['ready'] and not report['ai_ready'] and report['ollama']=='not_checked'


def test_deepseek_default_allows_demo_without_claiming_cloud_authentication(monkeypatch):
    monkeypatch.delenv('AI_PROVIDER')
    result = runtime.check()
    assert result['provider'] == 'deepseek' and result['model'] == 'deepseek-flash'
    assert not result['ready'] and not result['authentication_verified']
    assert runtime.check(demo_only=True)['ready']
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'unit-test-placeholder')
    result = runtime.check()
    assert result['ready'] and result['thinking_enabled'] is False
    assert not result['authentication_verified'] and 'unit-test-placeholder' not in str(result)


@pytest.mark.parametrize('base', ['https://unapproved.example', 'http://api.deepseek.com',
                                 'https://api.deepseek.com.evil.example', 'https://api.deepseek.com/?x=1'])
def test_deepseek_unapproved_endpoint_is_never_ready(monkeypatch, base):
    monkeypatch.setenv('AI_PROVIDER', 'deepseek')
    monkeypatch.setenv('DEEPSEEK_BASE_URL', base)
    assert runtime.check(demo_only=True)['ready'] is False
