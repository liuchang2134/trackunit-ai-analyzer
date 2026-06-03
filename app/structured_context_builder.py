from typing import Any

from app.risk_intelligence import rank_risks
from app.service_intelligence import build_service_recommendations


MAX_MATCHED_RECORDS = 20
MAX_RISK_RECORDS = 20


def build_structured_context(question: str, query_plan: dict[str, Any], analysis_result: dict[str, Any]) -> dict[str, Any]:
    records = list(analysis_result.get("records") or [])
    risk_ranking = rank_risks(records, limit=MAX_RISK_RECORDS)
    service_recommendations = build_service_recommendations(risk_ranking)
    data_summary = analysis_result.get("data_summary") or {}
    metrics = analysis_result.get("summary_metrics") or {}

    return {
        "analysis_mode": _analysis_mode(query_plan.get("intent") or analysis_result.get("intent")),
        "question": question,
        "intent": analysis_result.get("intent"),
        "language": query_plan.get("language"),
        "data_governance": {
            "ground_truth_policy": "Only use provided structured data. Do not invent machines, numbers, fault codes, or part numbers.",
            "data_source": analysis_result.get("data_source"),
            "cache_fresh": data_summary.get("cache_fresh"),
            "cache_updated_at": data_summary.get("cache_updated_at"),
            "fallback_used": analysis_result.get("fallback_used"),
            "api_error": analysis_result.get("api_error"),
            "missing_fields": analysis_result.get("missing_fields") or [],
        },
        "statistics": {
            **metrics,
            "machines_scanned": data_summary.get("machines_scanned"),
            "records_used": data_summary.get("records_used"),
            "telemetry_records": data_summary.get("telemetry_records"),
            "fault_records": data_summary.get("fault_records"),
        },
        "matched_records": [_compact_machine_record(item) for item in records[:MAX_MATCHED_RECORDS]],
        "risk_ranking": [_compact_machine_record(item) for item in risk_ranking],
        "service_recommendations": service_recommendations,
        "service_parts_limitations": (
            "Current system does not yet contain fault-code-to-parts mapping. "
            "Real XCMG part-number recommendations are unavailable."
        ),
    }


def build_fleet_analyst_prompt(structured_context: dict[str, Any], language: str) -> str:
    language_rule = (
        "Respond only in simplified Chinese. Use concise, professional operations language."
        if language == "zh"
        else "Respond only in English. Use concise, professional operations language."
    )
    return f"""
You are an expert fleet operations analyst, construction equipment telematics specialist,
service manager, and maintenance planner.

Your responsibilities:
- Analyze fleet data.
- Identify operational risks.
- Identify maintenance priorities.
- Identify service opportunities.
- Generate executive summaries.
- Explain findings clearly.

Non-negotiable rules:
- Never invent data.
- Never invent machines.
- Never invent fault codes.
- Never invent part numbers.
- Only use provided structured data.
- If data is unavailable, state that clearly.
- Risk scores are calculated by rules. Explain them, do not recalculate different scores.
- Service parts recommendations are unavailable unless a mapping table is provided.
- {language_rule}

Output requirements:
- Start with a direct answer to the user's question.
- Reference actual records, statistics, risk scores, data source, and cache status when relevant.
- For service questions, include service priority and recommended next action.
- For executive/reporting questions, use sections: Executive Summary, Fleet Health, Critical Machines,
  Operational Risks, Maintenance Priorities, Recommended Actions, Data Source, Missing Data.
- Keep ordinary answers short. Use a report format only when the user asks for a report or summary.

Structured context:
{structured_context}
""".strip()


def _analysis_mode(intent: str | None) -> str:
    if intent in {"executive_summary", "fleet_summary"}:
        return "executive_reporting"
    if intent in {"fault_machines", "repeated_faults", "fault_summary"}:
        return "service_intelligence"
    if intent in {"offline_machines", "low_fuel", "low_utilization"}:
        return "fleet_risk_intelligence"
    return "fleet_intelligence_copilot"


def _compact_machine_record(record: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "machine_id",
        "serial_number",
        "model",
        "machine_type",
        "customer",
        "location",
        "last_seen_at",
        "hours_since_last_seen",
        "operating_hours",
        "idle_hours",
        "fuel_remaining_percent",
        "engine_status",
        "fault_count",
        "fault_codes",
        "risk_score",
        "risk_level",
        "risk_reason",
        "missing_fields",
    ]
    return {key: record.get(key) for key in keys if key in record}
