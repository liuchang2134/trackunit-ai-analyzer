"""Last completed investigation outcome; local metadata, never a provider probe."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

STATUS_PATH = Path(__file__).resolve().parents[1] / 'data/local/ai-request-status.json'
_lock = RLock()
FailureKind = Literal['daily_quota', 'minute_quota', 'quota_unavailable', 'quota_unknown',
                      'configuration_missing', 'configuration_invalid', 'authentication',
                      'service_unavailable', 'network', 'timeout', 'invalid_response', 'analysis_incomplete']


class QuotaLimit(BaseModel):
    model_config = ConfigDict(extra='ignore')
    window: Literal['day', 'minute']
    measure: Literal['requests', 'tokens']
    limit: int | None = Field(default=None, ge=0, le=10**12, strict=True)


class Failure(BaseModel):
    model_config = ConfigDict(extra='ignore')
    kind: FailureKind
    limits: list[QuotaLimit] = Field(default_factory=list, max_length=20)


class Attempt(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    provider: Literal['gemini', 'ollama_local']
    context_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    finished_at: AwareDatetime
    outcome: Literal['report_saved', 'report_unsaved', 'failed']
    failure: Failure | None = None
    source: Literal['application', 'prior_verification'] = 'application'

    @model_validator(mode='after')
    def consistent(self):
        if (self.outcome == 'failed') != (self.failure is not None):
            raise ValueError('Failure category must match outcome')
        if (self.source == 'application') != (self.context_id is not None):
            raise ValueError('Historical verification must not assert configuration identity')
        return self


def now_utc():
    return datetime.now(timezone.utc)


def capture_context() -> dict:
    from app.local_assistant import assistant_runtime
    runtime = assistant_runtime()
    values = [runtime['provider'], runtime['model'], os.getenv('GEMINI_BASE_URL', ''),
              os.getenv('GEMINI_API_KEY', ''), os.getenv('OLLAMA_BASE_URL', '')]
    return {'provider': runtime['provider'], 'model': runtime['model'],
            'configured': runtime['cloud_credentials_configured'] if runtime['provider'] == 'gemini' else True,
            'context_id': sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()}


def _read(now):
    try:
        if STATUS_PATH.stat().st_size > 8192:
            return None, 'invalid'
        record = Attempt.model_validate_json(STATUS_PATH.read_text(encoding='utf-8'))
        if record.finished_at > now:
            return None, 'invalid'
        return record, 'available'
    except FileNotFoundError:
        return None, 'missing'
    except (ValidationError, ValueError, UnicodeError):
        return None, 'invalid'
    except OSError:
        return None, 'unreadable'


def _public(record, context, now, state='available'):
    result = {'provider': context['provider'], 'model': context['model'], 'configured': context['configured'],
              'is_live_check': False, 'current_availability': 'not_verified',
              'record_state': state, 'last_attempt': None}
    if record is None:
        return result
    if record.provider != context['provider'] or (record.context_id and record.context_id != context['context_id']):
        result['record_state'] = 'other_configuration'
        return result
    result['last_attempt'] = {'finished_at': record.finished_at.isoformat(), 'outcome': record.outcome,
        'failure': record.failure.model_dump(exclude_none=True) if record.failure else None,
        'source': record.source, 'configuration_match': record.context_id == context['context_id'],
        'older_than_24h': (now - record.finished_at).total_seconds() > 86400}
    return result


def request_status(context: dict | None = None) -> dict:
    context = context or capture_context()
    now = now_utc()
    with _lock:
        record, state = _read(now)
    return _public(record, context, now, state)


def _failure(error):
    kind = getattr(error, 'kind', 'analysis_incomplete')
    details = getattr(error, 'provider_error', None)
    limits = []
    if isinstance(details, dict) and details.get('kind') in {'daily_quota', 'minute_quota', 'quota_unavailable', 'quota_unknown'}:
        kind = details['kind']
        supplied = details.get('limits', [])
        if isinstance(supplied, list):
            for item in supplied[:20]:
                try:
                    limits.append(QuotaLimit.model_validate(item))
                except (ValidationError, TypeError):
                    continue
    try:
        return Failure(kind=kind, limits=limits)
    except ValidationError:
        return Failure(kind='analysis_incomplete')


def record_outcome(context: dict, outcome: str, *, error=None) -> dict:
    if context['provider'] not in {'gemini', 'ollama_local'}:
        return {**_public(None, context, now_utc(), 'unsupported_configuration'), 'recording_saved': False}
    written = False
    temporary = None
    with _lock:
        now = now_utc()
        record = Attempt(provider=context['provider'], context_id=context['context_id'], finished_at=now,
                         outcome=outcome, failure=_failure(error) if outcome == 'failed' else None)
        try:
            STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=STATUS_PATH.parent,
                                             prefix='.ai-status-', suffix='.tmp', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(record.model_dump_json())
            os.replace(temporary, STATUS_PATH)
            written = True
        except OSError:
            pass  # An optional status record must not turn a usable report into a failure.
        finally:
            if temporary:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
    return {**_public(record, context, now), 'recording_saved': written}
