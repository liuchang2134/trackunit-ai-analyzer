import httpx
import pytest

from app.ollama_client import OllamaError, generate_with_ollama


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_generate_with_ollama_returns_response(monkeypatch):
    def fake_post(url, json, timeout):
        assert url == "http://127.0.0.1:11434/api/generate"
        assert json["model"] == "qwen2.5:7b"
        assert json["stream"] is False
        return DummyResponse(payload={"response": "AI report text"})

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(httpx, "post", fake_post)

    assert generate_with_ollama("prompt") == "AI report text"


def test_generate_with_ollama_not_running(monkeypatch):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(OllamaError, match="Ollama is not running"):
        generate_with_ollama("prompt")


def test_generate_with_ollama_model_not_available(monkeypatch):
    def fake_post(url, json, timeout):
        return DummyResponse(status_code=404, payload={"error": "model not found"})

    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(OllamaError, match="ollama pull qwen2.5:7b"):
        generate_with_ollama("prompt")

