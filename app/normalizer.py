import json
from pathlib import Path
from typing import Any

from app.models import FaultCode, Machine, TelemetrySnapshot


DATA_DIR = Path(__file__).resolve().parent / "mock_data"


def load_json_file(filename: str) -> list[dict[str, Any]]:
    path = DATA_DIR / filename
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def get_nested(data: dict[str, Any], path: list[str], default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def normalize_machine(raw: dict[str, Any]) -> Machine:
    return Machine(
        machine_id=raw.get("id", "Data not available"),
        trackunit_asset_id=raw.get("trackunit_asset_id") or raw.get("id"),
        equipment_id=raw.get("equipment_id"),
        serial_number=raw.get("serialNumber", "Data not available"),
        model=raw.get("model", "Data not available"),
        machine_type=raw.get("type", "Data not available"),
        customer=raw.get("customer", "Data not available"),
        location=raw.get("location", "Data not available"),
        latitude=raw.get("latitude"),
        longitude=raw.get("longitude"),
        last_seen_at=raw.get("lastSeenAt", "Data not available"),
    )


def normalize_telemetry(raw: dict[str, Any]) -> TelemetrySnapshot:
    running = get_nested(raw, ["EngineStatus", "Running"])
    if running is True:
        engine_status = "running"
    elif running is False:
        engine_status = "stopped"
    else:
        engine_status = "unknown"

    return TelemetrySnapshot(
        machine_id=raw.get("assetId", "Data not available"),
        trackunit_asset_id=raw.get("assetId"),
        equipment_id=raw.get("equipmentId"),
        operating_hours=get_nested(raw, ["CumulativeOperatingHours", "Hour"]),
        idle_hours=get_nested(raw, ["CumulativeIdleHours", "Hour"]),
        fuel_remaining_percent=get_nested(raw, ["FuelRemaining", "Percent"]),
        engine_status=engine_status,
        latitude=get_nested(raw, ["Location", "Latitude"]),
        longitude=get_nested(raw, ["Location", "Longitude"]),
        recorded_at=raw.get("recordedAt", "Data not available"),
        raw_payload=raw,
    )


def normalize_fault(raw: dict[str, Any]) -> FaultCode:
    return FaultCode(
        machine_id=raw.get("assetId", "Data not available"),
        trackunit_asset_id=raw.get("assetId"),
        equipment_id=raw.get("equipmentId"),
        spn=raw.get("SPN"),
        fmi=raw.get("FMI"),
        fault_code=raw.get("code", "Data not available"),
        description=raw.get("text", "Data not available"),
        severity=raw.get("severity", "low"),
        occurred_at=raw.get("occurredAt", "Data not available"),
        status=raw.get("status", "open"),
        raw_payload=raw,
    )


def normalize_trackunit_machine(raw: dict[str, Any]) -> Machine:
    header = raw.get("EquipmentHeader") or {}
    metadata = raw.get("metadata") or raw.get("Metadata") or {}
    location = raw.get("Location") or raw.get("location") or {}
    asset_id = raw.get("id") or raw.get("assetId") or metadata.get("MachineId")
    equipment_id = header.get("EquipmentID") or raw.get("equipmentId") or raw.get("equipment_id")
    serial_number = (
        header.get("SerialNumber")
        or raw.get("SerialNumber")
        or raw.get("serialNumber")
        or raw.get("serial_number")
        or raw.get("name")
        or "Data not available"
    )
    city = get_nested(raw, ["properties", "locationAddress", "city"]) or raw.get("city")
    country = get_nested(raw, ["properties", "locationAddress", "country"]) or raw.get("country")
    location_label = raw.get("location") or ", ".join(part for part in [city, country] if part) or "Data not available"

    return Machine(
        machine_id=str(asset_id or equipment_id or serial_number),
        trackunit_asset_id=str(asset_id) if asset_id else None,
        equipment_id=str(equipment_id) if equipment_id else None,
        serial_number=str(serial_number),
        model=header.get("Model") or raw.get("model") or "Data not available",
        machine_type=raw.get("type") or raw.get("assetType") or "Data not available",
        customer=raw.get("customer") or raw.get("ownerAccountId") or "Data not available",
        location=location_label,
        latitude=location.get("Latitude") or raw.get("latitude"),
        longitude=location.get("Longitude") or raw.get("longitude"),
        last_seen_at=(
            raw.get("lastSeenAt")
            or location.get("datetime")
            or raw.get("createdAt")
            or raw.get("updatedAt")
            or "Data not available"
        ),
    )


def normalize_trackunit_telemetry(raw: dict[str, Any]) -> TelemetrySnapshot:
    location = raw.get("Location") or raw.get("location") or {}
    engine = raw.get("EngineStatus") or raw.get("engineStatus") or {}
    running = engine.get("Running") if isinstance(engine, dict) else None
    if running is True:
        engine_status = "running"
    elif running is False:
        engine_status = "stopped"
    else:
        engine_status = "unknown"

    asset_id = raw.get("id") or raw.get("assetId") or get_nested(raw, ["metadata", "MachineId"])
    equipment_id = get_nested(raw, ["EquipmentHeader", "EquipmentID"]) or raw.get("equipmentId")

    return TelemetrySnapshot(
        machine_id=str(asset_id or equipment_id or "Data not available"),
        trackunit_asset_id=str(asset_id) if asset_id else None,
        equipment_id=str(equipment_id) if equipment_id else None,
        operating_hours=get_nested(raw, ["CumulativeOperatingHours", "Hour"]) or raw.get("operating_hours"),
        idle_hours=get_nested(raw, ["CumulativeIdleHours", "Hour"]) or raw.get("idle_hours"),
        fuel_remaining_percent=get_nested(raw, ["FuelRemaining", "Percent"]) or raw.get("fuel_remaining_percent"),
        engine_status=engine_status,
        latitude=location.get("Latitude") or raw.get("latitude"),
        longitude=location.get("Longitude") or raw.get("longitude"),
        recorded_at=(
            location.get("datetime")
            or get_nested(raw, ["CumulativeOperatingHours", "datetime"])
            or raw.get("recordedAt")
            or raw.get("updatedAt")
            or "Data not available"
        ),
        raw_payload=raw,
    )


def normalize_trackunit_fault(raw: dict[str, Any]) -> FaultCode:
    asset_id = raw.get("assetId") or raw.get("machineId") or raw.get("id")
    equipment_id = raw.get("equipmentId") or raw.get("EquipmentID")
    severity = str(raw.get("severity") or "medium").lower()
    if severity not in {"low", "medium", "high", "critical"}:
        severity = "medium"
    status = str(raw.get("status") or "open").lower()
    if status not in {"open", "resolved", "acknowledged"}:
        status = "open"

    return FaultCode(
        machine_id=str(asset_id or equipment_id or "Data not available"),
        trackunit_asset_id=str(asset_id) if asset_id else None,
        equipment_id=str(equipment_id) if equipment_id else None,
        spn=raw.get("SPN") or raw.get("spn"),
        fmi=raw.get("FMI") or raw.get("fmi"),
        fault_code=str(raw.get("code") or raw.get("fault_code") or raw.get("faultCode") or "Data not available"),
        description=str(raw.get("text") or raw.get("description") or raw.get("fault_description") or "Data not available"),
        severity=severity,
        occurred_at=str(raw.get("occurredAt") or raw.get("datetime") or raw.get("occurred_at") or "Data not available"),
        status=status,
        raw_payload=raw,
    )


def load_machines() -> list[Machine]:
    return [normalize_machine(item) for item in load_json_file("machines.json")]


def load_telemetry_snapshots() -> list[TelemetrySnapshot]:
    return [normalize_telemetry(item) for item in load_json_file("telemetry_snapshots.json")]


def load_fault_codes() -> list[FaultCode]:
    return [normalize_fault(item) for item in load_json_file("fault_codes.json")]


def find_machine(machine_id: str) -> Machine | None:
    return next((machine for machine in load_machines() if machine.machine_id == machine_id), None)


def find_telemetry(machine_id: str) -> list[TelemetrySnapshot]:
    return [item for item in load_telemetry_snapshots() if item.machine_id == machine_id]


def find_faults(machine_id: str) -> list[FaultCode]:
    return [item for item in load_fault_codes() if item.machine_id == machine_id]
