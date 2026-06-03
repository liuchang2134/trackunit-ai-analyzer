from datetime import datetime, timezone
from typing import Any
import re

from app.ai_provider import generate_fleet_ai_report
from app.answer_generator import generate_answer
from app.intent_planner import plan_question
from app.live_data_service import collect_live_data
from app.query_engine import run_query
from app.query_engine import run_query_with_data


SYSTEM_INSTRUCTION = """
You are a fleet telematics analyst for construction equipment. Answer only based on the provided data. Do not invent machine records, fault codes, locations, timestamps, or utilization values. If the data is incomplete, clearly state the limitation. Provide concise but actionable recommendations.
""".strip()


def detect_question_language(question: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", question) else "en"


def build_nl_prompt(question: str, query_result: dict[str, Any], language: str = "auto") -> str:
    if language == "auto":
        language = detect_question_language(question)
    if language == "zh":
        language_instruction = """
重要：用户使用中文提问。你必须只用简体中文回答。
不要使用英文标题，例如 Direct Answer、Evidence、Recommended Action。
不要中英混写，除非机器型号、字段名或故障码本身是英文。
回答必须简洁：最多 5 条项目符号，尽量控制在 150 个中文字以内。
不要写长段落，不要展开背景说明。
""".strip()
        answer_format = """
回答格式：
- 结论
- 关键依据
- 建议
- 数据限制（如有）
""".strip()
    else:
        language_instruction = """
Important: The user asked in English. Answer only in English.
Be concise. Use at most 5 bullets and keep the answer under about 120 words.
Do not write long background explanations.
""".strip()
        answer_format = """
Answer format:
- Direct answer
- Key evidence
- Recommended action
- Data limitations, if any
""".strip()
    return f"""
{language_instruction}

{SYSTEM_INSTRUCTION}

User question:
{question}

Intent:
{query_result["intent"]}

Data source:
{query_result["data_source"]}

Current time:
{datetime.now(timezone.utc).isoformat()}

Summary metrics:
{query_result["summary_metrics"]}

Structured records:
{query_result["records"]}

{answer_format}
""".strip()


def answer_question(question: str, language: str = "auto", provider_override: str | None = None) -> dict[str, Any]:
    if language == "auto":
        language = detect_question_language(question)
    llm_generate = lambda prompt: generate_fleet_ai_report(prompt, provider_override=provider_override)
    query_plan = plan_question(question, llm_generate=llm_generate)
    if not query_plan.get("intent"):
        legacy_plan = run_query(question)["intent_plan"]
        query_plan = {**query_plan, **legacy_plan, "source": "rule_fallback", "language": language}
    query_plan["language"] = query_plan.get("language") or language

    live_data = collect_live_data(query_plan)
    query_result = run_query_with_data(question, query_plan, live_data)
    ai_result = generate_answer(
        question=question,
        query_plan=query_plan,
        analysis_result=query_result,
        language=language,
        provider_override=provider_override,
    )
    report_markdown = ai_result["answer"]

    return {
        "question": question,
        "intent": query_result["intent"],
        "answer": report_markdown,
        "answer_markdown": report_markdown,
        "used_data": query_result,
        "data_source": query_result["data_source"],
        "provider": ai_result["provider"],
        "model": ai_result["model"],
        "error": ai_result["error"],
        "language": language,
        "query_plan": query_plan,
        "intent_plan": query_plan,
        "data_summary": query_result.get("data_summary", {}),
        "missing_fields": query_result.get("missing_fields", []),
        "fallback_used": query_result.get("fallback_used", False),
        "api_error": query_result.get("api_error"),
        "structured_context": ai_result.get("structured_context"),
        "quality_validation": ai_result.get("quality_validation"),
        "analysis_mode": (ai_result.get("structured_context") or {}).get("analysis_mode"),
        "risk_ranking": (ai_result.get("structured_context") or {}).get("risk_ranking", []),
        "service_recommendations": (ai_result.get("structured_context") or {}).get("service_recommendations", []),
    }


def _looks_like_english_answer(text: str) -> bool:
    sample = text[:400].lower()
    english_markers = [
        "direct answer",
        "key evidence",
        "recommended action",
        "data limitations",
        "based on the provided data",
    ]
    return any(marker in sample for marker in english_markers)


def _needs_concise_fallback(text: str, language: str) -> bool:
    if not text:
        return True
    if language == "zh":
        return _looks_like_english_answer(text) or len(text) > 450
    return len(text) > 1200


def build_concise_data_answer(question: str, query_result: dict[str, Any], language: str = "zh") -> str:
    records = query_result.get("records", [])
    metrics = query_result.get("summary_metrics", {})
    intent = query_result.get("intent", "fleet_summary")
    data_source = query_result.get("data_source", "unknown")

    if language != "zh":
        return _build_concise_english_answer(intent, records, metrics, data_source)

    examples = _format_machine_examples(records)

    if intent == "offline_machines":
        return "\n".join([
            f"- 离线超过 72 小时的设备共有 {metrics.get('returned_records', len(records))} 台。",
            f"- 示例：{examples}。" if examples else "- 当前未返回具体设备记录。",
            "- 建议：优先检查终端供电、网络和最近作业状态。",
            f"- 数据源：{data_source}。",
        ])
    if intent == "repeated_faults":
        return "\n".join([
            f"- 重复故障设备共有 {metrics.get('returned_records', len(records))} 台。",
            f"- 示例：{examples}。" if examples else "- 当前没有发现故障次数 >= 2 的设备。",
            "- 建议：按故障码频次排序，优先排查同一设备的重复报警。",
            f"- 数据源：{data_source}。",
        ])
    if intent == "fault_machines":
        unmatched_count = sum(1 for item in records if item.get("mapping_status"))
        lines = [
            f"- 当前有故障/报错记录的设备共有 {metrics.get('returned_records', len(records))} 台。",
            f"- 示例：{examples}。" if examples else "- 当前没有发现有故障记录的设备。",
            "- 建议：优先查看 open 状态和高严重度故障。",
            f"- 数据源：{data_source}。",
        ]
        if unmatched_count:
            lines.insert(3, f"- 数据限制：其中 {unmatched_count} 台/组故障记录暂时无法匹配到真实设备缓存。")
        return "\n".join(lines)
    if intent == "low_utilization":
        return "\n".join([
            f"- 低利用率设备共有 {metrics.get('returned_records', len(records))} 台。",
            f"- 示例：{examples}。" if examples else "- 当前没有发现 operating_hours 低于规则阈值的设备。",
            "- 建议：结合租赁状态、客户现场和计划作业判断是否闲置。",
            f"- 数据源：{data_source}。",
        ])
    if intent == "low_fuel":
        fuel_examples = _format_fuel_examples(records)
        return "\n".join([
            f"- 油量低的设备共有 {metrics.get('returned_records', len(records))} 台（默认按燃油剩余 <= 20% 判断）。",
            f"- 示例：{fuel_examples}。" if fuel_examples else "- 当前没有发现燃油剩余 <= 20% 的设备。",
            "- 建议：优先核对这些设备的现场燃油状态和最近作业计划。",
            f"- 数据源：{data_source}。",
        ])
    if intent == "missing_data":
        return "\n".join([
            f"- 当前没有可靠的“油耗低”结论，系统只检测到 {metrics.get('returned_records', len(records))} 台存在燃油或状态数据缺失。",
            f"- 示例：{examples}。" if examples else "- 当前未返回具体缺失记录。",
            "- 建议：后续接入 fuel used / fuel rate 字段后，再做真实油耗排名。",
            f"- 数据源：{data_source}。",
        ])
    if intent == "single_machine_status":
        if not records:
            return "- 没找到这台设备。\n- 请确认设备编号、序列号或型号是否正确。"
        item = records[0]
        return "\n".join([
            f"- 设备 {item.get('machine_id')}：{item.get('model')}，客户 {item.get('customer')}。",
            f"- 状态：engine_status={item.get('engine_status')}，operating_hours={item.get('operating_hours')}，fault_count={item.get('fault_count')}。",
            f"- 最近上报：{item.get('last_seen_at')}，位置：{item.get('location')}。",
            f"- 数据源：{data_source}。",
        ])
    if intent == "fault_summary":
        fault_examples = ", ".join(
            f"{item.get('fault_code')}({item.get('count')})" for item in records[:5]
        )
        return "\n".join([
            f"- 当前故障记录总数：{metrics.get('total_fault_records', 0)}。",
            f"- 高频故障：{fault_examples or '暂无'}。",
            "- 建议：优先处理高频和高严重度故障。",
            f"- 数据源：{data_source}。",
        ])

    return "\n".join([
        f"- 车队总数：{metrics.get('total_machines', 0)} 台。",
        f"- 离线：{metrics.get('offline_machines', 0)} 台；重复故障：{metrics.get('repeated_fault_machines', 0)} 台；低利用率：{metrics.get('low_utilization_machines', 0)} 台。",
        "- 建议：先处理离线、重复故障和数据缺失设备。",
        f"- 数据源：{data_source}。",
    ])


def _build_concise_english_answer(intent: str, records: list[dict[str, Any]], metrics: dict[str, Any], data_source: str) -> str:
    examples = _format_machine_examples(records)
    if intent == "offline_machines":
        return f"- {metrics.get('returned_records', len(records))} machines are offline for more than 72 hours.\n- Examples: {examples or 'none'}.\n- Data source: {data_source}."
    if intent == "low_utilization":
        return f"- {metrics.get('returned_records', len(records))} machines are low utilization.\n- Examples: {examples or 'none'}.\n- Data source: {data_source}."
    if intent == "low_fuel":
        return f"- {metrics.get('returned_records', len(records))} machines have low fuel remaining (<= 20%).\n- Examples: {_format_fuel_examples(records) or 'none'}.\n- Data source: {data_source}."
    return f"- Total machines: {metrics.get('total_machines', 0)}.\n- Offline: {metrics.get('offline_machines', 0)}; repeated faults: {metrics.get('repeated_fault_machines', 0)}; low utilization: {metrics.get('low_utilization_machines', 0)}.\n- Data source: {data_source}."


def _format_machine_examples(records: list[dict[str, Any]], limit: int = 3) -> str:
    examples = []
    for item in records[:limit]:
        serial_number = item.get("serial_number")
        machine_id = serial_number if serial_number and serial_number != "Data not available" else item.get("machine_id")
        machine_id = machine_id or "unknown"
        machine_id = _short_display_value(machine_id)
        model = item.get("model") or "Data not available"
        examples.append(f"{machine_id}/{model}")
    return "；".join(examples)


def _format_fuel_examples(records: list[dict[str, Any]], limit: int = 5) -> str:
    examples = []
    for item in records[:limit]:
        serial_number = item.get("serial_number")
        machine_id = serial_number if serial_number and serial_number != "Data not available" else item.get("machine_id")
        machine_id = _short_display_value(machine_id or "unknown")
        model = item.get("model") or "Data not available"
        fuel = item.get("fuel_remaining_percent")
        fuel_text = "Data not available" if fuel is None else f"{fuel}%"
        examples.append(f"{machine_id}/{model}/{fuel_text}")
    return "；".join(examples)


def _short_display_value(value: Any) -> str:
    text = str(value)
    if len(text) > 18 and text.count("-") >= 4:
        return text[:8]
    return text
