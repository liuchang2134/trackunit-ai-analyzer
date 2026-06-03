from app.intent_planner import plan_question


def test_plan_question_parses_ai_json():
    def fake_llm(prompt):
        return {
            "report_markdown": '{"intent":"low_fuel","language":"zh","confidence":0.91,"target_machines":[],"time_range":{"type":"none","value":null,"unit":null,"start":null,"end":null},"filters":{"fuel_threshold_percent":20},"thresholds":{"fuel_remaining_percent":20},"required_fields":["machine_id","fuel_remaining_percent"],"answer_shape":"machine_list"}',
            "error": None,
        }

    plan = plan_question("哪些设备快没油了？", llm_generate=fake_llm)

    assert plan["source"] == "ai_intent_planner"
    assert plan["intent"] == "low_fuel"
    assert plan["language"] == "zh"
    assert plan["confidence"] == 0.91
    assert plan["filters"]["fuel_threshold_percent"] == 20
    assert plan["required_fields"] == ["machine_id", "fuel_remaining_percent"]


def test_plan_question_merges_offline_days_threshold():
    def fake_llm(prompt):
        return {
            "report_markdown": '{"intent":"offline_machines","language":"zh","confidence":0.9,"filters":{},"thresholds":{"offline_days":3},"answer_shape":"machine_list"}',
            "error": None,
        }

    plan = plan_question("哪些设备超过3天没上线？", llm_generate=fake_llm)

    assert plan["intent"] == "offline_machines"
    assert plan["filters"]["offline_hours"] == 72


def test_plan_question_falls_back_on_invalid_json():
    def fake_llm(prompt):
        return {"report_markdown": "I think this is about fuel.", "error": None}

    plan = plan_question("哪些设备快没油了？", llm_generate=fake_llm)

    assert plan["source"] == "rule_fallback"
    assert plan["intent"] is None
    assert plan["error"]
