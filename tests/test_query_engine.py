from app.query_engine import run_query, run_query_with_data


def test_offline_machines_intent(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mock")
    result = run_query("Which machines are offline for more than 72 hours?")

    assert result["intent"] == "offline_machines"
    assert result["summary_metrics"]["returned_records"] == 1
    assert result["records"][0]["machine_id"] == "M-1003"


def test_repeated_faults_intent(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mock")
    result = run_query("Which machines have repeated faults?")

    assert result["intent"] == "repeated_faults"
    assert result["records"][0]["machine_id"] == "M-1002"
    assert result["records"][0]["fault_count"] == 3


def test_chinese_fault_machines_intent(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mock")
    result = run_query("哪些车报错了")

    assert result["intent"] == "fault_machines"
    assert {record["machine_id"] for record in result["records"]} == {"M-1001", "M-1002", "M-1004"}


def test_low_utilization_intent(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mock")
    result = run_query("Show low utilization machines.")

    assert result["intent"] == "low_utilization"
    assert any(record["machine_id"] == "M-1005" for record in result["records"])


def test_chinese_low_fuel_intent(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mock")
    result = run_query("哪些车油量低")

    assert result["intent"] == "low_fuel"
    assert result["summary_metrics"]["returned_records"] == 1
    assert result["records"][0]["machine_id"] == "M-1003"
    assert result["records"][0]["fuel_remaining_percent"] == 18.0


def test_ai_intent_plan_can_drive_low_fuel_query(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mock")
    result = run_query(
        "哪些设备快没油了",
        intent_plan={
            "source": "ai_intent_planner",
            "intent": "low_fuel",
            "confidence": 0.9,
            "filters": {"fuel_threshold_percent": 20},
        },
    )

    assert result["intent"] == "low_fuel"
    assert result["intent_plan"]["source"] == "ai_intent_planner"
    assert result["records"][0]["machine_id"] == "M-1003"


def test_ai_intent_plan_null_filters_use_defaults(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mock")
    result = run_query(
        "哪些设备离线了",
        intent_plan={
            "source": "ai_intent_planner",
            "intent": "offline_machines",
            "confidence": 0.9,
            "filters": {"offline_hours": None},
        },
    )

    assert result["intent"] == "offline_machines"
    assert result["records"][0]["machine_id"] == "M-1003"


def test_run_query_with_live_data_low_fuel():
    live_data = {
        "source": "trackunit_api",
        "fallback_used": False,
        "api_error": None,
        "warnings": [],
        "missing_fields": [],
        "data_summary": {"source": "trackunit_api", "machines_scanned": 2},
        "faults": [],
        "machines": [
            {
                "machine_id": "A1",
                "serial_number": "SN-A1",
                "model": "XE490U",
                "machine_type": "excavator",
                "customer": "Customer A",
                "location": "Dallas, TX",
                "last_seen_at": "2026-06-02T12:00:00Z",
                "operating_hours": 100,
                "idle_hours": 10,
                "fuel_remaining_percent": 9,
                "engine_status": "stopped",
                "latitude": None,
                "longitude": None,
                "recorded_at": "2026-06-02T12:00:00Z",
                "fault_count": 0,
                "missing_fields": [],
            },
            {
                "machine_id": "A2",
                "serial_number": "SN-A2",
                "model": "XC958",
                "machine_type": "wheel loader",
                "customer": "Customer B",
                "location": "Houston, TX",
                "last_seen_at": "2026-06-02T12:00:00Z",
                "operating_hours": 200,
                "idle_hours": 20,
                "fuel_remaining_percent": 50,
                "engine_status": "running",
                "latitude": None,
                "longitude": None,
                "recorded_at": "2026-06-02T12:00:00Z",
                "fault_count": 0,
                "missing_fields": [],
            },
        ],
    }

    result = run_query_with_data(
        "哪些车油量低于10%",
        {"intent": "low_fuel", "confidence": 0.9, "filters": {"fuel_threshold_percent": 10}},
        live_data,
    )

    assert result["data_source"] == "trackunit_api"
    assert result["data_summary"]["records_used"] == 1
    assert result["records"][0]["machine_id"] == "A1"


def test_single_machine_status_intent(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mock")
    result = run_query("What happened to M-1002?")

    assert result["intent"] == "single_machine_status"
    assert result["records"][0]["machine_id"] == "M-1002"
