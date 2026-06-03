from collections import Counter
from datetime import datetime, timezone
from typing import Iterable

from app.models import FaultCode, Machine, TelemetrySnapshot


REFERENCE_TIME = datetime(2026, 6, 2, 15, 0, 0, tzinfo=timezone.utc)


def value_or_na(value: object) -> object:
    if value is None or value == "":
        return "Data not available"
    return value


def parse_time(value: str) -> datetime | None:
    if not value or value == "Data not available":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def hours_since(value: str) -> float | None:
    parsed = parse_time(value)
    if parsed is None:
        return None
    return round((REFERENCE_TIME - parsed).total_seconds() / 3600, 2)


def is_low_utilization(telemetry: TelemetrySnapshot | None) -> bool:
    if telemetry is None or telemetry.operating_hours is None:
        return False
    return telemetry.operating_hours < 10


def is_offline(machine: Machine) -> bool:
    age = hours_since(machine.last_seen_at)
    return age is not None and age > 72


def repeated_faults(faults: Iterable[FaultCode]) -> list[tuple[str, int]]:
    counts = Counter(fault.fault_code for fault in faults)
    return [(code, count) for code, count in counts.items() if count > 1]


def build_machine_prompt(
    machine: Machine,
    telemetry: list[TelemetrySnapshot],
    faults: list[FaultCode],
) -> str:
    latest = telemetry[-1] if telemetry else None
    repeated = repeated_faults(faults)

    fault_lines = []
    for fault in faults:
        fault_lines.append(
            "- "
            f"Code: {value_or_na(fault.fault_code)}, "
            f"SPN: {value_or_na(fault.spn)}, "
            f"FMI: {value_or_na(fault.fmi)}, "
            f"Severity: {value_or_na(fault.severity)}, "
            f"Status: {value_or_na(fault.status)}, "
            f"Occurred at: {value_or_na(fault.occurred_at)}, "
            f"Description: {value_or_na(fault.description)}"
        )

    if not fault_lines:
        fault_lines.append("- Data not available")

    prompt = f"""
You are an AI analyst for construction equipment telematics.

Generate a single-machine health analysis report in clear business English.
Do not invent facts. If a field is missing, write "Data not available".

Machine basic information:
- Machine ID: {value_or_na(machine.machine_id)}
- Serial number: {value_or_na(machine.serial_number)}
- Model: {value_or_na(machine.model)}
- Machine type: {value_or_na(machine.machine_type)}
- Customer: {value_or_na(machine.customer)}
- Last known location: {value_or_na(machine.location)}
- Last seen at: {value_or_na(machine.last_seen_at)}
- Hours since last seen: {value_or_na(hours_since(machine.last_seen_at))}

Latest telemetry:
- Operating hours: {value_or_na(latest.operating_hours if latest else None)}
- Idle hours: {value_or_na(latest.idle_hours if latest else None)}
- Fuel remaining percent: {value_or_na(latest.fuel_remaining_percent if latest else None)}
- Engine status: {value_or_na(latest.engine_status if latest else None)}
- Latitude: {value_or_na(latest.latitude if latest else None)}
- Longitude: {value_or_na(latest.longitude if latest else None)}
- Recorded at: {value_or_na(latest.recorded_at if latest else None)}

Fault codes:
{chr(10).join(fault_lines)}

Known risk flags:
- Low utilization: {is_low_utilization(latest)}
- Offline more than 72 hours: {is_offline(machine)}
- Repeated fault codes: {repeated if repeated else "None detected"}

Please provide:
1. Health score from 0 to 100.
2. Main operational risks.
3. Utilization and idle time comments.
4. Fuel and engine status comments.
5. Fault code summary.
6. Location or offline risk comments.
7. Recommended maintenance or follow-up actions.
8. A concise manager-friendly summary.
""".strip()
    return prompt


def build_fleet_prompt(
    machines: list[Machine],
    telemetry: list[TelemetrySnapshot],
    faults: list[FaultCode],
) -> str:
    telemetry_by_machine = {item.machine_id: item for item in telemetry}
    online = [machine for machine in machines if not is_offline(machine)]
    offline = [machine for machine in machines if is_offline(machine)]
    low_utilization = [
        machine for machine in machines
        if is_low_utilization(telemetry_by_machine.get(machine.machine_id))
    ]

    high_risk = set()
    for machine in offline:
        high_risk.add(machine.machine_id)
    for machine in low_utilization:
        high_risk.add(machine.machine_id)
    for fault in faults:
        if fault.severity in {"high", "critical"} and fault.status != "resolved":
            high_risk.add(fault.machine_id)

    repeated = repeated_faults(faults)
    fault_summary = Counter(fault.fault_code for fault in faults)

    machine_lines = []
    for machine in machines:
        item = telemetry_by_machine.get(machine.machine_id)
        machine_lines.append(
            "- "
            f"{machine.machine_id} | {machine.model} | {machine.machine_type} | "
            f"Customer: {machine.customer} | "
            f"Operating hours: {value_or_na(item.operating_hours if item else None)} | "
            f"Idle hours: {value_or_na(item.idle_hours if item else None)} | "
            f"Fuel: {value_or_na(item.fuel_remaining_percent if item else None)} | "
            f"Engine: {value_or_na(item.engine_status if item else None)} | "
            f"Last seen: {machine.last_seen_at}"
        )

    prompt = f"""
You are an AI analyst preparing a weekly fleet telematics report for XCMG North America.

Generate a fleet weekly report in professional business English.
Do not invent facts. If a field is missing, write "Data not available".

Fleet summary:
- Total machines: {len(machines)}
- Online machines: {len(online)}
- Offline machines: {len(offline)}
- High-risk machines: {len(high_risk)}
- Low-utilization machines: {len(low_utilization)}
- Fault records: {len(faults)}

High-risk machine IDs:
- {", ".join(sorted(high_risk)) if high_risk else "None detected"}

Low-utilization machine IDs:
- {", ".join(machine.machine_id for machine in low_utilization) if low_utilization else "None detected"}

Fault summary:
- Fault counts by code: {dict(fault_summary) if fault_summary else "Data not available"}
- Repeated fault codes: {repeated if repeated else "None detected"}

Machine telemetry overview:
{chr(10).join(machine_lines)}

Please provide:
1. Executive summary.
2. Fleet utilization observations.
3. Offline machine risks.
4. Fuel and engine status observations.
5. Fault code summary and repeated fault risks.
6. Top machines requiring follow-up.
7. Recommended next actions for operations and service teams.
""".strip()
    return prompt

