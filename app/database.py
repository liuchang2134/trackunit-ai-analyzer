import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.core.config import settings
from app.models import FaultCode, Machine, TelemetrySnapshot
from app.prompt_builder import is_low_utilization, is_offline


DB_PATH = settings.sqlite_db_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    if value is None:
        return "{}"
    return json.dumps(value, ensure_ascii=False, default=str)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS machines (
                machine_id TEXT PRIMARY KEY,
                trackunit_asset_id TEXT,
                equipment_id TEXT,
                serial_number TEXT,
                model TEXT,
                machine_type TEXT,
                customer TEXT,
                location TEXT,
                latitude REAL,
                longitude REAL,
                last_seen_at TEXT,
                raw_json TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS telemetry_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                trackunit_asset_id TEXT,
                equipment_id TEXT,
                operating_hours REAL,
                idle_hours REAL,
                fuel_remaining_percent REAL,
                engine_status TEXT,
                latitude REAL,
                longitude REAL,
                recorded_at TEXT,
                raw_json TEXT,
                inserted_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_telemetry_machine_recorded
                ON telemetry_snapshots(machine_id, recorded_at);

            CREATE TABLE IF NOT EXISTS fault_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                trackunit_asset_id TEXT,
                equipment_id TEXT,
                spn INTEGER,
                fmi INTEGER,
                fault_code TEXT,
                description TEXT,
                severity TEXT,
                occurred_at TEXT,
                status TEXT,
                raw_json TEXT,
                inserted_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_faults_machine_occurred
                ON fault_codes(machine_id, occurred_at);

            CREATE TABLE IF NOT EXISTS sync_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT NOT NULL,
                status TEXT NOT NULL,
                records INTEGER DEFAULT 0,
                error TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fleet_snapshot_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                total_machines INTEGER NOT NULL,
                online_machines INTEGER NOT NULL,
                offline_machines INTEGER NOT NULL,
                low_fuel_machines INTEGER NOT NULL,
                low_utilization_machines INTEGER NOT NULL,
                fault_records INTEGER NOT NULL,
                average_fuel_percent REAL,
                average_operating_hours REAL,
                source TEXT NOT NULL
            );
            """
        )


def upsert_machines(machines: list[Machine]) -> None:
    init_database()
    now = _utc_now()
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO machines (
                machine_id, trackunit_asset_id, equipment_id, serial_number, model,
                machine_type, customer, location, latitude, longitude, last_seen_at,
                raw_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(machine_id) DO UPDATE SET
                trackunit_asset_id=excluded.trackunit_asset_id,
                equipment_id=excluded.equipment_id,
                serial_number=excluded.serial_number,
                model=excluded.model,
                machine_type=excluded.machine_type,
                customer=excluded.customer,
                location=excluded.location,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                last_seen_at=excluded.last_seen_at,
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            [
                (
                    item.machine_id,
                    item.trackunit_asset_id,
                    item.equipment_id,
                    item.serial_number,
                    item.model,
                    item.machine_type,
                    item.customer,
                    item.location,
                    item.latitude,
                    item.longitude,
                    item.last_seen_at,
                    _json(item.model_dump()),
                    now,
                )
                for item in machines
            ],
        )


def insert_telemetry_snapshots(telemetry: list[TelemetrySnapshot]) -> None:
    init_database()
    now = _utc_now()
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO telemetry_snapshots (
                machine_id, trackunit_asset_id, equipment_id, operating_hours,
                idle_hours, fuel_remaining_percent, engine_status, latitude,
                longitude, recorded_at, raw_json, inserted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item.machine_id,
                    item.trackunit_asset_id,
                    item.equipment_id,
                    item.operating_hours,
                    item.idle_hours,
                    item.fuel_remaining_percent,
                    item.engine_status,
                    item.latitude,
                    item.longitude,
                    item.recorded_at,
                    _json(item.raw_payload or item.model_dump()),
                    now,
                )
                for item in telemetry
            ],
        )


def insert_fault_codes(faults: list[FaultCode]) -> None:
    init_database()
    now = _utc_now()
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO fault_codes (
                machine_id, trackunit_asset_id, equipment_id, spn, fmi, fault_code,
                description, severity, occurred_at, status, raw_json, inserted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item.machine_id,
                    item.trackunit_asset_id,
                    item.equipment_id,
                    item.spn,
                    item.fmi,
                    item.fault_code,
                    item.description,
                    item.severity,
                    item.occurred_at,
                    item.status,
                    _json(item.raw_payload or item.model_dump()),
                    now,
                )
                for item in faults
            ],
        )


def insert_sync_log(log: dict[str, Any]) -> None:
    init_database()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO sync_logs (sync_type, status, records, error, finished_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                log.get("sync_type"),
                log.get("status"),
                int(log.get("records") or 0),
                log.get("error"),
                log.get("finished_at"),
                log.get("created_at") or _utc_now(),
            ),
        )


def insert_fleet_history(
    machines: list[Machine],
    telemetry: list[TelemetrySnapshot],
    faults: list[FaultCode] | None = None,
    source: str = "trackunit_cache",
) -> dict[str, Any]:
    init_database()
    telemetry_by_machine = {item.machine_id: item for item in telemetry}
    fuel_values = [
        item.fuel_remaining_percent
        for item in telemetry
        if item.fuel_remaining_percent is not None
    ]
    operating_values = [
        item.operating_hours
        for item in telemetry
        if item.operating_hours is not None
    ]
    offline_count = len([machine for machine in machines if is_offline(machine)])
    low_fuel_count = len([
        item for item in telemetry
        if item.fuel_remaining_percent is not None and item.fuel_remaining_percent <= 10
    ])
    low_utilization_count = len([
        machine for machine in machines
        if is_low_utilization(telemetry_by_machine.get(machine.machine_id))
    ])
    record = {
        "captured_at": _utc_now(),
        "total_machines": len(machines),
        "online_machines": max(len(machines) - offline_count, 0),
        "offline_machines": offline_count,
        "low_fuel_machines": low_fuel_count,
        "low_utilization_machines": low_utilization_count,
        "fault_records": len(faults or []),
        "average_fuel_percent": sum(fuel_values) / len(fuel_values) if fuel_values else None,
        "average_operating_hours": sum(operating_values) / len(operating_values) if operating_values else None,
        "source": source,
    }
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO fleet_snapshot_history (
                captured_at, total_machines, online_machines, offline_machines,
                low_fuel_machines, low_utilization_machines, fault_records,
                average_fuel_percent, average_operating_hours, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["captured_at"],
                record["total_machines"],
                record["online_machines"],
                record["offline_machines"],
                record["low_fuel_machines"],
                record["low_utilization_machines"],
                record["fault_records"],
                record["average_fuel_percent"],
                record["average_operating_hours"],
                record["source"],
            ),
        )
    return record


def get_fleet_history(days: int = 30) -> list[dict[str, Any]]:
    init_database()
    since = datetime.now(timezone.utc) - timedelta(days=max(days, 1))
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM fleet_snapshot_history
            WHERE captured_at >= ?
            ORDER BY captured_at ASC
            """,
            (since.isoformat(),),
        ).fetchall()
    return [dict(row) for row in rows]


def get_database_status() -> dict[str, Any]:
    init_database()
    with get_connection() as connection:
        tables = {}
        for table in ("machines", "telemetry_snapshots", "fault_codes", "sync_logs", "fleet_snapshot_history"):
            tables[table] = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
    return {
        "provider": "sqlite",
        "path": str(DB_PATH),
        "exists": DB_PATH.exists(),
        "tables": tables,
        "postgresql_ready": False,
        "note": "PostgreSQL can be added behind this adapter without exposing secrets to frontend.",
    }
