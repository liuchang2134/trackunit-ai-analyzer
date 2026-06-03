from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from app.data_store import get_data_source, load_faults, load_machines, load_telemetry
from app.intent_planner import SUPPORTED_INTENTS
from app.models import FaultCode, Machine, TelemetrySnapshot


def _parse_time(value: str) -> datetime | None:
    if not value or value == "Data not available":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hours_since(value: str) -> float | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return round((datetime.now(timezone.utc) - parsed).total_seconds() / 3600, 2)


def _latest_telemetry_by_machine(telemetry: list[TelemetrySnapshot]) -> dict[str, TelemetrySnapshot]:
    latest: dict[str, TelemetrySnapshot] = {}
    for item in telemetry:
        latest[item.machine_id] = item
    return latest


def _faults_by_machine(faults: list[FaultCode]) -> dict[str, list[FaultCode]]:
    grouped: dict[str, list[FaultCode]] = defaultdict(list)
    for fault in faults:
        grouped[fault.machine_id].append(fault)
    return grouped


def _machine_record(machine: Machine, telemetry: TelemetrySnapshot | None, faults: list[FaultCode]) -> dict[str, Any]:
    return {
        "machine_id": machine.machine_id,
        "serial_number": machine.serial_number,
        "model": machine.model,
        "machine_type": machine.machine_type,
        "customer": machine.customer,
        "location": machine.location,
        "last_seen_at": machine.last_seen_at,
        "hours_since_last_seen": _hours_since(machine.last_seen_at),
        "operating_hours": telemetry.operating_hours if telemetry else None,
        "idle_hours": telemetry.idle_hours if telemetry else None,
        "fuel_remaining_percent": telemetry.fuel_remaining_percent if telemetry else None,
        "engine_status": telemetry.engine_status if telemetry else "Data not available",
        "fault_count": len(faults),
        "fault_codes": [fault.fault_code for fault in faults],
    }


def detect_intent(question: str, machines: list[Machine]) -> tuple[str, dict[str, Any]]:
    q = question.lower()
    filters: dict[str, Any] = {}

    for machine in machines:
        candidates = [machine.machine_id, machine.serial_number, machine.model]
        if any(candidate and candidate.lower() in q for candidate in candidates):
            filters["machine_id"] = machine.machine_id
            return "single_machine_status", filters

    if any(term in q for term in ["offline", "not reporting", "last seen", "72 hours", "disconnected", "离线", "未上报", "最后在线", "断联"]):
        filters["offline_hours"] = 72
        return "offline_machines", filters
    if any(term in q for term in ["repeated faults", "frequent faults", "recurring faults", "fault count", "重复故障", "频繁故障", "故障次数"]):
        return "repeated_faults", filters
    if any(term in q for term in ["low fuel", "fuel low", "low fuel level", "fuel remaining low", "燃油低", "油量低", "低油量", "低燃油", "剩余燃油低"]):
        filters["fuel_threshold_percent"] = 20
        return "low_fuel", filters
    if any(term in q for term in ["low utilization", "low usage", "idle", "operating hours", "低利用率", "使用率低", "利用率", "怠速", "运行小时"]):
        return "low_utilization", filters
    if any(term in q for term in ["missing data", "no fuel data", "unknown", "data limitation", "缺失", "没有燃油", "未知", "数据不完整", "油耗低"]):
        return "missing_data", filters
    if any(term in q for term in ["compare", "对比", "比较"]) and any(term in q for term in ["excavator", "wheel loader", "roller", "boom lift", "telehandler", "挖掘机", "装载机", "压路机", "高空作业", "伸缩臂叉装车"]):
        return "compare_machine_type", filters
    if any(term in q for term in ["which machines have faults", "machines with faults", "faulted machines", "报错", "报警", "告警", "有故障", "有问题"]):
        return "fault_machines", filters
    if any(term in q for term in ["fault", "spn", "fmi", "can fault", "diagnostic", "故障", "诊断"]):
        return "fault_summary", filters
    if any(term in q for term in ["summary", "fleet health", "weekly report", "management summary", "overview", "摘要", "车队健康", "周报", "管理层", "总览"]):
        return "fleet_summary", filters

    return "fleet_summary", filters


def run_query(question: str, intent_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    machines = load_machines()
    telemetry = load_telemetry()
    faults = load_faults()
    latest = _latest_telemetry_by_machine(telemetry)
    grouped_faults = _faults_by_machine(faults)
    if _use_ai_plan(intent_plan):
        intent = intent_plan["intent"]
        filters = intent_plan.get("filters", {})
    else:
        intent, filters = detect_intent(question, machines)

    records: list[dict[str, Any]] = []

    if intent == "offline_machines":
        threshold = filters.get("offline_hours") or 72
        records = [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if (_hours_since(machine.last_seen_at) or 0) > threshold
        ]
    elif intent == "repeated_faults":
        records = [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if len(grouped_faults.get(machine.machine_id, [])) >= 2
        ]
    elif intent == "low_utilization":
        records = [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if latest.get(machine.machine_id) and (latest[machine.machine_id].operating_hours or 0) < 10
        ]
    elif intent == "low_fuel":
        threshold = filters.get("fuel_threshold_percent") or 20
        records = [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if (
                latest.get(machine.machine_id)
                and latest[machine.machine_id].fuel_remaining_percent is not None
                and latest[machine.machine_id].fuel_remaining_percent <= threshold
            )
        ]
        records.sort(key=lambda item: item["fuel_remaining_percent"] if item["fuel_remaining_percent"] is not None else 999)
    elif intent == "single_machine_status":
        machine_id = filters.get("machine_id")
        records = [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if machine.machine_id == machine_id
        ]
    elif intent == "fault_summary":
        counts = Counter(fault.fault_code for fault in faults)
        records = [{"fault_code": code, "count": count} for code, count in counts.most_common()]
    elif intent == "fault_machines":
        records = [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if grouped_faults.get(machine.machine_id)
        ]
        matched_ids = {record["machine_id"] for record in records}
        for machine_id, machine_faults in grouped_faults.items():
            if machine_id not in matched_ids:
                records.append({
                    "machine_id": machine_id,
                    "serial_number": "Data not available",
                    "model": "Data not available",
                    "machine_type": "Data not available",
                    "customer": "Data not available",
                    "location": "Data not available",
                    "last_seen_at": "Data not available",
                    "hours_since_last_seen": None,
                    "operating_hours": None,
                    "idle_hours": None,
                    "fuel_remaining_percent": None,
                    "engine_status": "Data not available",
                    "fault_count": len(machine_faults),
                    "fault_codes": [fault.fault_code for fault in machine_faults],
                    "mapping_status": "Fault record could not be matched to the machine cache",
                })
    elif intent == "missing_data":
        for machine in machines:
            item = latest.get(machine.machine_id)
            missing = []
            if item is None:
                missing.append("telemetry")
            elif item.fuel_remaining_percent is None:
                missing.append("fuel_remaining_percent")
            if item and item.engine_status == "unknown":
                missing.append("engine_status")
            if missing:
                record = _machine_record(machine, item, grouped_faults.get(machine.machine_id, []))
                record["missing_fields"] = missing
                records.append(record)
    elif intent == "compare_machine_type":
        by_type: dict[str, dict[str, Any]] = {}
        for machine in machines:
            item = latest.get(machine.machine_id)
            bucket = by_type.setdefault(machine.machine_type, {
                "machine_type": machine.machine_type,
                "machine_count": 0,
                "total_operating_hours": 0.0,
                "fault_count": 0,
                "offline_count": 0,
            })
            bucket["machine_count"] += 1
            bucket["total_operating_hours"] += item.operating_hours if item and item.operating_hours else 0
            bucket["fault_count"] += len(grouped_faults.get(machine.machine_id, []))
            if (_hours_since(machine.last_seen_at) or 0) > 72:
                bucket["offline_count"] += 1
        records = list(by_type.values())
    else:
        records = [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
        ]

    offline_count = sum(1 for machine in machines if (_hours_since(machine.last_seen_at) or 0) > 72)
    repeated_fault_count = sum(1 for machine in machines if len(grouped_faults.get(machine.machine_id, [])) >= 2)
    low_utilization_count = sum(
        1 for machine in machines
        if latest.get(machine.machine_id) and (latest[machine.machine_id].operating_hours or 0) < 10
    )
    low_fuel_count = sum(
        1 for machine in machines
        if (
            latest.get(machine.machine_id)
            and latest[machine.machine_id].fuel_remaining_percent is not None
            and latest[machine.machine_id].fuel_remaining_percent <= 20
        )
    )
    summary_metrics = {
        "total_machines": len(machines),
        "total_fault_records": len(faults),
        "offline_machines": offline_count,
        "repeated_fault_machines": repeated_fault_count,
        "low_utilization_machines": low_utilization_count,
        "low_fuel_machines": low_fuel_count,
        "returned_records": len(records),
    }

    return {
        "intent": intent,
        "filters": filters,
        "records": records[:25],
        "summary_metrics": summary_metrics,
        "data_source": get_data_source(),
        "intent_plan": intent_plan or {"source": "rule_only", "intent": intent, "filters": filters},
    }


def run_query_with_data(question: str, query_plan: dict[str, Any], live_data: dict[str, Any]) -> dict[str, Any]:
    machines = [Machine(**item) for item in live_data.get("machines", [])]
    telemetry = [TelemetrySnapshot(**_telemetry_from_machine_record(item)) for item in live_data.get("machines", []) if item.get("recorded_at")]
    faults = [FaultCode(**item) for item in live_data.get("faults", [])]

    latest = _latest_telemetry_by_machine(telemetry)
    grouped_faults = _faults_by_machine(faults)
    if _use_ai_plan(query_plan):
        intent = _canonical_intent(query_plan["intent"])
        filters = query_plan.get("filters", {})
    else:
        intent, filters = detect_intent(question, machines)
        intent = _canonical_intent(intent)

    records = _records_for_intent(intent, filters, machines, latest, grouped_faults, faults)
    missing_fields = set(live_data.get("missing_fields", []))
    for record in records:
        missing_fields.update(record.get("missing_fields", []))

    offline_count = sum(1 for machine in machines if (_hours_since(machine.last_seen_at) or 0) > 72)
    repeated_fault_count = sum(1 for machine in machines if len(grouped_faults.get(machine.machine_id, [])) >= 2)
    low_utilization_count = sum(
        1 for machine in machines
        if latest.get(machine.machine_id) and (latest[machine.machine_id].operating_hours or 0) < 10
    )
    low_fuel_count = sum(
        1 for machine in machines
        if (
            latest.get(machine.machine_id)
            and latest[machine.machine_id].fuel_remaining_percent is not None
            and latest[machine.machine_id].fuel_remaining_percent <= 20
        )
    )
    summary_metrics = {
        "total_machines": len(machines),
        "total_fault_records": len(faults),
        "offline_machines": offline_count,
        "repeated_fault_machines": repeated_fault_count,
        "low_utilization_machines": low_utilization_count,
        "low_fuel_machines": low_fuel_count,
        "returned_records": len(records),
    }
    data_summary = dict(live_data.get("data_summary", {}))
    data_summary["records_used"] = len(records)

    return {
        "intent": intent,
        "filters": filters,
        "records": records[:25],
        "summary_metrics": summary_metrics,
        "data_source": live_data.get("source", "trackunit_cache"),
        "query_plan": query_plan,
        "intent_plan": query_plan,
        "data_summary": data_summary,
        "missing_fields": sorted(missing_fields),
        "fallback_used": live_data.get("fallback_used", False),
        "api_error": live_data.get("api_error"),
        "warnings": live_data.get("warnings", []),
    }


def _use_ai_plan(intent_plan: dict[str, Any] | None) -> bool:
    if not intent_plan:
        return False
    intent = intent_plan.get("intent")
    confidence = intent_plan.get("confidence", 0)
    return intent in SUPPORTED_INTENTS and confidence >= 0.45


def _records_for_intent(
    intent: str,
    filters: dict[str, Any],
    machines: list[Machine],
    latest: dict[str, TelemetrySnapshot],
    grouped_faults: dict[str, list[FaultCode]],
    faults: list[FaultCode],
) -> list[dict[str, Any]]:
    if intent == "offline_machines":
        threshold = filters.get("offline_hours") or 72
        return [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if (_hours_since(machine.last_seen_at) or 0) > threshold
        ]
    if intent == "repeated_faults":
        return [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if len(grouped_faults.get(machine.machine_id, [])) >= 2
        ]
    if intent == "low_utilization":
        return [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if latest.get(machine.machine_id) and (latest[machine.machine_id].operating_hours or 0) < 10
        ]
    if intent == "low_fuel":
        threshold = filters.get("fuel_threshold_percent") or 20
        records = [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if (
                latest.get(machine.machine_id)
                and latest[machine.machine_id].fuel_remaining_percent is not None
                and latest[machine.machine_id].fuel_remaining_percent <= threshold
            )
        ]
        records.sort(key=lambda item: item["fuel_remaining_percent"] if item["fuel_remaining_percent"] is not None else 999)
        return records
    if intent in {"machine_status", "single_machine_status", "location_query"}:
        target = _target_from_filters(filters)
        return [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if _matches_target(machine, target)
        ]
    if intent == "fault_summary":
        counts = Counter(fault.fault_code for fault in faults)
        return [{"fault_code": code, "count": count} for code, count in counts.most_common()]
    if intent == "fault_machines":
        return [
            _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
            for machine in machines
            if grouped_faults.get(machine.machine_id)
        ]
    if intent == "missing_data":
        records = []
        for machine in machines:
            item = latest.get(machine.machine_id)
            record = _machine_record(machine, item, grouped_faults.get(machine.machine_id, []))
            missing = []
            if item is None:
                missing.append("telemetry")
            elif item.fuel_remaining_percent is None:
                missing.append("fuel_remaining_percent")
            if item and item.engine_status == "unknown":
                missing.append("engine_status")
            if missing:
                record["missing_fields"] = missing
                records.append(record)
        return records
    if intent == "compare_machine_type":
        by_type: dict[str, dict[str, Any]] = {}
        for machine in machines:
            item = latest.get(machine.machine_id)
            bucket = by_type.setdefault(machine.machine_type, {
                "machine_type": machine.machine_type,
                "machine_count": 0,
                "total_operating_hours": 0.0,
                "fault_count": 0,
                "offline_count": 0,
            })
            bucket["machine_count"] += 1
            bucket["total_operating_hours"] += item.operating_hours if item and item.operating_hours else 0
            bucket["fault_count"] += len(grouped_faults.get(machine.machine_id, []))
            if (_hours_since(machine.last_seen_at) or 0) > 72:
                bucket["offline_count"] += 1
        return list(by_type.values())
    return [
        _machine_record(machine, latest.get(machine.machine_id), grouped_faults.get(machine.machine_id, []))
        for machine in machines
    ]


def _telemetry_from_machine_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "machine_id": item.get("machine_id"),
        "operating_hours": item.get("operating_hours"),
        "idle_hours": item.get("idle_hours"),
        "fuel_remaining_percent": item.get("fuel_remaining_percent"),
        "engine_status": item.get("engine_status"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "recorded_at": item.get("recorded_at"),
    }


def _canonical_intent(intent: str) -> str:
    if intent == "single_machine_status":
        return "machine_status"
    return intent


def _target_from_filters(filters: dict[str, Any]) -> str | None:
    value = filters.get("machine_query") or filters.get("machine_id")
    return str(value).lower() if value else None


def _matches_target(machine: Machine, target: str | None) -> bool:
    if not target:
        return True
    candidates = [machine.machine_id, machine.serial_number, machine.model]
    return any(candidate and target in candidate.lower() for candidate in candidates)
