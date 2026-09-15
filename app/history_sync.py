"""Explicit read-only AEMP history sync from a previously saved equipment snapshot."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import os
import re
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
from app.aemp_history import normalize_hour_series
from app.local_datasets import LocalDataset, save_dataset
from app.trackunit_client import TrackunitClient, TrackunitError
from app.telemetry_evidence import timestamp

SOURCES = ROOT / "data/local/history-sources"
STATE_DIR = ROOT / "data/local/sync-state"
STATUS_PATH = ROOT / "data/local/integration-status.json"


def registered_sources() -> list[dict]:
    result = []
    for path in SOURCES.glob("*.json"):
        try:
            snapshot = load_source(path.stem)
            header = snapshot["EquipmentHeader"]
            result.append({"source_id": path.stem, "model": header["Model"],
                           "serial_number": header.get("SerialNumber", "未提供")})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return result


def load_source(source_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", source_id):
        raise ValueError("Invalid registered source")
    return json.loads((SOURCES / (source_id + ".json")).read_text(encoding="utf-8"))


def sync_registered_source(source_id: str, days: int) -> dict:
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 14:
        raise ValueError("Days must be between 1 and 14")
    snapshot = load_source(source_id)
    end = datetime.now(timezone.utc).replace(microsecond=0)
    return persist_sync_result(fetch_history(snapshot, end-timedelta(days=days), end,
                               TrackunitClient(retries=0), STATE_DIR))


def persist_sync_result(result: dict) -> dict:
    saved = save_dataset(result["dataset"]) if result["dataset"] else None
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=STATUS_PATH.parent, delete=False) as handle:
            temporary = handle.name
            json.dump(result["verification"], handle, indent=2)
        os.replace(temporary, STATUS_PATH)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return {"dataset_id": saved["dataset_id"] if saved else None,
            "sample_count": saved["sample_count"] if saved else 0, "verification": result["verification"]}


def fetch_history(snapshot: dict, start: datetime, end: datetime, client, state_dir: Path) -> dict:
    now = datetime.now(timezone.utc)
    if start.tzinfo is None or end.tzinfo is None or not start < end <= now or end-start > timedelta(days=14):
        raise ValueError("Use timezone-aware dates, start < end <= now, with a maximum 14-day window")
    header, metadata = snapshot.get("EquipmentHeader", {}), snapshot.get("metadata", {})
    identifier = header.get("PIN") or header.get("VIN") or metadata.get("telematicSerialNumber")
    identity = metadata.get("assetId")
    if not identifier or not identity or not header.get("Model"):
        raise ValueError("Snapshot requires OEM PIN/VIN/device serial, metadata.assetId and Model")
    state_dir.mkdir(parents=True, exist_ok=True)
    # Record the attempt before network work; failed requests can also consume quota.
    key = hashlib.sha256(str(identifier).encode()).hexdigest()
    guard = state_dir / (key + ".lock")
    try:
        handle = guard.open("x", encoding="utf-8")
    except FileExistsError:
        raise ValueError("A sync for this equipment is already running; inspect the local lock before retrying") from None
    with handle:
        handle.write(now.isoformat())
    try:
        stamp = state_dir / (key + ".last-attempt")
        if stamp.exists():
            last = timestamp(stamp.read_text(encoding="utf-8"))
            if last is None or now-last < timedelta(minutes=15):
                raise ValueError("Wait at least 15 minutes after the last history request for this equipment")
        stamp.write_text(now.isoformat(), encoding="utf-8")
        payloads, capabilities = {}, []
        for kind, name, field in (("CumulativeOperatingHours", "operating_hours", "cumulativeOperatingHours"),
                                  ("CumulativeIdleHours", "idle_hours", "cumulativeIdleHours")):
            endpoint = "https://iris.trackunit.com/public/api/aemp/v2/15143/-3/Fleet/Equipment/ID/" + "/".join(
                quote(str(v), safe="") for v in (identifier, kind, start.isoformat(), end.isoformat(), 1))
            try:
                payload = client.request("GET", endpoint)
                if not isinstance(payload, dict) or not isinstance(payload.get(field), list):
                    raise ValueError("Unexpected AEMP history response")
                payloads[kind] = payload
                count = len(payload[field])
                capabilities.append({"name": name, "status": "data" if count else "empty", "record_count": count, "http_status": 200})
            except TrackunitError as exc:
                # Do not serialize provider error strings, which can contain URLs or identifiers.
                payloads[kind] = {field: []}
                status = "unauthorized" if exc.status_code in (401, 403) else "rate_limited" if exc.status_code == 429 else "error"
                capabilities.append({"name": name, "status": status, "record_count": None, "http_status": exc.status_code})
        verification = {"checked_at": now.isoformat(), "window_start": start.isoformat(), "window_end": end.isoformat(),
                        "capabilities": capabilities + [{"name": "fault_events", "status": "not_checked"}]}
        rows = normalize_hour_series(str(identity), payloads["CumulativeOperatingHours"], payloads["CumulativeIdleHours"])
        if any(not start <= timestamp(row.recorded_at) <= end for row in rows):
            raise ValueError("Provider returned samples outside the requested window")
        dataset = None
        if rows:
            source = "Trackunit AEMP; " + "; ".join(c["name"]+"="+c["status"] for c in capabilities) + "; fault_events=not_checked"
            dataset = LocalDataset.model_validate({"name": "Trackunit 实测历史 · " + header["Model"],
                "source_document": source, "provenance": "user_supplied", "machine": {
                    "machine_id":str(identity), "trackunit_asset_id":str(identity), "model":header["Model"],
                    "serial_number": header.get("SerialNumber") or str(identifier), "machine_type":"unknown",
                    "customer":"本地开发数据", "location":"未导入位置", "last_seen_at": rows[-1].recorded_at},
                "telemetry":[row.model_dump() for row in rows], "faults":[]})
        return {"dataset":dataset, "verification":verification}
    finally:
        guard.unlink(missing_ok=True)
