from typing import Any


def build_service_recommendations(risk_records: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    recommendations = []
    for record in risk_records:
        risk_score = int(record.get("risk_score") or 0)
        fault_count = int(record.get("fault_count") or 0)
        fuel = record.get("fuel_remaining_percent")
        hours_since_last_seen = record.get("hours_since_last_seen")
        reasons = record.get("risk_reason") or []

        if risk_score < 20:
            continue

        action = "Review machine status and validate latest telematics data."
        if fault_count >= 2:
            action = "Create service case, inspect repeated fault history, and verify active diagnostic codes."
        elif isinstance(hours_since_last_seen, (int, float)) and hours_since_last_seen > 72:
            action = "Check telematics power, site connectivity, and machine availability with customer."
        elif isinstance(fuel, (int, float)) and fuel <= 10:
            action = "Confirm refuel plan and verify customer/site operating schedule."

        recommendations.append({
            "machine_id": record.get("machine_id"),
            "serial_number": record.get("serial_number"),
            "model": record.get("model"),
            "priority": _priority(risk_score),
            "reason": "; ".join(str(item) for item in reasons),
            "recommended_action": action,
            "parts_recommendation": (
                "Current system does not yet contain fault-code-to-parts mapping. "
                "Real part recommendations are unavailable."
            ),
            "source": "rule_based_service_intelligence",
        })

    return recommendations[:limit]


def _priority(score: int) -> str:
    if score >= 70:
        return "Priority 1"
    if score >= 40:
        return "Priority 2"
    return "Priority 3"
