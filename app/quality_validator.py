from typing import Any


def validate_ai_answer(answer: str, structured_context: dict[str, Any], language: str) -> dict[str, Any]:
    issues: list[str] = []
    if not answer.strip():
        issues.append("empty_answer")
    if language == "zh" and _has_english_report_markers(answer):
        issues.append("wrong_language_or_template_markers")

    governance = structured_context.get("data_governance") or {}
    source = governance.get("data_source")
    if source and source not in answer:
        issues.append("missing_data_source_reference")

    records = structured_context.get("matched_records") or []
    risk_records = structured_context.get("risk_ranking") or []
    if records and not _mentions_any_machine(answer, records):
        issues.append("missing_machine_evidence")
    if risk_records and not _mentions_risk(answer):
        issues.append("missing_risk_evidence")

    stats = structured_context.get("statistics") or {}
    if stats and not _mentions_any_stat(answer, stats):
        issues.append("missing_statistical_evidence")

    return {
        "valid": not issues,
        "issues": issues,
    }


def build_validator_retry_instruction(validation: dict[str, Any]) -> str:
    return (
        "\n\nQuality validation failed. Regenerate the answer and fix these issues: "
        f"{validation.get('issues')}. "
        "Use only the structured context. Cite machine identifiers, statistics, risk scores, data source, "
        "and missing fields when available. Do not add unsupported claims."
    )


def _mentions_any_machine(answer: str, records: list[dict[str, Any]]) -> bool:
    lower = answer.lower()
    for record in records[:10]:
        for key in ("serial_number", "machine_id", "model"):
            value = record.get(key)
            if value and str(value).lower() in lower:
                return True
    return False


def _mentions_risk(answer: str) -> bool:
    lower = answer.lower()
    return any(marker in lower for marker in ["risk", "风险", "critical", "high", "medium", "low", "score", "评分"])


def _mentions_any_stat(answer: str, stats: dict[str, Any]) -> bool:
    for value in stats.values():
        if isinstance(value, (int, float)) and str(int(value)) in answer:
            return True
    return False


def _has_english_report_markers(answer: str) -> bool:
    lower = answer[:500].lower()
    return any(marker in lower for marker in ["direct answer", "key evidence", "recommended action"])
