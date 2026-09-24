import json
import os
from datetime import datetime, timedelta, timezone
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
    """Which store the loaders read.

    `demo` is a third source rather than a flag on the mock fleet: the demonstration ships
    its own machine, and adding it to `app/mock_data/` would change the fixture every other
    test and the offline walkthrough depend on — including tests that pick a machine by
    model, which a second XE55U would silently make ambiguous.
    """
    from app.request_data_mode import selected_mode
    request_mode = selected_mode()
    if request_mode == 'demo':
        return 'demo'
    if request_mode == 'live':
        # An empty live cache remains empty; it must never fall back to mock data.
        return 'trackunit_cache'
    configured = os.getenv("DATA_SOURCE", "mock")
    if configured == "demo":
        return "demo"
    if configured == "trackunit_cache" and cache_exists():
        return "trackunit_cache"
    if cache_exists() and configured != "mock":
        return "trackunit_cache"
    return "mock"


DEMO_DIR = ROOT / "app" / "demo_data"
DEMO_MACHINES = DEMO_DIR / "machines.json"
DEMO_TELEMETRY = DEMO_DIR / "telemetry_snapshots.json"
DEMO_FAULTS = DEMO_DIR / "fault_codes.json"


def _demo_rows_with_recent_timestamps(path: Path, *fields: str) -> list[dict]:
    """Replay the synthetic case near now without changing its original intervals."""
    rows = _read_json(path)
    source_samples = _read_json(DEMO_TELEMETRY)
    timestamps = [datetime.fromisoformat(row['recorded_at'].replace('Z', '+00:00'))
                  for row in source_samples if row.get('recorded_at')]
    if not timestamps:
        return rows
    # One shared, hour-stable offset keeps machine, telemetry and fault loaders aligned.
    anchor = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(minutes=10)
    offset = anchor - max(timestamps)
    for row in rows:
        for field in fields:
            if value := row.get(field):
                instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
                row[field] = (instant + offset).isoformat().replace('+00:00', 'Z')
    return rows


def _is_demo_cache_machine(row: dict) -> bool:
    """Old sample imports may reside in the Trackunit cache; never show them as live."""
    return (str(row.get('serial_number') or '').upper().startswith('SIM-') or
            str(row.get('customer') or '').startswith('演示客户') or
            str(row.get('location') or '').startswith('模拟作业区'))


def load_machines() -> list[Machine]:
    source = get_data_source()
    if source == "trackunit_cache":
        rows = _read_json(MACHINES_CACHE)
        from app.request_data_mode import selected_mode
        if selected_mode() == 'live':
            rows = [row for row in rows if not _is_demo_cache_machine(row)]
        return [Machine(**item) for item in rows]
    if source == "demo":
        return [Machine(**item) for item in _demo_rows_with_recent_timestamps(DEMO_MACHINES, 'last_seen_at')]
    return load_mock_machines()


def load_telemetry() -> list[TelemetrySnapshot]:
    source = get_data_source()
    if source == "trackunit_cache":
        rows = _read_json(TELEMETRY_CACHE)
        from app.request_data_mode import selected_mode
        if selected_mode() == 'live':
            allowed = {machine.machine_id for machine in load_machines()}
            rows = [row for row in rows if row.get('machine_id') in allowed]
        return [TelemetrySnapshot(**item) for item in rows]
    if source == "demo":
        return [TelemetrySnapshot(**item) for item in _demo_rows_with_recent_timestamps(DEMO_TELEMETRY, 'recorded_at')]
    return load_mock_telemetry()


def load_faults() -> list[FaultCode]:
    source = get_data_source()
    if source == "trackunit_cache":
        rows = _read_json(FAULTS_CACHE)
        from app.request_data_mode import selected_mode
        if selected_mode() == 'live':
            allowed = {machine.machine_id for machine in load_machines()}
            rows = [row for row in rows if row.get('machine_id') in allowed]
        return [FaultCode(**item) for item in rows]
    if source == "demo":
        return [FaultCode(**item) for item in _demo_rows_with_recent_timestamps(DEMO_FAULTS, 'occurred_at')]
    return load_mock_faults()
