from datetime import datetime, timezone
from typing import Any

from app.data_store import append_sync_log, save_faults, save_machines, save_telemetry
from app.database import (
    insert_fault_codes,
    insert_fleet_history,
    insert_sync_log,
    insert_telemetry_snapshots,
    upsert_machines,
)
from app.normalizer import (
    normalize_trackunit_fault,
    normalize_trackunit_machine,
    normalize_trackunit_telemetry_series,
)
from app.trackunit_client import TrackunitClient, TrackunitError


def _extract_items(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("equipment", "content", "items", "data", "results", "faultCode", "faults"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return [payload]


def _paged_get(client: TrackunitClient, endpoint: str) -> list[dict]:
    if "{page}" in endpoint:
        items: list[dict] = []
        page = 1
        while True:
            payload = client.request("GET", endpoint.format(page=page))
            page_items = _extract_items(payload)
            if not page_items:
                break
            items.extend(page_items)

            links = payload.get("links", []) if isinstance(payload, dict) else []
            has_next = any(link.get("rel") == "next" for link in links if isinstance(link, dict))
            if not has_next:
                break
            page += 1
        return items

    first = client.request("GET", endpoint)
    items = _extract_items(first)

    if isinstance(first, dict) and "totalPages" in first:
        total_pages = int(first.get("totalPages") or 1)
        separator = "&" if "?" in endpoint else "?"
        for page in range(1, total_pages):
            payload = client.request("GET", f"{endpoint}{separator}page={page}")
            items.extend(_extract_items(payload))

    return items


def _log(sync_type: str, status: str, records: int = 0, error: str | None = None) -> dict:
    log = {
        "sync_type": sync_type,
        "status": status,
        "records": records,
        "error": error,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    append_sync_log(log)
    insert_sync_log(log)
    return log


def sync_fleet_snapshot() -> dict:
    client = TrackunitClient()
    try:
        endpoint = client.get_configured_endpoint("TRACKUNIT_FLEET_SNAPSHOT_ENDPOINT")
        items = _paged_get(client, endpoint)
        machines = [normalize_trackunit_machine(item) for item in items]
        telemetry = [row for item in items for row in normalize_trackunit_telemetry_series(item)]
        save_machines(machines)
        save_telemetry(telemetry)
        upsert_machines(machines)
        insert_telemetry_snapshots(telemetry)
        insert_fleet_history(machines, telemetry, source="trackunit_api")
        return _log("fleet_snapshot", "success", len(items))
    except TrackunitError as exc:
        return _log("fleet_snapshot", "error", 0, str(exc))


def sync_single_asset(asset_id: str) -> dict:
    client = TrackunitClient()
    try:
        endpoint_template = client.get_configured_endpoint("TRACKUNIT_SINGLE_ASSET_ENDPOINT")
        endpoint = endpoint_template.format(asset_id=asset_id)
        payload = client.request("GET", endpoint)
        items = _extract_items(payload)
        machines = [normalize_trackunit_machine(item) for item in items]
        telemetry = [row for item in items for row in normalize_trackunit_telemetry_series(item)]
        save_machines(machines)
        save_telemetry(telemetry)
        upsert_machines(machines)
        insert_telemetry_snapshots(telemetry)
        insert_fleet_history(machines, telemetry, source="trackunit_api")
        return _log("single_asset", "success", len(items))
    except TrackunitError as exc:
        return _log("single_asset", "error", 0, str(exc))


def sync_time_series(start_date: str, end_date: str) -> dict:
    client = TrackunitClient()
    try:
        endpoint_template = client.get_configured_endpoint("TRACKUNIT_TIME_SERIES_ENDPOINT")
        endpoint = endpoint_template.format(start_date=start_date, end_date=end_date)
        items = _paged_get(client, endpoint)
        telemetry = [row for item in items for row in normalize_trackunit_telemetry_series(item)]
        save_telemetry(telemetry)
        insert_telemetry_snapshots(telemetry)
        return _log("time_series", "success", len(items))
    except TrackunitError as exc:
        return _log("time_series", "error", 0, str(exc))


def sync_faults(start_date: str, end_date: str) -> dict:
    client = TrackunitClient()
    try:
        endpoint_template = client.get_configured_endpoint("TRACKUNIT_FAULTS_ENDPOINT")
        endpoint = endpoint_template.format(start_date=start_date, end_date=end_date)
        items = _paged_get(client, endpoint)
        faults = [normalize_trackunit_fault(item) for item in items]
        save_faults(faults)
        insert_fault_codes(faults)
        return _log("faults", "success", len(items))
    except TrackunitError as exc:
        return _log("faults", "error", 0, str(exc))
