from app import nl_query


def test_detect_question_language():
    assert nl_query.detect_question_language("哪些设备离线？") == "zh"
    assert nl_query.detect_question_language("Which machines are offline?") == "en"


def test_answer_question_returns_structure(monkeypatch):
    def fake_generate(prompt, fleet_context=None, provider_override=None):
        return {
            "provider": "ollama_local",
            "model": "qwen2.5:7b",
            "report_markdown": '{"intent":"offline_machines","confidence":0.9,"filters":{"offline_hours":72},"answer_shape":"machine_list"}',
            "error": None,
        }
    monkeypatch.setattr(nl_query, "generate_fleet_ai_report", fake_generate)
    monkeypatch.setattr(nl_query, "collect_live_data", lambda query_plan: _fake_live_data())
    monkeypatch.setattr(nl_query, "generate_answer", lambda **kwargs: {
        "provider": "ollama_local",
        "model": "qwen2.5:7b",
        "answer": "Offline machines: M-1003.",
        "error": None,
    })


    result = nl_query.answer_question("Which machines are offline for more than 72 hours?", language="zh")

    assert result["question"].startswith("Which machines")
    assert result["intent"] == "offline_machines"
    assert result["answer_markdown"] == "Offline machines: M-1003."
    assert result["provider"] == "ollama_local"
    assert result["model"] == "qwen2.5:7b"
    assert "used_data" in result
    assert "query_plan" in result
    assert "data_summary" in result
    assert "missing_fields" in result
    assert result["language"] == "zh"


def test_answer_question_auto_english(monkeypatch):
    def fake_generate(prompt, fleet_context=None, provider_override=None):
        return {
            "provider": "ollama_local",
            "model": "qwen2.5:7b",
            "report_markdown": '{"intent":"offline_machines","confidence":0.9,"filters":{"offline_hours":72},"answer_shape":"machine_list"}',
            "error": None,
        }

    monkeypatch.setattr(nl_query, "generate_fleet_ai_report", fake_generate)
    monkeypatch.setattr(nl_query, "collect_live_data", lambda query_plan: _fake_live_data())
    monkeypatch.setattr(nl_query, "generate_answer", lambda **kwargs: {
        "provider": "ollama_local",
        "model": "qwen2.5:7b",
        "answer": "M-1003 is offline.",
        "error": None,
    })

    result = nl_query.answer_question("Which machines are offline for more than 72 hours?")

    assert result["language"] == "en"


def test_chinese_question_returns_answer_from_new_flow(monkeypatch):
    def fake_generate(prompt, fleet_context=None, provider_override=None):
        return {
            "provider": "ollama_local",
            "model": "qwen2.5:7b",
            "report_markdown": '{"intent":"offline_machines","confidence":0.9,"filters":{"offline_hours":72},"answer_shape":"machine_list"}',
            "error": None,
        }

    monkeypatch.setattr(nl_query, "generate_fleet_ai_report", fake_generate)
    monkeypatch.setattr(nl_query, "collect_live_data", lambda query_plan: _fake_live_data())
    monkeypatch.setattr(nl_query, "generate_answer", lambda **kwargs: {
        "provider": "ollama_local",
        "model": "qwen2.5:7b",
        "answer": "- 离线设备共有 1 台。",
        "error": None,
    })

    result = nl_query.answer_question("哪些设备离线超过72小时？")

    assert result["language"] == "zh"
    assert "离线设备共有 1 台" in result["answer_markdown"]


def _fake_live_data():
    return {
        "source": "trackunit_api",
        "fallback_used": False,
        "api_error": None,
        "warnings": [],
        "missing_fields": [],
        "data_summary": {"source": "trackunit_api", "machines_scanned": 1},
        "faults": [],
        "machines": [
            {
                "machine_id": "M-1003",
                "serial_number": "SN-1003",
                "model": "XS123",
                "machine_type": "roller",
                "customer": "Customer",
                "location": "Kansas City, MO",
                "last_seen_at": "2026-05-28T09:10:00Z",
                "operating_hours": 12.7,
                "idle_hours": 8.1,
                "fuel_remaining_percent": 18.0,
                "engine_status": "stopped",
                "latitude": None,
                "longitude": None,
                "recorded_at": "2026-05-28T09:10:00Z",
                "fault_count": 0,
                "missing_fields": [],
            }
        ],
    }
