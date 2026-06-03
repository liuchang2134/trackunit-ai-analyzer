from typing import Any


def enrich_records_with_risk(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for record in records:
        risk = calculate_machine_risk(record)
        enriched.append({**record, **risk})
    return enriched


def calculate_machine_risk(record: dict[str, Any]) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []

    hours_since_last_seen = _number(record.get("hours_since_last_seen"))
    fault_count = _number(record.get("fault_count")) or 0
    fuel = _number(record.get("fuel_remaining_percent"))
    operating_hours = _number(record.get("operating_hours"))
    engine_status = str(record.get("engine_status") or "").lower()
    missing_fields = record.get("missing_fields") or []

    if hours_since_last_seen is not None and hours_since_last_seen > 72:
        score += 35
        reasons.append(f"Offline or not reporting for {round(hours_since_last_seen, 1)} hours")
    elif hours_since_last_seen is not None and hours_since_last_seen > 24:
        score += 20
        reasons.append(f"No communication for {round(hours_since_last_seen, 1)} hours")

    if fault_count >= 2:
        score += 30
        reasons.append(f"Repeated fault events: {fault_count}")
    elif fault_count == 1:
        score += 15
        reasons.append("Fault event reported")

    if fuel is not None and fuel <= 10:
        score += 20
        reasons.append(f"Fuel below 10%: {fuel}%")
    elif fuel is not None and fuel <= 20:
        score += 10
        reasons.append(f"Fuel low: {fuel}%")

    if operating_hours is not None and operating_hours < 10:
        score += 10
        reasons.append(f"Low utilization: operating_hours={operating_hours}")

    if engine_status in {"unknown", "data not available"}:
        score += 5
        reasons.append("Engine status is incomplete")

    if missing_fields:
        score += min(len(missing_fields) * 3, 12)
        reasons.append(f"Missing fields: {', '.join(str(item) for item in missing_fields)}")

    score = min(score, 100)
    return {
        "risk_score": score,
        "risk_level": _risk_level(score),
        "risk_reason": reasons or ["No major risk rule triggered from current structured data"],
    }


def rank_risks(records: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    enriched = enrich_records_with_risk(records)
    return sorted(enriched, key=lambda item: item.get("risk_score", 0), reverse=True)[:limit]


def _risk_level(score: int) -> str:
    if score >= 70:
        return "Critical"
    if score >= 40:
        return "High"
    if score >= 20:
        return "Medium"
    return "Low"


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
