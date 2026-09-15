from collections import Counter
from datetime import datetime, timedelta, timezone
import os
from typing import Any

from app.data_store import cache_status, get_data_source, load_faults, load_machines, load_telemetry
from app.models import FaultCode, Machine, TelemetrySnapshot
from app.normalizer import normalize_trackunit_fault, normalize_trackunit_machine, normalize_trackunit_telemetry_series
from app.trackunit_client import TrackunitClient, TrackunitError


FLEET_INTENTS = {
    "fleet_summary",
    "executive_summary",
    "offline_machines",
    "low_fuel",
    "low_utilization",
    "compare_machine_type",
    "missing_data",
}
FAULT_INTENTS = {"fault_machines", "fault_summary", "repeated_faults"}
SINGLE_MACHINE_INTENTS = {"machine_status", "single_machine_status", "location_query"}


def collect_live_data(query_plan: dict[str, Any], client: TrackunitClient | None = None) -> dict[str, Any]:
    intent = query_plan.get("intent") or "fleet_summary"
    calls = _calls_for_intent(intent)
    status = cache_status()
    if _should_use_cache_first(intent, status):
        return collect_cache_data(query_plan, api_calls=[], cache_meta=status)

    client = client or TrackunitClient(
        timeout_seconds=float(os.getenv("TRACKUNIT_LIVE_TIMEOUT_SECONDS", "10")),
        retries=int(os.getenv("TRACKUNIT_LIVE_RETRIES", "1")),
    )
    errors: list[str] = []

    try:
        machines: list[Machine] = []
        telemetry: list[TelemetrySnapshot] = []
        faults: list[FaultCode] = []

        if "machines" in calls:
            machine_payload = client.get_machine_list()
            machines = _normalize_machines(machine_payload)
            telemetry = _normalize_telemetry(machine_payload)

        if "single_machine" in calls:
            target = _first_target(query_plan)
            if target:
                machines = _normalize_machines(client.get_single_machine_detail(target))
            else:
                errors.append("No target machine was identified for single-machine API call.")

        if "telemetry" in calls and not _has_useful_telemetry(telemetry):
            target = _first_target(query_plan)
            start, end = _time_range_bounds(query_plan)
            telemetry = _normalize_telemetry(client.get_telemetry(target, start, end))

        if "faults" in calls:
            target = _first_target(query_plan)
            start, end = _time_range_bounds(query_plan)
            faults = _normalize_faults(client.get_faults(target, start, end))
            faults.extend(_try_optional_fault_endpoint(client.get_can_faults, target, start, end, errors))
            faults.extend(_try_optional_fault_endpoint(client.get_machine_faults, target, start, end, errors))

        if not machines and "machines" in calls:
            raise TrackunitError("Trackunit API returned no machine records")

        if machines and not telemetry and "telemetry" in calls:
            errors.append("Trackunit telemetry endpoint returned no records or is not configured.")
        if "faults" in calls and not faults:
            errors.append("Trackunit fault endpoint returned no records or is not configured.")

        return _build_result(
            source="trackunit_api",
            query_plan=query_plan,
            machines=machines,
            telemetry=telemetry,
            faults=faults,
            api_calls=calls,
            api_error=None,
            warnings=errors,
            cache_meta=status,
        )
    except TrackunitError as exc:
        return collect_cache_data(query_plan, api_error=str(exc), api_calls=calls, cache_meta=status)


def collect_cache_data(
    query_plan: dict[str, Any],
    api_error: str | None = None,
    api_calls: list[str] | None = None,
    cache_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _build_result(
        source="trackunit_cache" if get_data_source() == "trackunit_cache" else "mock",
        query_plan=query_plan,
        machines=load_machines(),
        telemetry=load_telemetry(),
        faults=load_faults(),
        api_calls=api_calls or [],
        api_error=api_error,
        warnings=[],
        cache_meta=cache_meta or cache_status(),
    )


def _calls_for_intent(intent: str) -> list[str]:
    calls: list[str] = []
    if intent in FLEET_INTENTS:
        calls.extend(["machines", "telemetry"])
    if intent in FAULT_INTENTS:
        calls.extend(["machines", "faults"])
    if intent in SINGLE_MACHINE_INTENTS:
        calls.extend(["single_machine", "telemetry", "faults"])
    if intent == "executive_summary":
        calls.append("faults")
    if not calls:
        calls.extend(["machines", "telemetry"])
    return list(dict.fromkeys(calls))


def _build_result(
    source: str,
    query_plan: dict[str, Any],
    machines: list[Machine],
    telemetry: list[TelemetrySnapshot],
    faults: list[FaultCode],
    api_calls: list[str],
    api_error: str | None,
    warnings: list[str],
    cache_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest = {item.machine_id: item for item in telemetry}
    faults_by_machine = Counter(fault.machine_id for fault in faults)
    machine_records = []
    missing_fields: set[str] = set()

    for machine in machines:
        item = latest.get(machine.machine_id)
        missing = []
        if item is None:
            missing.extend(["telemetry", "fuel_remaining_percent", "engine_status"])
        else:
            if item.fuel_remaining_percent is None:
                missing.append("fuel_remaining_percent")
            if item.engine_status in {None, "", "unknown", "Data not available"}:
                missing.append("engine_status")
        if machine.location in {"", "Data not available", None}:
            missing.append("location")
        if machine.last_seen_at in {"", "Data not available", None}:
            missing.append("last_seen_at")
        missing_fields.update(missing)
        machine_records.append({
            **machine.model_dump(),
            "operating_hours": item.operating_hours if item else None,
            "idle_hours": item.idle_hours if item else None,
            "fuel_remaining_percent": item.fuel_remaining_percent if item else None,
            "engine_status": item.engine_status if item else "Data not available",
            "latitude": item.latitude if item else None,
            "longitude": item.longitude if item else None,
            "recorded_at": item.recorded_at if item else None,
            "fault_count": faults_by_machine.get(machine.machine_id, 0),
            "missing_fields": missing,
        })

    return {
        "source": source,
        "query_plan": query_plan,
        "api_calls": api_calls,
        "api_error": api_error,
        "fallback_used": bool(api_error),
        "warnings": warnings,
        "cache_status": cache_meta,
        "machines": machine_records,
        "telemetry": [item.model_dump() for item in telemetry],
        "faults": [item.model_dump() for item in faults],
        "data_summary": {
            "source": source,
            "machines_scanned": len(machines),
            "telemetry_records": len(telemetry),
            "fault_records": len(faults),
            "records_used": 0,
            "api_calls": api_calls,
            "fallback_used": bool(api_error),
            "api_error": api_error,
            "cache_updated_at": (cache_meta or {}).get("updated_at"),
            "cache_age_seconds": (cache_meta or {}).get("age_seconds"),
            "cache_fresh": (cache_meta or {}).get("fresh"),
        },
        "missing_fields": sorted(missing_fields),
    }


def _should_use_cache_first(intent: str, status: dict[str, Any]) -> bool:
    if os.getenv("TRACKUNIT_CACHE_FIRST", "true").lower() not in {"1", "true", "yes", "on"}:
        return False
    if not status.get("exists"):
        return False
    realtime_single = os.getenv("TRACKUNIT_REALTIME_SINGLE_MACHINE", "true").lower() in {"1", "true", "yes", "on"}
    if realtime_single and intent in SINGLE_MACHINE_INTENTS:
        return False
    if status.get("fresh"):
        return True
    refresh_stale_on_ask = os.getenv("TRACKUNIT_REFRESH_STALE_CACHE_ON_ASK", "false").lower() in {"1", "true", "yes", "on"}
    return not refresh_stale_on_ask


def _normalize_machines(payload: Any) -> list[Machine]:
    items = _extract_items(payload)
    return [normalize_trackunit_machine(item) for item in items if isinstance(item, dict)]


def _normalize_telemetry(payload: Any) -> list[TelemetrySnapshot]:
    items = _extract_items(payload)
    return [row for item in items if isinstance(item, dict) for row in normalize_trackunit_telemetry_series(item)]


def _normalize_faults(payload: Any) -> list[FaultCode]:
    items = _extract_items(payload)
    return [normalize_trackunit_fault(item) for item in items if isinstance(item, dict)]


def _has_useful_telemetry(telemetry: list[TelemetrySnapshot]) -> bool:
    return any(
        item.operating_hours is not None
        or item.idle_hours is not None
        or item.fuel_remaining_percent is not None
        or item.engine_status not in {None, "", "unknown", "Data not available"}
        for item in telemetry
    )


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("equipment", "content", "items", "data", "results", "faults", "faultCode"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
    return [payload]


def _try_optional_fault_endpoint(method: Any, target: str | None, start: str | None, end: str | None, errors: list[str]) -> list[FaultCode]:
    try:
        return _normalize_faults(method(target, start, end))
    except TrackunitError as exc:
        errors.append(str(exc))
        return []


def _first_target(query_plan: dict[str, Any]) -> str | None:
    targets = query_plan.get("target_machines") or []
    if targets:
        return str(targets[0])
    filters = query_plan.get("filters") or {}
    target = filters.get("machine_query") or filters.get("machine_id")
    return str(target) if target else None


def _time_range_bounds(query_plan: dict[str, Any]) -> tuple[str | None, str | None]:
    time_range = query_plan.get("time_range") or {}
    if time_range.get("type") == "absolute":
        return time_range.get("start"), time_range.get("end")
    if time_range.get("type") == "relative" and time_range.get("value") and time_range.get("unit") == "days":
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=float(time_range["value"]))
        return start.isoformat(), end.isoformat()
    return None, None
