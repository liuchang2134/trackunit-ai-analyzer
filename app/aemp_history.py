"""Normalize AEMP counters without interpolating or fabricating aligned samples."""
from app.models import TelemetrySnapshot
from app.telemetry_evidence import timestamp, number


def normalize_hour_series(machine_id: str, operating: dict, idle: dict) -> list[TelemetrySnapshot]:
    samples = {}
    for payload, key, field in ((operating, "cumulativeOperatingHours", "operating_hours"),
                                (idle, "cumulativeIdleHours", "idle_hours")):
        rows = payload.get(key)
        if not isinstance(rows, list):
            raise ValueError("AEMP response is missing its expected counter series")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Invalid AEMP counter row")
            instant = timestamp(row.get("datetime"))
            value = row.get("Hour")
            if instant is None or not number(value) or value < 0:
                raise ValueError("AEMP counters require timestamp timezone and finite nonnegative hours")
            values = samples.setdefault(instant, {})
            if field in values and values[field] != value:
                raise ValueError("Conflicting AEMP counters at the same timestamp")
            values[field] = value
    return [TelemetrySnapshot(machine_id=machine_id, recorded_at=t.isoformat(), **values)
            for t, values in sorted(samples.items())]
