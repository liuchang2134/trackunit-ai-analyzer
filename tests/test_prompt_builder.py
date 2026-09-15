from app.normalizer import find_faults, find_machine, find_telemetry, load_fault_codes, load_machines, load_telemetry_snapshots
from app.prompt_builder import build_fleet_prompt, build_machine_prompt


def test_machine_prompt_contains_key_fields():
    machine = find_machine("M-1002")
    prompt = build_machine_prompt(
        machine=machine,
        telemetry=find_telemetry("M-1002"),
        faults=find_faults("M-1002"),
    )

    assert "Machine ID: M-1002" in prompt
    assert "Serial number: SIM-M-1002" in prompt
    assert "Operating hours: 3761.6" in prompt
    assert "Idle hours: 2104.0" in prompt
    assert "Fuel remaining percent: 94.8" in prompt
    assert "Engine status: running" in prompt
    assert "FUEL-RAIL-157-17" in prompt
    assert "Repeated fault codes" in prompt


def test_machine_prompt_uses_data_not_available_for_missing_fuel():
    machine = find_machine("M-1004")
    prompt = build_machine_prompt(
        machine=machine,
        telemetry=find_telemetry("M-1004"),
        faults=find_faults("M-1004"),
    )

    assert "Fuel remaining percent: Data not available" in prompt


def test_fleet_prompt_contains_fleet_summary_and_risk_flags():
    prompt = build_fleet_prompt(
        machines=load_machines(),
        telemetry=load_telemetry_snapshots(),
        faults=load_fault_codes(),
    )

    assert "Total machines: 5" in prompt
    assert "Online machines: 4" in prompt
    assert "Offline machines: 1" in prompt
    assert "Low-utilization machines: 1" in prompt
    assert "M-1003" in prompt
    assert "M-1005" in prompt
    assert "FUEL-RAIL-157-17" in prompt

