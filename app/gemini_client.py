import os
import re
import random
import time

import httpx
from app.gemini_quota import quota_failure


DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"


class GeminiError(Exception):
    def __init__(self, message: str, *, attempts: int = 0, provider_error: dict | None = None,
                 kind: str = 'analysis_incomplete'):
        super().__init__(message)
        self.attempts = attempts
        self.provider_error = provider_error
        self.kind = kind


def _http_failure_kind(status):
    if status == 429: return 'quota_unknown'
    if status in {401, 403}: return 'authentication'
    if status >= 500: return 'service_unavailable'
    return 'configuration_invalid'


def get_gemini_base_url() -> str:
    return os.getenv("GEMINI_BASE_URL", DEFAULT_GEMINI_BASE_URL).rstrip("/")


def get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def get_gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "")


def generate_with_gemini(prompt: str, timeout_seconds: float = 120.0) -> str:
    return _generate({'contents': [{'parts': [{'text': prompt}]}]}, timeout_seconds)


def generate_structured_with_gemini(messages: list[dict], schema: dict, timeout_seconds: float = 60.0) -> str:
    """Preserve application instructions and decision history without transmitting private metadata."""
    system = []
    contents = []
    for message in messages:
        if message['role'] == 'system':
            system.append({'text': message['content']})
            continue
        role = 'model' if message['role'] == 'assistant' else 'user'
        part = {'text': message['content']}
        if contents and contents[-1]['role'] == role:
            contents[-1]['parts'].append(part)
        else:
            contents.append({'role': role, 'parts': [part]})
    # Length constraints remain enforced by Pydantic after generation.
    def supported(value):
        if isinstance(value, dict):
            # Enforce empty allowlists locally. Earlier capacity failures did
            # not establish that zero-length array constraints caused them.
            return {k: supported(v) for k, v in value.items()
                    if k not in {'default', 'maxLength', 'minLength'} and not (k == 'maxItems' and v == 0)}
        if isinstance(value, list):
            return [supported(v) for v in value]
        return value
    payload = {'contents': contents or [{'role': 'user', 'parts': [{'text': 'Choose the next decision.'}]}],
               'generationConfig': {'temperature': 0, 'maxOutputTokens': 4096,
                                    'responseMimeType': 'application/json', 'responseJsonSchema': supported(schema)}}
    if system:
        payload['systemInstruction'] = {'parts': system}
    return _generate(payload, timeout_seconds)


def _generate(payload: dict, timeout_seconds: float) -> str:
    api_key = get_gemini_api_key()
    model = get_gemini_model()
    if not api_key:
        raise GeminiError("GEMINI_API_KEY is not configured. Add it to .env and restart the backend.", kind='configuration_missing')

    if get_gemini_base_url() != DEFAULT_GEMINI_BASE_URL or not re.fullmatch(r'[A-Za-z0-9._-]+', model):
        raise GeminiError('Gemini requires the configured official HTTPS endpoint and a valid model name.', kind='configuration_invalid')
    url = f"{DEFAULT_GEMINI_BASE_URL}/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key,
    }

    deadline = time.monotonic() + timeout_seconds
    attempts = 0
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GeminiError('Gemini request timed out within its time limit.', attempts=attempts, kind='timeout')
        attempts += 1
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=min(45.0, remaining))
        except httpx.ConnectError as exc:
            raise GeminiError('Cannot connect to Gemini API. Please check internet access.', attempts=attempts, kind='network') from exc
        except httpx.TimeoutException as exc:
            # The server may already have processed a timed-out request.
            raise GeminiError('Gemini request timed out. Please retry or use a smaller prompt.', attempts=attempts, kind='timeout') from exc
        except httpx.HTTPError:
            raise GeminiError('Gemini network request failed.', attempts=attempts, kind='network') from None
        if response.status_code == 200:
            break
        if response.status_code not in {500, 502, 503, 504} or attempt == 2:
            raise GeminiError(_format_error(response, model) + f' Attempts: {attempts}.', attempts=attempts,
                              provider_error=quota_failure(response), kind=_http_failure_kind(response.status_code))
        delay = 2 ** (attempt + 1) + random.uniform(0, 0.5)
        retry_after = getattr(response, 'headers', {}).get('Retry-After', '')
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except (TypeError, ValueError):
                # An unparsed server delay is not permission to retry early.
                raise GeminiError(_format_error(response, model) + f' Attempts: {attempts}.', attempts=attempts,
                                  kind=_http_failure_kind(response.status_code)) from None
        if delay >= deadline - time.monotonic():
            raise GeminiError(_format_error(response, model) + f' Attempts: {attempts}. Time limit reached.', attempts=attempts,
                              kind=_http_failure_kind(response.status_code))
        time.sleep(delay)

    try:
        data = response.json()
    except ValueError as exc:
        raise GeminiError("Gemini returned invalid JSON.", kind='invalid_response') from exc

    try:
        candidate = data["candidates"][0]
        if candidate.get('finishReason') not in {None, 'STOP'}:
            raise GeminiError('Gemini did not complete its response. Please retry with a narrower question.', kind='invalid_response')
        parts = candidate["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiError("Gemini response did not include generated text.", kind='invalid_response') from exc

    text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict) and not part.get('thought')).strip()
    if not text:
        raise GeminiError("Gemini response text is empty.", kind='invalid_response')
    return text


def _format_error(response: httpx.Response, model: str) -> str:
    try:
        payload = response.json()
        message = str(payload.get("error", {}).get("message", ""))
    except (ValueError, AttributeError, TypeError):
        message = response.text

    if response.status_code in {400, 404} and "model" in message.lower():
        return f"Gemini model {model} is not available. Check GEMINI_MODEL in .env."
    if response.status_code in {401, 403} or 'api key not valid' in message.lower():
        return "Gemini API key is invalid or not allowed. Create a new key and update GEMINI_API_KEY."
    if response.status_code == 429:
        return "Gemini API rate limit or quota was exceeded. Retry later or check the project quota."
    if response.status_code >= 500:
        return f"Gemini returned HTTP {response.status_code}. The request could not be completed; retry later."
    return f"Gemini returned HTTP {response.status_code}. Check the API configuration and request schema."
