from collections import Counter
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.ai_provider import generate_fleet_ai_report, generate_machine_ai_report
from app.data_store import cache_status, get_data_source, load_sync_logs
from app.data_store import load_faults as store_load_faults
from app.data_store import load_machines as store_load_machines
from app.data_store import load_telemetry as store_load_telemetry
from app.database import get_database_status, init_database
from app.models import FleetAnalysisPrompt, MachineAnalysisPrompt
from app.nl_query import answer_question
from app.normalizer import (
    find_faults as mock_find_faults,
    find_machine as mock_find_machine,
    find_telemetry as mock_find_telemetry,
)
from app.prompt_builder import (
    build_fleet_prompt,
    build_machine_prompt,
    is_low_utilization,
    is_offline,
)
from app.report_exporter import build_fleet_excel_report, build_fleet_pdf_report
from app.scheduler import auto_sync_status, start_auto_sync, stop_auto_sync
from app.trackunit_sync import sync_faults, sync_fleet_snapshot, sync_time_series
from app.trend_analysis import get_fleet_trends


app = FastAPI(
    title="Trackunit AI Analyzer",
    description="Phase 1 mock-data API for Trackunit telematics AI prompt generation.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DateRangeRequest(BaseModel):
    start_date: str
    end_date: str


class AskRequest(BaseModel):
    question: str
    language: str = "auto"
    ai_provider: str | None = None


class AiProviderRequest(BaseModel):
    ai_provider: str | None = None


def load_machines():
    return store_load_machines()


def load_telemetry_snapshots():
    return store_load_telemetry()


def load_fault_codes():
    return store_load_faults()


@app.on_event("startup")
async def start_optional_auto_sync() -> None:
    init_database()
    start_auto_sync(sync_fleet_snapshot)


@app.on_event("shutdown")
async def stop_optional_auto_sync() -> None:
    stop_auto_sync()


def find_machine(machine_id: str):
    return next((machine for machine in load_machines() if machine.machine_id == machine_id), None)


def find_telemetry(machine_id: str):
    return [item for item in load_telemetry_snapshots() if item.machine_id == machine_id]


def find_faults(machine_id: str):
    return [item for item in load_fault_codes() if item.machine_id == machine_id]


def get_risk_level(machine_id: str) -> str:
    machine = find_machine(machine_id)
    telemetry = find_telemetry(machine_id)
    faults = find_faults(machine_id)
    latest = telemetry[-1] if telemetry else None

    if machine and is_offline(machine):
        return "High Risk"
    if len(faults) >= 2:
        return "High Risk"
    if latest and is_low_utilization(latest):
        return "Low Utilization"
    return "Normal"


def build_risk_explanation(machine_id: str) -> list[str]:
    machine = find_machine(machine_id)
    telemetry = find_telemetry(machine_id)
    faults = find_faults(machine_id)
    latest = telemetry[-1] if telemetry else None
    notes: list[str] = []

    if machine and is_offline(machine):
        notes.append("Last seen is more than 72 hours ago, so this machine is considered offline and high risk.")
    if latest and is_low_utilization(latest):
        notes.append("Recent operating hours are very low, so this machine is flagged for low utilization.")
    if len(faults) >= 2:
        notes.append("This machine has two or more fault records, so it is flagged for repeated faults.")
    if latest and latest.fuel_remaining_percent is None:
        notes.append("Fuel remaining percent is missing, so fuel analysis has a data limitation.")
    if latest and latest.engine_status == "unknown":
        notes.append("Engine status is unknown, so machine status is data incomplete.")
    if not notes:
        notes.append("No major mock-data risk rule was triggered.")
    return notes


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "phase": "live-ai-prototype", "data_source": get_data_source()}


@app.get("/data/source")
def get_current_data_source():
    return {"data_source": get_data_source()}


@app.get("/cache/status")
def get_cache_status():
    return cache_status()


@app.get("/database/status")
def get_db_status():
    return get_database_status()


@app.get("/sync/auto/status")
def get_auto_sync_status():
    return auto_sync_status()


@app.post("/sync/trackunit/fleet")
def sync_trackunit_fleet():
    return sync_fleet_snapshot()


@app.post("/sync/trackunit/timeseries")
def sync_trackunit_timeseries(request: DateRangeRequest):
    return sync_time_series(request.start_date, request.end_date)


@app.post("/sync/trackunit/faults")
def sync_trackunit_faults(request: DateRangeRequest):
    return sync_faults(request.start_date, request.end_date)


@app.get("/sync/logs")
def get_sync_logs():
    return load_sync_logs()


@app.get("/analytics/trends")
def get_analytics_trends(days: int = 30):
    return get_fleet_trends(days)


@app.get("/reports/fleet/excel")
def download_fleet_excel_report(days: int = 30):
    path = build_fleet_excel_report(days)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/reports/fleet/pdf")
def download_fleet_pdf_report(days: int = 30):
    path = build_fleet_pdf_report(days)
    return FileResponse(path, filename=path.name, media_type="application/pdf")


@app.get("/machines")
def get_machines():
    telemetry_by_machine = {item.machine_id: item for item in load_telemetry_snapshots()}
    faults_by_machine = Counter(fault.machine_id for fault in load_fault_codes())
    enriched = []
    for machine in load_machines():
        latest = telemetry_by_machine.get(machine.machine_id)
        enriched.append(
            {
                **machine.model_dump(),
                "engine_status": latest.engine_status if latest else "Data not available",
                "fuel_remaining_percent": latest.fuel_remaining_percent if latest else None,
                "operating_hours": latest.operating_hours if latest else None,
                "fault_count": faults_by_machine.get(machine.machine_id, 0),
                "risk_level": get_risk_level(machine.machine_id),
                "risk_explanation": build_risk_explanation(machine.machine_id),
            }
        )
    return enriched


@app.get("/machines/{machine_id}")
def get_machine(machine_id: str):
    machine = find_machine(machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    return machine


@app.get("/machines/{machine_id}/telemetry")
def get_machine_telemetry(machine_id: str):
    if find_machine(machine_id) is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    return find_telemetry(machine_id)


@app.get("/machines/{machine_id}/faults")
def get_machine_faults(machine_id: str):
    if find_machine(machine_id) is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    return find_faults(machine_id)


@app.post("/analysis/machine/{machine_id}/prompt", response_model=MachineAnalysisPrompt)
def create_machine_analysis_prompt(machine_id: str):
    machine = find_machine(machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")

    prompt = build_machine_prompt(
        machine=machine,
        telemetry=find_telemetry(machine_id),
        faults=find_faults(machine_id),
    )
    return MachineAnalysisPrompt(machine_id=machine_id, prompt=prompt)


@app.post("/analysis/fleet/prompt", response_model=FleetAnalysisPrompt)
def create_fleet_analysis_prompt():
    prompt = build_fleet_prompt(
        machines=load_machines(),
        telemetry=load_telemetry_snapshots(),
        faults=load_fault_codes(),
    )
    return FleetAnalysisPrompt(prompt=prompt)


@app.get("/dashboard/summary")
def get_dashboard_summary():
    machines = load_machines()
    telemetry_by_machine = {item.machine_id: item for item in load_telemetry_snapshots()}
    faults = load_fault_codes()
    faults_by_machine = Counter(fault.machine_id for fault in faults)

    online = [machine for machine in machines if not is_offline(machine)]
    offline = [machine for machine in machines if is_offline(machine)]
    low_utilization = [
        machine for machine in machines
        if is_low_utilization(telemetry_by_machine.get(machine.machine_id))
    ]
    repeated_fault_machine_ids = {
        machine_id for machine_id, count in faults_by_machine.items() if count >= 2
    }
    high_risk_machine_ids = {
        machine.machine_id for machine in offline
    } | repeated_fault_machine_ids

    return {
        "total_machines": len(machines),
        "online_machines": len(online),
        "offline_machines": len(offline),
        "high_risk_machines": len(high_risk_machine_ids),
        "low_utilization_machines": len(low_utilization),
        "repeated_fault_machines": len(repeated_fault_machine_ids),
    }


@app.post("/analysis/machine/{machine_id}/ai-report")
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


@app.post("/analysis/fleet/ai-report")
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


@app.post("/ask")
def ask_fleet_assistant(request: AskRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")
    language = request.language if request.language in {"zh", "en"} else "auto"
    return answer_question(request.question, language=language, provider_override=request.ai_provider)
