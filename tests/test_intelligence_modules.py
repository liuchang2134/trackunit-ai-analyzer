from app.risk_intelligence import calculate_machine_risk, rank_risks
from app.service_intelligence import build_service_recommendations
from app.structured_context_builder import build_structured_context


def test_risk_score_uses_rule_based_evidence():
    result = calculate_machine_risk({
        "hours_since_last_seen": 90,
        "fault_count": 2,
        "fuel_remaining_percent": 8,
        "operating_hours": 5,
    })

    assert result["risk_score"] >= 70
    assert result["risk_level"] == "Critical"
    assert any("Offline" in reason for reason in result["risk_reason"])


def test_service_recommendations_do_not_invent_parts():
    risks = rank_risks([{
        "machine_id": "M1",
        "serial_number": "SN1",
        "model": "XE490U",
        "fault_count": 2,
    }])

    recommendations = build_service_recommendations(risks)

    assert recommendations
    assert "real captured catalog entries" in recommendations[0]["parts_recommendation"]


def test_structured_context_limits_records_and_includes_risk():
    analysis_result = {
        "intent": "fleet_summary",
        "records": [
            {"machine_id": f"M{i}", "serial_number": f"SN{i}", "model": "XE", "fault_count": i % 3}
            for i in range(30)
        ],
        "summary_metrics": {"total_machines": 30, "returned_records": 30},
        "data_source": "trackunit_cache",
        "data_summary": {"source": "trackunit_cache", "records_used": 30},
        "missing_fields": [],
    }

    context = build_structured_context("生成管理层摘要", {"intent": "fleet_summary", "language": "zh"}, analysis_result)

    assert len(context["matched_records"]) == 20
    assert len(context["risk_ranking"]) == 20
    assert context["analysis_mode"] == "executive_reporting"
