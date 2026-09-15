from app.normalizer import (
    find_faults,
    find_machine,
    find_telemetry,
    load_fault_codes,
    load_machines,
    load_telemetry_snapshots,
)


def test_load_machines_normalizes_required_fields():
    machines = load_machines()

    assert len(machines) == 5
    assert all(machine.serial_number.startswith('SIM-') for machine in machines)
    assert all(machine.customer.startswith('演示客户') for machine in machines)
    assert all(machine.location.startswith('模拟作业区') for machine in machines)
    assert machines[0].machine_id == "M-1001"
    assert machines[0].serial_number == "SIM-M-1001"
    assert machines[0].machine_type == "excavator"


def test_load_telemetry_normalizes_trackunit_like_fields():
    telemetry = load_telemetry_snapshots()
    item = next(row for row in telemetry if row.machine_id == "M-1002")

    assert item.operating_hours == 3761.6
    assert item.idle_hours == 2104.0
    assert item.fuel_remaining_percent == 94.8
    assert item.engine_status == "running"
    assert item.latitude is None
    assert item.longitude is None
    assert all(row.latitude is None and row.longitude is None for row in telemetry)


def test_load_faults_normalizes_repeated_faults():
    faults = load_fault_codes()
    machine_faults = [fault for fault in faults if fault.machine_id == "M-1002"]

    assert len(machine_faults) == 3
    assert machine_faults[0].spn == 157
    assert machine_faults[0].fmi == 17
    assert machine_faults[0].fault_code == "FUEL-RAIL-157-17"
    assert machine_faults[0].severity == "high"


def test_find_helpers_filter_by_machine_id():
    assert find_machine("M-1003").model == "XS123"
    assert len(find_telemetry("M-1003")) == 1
    assert find_faults("M-1003") == []

