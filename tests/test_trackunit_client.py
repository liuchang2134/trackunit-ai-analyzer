import httpx
import pytest
from app.trackunit_client import TrackunitClient, TrackunitError


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    import os
    for name in list(os.environ):
        if name.startswith("TRACKUNIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("TRACKUNIT_CLIENT_ID", "client")
    monkeypatch.setenv("TRACKUNIT_CLIENT_SECRET", "secret")
    TrackunitClient._shared_access_token = None
    TrackunitClient._shared_expires_at = 0
    TrackunitClient._shared_credential_key = None
    yield
    TrackunitClient._shared_access_token = None


def test_credentials_missing(monkeypatch):
    monkeypatch.delenv("TRACKUNIT_CLIENT_SECRET")
    with pytest.raises(TrackunitError, match="credentials are missing"):
        TrackunitClient().get_token()


def test_v2_and_cache_renewal(monkeypatch):
    now = [1000.0]
    calls = []
    monkeypatch.setattr("app.trackunit_client.time.monotonic", lambda: now[0])
    def post(url, data, headers, timeout):
        assert url == "https://auth.trackunit.com/token/v2"
        assert data["grant_type"] == "client_credentials"
        assert data["client_id"] == "client" and data["client_secret"] == "secret"
        assert "username" not in data and "password" not in data
        assert set(data["scope"].split()) == {"api.iso15143.snapshot", "api.iso15143.timeseries", "asset.view", "account.event.view"}
        calls.append(data)
        return httpx.Response(200, json={"access_token": f"token{len(calls)}", "expires_in": 1200})
    monkeypatch.setattr(httpx, "post", post)
    a, b = TrackunitClient(), TrackunitClient()
    assert a.get_token() == b.get_token() == "token1"
    now[0] = 2139
    assert a.get_token() == "token1"
    now[0] = 2141
    assert b.get_token() == a.get_token() == "token2"
    assert len(calls) == 2


def test_401_reauth(monkeypatch):
    tokens, requests = [], []
    def post(*args, **kwargs):
        tokens.append(1)
        return httpx.Response(200, json={"access_token": f"t{len(tokens)}", "expires_in": 1200})
    def request(method, url, **kwargs):
        requests.append(kwargs["headers"]["Authorization"])
        return httpx.Response(401 if len(requests) == 1 else 200, json={"equipment": []})
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "request", request)
    assert TrackunitClient(retries=1).request("GET", "https://iris.trackunit.com/test") == {"equipment": []}
    assert requests == ["Bearer t1", "Bearer t2"]


@pytest.mark.parametrize("payload,status", [({"error": "invalid_scope", "error_description": "secret"}, 400), ({"access_token": "private-token", "expires_in": "bad"}, 200), ({"access_token": "private-token", "expires_in": 0}, 200)])
def test_safe_auth_failure(monkeypatch, payload, status):
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(status, json=payload))
    with pytest.raises(TrackunitError) as exc:
        TrackunitClient().get_token()
    assert "secret" not in str(exc.value) and "private-token" not in str(exc.value)


def test_legacy_explicit(monkeypatch):
    monkeypatch.setenv("TRACKUNIT_AUTH_GRANT_TYPE", "password")
    monkeypatch.setenv("TRACKUNIT_AUTH_URL", "https://auth.example/token")
    monkeypatch.setenv("TRACKUNIT_USERNAME", "user")
    monkeypatch.setenv("TRACKUNIT_PASSWORD", "pass")
    def post(url, data, headers, timeout):
        assert data == {"grant_type": "password", "username": "user", "password": "pass", "scope": "api"}
        assert headers["Authorization"].startswith("Basic ")
        return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
    monkeypatch.setattr(httpx, "post", post)
    assert TrackunitClient().get_token() == "token"


def test_credentials_change(monkeypatch):
    calls = []
    def post(*a, **kw):
        calls.append(1)
        return httpx.Response(200, json={"access_token": str(len(calls)), "expires_in": 1200})
    monkeypatch.setattr(httpx, "post", post)
    assert TrackunitClient().get_token() == "1"
    monkeypatch.setenv("TRACKUNIT_CLIENT_SECRET", "different")
    assert TrackunitClient().get_token() == "2"


def test_endpoint_missing():
    with pytest.raises(TrackunitError, match="endpoint is not configured"):
        TrackunitClient().get_configured_endpoint("TRACKUNIT_FAULTS_ENDPOINT")
