from pathlib import Path

from app import database
from app.trend_analysis import get_fleet_trends


def test_fleet_trends_returns_latest_and_delta(tmp_path: Path):
    database.DB_PATH = tmp_path / "trend_test.db"
    database.init_database()
    with database.get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO fleet_snapshot_history (
                captured_at, total_machines, online_machines, offline_machines,
                low_fuel_machines, low_utilization_machines, fault_records,
                average_fuel_percent, average_operating_hours, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-06-02T10:00:00+00:00", 10, 8, 2, 1, 3, 4, 55.0, 120.0, "test"),
                ("2026-06-03T10:00:00+00:00", 10, 7, 3, 2, 4, 5, 50.0, 122.0, "test"),
            ],
        )

    trends = get_fleet_trends(days=10)

    assert trends["point_count"] == 2
    assert trends["latest"]["offline_machines"] == 3
    assert trends["deltas"]["offline_machines"] == 1
    assert trends["has_history"] is True
