import httpx
import pytest

from app.gemini_client import GeminiError, generate_with_gemini


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
