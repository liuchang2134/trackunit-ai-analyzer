"""DeepSeek's official Chat Completions API, with bounded retries and JSON output."""

import contextvars
import json
import math
import os
import random
import re
import time

import httpx


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-flash"

# Cooperative cancellation for one in-flight investigation. A worker thread sets
# a token; every request this module starts observes it before and while reading
# the response, so a cancelled request closes upstream instead of running on and
# only being discarded at the end. Unset by default so existing callers keep the
# exact previous behaviour.
_cancel_check: contextvars.ContextVar = contextvars.ContextVar('deepseek_cancel_check', default=None)


class InvestigationCancelled(Exception):
    """The caller withdrew the request; nothing further should be sent upstream."""


def cancellation_scope(should_cancel):
    """Install a cancellation predicate for requests started in this context."""
    return _cancel_check.set(should_cancel)


def reset_cancellation_scope(token) -> None:
    _cancel_check.reset(token)


def _check_cancelled() -> None:
    check = _cancel_check.get()
    if check is not None and check():
        raise InvestigationCancelled('investigation cancelled by the caller')


class DeepSeekError(Exception):
    def __init__(self, message: str, *, attempts: int = 0, provider_error: dict | None = None,
                 kind: str = 'analysis_incomplete'):
        super().__init__(message)
        self.attempts = attempts
        self.provider_error = provider_error
        self.kind = kind


def get_deepseek_base_url() -> str:
    return os.getenv('DEEPSEEK_BASE_URL', DEFAULT_DEEPSEEK_BASE_URL).strip().rstrip('/')


def get_deepseek_model() -> str:
    return os.getenv('DEEPSEEK_MODEL', DEFAULT_DEEPSEEK_MODEL).strip()


def get_deepseek_api_key() -> str:
    return os.getenv('DEEPSEEK_API_KEY', '').strip()


def generate_with_deepseek(prompt: str, timeout_seconds: float = 120.0) -> str:
    return _generate({'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 4096}, timeout_seconds)


def _schema_example(schema: dict):
    """A format example only; the caller still validates every actual decision."""
    if schema.get('enum'):
        return schema['enum'][0]
    if schema.get('type') == 'object':
        return {key: _schema_example(value) for key, value in schema.get('properties', {}).items()}
    if schema.get('type') == 'array':
        return []
    if schema.get('type') in {'integer', 'number'}:
        return 0
    if schema.get('type') == 'boolean':
        return False
    if schema.get('type') == 'null':
        return None
    return ''


def generate_structured_with_deepseek(messages: list[dict], schema: dict,
                                      timeout_seconds: float = 60.0) -> str:
    # Only role/content cross the provider boundary; local decision metadata does not.
    wire_messages = []
    for message in messages:
        role, content = message.get('role'), message.get('content')
        if role not in {'system', 'user', 'assistant'} or not isinstance(content, str):
            raise DeepSeekError('DeepSeek requires text messages with a supported role.', kind='configuration_invalid')
        wire_messages.append({'role': role, 'content': content})
    instruction = (
        'Return one complete JSON object, without markdown or additional text. '
        'Follow this JSON Schema exactly; only use the allowed actions and identifiers. '
        'The example illustrates the format, not the decision to make.\n'
        'JSON Schema: ' + json.dumps(schema, ensure_ascii=False, separators=(',', ':')) + '\n'
        'Example JSON format: ' + json.dumps(_schema_example(schema), ensure_ascii=False, separators=(',', ':'))
    )
    wire_messages.insert(0, {'role': 'system', 'content': instruction})
    if not any(message['role'] == 'user' for message in wire_messages):
        wire_messages.append({'role': 'user', 'content': 'Choose the next decision from the supplied JSON Schema.'})
    output_tokens = 4096 if 'component_hypotheses' in schema.get('properties', {}) else 2048
    return _generate({'messages': wire_messages, 'max_tokens': output_tokens,
                      'response_format': {'type': 'json_object'}}, timeout_seconds)


def _http_failure(status: int) -> tuple[str, str]:
    if status in {401, 403}:
        return 'authentication', 'DeepSeek API key is invalid or not allowed. Check DEEPSEEK_API_KEY.'
    if status == 402:
        return 'insufficient_balance', 'DeepSeek account balance is insufficient. Check the API account balance.'
    if status == 429:
        return 'rate_limit', 'DeepSeek API rate limit was exceeded. Please retry later.'
    if status >= 500:
        return 'service_unavailable', f'DeepSeek returned HTTP {status}. The service is temporarily unavailable; retry later.'
    return 'configuration_invalid', f'DeepSeek returned HTTP {status}. Check DEEPSEEK_MODEL and the request configuration.'


def _raise_http_error(response: httpx.Response, attempts: int, *, time_limit: bool = False):
    kind, message = _http_failure(response.status_code)
    # Never expose the provider body: it can echo submitted data or credentials.
    suffix = ' Time limit reached.' if time_limit else ''
    raise DeepSeekError(f'{message} Attempts: {attempts}.{suffix}', attempts=attempts, kind=kind)


def _post_completion(url: str, headers: dict, body: dict, timeout: float) -> httpx.Response:
    """POST one completion.

    Cancellation is checked before the request is sent and again immediately
    after the response arrives, so a withdrawn investigation stops issuing model
    calls and discards an in-flight answer instead of continuing to build a
    report. One already-sent HTTP request still has to finish at the provider,
    because httpx.post reads the whole body before returning; this module does
    not claim to abort that single upstream request mid-body.
    """
    _check_cancelled()
    response = httpx.post(url, headers=headers, json=body, timeout=timeout, follow_redirects=False)
    _check_cancelled()
    return response


def _generate(payload: dict, timeout_seconds: float) -> str:
    key, model, base_url = get_deepseek_api_key(), get_deepseek_model(), get_deepseek_base_url()
    if not key:
        raise DeepSeekError('DEEPSEEK_API_KEY is not configured. Add it to .env and restart the backend.',
                            kind='configuration_missing')
    if base_url not in {DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_BASE_URL + '/v1'} or not re.fullmatch(r'[A-Za-z0-9._-]+', model):
        raise DeepSeekError('DeepSeek requires the configured official HTTPS endpoint and a valid model name.',
                            kind='configuration_invalid')
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise DeepSeekError('DeepSeek request timed out within its time limit.', kind='timeout')
    # Thinking is enabled by the provider by default; this assistant explicitly uses non-thinking mode.
    body = {**payload, 'model': model, 'thinking': {'type': 'disabled'}, 'temperature': 0, 'stream': False}
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'}
    deadline = time.monotonic() + min(timeout_seconds, 120.0)
    attempts = 0
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DeepSeekError('DeepSeek request timed out within its time limit.', attempts=attempts, kind='timeout')
        attempts += 1
        try:
            response = _post_completion(base_url + '/chat/completions', headers, body, min(45.0, remaining))
        except httpx.TimeoutException:
            # A timed-out request may already have been processed. Never retry it automatically.
            raise DeepSeekError('DeepSeek request timed out. Please retry or use a smaller question.',
                                attempts=attempts, kind='timeout') from None
        except httpx.HTTPError:
            raise DeepSeekError('DeepSeek network request failed. Please check internet access.',
                                attempts=attempts, kind='network') from None
        if time.monotonic() >= deadline:
            raise DeepSeekError('DeepSeek request timed out within its time limit.', attempts=attempts, kind='timeout')
        if response.status_code == 200:
            break
        if response.status_code not in {500, 502, 503, 504} or attempt == 2:
            _raise_http_error(response, attempts)
        delay = 2 ** (attempt + 1) + random.uniform(0, 0.5)
        retry_after = response.headers.get('Retry-After', '')
        if retry_after:
            try:
                requested_delay = float(retry_after)
                if not math.isfinite(requested_delay) or requested_delay < 0:
                    raise ValueError
                delay = max(delay, requested_delay)
            except (ValueError, TypeError):
                # Do not retry early if the server delay is unrecognised (including HTTP dates).
                _raise_http_error(response, attempts)
        if delay >= deadline - time.monotonic():
            _raise_http_error(response, attempts, time_limit=True)
        time.sleep(delay)

    try:
        data = response.json()
        choice = data['choices'][0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError('incomplete response')
        content = choice['message']['content']
        if not isinstance(content, str) or not content.strip():
            raise ValueError('missing content')
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise DeepSeekError('DeepSeek returned an empty, invalid or incomplete response. Please retry with a narrower question.',
                            attempts=attempts, kind='invalid_response') from None
    return content.strip()
