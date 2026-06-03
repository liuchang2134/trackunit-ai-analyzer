import httpx
import pytest

from app.trackunit_client import TrackunitClient, TrackunitError


def test_trackunit_credentials_missing(monkeypatch):
    for name in [
        "TRACKUNIT_AUTH_URL",
        "TRACKUNIT_CLIENT_ID",
        "TRACKUNIT_CLIENT_SECRET",
        "TRACKUNIT_USERNAME",
        "TRACKUNIT_PASSWORD",
    ]:
        monkeypatch.delenv(name, raising=False)

    client = TrackunitClient()

    with pytest.raises(TrackunitError, match="Trackunit credentials are missing"):
        client.get_token()


def test_trackunit_auth_success(monkeypatch):
    monkeypatch.setenv("TRACKUNIT_AUTH_URL", "https://auth.example/token")
    monkeypatch.setenv("TRACKUNIT_CLIENT_ID", "client")
    monkeypatch.setenv("TRACKUNIT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TRACKUNIT_USERNAME", "user")
    monkeypatch.setenv("TRACKUNIT_PASSWORD", "pass")

    def fake_post(url, data, headers, timeout):
        return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = TrackunitClient()

    assert client.get_token() == "token"


def test_trackunit_endpoint_not_configured(monkeypatch):
    monkeypatch.delenv("TRACKUNIT_FLEET_SNAPSHOT_ENDPOINT", raising=False)
    client = TrackunitClient()

    with pytest.raises(TrackunitError, match="Trackunit API endpoint is not configured"):
        client.get_configured_endpoint("TRACKUNIT_FLEET_SNAPSHOT_ENDPOINT")
