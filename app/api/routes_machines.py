from fastapi import APIRouter, HTTPException

from app.models import FleetAnalysisPrompt, MachineAnalysisPrompt
from app.prompt_builder import build_fleet_prompt, build_machine_prompt
from app.services.dashboard_service import get_dashboard_summary as build_dashboard_summary
from app.services.machine_service import (
    find_faults,
    find_machine,
    find_telemetry,
    get_enriched_machines,
    load_fault_codes,
    load_machines,
    load_telemetry_snapshots,
)


router = APIRouter()


@router.get("/machines")
def get_machines():
    return get_enriched_machines()


@router.get("/machines/{machine_id}")
def get_machine(machine_id: str):
    machine = find_machine(machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    return machine


@router.get("/machines/{machine_id}/telemetry")
def get_machine_telemetry(machine_id: str):
    if find_machine(machine_id) is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    return find_telemetry(machine_id)


@router.get("/machines/{machine_id}/faults")
def get_machine_faults(machine_id: str):
    if find_machine(machine_id) is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    return find_faults(machine_id)


@router.post("/analysis/machine/{machine_id}/prompt", response_model=MachineAnalysisPrompt)
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


@router.post("/analysis/fleet/prompt", response_model=FleetAnalysisPrompt)
def create_fleet_analysis_prompt():
    prompt = build_fleet_prompt(
        machines=load_machines(),
        telemetry=load_telemetry_snapshots(),
        faults=load_fault_codes(),
    )
    return FleetAnalysisPrompt(prompt=prompt)


@router.get("/dashboard/summary")
def get_dashboard_summary():
    return build_dashboard_summary()
