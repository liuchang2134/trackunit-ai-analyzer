import os

import httpx


DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"


class GeminiError(Exception):
    pass


def get_gemini_base_url() -> str:
    return os.getenv("GEMINI_BASE_URL", DEFAULT_GEMINI_BASE_URL).rstrip("/")


def get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def get_gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "")


def generate_with_gemini(prompt: str, timeout_seconds: float = 120.0) -> str:
    api_key = get_gemini_api_key()
    model = get_gemini_model()
    if not api_key:
        raise GeminiError("GEMINI_API_KEY is not configured. Add it to .env and restart the backend.")

    url = f"{get_gemini_base_url()}/models/{model}:generateContent"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key,
    }

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout_seconds)
    except httpx.ConnectError as exc:
        raise GeminiError("Cannot connect to Gemini API. Please check internet access.") from exc
    except httpx.TimeoutException as exc:
        raise GeminiError("Gemini request timed out. Please retry or use a smaller prompt.") from exc
    except httpx.HTTPError as exc:
        raise GeminiError(f"Gemini request failed: {exc}") from exc

    if response.status_code != 200:
        raise GeminiError(_format_error(response, model))

    try:
        data = response.json()
    except ValueError as exc:
        raise GeminiError("Gemini returned invalid JSON.") from exc

    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiError("Gemini response did not include generated text.") from exc

    text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise GeminiError("Gemini response text is empty.")
    return text


def _format_error(response: httpx.Response, model: str) -> str:
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message", "")
    except ValueError:
        message = response.text

    if response.status_code in {400, 404} and "model" in message.lower():
        return f"Gemini model {model} is not available. Check GEMINI_MODEL in .env."
    if response.status_code in {401, 403}:
        return "Gemini API key is invalid or not allowed. Create a new key and update GEMINI_API_KEY."
    if response.status_code == 429:
        return "Gemini API rate limit or free quota was exceeded. Retry later or switch provider."
    return f"Gemini returned HTTP {response.status_code}: {message or 'No error details available.'}"
