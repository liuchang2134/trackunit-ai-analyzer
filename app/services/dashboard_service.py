from collections import Counter

from app.prompt_builder import is_low_utilization, is_offline
from app.services.machine_service import load_fault_codes, load_machines, load_telemetry_snapshots


def get_dashboard_summary() -> dict[str, int]:
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
