from collections import Counter
from typing import Any

from app.data_store import load_faults as store_load_faults
from app.data_store import load_machines as store_load_machines
from app.data_store import load_telemetry as store_load_telemetry
from app.models import FaultCode, Machine, TelemetrySnapshot
from app.prompt_builder import is_low_utilization, is_offline


def load_machines() -> list[Machine]:
    return store_load_machines()


def load_telemetry_snapshots() -> list[TelemetrySnapshot]:
    return store_load_telemetry()


def load_fault_codes() -> list[FaultCode]:
    return store_load_faults()


def find_machine(machine_id: str) -> Machine | None:
    return next((machine for machine in load_machines() if machine.machine_id == machine_id), None)


def find_telemetry(machine_id: str) -> list[TelemetrySnapshot]:
    return [item for item in load_telemetry_snapshots() if item.machine_id == machine_id]


def find_faults(machine_id: str) -> list[FaultCode]:
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


def get_enriched_machines() -> list[dict[str, Any]]:
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
