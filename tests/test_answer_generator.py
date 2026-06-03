from app import answer_generator


def test_generate_answer_returns_real_provider_error(monkeypatch):
    def fake_generate(prompt, fleet_context=None, provider_override=None):
        return {
            "provider": "gemini",
            "model": "gemini-flash-latest",
            "report_markdown": "",
            "error": "Gemini API key is not configured.",
        }

    monkeypatch.setattr(answer_generator, "generate_fleet_ai_report", fake_generate)
    result = answer_generator.generate_answer(
        question="哪些设备离线了",
        query_plan={"intent": "offline_machines", "language": "zh"},
        analysis_result={
            "intent": "offline_machines",
            "records": [{"serial_number": "SN1", "model": "XE490U", "risk_score": 50, "risk_level": "High"}],
            "summary_metrics": {"returned_records": 1},
            "data_source": "trackunit_cache",
            "data_summary": {"source": "trackunit_cache", "records_used": 1},
            "fallback_used": False,
        },
        language="zh",
        provider_override="gemini",
    )

    assert result["answer"] == ""
    assert result["error"] == "Gemini API key is not configured."


def test_generate_answer_retries_failed_quality_validation(monkeypatch):
    calls = {"count": 0}

    def fake_generate(prompt, fleet_context=None, provider_override=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "provider": "gemini",
                "model": "gemini-flash-latest",
                "report_markdown": "泛泛而谈，没有引用数据。",
                "error": None,
            }
        return {
            "provider": "gemini",
            "model": "gemini-flash-latest",
            "report_markdown": "结论：SN1/XE490U 风险评分 50，数据源 trackunit_cache，建议优先检查通信和故障记录。",
            "error": None,
        }

    monkeypatch.setattr(answer_generator, "generate_fleet_ai_report", fake_generate)
    result = answer_generator.generate_answer(
        question="哪些设备需要关注",
        query_plan={"intent": "offline_machines", "language": "zh"},
        analysis_result={
            "intent": "offline_machines",
            "records": [{
                "machine_id": "M1",
                "serial_number": "SN1",
                "model": "XE490U",
                "hours_since_last_seen": 80,
            }],
            "summary_metrics": {"returned_records": 1},
            "data_source": "trackunit_cache",
            "data_summary": {"source": "trackunit_cache", "records_used": 1},
            "fallback_used": False,
        },
        language="zh",
        provider_override="gemini",
    )

    assert calls["count"] == 2
    assert result["error"] is None
    assert "SN1" in result["answer"]
    assert result["quality_validation"]["valid"] is True
