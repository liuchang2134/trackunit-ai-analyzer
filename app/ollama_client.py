import os

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b"


class OllamaError(Exception):
    pass


def get_ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def get_ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)


def generate_with_ollama(prompt: str, timeout_seconds: float = 120.0) -> str:
    base_url = get_ollama_base_url()
    model = get_ollama_model()
    url = f"{base_url}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    try:
        response = httpx.post(url, json=payload, timeout=timeout_seconds)
    except httpx.ConnectError as exc:
        raise OllamaError("Ollama is not running. Please start Ollama and try again.") from exc
    except httpx.TimeoutException as exc:
        raise OllamaError("Ollama request timed out. Please retry or use a smaller prompt.") from exc
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollama request failed: {exc}") from exc

    if response.status_code == 404:
        raise OllamaError(f"Model {model} is not available. Please run: ollama pull {model}")

    if response.status_code != 200:
        error_text = ""
        try:
            error_text = response.json().get("error", "")
        except ValueError:
            error_text = response.text

        if "model" in error_text.lower() and ("not found" in error_text.lower() or "not available" in error_text.lower()):
            raise OllamaError(f"Model {model} is not available. Please run: ollama pull {model}")

        raise OllamaError(f"Ollama returned HTTP {response.status_code}: {error_text or 'No error details available.'}")

    try:
        data = response.json()
    except ValueError as exc:
        raise OllamaError("Ollama returned invalid JSON.") from exc

    if "error" in data and data["error"]:
        error_text = str(data["error"])
        if "model" in error_text.lower() and ("not found" in error_text.lower() or "not available" in error_text.lower()):
            raise OllamaError(f"Model {model} is not available. Please run: ollama pull {model}")
        raise OllamaError(error_text)

    generated = data.get("response")
    if not generated:
        raise OllamaError("Ollama response did not include generated text.")

    return generated
