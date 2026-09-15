"""Deterministic time-window evidence, not a calibrated failure predictor."""
from collections import Counter
from datetime import datetime, timezone
import math

from app.models import Machine, TelemetrySnapshot, FaultCode


def timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, AttributeError):
        return None


def number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def ordered_samples(machine_id: str, telemetry: list[TelemetrySnapshot], now: datetime):
    """One ordering policy shared by calculations and the plotted observations."""
    groups = {}
    excluded = Counter()
    for sample in telemetry:
        if sample.machine_id != machine_id:
            excluded["other_machine"] += 1
            continue
        instant = timestamp(sample.recorded_at)
        if instant is None or instant > now:
            excluded["invalid_or_future_timestamp"] += 1
            continue
        groups.setdefault(instant, []).append(sample)
    ordered = []
    for instant, samples in sorted(groups.items()):
        # Contradictory records at the same instant have no authoritative ordering.
        fields = [(s.operating_hours, s.idle_hours, s.fuel_remaining_percent) for s in samples]
        if any(values != fields[0] for values in fields[1:]):
            excluded["conflicting_timestamp"] += len(samples)
            continue
        ordered.append((instant, samples[0]))
        excluded["duplicate"] += len(samples) - 1
    return ordered, excluded


def assess_history(machine: Machine, telemetry: list[TelemetrySnapshot], faults: list[FaultCode],
                   now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Reference time must include timezone")
    findings = []
    ordered, excluded = ordered_samples(machine.machine_id, telemetry, now)
    latest = ordered[-1][0] if ordered else None
    age = (now - latest).total_seconds() / 3600 if latest else None
    if age is not None and age > 24:
        findings.append({"code": "stale_telemetry", "kind": "data_quality",
                         "evidence": {"age_hours": round(age, 2)},
                         "meaning": "Old observations cannot establish current machine condition."})
    last_seen = timestamp(machine.last_seen_at)
    last_seen_age = (now - last_seen).total_seconds() / 3600 if last_seen and last_seen <= now else None
    if last_seen_age is not None and last_seen_age > 72:
        findings.append({"code": "reporting_gap", "kind": "connectivity_or_shutdown",
                         "evidence": {"last_seen_age_hours": round(last_seen_age, 2)},
                         "meaning": "Confirm work schedule, terminal power and communications; this is not proof of mechanical failure."})
    intervals = []
    invalid_intervals = 0
    operating_samples = [(t, row) for t, row in ordered if row.operating_hours is not None]
    for (t0, a), (t1, b) in zip(operating_samples, operating_samples[1:]):
        elapsed = (t1 - t0).total_seconds() / 3600
        if not all(number(v) and v >= 0 for v in (a.operating_hours, b.operating_hours)):
            invalid_intervals += 1
            continue
        operating = b.operating_hours - a.operating_hours
        idle = b.idle_hours - a.idle_hours if all(number(v) and v >= 0 for v in (a.idle_hours, b.idle_hours)) else None
        # Allow one minute rounding on counters; never clamp a reset into activity.
        if operating < 0 or operating > elapsed + 1/60:
            invalid_intervals += 1
            findings.append({"code": "invalid_counter_interval", "kind": "data_quality",
                "evidence": {"start": t0.isoformat(), "end": t1.isoformat(),
                             "operating_delta": operating, "idle_delta": idle},
                "meaning": "Counter reset, mismatched measurement times or inconsistent data; excluded from utilization."})
            continue
        if idle is not None and (idle < 0 or idle > operating + 1/60):
            findings.append({"code": "invalid_idle_interval", "kind": "data_quality",
                "evidence": {"start": t0.isoformat(), "end": t1.isoformat(), "idle_delta": idle},
                "meaning": "Invalid idle increment excluded; independently valid operating increment retained."})
            idle = None
        intervals.append({"elapsed_hours": elapsed, "operating_hours": operating, "idle_hours": idle})
    operating = sum(i["operating_hours"] for i in intervals)
    paired_intervals = [i for i in intervals if i["idle_hours"] is not None]
    idle = sum(i["idle_hours"] for i in paired_intervals)
    idle_coverage = bool(intervals) and len(paired_intervals) == len(intervals)
    ratio = idle / operating if idle_coverage and operating >= 0.5 and idle <= operating else None
    valid_operating_samples = sum(number(row.operating_hours) and row.operating_hours >= 0 for _, row in ordered)
    valid_idle_samples = sum(number(row.idle_hours) and row.idle_hours >= 0 for _, row in ordered)
    operating_reasons = []
    if not intervals:
        operating_reasons.append(
            "Fewer than two valid operating-counter timestamps; an increment needs two distinct timestamps."
            if valid_operating_samples < 2 else
            "No operating interval passed counter consistency checks; inspect excluded intervals.")
    idle_reasons = list(operating_reasons)
    if intervals and not idle_coverage:
        idle_reasons.append("Some accepted operating intervals lack valid aligned idle-counter endpoints or increments.")
    ratio_reasons = list(idle_reasons)
    if intervals and operating < 0.5:
        ratio_reasons.append("Accepted operating increments total less than the 0.5-hour calculation minimum; this is not a fault limit or a full work-cycle requirement.")
    if idle_coverage and idle > operating:
        ratio_reasons.append("Summed idle increment exceeds summed operating increment; no ratio is reported.")
    if ratio is not None and ratio > 0.4:
        findings.append({"code": "high_idle_share", "kind": "operating_efficiency",
            "evidence": {"idle_share": round(ratio, 4), "operating_hours": operating},
            "meaning": "Review work organization. 40% is an assumed screening threshold, not an OEM fault limit."})
    events = {}
    for fault in faults:
        instant = timestamp(fault.occurred_at)
        if fault.machine_id != machine.machine_id or instant is None or instant > now:
            continue
        if (now - instant).total_seconds() > 7 * 86400:
            continue
        # Repeated copies of the same code/time are not independent failures.
        key = (fault.fault_code, instant)
        events.setdefault(key, set()).add(fault.status)
    counts = Counter(code for (code, _), statuses in events.items() if "resolved" not in statuses)
    for code, count in counts.items():
        if count >= 2:
            findings.append({"code": "repeated_unresolved_events", "kind": "inspection_priority",
                "evidence": {"fault_code": code, "unique_events_7d": count},
                "meaning": "Repeated records warrant inspection; verify whether the source repeats one persistent fault."})
    return {"method": "time_window_rules_v1", "as_of": now.isoformat(),
        "sample_count": len(ordered), "completeness": "not_verified", "fault_coverage": "unknown",
        "window_duration_hours": round((ordered[-1][0] - ordered[0][0]).total_seconds()/3600,4) if len(ordered)>1 else None, "excluded_samples": dict(excluded),
        "window_start": ordered[0][0].isoformat() if ordered else None,
        "window_end": latest.isoformat() if latest else None,
        "valid_intervals": len(intervals), "excluded_intervals": invalid_intervals,
        "operating_hours_delta": round(operating, 4) if intervals else None,
        "idle_hours_delta": round(idle, 4) if idle_coverage else None,
        "paired_idle_intervals": len(paired_intervals),
        "idle_counter_coverage": "all_valid_operating_intervals" if idle_coverage else "missing_or_invalid" if intervals else "no_valid_operating_intervals",
        "valid_counter_sample_counts": {"operating": valid_operating_samples, "idle": valid_idle_samples},
        "metric_unavailable_reasons": {"operating_hours_delta": operating_reasons,
            "idle_hours_delta": idle_reasons, "idle_share": ratio_reasons},
        "operating_counter_window_start": operating_samples[0][0].isoformat() if operating_samples else None,
        "operating_counter_window_end": operating_samples[-1][0].isoformat() if operating_samples else None,
        "idle_share": round(ratio, 4) if ratio is not None else None,
        "latest_age_hours": round(age, 2) if age is not None else None,
        "findings": findings[:30], "findings_total": len(findings),
        "limitations": ["No remaining-life or calibrated failure probability is estimated.",
            "Only supplied records are assessed; absent findings do not prove health.",
            "Counter deltas assume aligned sample timestamps and cumulative engine-running/idle counters.",
            "Idle share requires at least 0.5 valid operating hours and aligned idle counters across every accepted operating interval. Operating increments are sums of valid intervals, not proof of full-window coverage."]}
