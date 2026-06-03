from app import ai_provider


def test_default_ai_provider_is_ollama_local(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(ai_provider, "generate_with_ollama", lambda prompt: "real local model report")

    result = ai_provider.generate_machine_report("sample prompt")

    assert result["provider"] == "ollama_local"
    assert result["model"] == "qwen2.5:7b"
    assert result["report_markdown"] == "real local model report"
    assert result["error"] is None


def test_ollama_provider_success(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama_local")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(ai_provider, "generate_with_ollama", lambda prompt: "local model report")

    result = ai_provider.generate_fleet_report("fleet prompt")

    assert result["provider"] == "ollama_local"
    assert result["model"] == "qwen2.5:7b"
    assert result["report_markdown"] == "local model report"
    assert result["error"] is None


def test_ollama_provider_returns_clear_error(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama_local")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")

    def fake_generate(prompt):
        raise ai_provider.OllamaError("Ollama is not running. Please start Ollama and retry.")

    monkeypatch.setattr(ai_provider, "generate_with_ollama", fake_generate)

    result = ai_provider.generate_machine_report("machine prompt")

    assert result["provider"] == "ollama_local"
    assert result["model"] == "qwen2.5:7b"
    assert result["report_markdown"] == ""
    assert result["error"] == "Ollama is not running. Please start Ollama and retry."


def test_gemini_provider_success(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-flash-latest")
    monkeypatch.setattr(ai_provider, "generate_with_gemini", lambda prompt: "gemini report")

    result = ai_provider.generate_fleet_report("fleet prompt")

    assert result["provider"] == "gemini"
    assert result["model"] == "gemini-flash-latest"
    assert result["report_markdown"] == "gemini report"
    assert result["error"] is None


def test_provider_override_uses_gemini(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama_local")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-flash-latest")
    monkeypatch.setattr(ai_provider, "generate_with_gemini", lambda prompt: "override report")

    result = ai_provider.generate_machine_report("machine prompt", provider_override="gemini")

    assert result["provider"] == "gemini"
    assert result["report_markdown"] == "override report"


def test_unknown_provider_is_not_supported(monkeypatch):
    result = ai_provider.generate_fleet_report("fleet prompt", provider_override="unsupported_provider")

    assert result["provider"] == "unsupported_provider"
    assert result["report_markdown"] == ""
    assert "Unsupported AI_PROVIDER" in result["error"]
