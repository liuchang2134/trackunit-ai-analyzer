import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.models import FaultCode, Machine, TelemetrySnapshot
from app.normalizer import load_fault_codes as load_mock_faults
from app.normalizer import load_machines as load_mock_machines
from app.normalizer import load_telemetry_snapshots as load_mock_telemetry


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

CACHE_DIR = ROOT / "data" / "cache"
MACHINES_CACHE = CACHE_DIR / "machines_cache.json"
TELEMETRY_CACHE = CACHE_DIR / "telemetry_cache.json"
FAULTS_CACHE = CACHE_DIR / "faults_cache.json"
SYNC_LOGS = CACHE_DIR / "sync_logs.json"


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _to_jsonable(items: list[Any]) -> list[dict[str, Any]]:
    output = []
    for item in items:
        if hasattr(item, "model_dump"):
            output.append(item.model_dump())
        else:
            output.append(dict(item))
    return output


def _read_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, items: list[Any]) -> None:
    ensure_cache_dir()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_to_jsonable(items), handle, ensure_ascii=False, indent=2)


def save_machines(machines: list[Machine | dict[str, Any]]) -> None:
    _write_json(MACHINES_CACHE, machines)


def save_telemetry(telemetry: list[TelemetrySnapshot | dict[str, Any]]) -> None:
    _write_json(TELEMETRY_CACHE, telemetry)


def save_faults(faults: list[FaultCode | dict[str, Any]]) -> None:
    _write_json(FAULTS_CACHE, faults)


def append_sync_log(log: dict[str, Any]) -> None:
    ensure_cache_dir()
    logs = _read_json(SYNC_LOGS)
    logs.append({
        "created_at": datetime.now(timezone.utc).isoformat(),
        **log,
    })
    with SYNC_LOGS.open("w", encoding="utf-8") as handle:
        json.dump(logs, handle, ensure_ascii=False, indent=2)


def load_sync_logs() -> list[dict[str, Any]]:
    return _read_json(SYNC_LOGS)


def latest_successful_sync(sync_type: str = "fleet_snapshot") -> dict[str, Any] | None:
    logs = [
        log for log in load_sync_logs()
        if log.get("sync_type") == sync_type and log.get("status") == "success"
    ]
    if not logs:
        return None
    return logs[-1]


def cache_exists() -> bool:
    return MACHINES_CACHE.exists() or TELEMETRY_CACHE.exists() or FAULTS_CACHE.exists()


def cache_updated_at() -> str | None:
    paths = [path for path in (MACHINES_CACHE, TELEMETRY_CACHE, FAULTS_CACHE) if path.exists()]
    if not paths:
        return None
    latest_mtime = max(path.stat().st_mtime for path in paths)
    return datetime.fromtimestamp(latest_mtime, timezone.utc).isoformat()


def cache_age_seconds() -> float | None:
    paths = [path for path in (MACHINES_CACHE, TELEMETRY_CACHE, FAULTS_CACHE) if path.exists()]
    if not paths:
        return None
    latest_mtime = max(path.stat().st_mtime for path in paths)
    return max(datetime.now(timezone.utc).timestamp() - latest_mtime, 0.0)


def cache_status(ttl_seconds: int | None = None) -> dict[str, Any]:
    if ttl_seconds is None:
        ttl_seconds = int(os.getenv("TRACKUNIT_CACHE_TTL_SECONDS", "300"))
    age = cache_age_seconds()
    exists = cache_exists()
    return {
        "exists": exists,
        "data_source": get_data_source(),
        "updated_at": cache_updated_at(),
        "age_seconds": age,
        "ttl_seconds": ttl_seconds,
        "fresh": bool(exists and age is not None and age <= ttl_seconds),
        "latest_successful_sync": latest_successful_sync(),
    }


def get_data_source() -> str:
    configured = os.getenv("DATA_SOURCE", "mock")
    if configured == "trackunit_cache" and cache_exists():
        return "trackunit_cache"
    if cache_exists() and configured != "mock":
        return "trackunit_cache"
    return "mock"


def load_machines() -> list[Machine]:
    if get_data_source() == "trackunit_cache" and MACHINES_CACHE.exists():
        return [Machine(**item) for item in _read_json(MACHINES_CACHE)]
    return load_mock_machines()


def load_telemetry() -> list[TelemetrySnapshot]:
    if get_data_source() == "trackunit_cache" and TELEMETRY_CACHE.exists():
        return [TelemetrySnapshot(**item) for item in _read_json(TELEMETRY_CACHE)]
    return load_mock_telemetry()


def load_faults() -> list[FaultCode]:
    if get_data_source() == "trackunit_cache" and FAULTS_CACHE.exists():
        return [FaultCode(**item) for item in _read_json(FAULTS_CACHE)]
    return load_mock_faults()
