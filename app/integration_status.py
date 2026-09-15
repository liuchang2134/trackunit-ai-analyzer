"""Public-safe summary of the last explicit integration verification, not a live probe."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

STATUS_PATH = Path(__file__).resolve().parents[1] / "data/local/integration-status.json"


class Capability(BaseModel):
    name: Literal["operating_hours", "idle_hours", "fault_events"]
    status: Literal["data", "empty", "unauthorized", "rate_limited", "error", "not_checked"]
    record_count: int | None = Field(default=None, ge=0)
    http_status: int | None = Field(default=None, ge=100, le=599)


class Verification(BaseModel):
    checked_at: datetime
    window_start: datetime
    window_end: datetime
    capabilities: list[Capability] = Field(max_length=3)


def integration_status() -> dict:
    fallback = {"status": "not_verified", "checked_at": None, "capabilities": [],
                "scope": "single_sample_verification", "is_live_check": False}
    try:
        verified = Verification.model_validate_json(STATUS_PATH.read_text(encoding="utf-8"))
        if any(t.tzinfo is None for t in (verified.checked_at, verified.window_start, verified.window_end)):
            return fallback
        if verified.window_start > verified.window_end or verified.checked_at > datetime.now(timezone.utc):
            return fallback
    except (OSError, ValidationError):
        return fallback
    age = (datetime.now(timezone.utc) - verified.checked_at).total_seconds()
    return {**verified.model_dump(mode="json"), "status": "last_verified", "is_live_check": False,
            "scope": "single_sample_verification", "older_than_24h": age > 86400}
