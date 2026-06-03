from typing import Any

from app.database import get_fleet_history


def _delta(current: float | int | None, previous: float | int | None) -> float | int | None:
    if current is None or previous is None:
        return None
    return current - previous


def get_fleet_trends(days: int = 30) -> dict[str, Any]:
    history = get_fleet_history(days)
    latest = history[-1] if history else None
    previous = history[-2] if len(history) >= 2 else None

    deltas = {}
    if latest:
        for key in (
            "total_machines",
            "online_machines",
            "offline_machines",
            "low_fuel_machines",
            "low_utilization_machines",
            "fault_records",
            "average_fuel_percent",
            "average_operating_hours",
        ):
            deltas[key] = _delta(latest.get(key), previous.get(key) if previous else None)

    return {
        "days": days,
        "points": history,
        "point_count": len(history),
        "latest": latest,
        "deltas": deltas,
        "has_history": bool(history),
        "summary": build_trend_summary(latest, deltas),
    }


def build_trend_summary(latest: dict[str, Any] | None, deltas: dict[str, Any]) -> list[str]:
    if not latest:
        return ["No fleet history is available yet. Run Trackunit sync to create the first trend point."]

    notes = [
        f"Latest snapshot has {latest['total_machines']} machines, {latest['offline_machines']} offline, and {latest['low_utilization_machines']} low-utilization machines.",
    ]
    if deltas.get("offline_machines") is not None:
        direction = "increased" if deltas["offline_machines"] > 0 else "decreased" if deltas["offline_machines"] < 0 else "stayed flat"
        notes.append(f"Offline machine count {direction} by {abs(deltas['offline_machines'])}.")
    if deltas.get("low_fuel_machines") is not None:
        direction = "increased" if deltas["low_fuel_machines"] > 0 else "decreased" if deltas["low_fuel_machines"] < 0 else "stayed flat"
        notes.append(f"Low-fuel machine count {direction} by {abs(deltas['low_fuel_machines'])}.")
    return notes
