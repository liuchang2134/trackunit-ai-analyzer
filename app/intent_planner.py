import json
import re
from typing import Any, Callable

from app.ai_provider import generate_fleet_ai_report


SUPPORTED_INTENTS = {
    "fleet_summary",
    "executive_summary",
    "offline_machines",
    "repeated_faults",
    "fault_machines",
    "fault_summary",
    "low_utilization",
    "low_fuel",
    "missing_data",
    "machine_status",
    "location_query",
    "single_machine_status",
    "compare_machine_type",
}


INTENT_REQUIRED_FIELDS = {
    "offline_machines": ["machine_id", "model", "serial_number", "last_seen_at", "location", "engine_status"],
    "low_fuel": ["machine_id", "model", "serial_number", "fuel_remaining_percent", "location", "last_seen_at"],
    "low_utilization": ["machine_id", "model", "serial_number", "operating_hours", "idle_hours", "last_seen_at"],
    "fault_machines": ["machine_id", "model", "serial_number", "fault_count", "fault_codes", "last_seen_at"],
    "repeated_faults": ["machine_id", "model", "serial_number", "fault_count", "fault_codes"],
    "fault_summary": ["fault_code", "spn", "fmi", "severity", "status", "occurred_at"],
    "machine_status": ["machine_id", "model", "serial_number", "engine_status", "location", "last_seen_at"],
    "single_machine_status": ["machine_id", "model", "serial_number", "engine_status", "location", "last_seen_at"],
    "location_query": ["machine_id", "model", "serial_number", "location", "latitude", "longitude", "last_seen_at"],
    "fleet_summary": ["machine_id", "model", "serial_number", "last_seen_at", "operating_hours", "fuel_remaining_percent", "fault_count"],
    "executive_summary": ["machine_id", "model", "serial_number", "last_seen_at", "operating_hours", "fuel_remaining_percent", "fault_count", "location"],
    "missing_data": ["machine_id", "model", "serial_number", "missing_fields"],
    "compare_machine_type": ["machine_type", "machine_count", "total_operating_hours", "fault_count", "offline_count"],
}


def build_intent_prompt(question: str) -> str:
    return f"""
You are an intent planner for a construction equipment telematics assistant.
Your job is to understand the user's real intent, not just match keywords.

Return JSON only. No markdown. No explanation.

Supported intents:
- fleet_summary: overall fleet status or management summary
- executive_summary: executive/leadership report or management briefing
- offline_machines: machines offline, not reporting, disconnected, last seen too old
- repeated_faults: machines with repeated or frequent faults
- fault_machines: which machines have faults, alarms, warnings, errors, fault records
- fault_summary: summarize fault codes, SPN/FMI, CAN faults, machine faults
- low_utilization: low usage, idle too much, low operating hours
- low_fuel: low fuel level, low oil/fuel remaining, fuel remaining percent is low
- missing_data: data missing, no fuel data, unknown fields
- machine_status: question about one specific machine/serial/model status
- location_query: where a specific machine is now
- single_machine_status: legacy alias for machine_status
- compare_machine_type: compare equipment types

Important Chinese domain mapping:
- "油量低", "燃油低", "剩余油量低" mean low_fuel, not missing_data.
- "油耗低" means low fuel consumption/usage. If fuel consumption data is unavailable, use missing_data.
- "报错", "报警", "告警", "有问题" usually mean fault_machines.
- "故障码", "SPN", "FMI", "CAN fault" mean fault_summary.

Return this schema:
{{
  "intent": "one supported intent",
  "language": "zh | en",
  "confidence": 0.0,
  "target_machines": ["machine id, serial number, or model mentioned by the user"],
  "time_range": {{
    "type": "relative | absolute | none",
    "value": 7,
    "unit": "days",
    "start": null,
    "end": null
  }},
  "filters": {{
    "fuel_threshold_percent": 20,
    "offline_hours": 72,
    "machine_query": null
  }},
  "thresholds": {{
    "fuel_remaining_percent": 20,
    "offline_days": 3
  }},
  "required_fields": ["machine_id", "model"],
  "answer_shape": "machine_list | count | summary | explain | executive_summary"
}}

User question:
{question}
""".strip()


def plan_question(
    question: str,
    llm_generate: Callable[[str], dict[str, Any]] = generate_fleet_ai_report,
) -> dict[str, Any]:
    prompt = build_intent_prompt(question)
    result = llm_generate(prompt)
    raw_text = result.get("report_markdown", "") if isinstance(result, dict) else ""
    parsed = _parse_json_object(raw_text)
    if not parsed:
        return _fallback_plan("Unable to parse AI intent JSON", raw_text)

    intent = parsed.get("intent")
    if intent not in SUPPORTED_INTENTS:
        return _fallback_plan(f"Unsupported AI intent: {intent}", raw_text)

    filters = parsed.get("filters")
    if not isinstance(filters, dict):
        filters = {}
    thresholds = parsed.get("thresholds")
    if not isinstance(thresholds, dict):
        thresholds = {}
    _merge_thresholds_into_filters(filters, thresholds)

    time_range = parsed.get("time_range")
    if not isinstance(time_range, dict):
        time_range = _infer_time_range(question)

    target_machines = parsed.get("target_machines")
    if not isinstance(target_machines, list):
        target_machines = []
    if target_machines and not filters.get("machine_query"):
        filters["machine_query"] = str(target_machines[0])

    required_fields = parsed.get("required_fields")
    if not isinstance(required_fields, list) or not required_fields:
        required_fields = INTENT_REQUIRED_FIELDS.get(intent, ["machine_id", "model", "serial_number"])

    confidence = _safe_float(parsed.get("confidence"), 0.0)
    return {
        "source": "ai_intent_planner",
        "intent": intent,
        "language": parsed.get("language") or _detect_language(question),
        "confidence": confidence,
        "target_machines": [str(item) for item in target_machines if item],
        "time_range": time_range,
        "filters": filters,
        "thresholds": thresholds,
        "required_fields": [str(item) for item in required_fields if item],
        "answer_shape": parsed.get("answer_shape") or "summary",
        "raw": raw_text,
        "error": None,
    }


def _parse_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fallback_plan(error: str, raw_text: str = "") -> dict[str, Any]:
    return {
        "source": "rule_fallback",
        "intent": None,
        "language": None,
        "confidence": 0.0,
        "target_machines": [],
        "time_range": {"type": "none", "value": None, "unit": None, "start": None, "end": None},
        "filters": {},
        "thresholds": {},
        "required_fields": [],
        "answer_shape": "summary",
        "raw": raw_text,
        "error": error,
    }


def _detect_language(question: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", question) else "en"


def _merge_thresholds_into_filters(filters: dict[str, Any], thresholds: dict[str, Any]) -> None:
    if filters.get("fuel_threshold_percent") is None and thresholds.get("fuel_remaining_percent") is not None:
        filters["fuel_threshold_percent"] = thresholds["fuel_remaining_percent"]
    if filters.get("offline_hours") is None and thresholds.get("offline_days") is not None:
        try:
            filters["offline_hours"] = float(thresholds["offline_days"]) * 24
        except (TypeError, ValueError):
            pass


def _infer_time_range(question: str) -> dict[str, Any]:
    q = question.lower()
    match = re.search(r"最近\s*(\d+)\s*天", question)
    if match:
        return {"type": "relative", "value": int(match.group(1)), "unit": "days", "start": None, "end": None}
    match = re.search(r"last\s+(\d+)\s+days?", q)
    if match:
        return {"type": "relative", "value": int(match.group(1)), "unit": "days", "start": None, "end": None}
    if "上周" in question or "last week" in q:
        return {"type": "relative", "value": 7, "unit": "days", "start": None, "end": None}
    if "今天" in question or "today" in q:
        return {"type": "relative", "value": 1, "unit": "days", "start": None, "end": None}
    return {"type": "none", "value": None, "unit": None, "start": None, "end": None}
