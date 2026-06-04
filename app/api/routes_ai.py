import sys
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.ai_provider import generate_fleet_ai_report, generate_machine_ai_report
from app.nl_query import answer_question as default_answer_question
from app.prompt_builder import build_fleet_prompt, build_machine_prompt
from app.services.dashboard_service import get_dashboard_summary
from app.services.machine_service import (
    find_faults,
    find_machine,
    find_telemetry,
    load_fault_codes,
    load_machines,
    load_telemetry_snapshots,
)


router = APIRouter()


class AskRequest(BaseModel):
    question: str
    language: str = "auto"
    ai_provider: str | None = None


class AiProviderRequest(BaseModel):
    ai_provider: str | None = None


def _answer_question(question: str, language: str, provider_override: str | None):
    main_module = sys.modules.get("app.main")
    answer_func = getattr(main_module, "answer_question", default_answer_question)
    return answer_func(question, language=language, provider_override=provider_override)


@router.post("/analysis/machine/{machine_id}/ai-report")
def create_machine_ai_report(machine_id: str, request: AiProviderRequest | None = None):
    machine = find_machine(machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")

    prompt = build_machine_prompt(
        machine=machine,
        telemetry=find_telemetry(machine_id),
        faults=find_faults(machine_id),
    )
    provider_override = request.ai_provider if request else None
    result = generate_machine_ai_report(prompt, machine_context=machine, provider_override=provider_override)

    return {
        "provider": result["provider"],
        "model": result["model"],
        "prompt_used": prompt,
        "ai_report_markdown": result["report_markdown"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "error": result["error"],
    }


@router.post("/analysis/fleet/ai-report")
def create_fleet_ai_report(request: AiProviderRequest | None = None):
    machines = load_machines()
    telemetry = load_telemetry_snapshots()
    faults = load_fault_codes()
    prompt = build_fleet_prompt(
        machines=machines,
        telemetry=telemetry,
        faults=faults,
    )
    provider_override = request.ai_provider if request else None
    result = generate_fleet_ai_report(prompt, fleet_context=get_dashboard_summary(), provider_override=provider_override)

    return {
        "provider": result["provider"],
        "model": result["model"],
        "prompt_used": prompt,
        "ai_report_markdown": result["report_markdown"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "error": result["error"],
    }


@router.post("/ask")
def ask_fleet_assistant(request: AskRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")
    language = request.language if request.language in {"zh", "en"} else "auto"
    return _answer_question(request.question, language=language, provider_override=request.ai_provider)
