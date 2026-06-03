import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.data_store import save_machines, save_telemetry
from app.models import Machine, TelemetrySnapshot


ROOT = Path(__file__).resolve().parents[2]
ASSETS_CSV = ROOT / "trackunit_assets_with_locations_2026-06-02.csv"
AEMP_CSV = ROOT / "trackunit_aemp_snapshot_2026-06-02.csv"


def to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def main():
    machines_by_id = {}
    telemetry_by_id = {}

    with ASSETS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            machine_id = row["id"]
            machines_by_id[machine_id] = Machine(
                machine_id=machine_id,
                trackunit_asset_id=machine_id,
                equipment_id=row.get("name") or None,
                serial_number=row.get("serialNumber") or row.get("telematicsSerialNumbers") or row.get("name") or "Data not available",
                model=row.get("model") or "Data not available",
                machine_type=row.get("type") or row.get("assetType") or "Data not available",
                customer=row.get("ownerAccountId") or "Data not available",
                location=", ".join(part for part in [row.get("city"), row.get("country")] if part) or "Data not available",
                latitude=to_float(row.get("latitude")),
                longitude=to_float(row.get("longitude")),
                last_seen_at=row.get("locationUpdatedAt") or row.get("createdAt") or "Data not available",
            )
            telemetry_by_id[machine_id] = TelemetrySnapshot(
                machine_id=machine_id,
                trackunit_asset_id=machine_id,
                equipment_id=row.get("name") or None,
                operating_hours=None,
                idle_hours=None,
                fuel_remaining_percent=None,
                engine_status="unknown",
                latitude=to_float(row.get("latitude")),
                longitude=to_float(row.get("longitude")),
                recorded_at=row.get("locationUpdatedAt") or "Data not available",
                raw_payload=row,
            )

    if AEMP_CSV.exists():
        with AEMP_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                trackunit_asset_id = row.get("machineId")
                if not trackunit_asset_id:
                    continue
                existing = telemetry_by_id.get(trackunit_asset_id)
                telemetry_by_id[trackunit_asset_id] = TelemetrySnapshot(
                    machine_id=trackunit_asset_id,
                    trackunit_asset_id=trackunit_asset_id,
                    equipment_id=row.get("equipmentId") or None,
                    operating_hours=to_float(row.get("operatingHours")),
                    idle_hours=to_float(row.get("idleHours")),
                    fuel_remaining_percent=to_float(row.get("fuelRemainingPercent")),
                    engine_status="running" if row.get("engineRunning") == "True" else "stopped" if row.get("engineRunning") == "False" else "unknown",
                    latitude=to_float(row.get("latitude")) or (existing.latitude if existing else None),
                    longitude=to_float(row.get("longitude")) or (existing.longitude if existing else None),
                    recorded_at=row.get("operatingHoursAt") or row.get("locationAt") or (existing.recorded_at if existing else "Data not available"),
                    raw_payload=row,
                )
                if trackunit_asset_id in machines_by_id:
                    machine = machines_by_id[trackunit_asset_id]
                    machines_by_id[trackunit_asset_id] = machine.model_copy(update={
                        "equipment_id": row.get("equipmentId") or machine.equipment_id,
                        "serial_number": row.get("serialNumber") or machine.serial_number,
                        "model": row.get("model") or machine.model,
                        "last_seen_at": row.get("locationAt") or machine.last_seen_at,
                    })

    save_machines(list(machines_by_id.values()))
    save_telemetry(list(telemetry_by_id.values()))
    print(json.dumps({
        "machines": len(machines_by_id),
        "telemetry": len(telemetry_by_id),
        "source_assets_csv": str(ASSETS_CSV),
        "source_aemp_csv": str(AEMP_CSV),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
