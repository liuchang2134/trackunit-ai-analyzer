from datetime import datetime, timezone
from typing import Any

from app.ai_provider import generate_fleet_ai_report
from app.quality_validator import build_validator_retry_instruction, validate_ai_answer
from app.structured_context_builder import build_fleet_analyst_prompt, build_structured_context


def generate_answer(
    question: str,
    query_plan: dict[str, Any],
    analysis_result: dict[str, Any],
    language: str,
    provider_override: str | None = None,
) -> dict[str, Any]:
    structured_context = build_structured_context(question, query_plan, analysis_result)
    prompt = build_fleet_analyst_prompt(structured_context, language)
    ai_result = generate_fleet_ai_report(prompt, fleet_context=structured_context, provider_override=provider_override)

    answer = ai_result.get("report_markdown", "")
    validation = validate_ai_answer(answer, structured_context, language)

    if ai_result.get("error"):
        return _result(ai_result, answer="", prompt=prompt, structured_context=structured_context, validation=validation)

    if not validation["valid"]:
        retry_prompt = prompt + build_validator_retry_instruction(validation)
        retry_result = generate_fleet_ai_report(retry_prompt, fleet_context=structured_context, provider_override=provider_override)
        retry_answer = retry_result.get("report_markdown", "")
        retry_validation = validate_ai_answer(retry_answer, structured_context, language)
        if retry_result.get("error"):
            return _result(retry_result, answer="", prompt=retry_prompt, structured_context=structured_context, validation=retry_validation)
        if retry_validation["valid"]:
            return _result(retry_result, answer=retry_answer, prompt=retry_prompt, structured_context=structured_context, validation=retry_validation)
        return {
            "provider": retry_result.get("provider"),
            "model": retry_result.get("model"),
            "answer": "",
            "error": f"AI answer failed quality validation: {retry_validation['issues']}",
            "prompt_used": retry_prompt,
            "structured_context": structured_context,
            "quality_validation": retry_validation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    return _result(ai_result, answer=answer, prompt=prompt, structured_context=structured_context, validation=validation)


def _result(
    ai_result: dict[str, Any],
    answer: str,
    prompt: str,
    structured_context: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": ai_result.get("provider"),
        "model": ai_result.get("model"),
        "answer": answer,
        "error": ai_result.get("error"),
        "prompt_used": prompt,
        "structured_context": structured_context,
        "quality_validation": validation,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
