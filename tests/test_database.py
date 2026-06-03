from pathlib import Path

from app import database
from app.models import Machine, TelemetrySnapshot


def test_sqlite_database_stores_fleet_history(tmp_path: Path):
    database.DB_PATH = tmp_path / "trackunit_test.db"
    machine = Machine(
        machine_id="M-DB-1",
        serial_number="SN-DB-1",
        model="XE35U",
        machine_type="excavator",
        customer="XCMG",
        location="Dallas, TX",
        last_seen_at="2026-06-03T12:00:00+00:00",
    )
    telemetry = TelemetrySnapshot(
        machine_id="M-DB-1",
        operating_hours=12.5,
        idle_hours=1.5,
        fuel_remaining_percent=8.0,
        engine_status="stopped",
        latitude=32.7,
        longitude=-96.8,
        recorded_at="2026-06-03T12:00:00+00:00",
    )

    database.init_database()
    database.upsert_machines([machine])
    database.insert_telemetry_snapshots([telemetry])
    history = database.insert_fleet_history([machine], [telemetry], source="test")
    status = database.get_database_status()

    assert history["total_machines"] == 1
    assert history["low_fuel_machines"] == 1
    assert status["tables"]["machines"] == 1
    assert status["tables"]["telemetry_snapshots"] == 1
    assert status["tables"]["fleet_snapshot_history"] == 1
