from datetime import datetime, timezone
from app.models import Machine, TelemetrySnapshot, FaultCode
from app.telemetry_evidence import assess_history

NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
M = Machine(machine_id="E1", serial_number="S", model="EX", machine_type="excavator", customer="demo", location="demo", last_seen_at="2026-09-14T12:00:00Z")


def sample(hour, op, idle, **kwargs):
    return TelemetrySnapshot(machine_id="E1", recorded_at=f"2026-09-14T{hour:02d}:00:00Z", operating_hours=op, idle_hours=idle, **kwargs)


def test_sorted_counter_deltas_not_lifetime_ratio():
    r = assess_history(M, [sample(12, 102, 80.5), sample(10, 100, 80)], [], NOW)
    assert r["operating_hours_delta"] == 2
    assert r["idle_share"] == .25
    assert not any(f["code"] == "high_idle_share" for f in r["findings"])
    assert not any(r['metric_unavailable_reasons'].values())


def test_single_counter_pair_is_insufficient_not_missing_idle():
    r=assess_history(M,[sample(12,100,20)],[],NOW)
    assert r['valid_counter_sample_counts']=={'operating':1,'idle':1}
    assert r['idle_counter_coverage']=='no_valid_operating_intervals'
    assert r['operating_hours_delta'] is None and r['idle_share'] is None
    assert all('two distinct timestamps' in reasons[0] for reasons in r['metric_unavailable_reasons'].values())


def test_ratio_minimum_is_distinct_from_missing_counter_data():
    r=assess_history(M,[sample(10,100,20),sample(11,100.25,20.1)],[],NOW)
    assert r['operating_hours_delta']==.25 and r['idle_hours_delta']==.1
    assert r['idle_share'] is None
    assert r['metric_unavailable_reasons']['operating_hours_delta']==[]
    assert r['metric_unavailable_reasons']['idle_hours_delta']==[]
    assert '0.5-hour' in r['metric_unavailable_reasons']['idle_share'][0]


def test_rejected_intervals_are_not_reported_as_too_few_samples():
    r=assess_history(M,[sample(10,100,20),sample(11,1,0)],[],NOW)
    assert r['valid_counter_sample_counts']=={'operating':2,'idle':2}
    assert 'consistency checks' in r['metric_unavailable_reasons']['operating_hours_delta'][0]


def test_reset_and_impossible_increments_excluded():
    r = assess_history(M, [sample(9, 100, 10), sample(10, 1, 0), sample(11, 5, 1)], [], NOW)
    assert r["excluded_intervals"] == 2
    assert r["operating_hours_delta"] is None


def test_conflicts_duplicates_future_and_missing_time():
    records = [sample(10, 100, 10), sample(10, 100, 10), sample(11, 101, 11), sample(11, 102, 11), sample(13, 103, 12)]
    records.append(TelemetrySnapshot(machine_id="E1", recorded_at="unknown"))
    r = assess_history(M, records, [], NOW)
    assert r["sample_count"] == 1
    assert r["excluded_samples"] == {"invalid_or_future_timestamp": 2, "duplicate": 1, "conflicting_timestamp": 2}
    assert r["idle_share"] is None


def test_fault_dedup_and_resolved_not_counted():
    def event(time, status="open"):
        return FaultCode(machine_id="E1", fault_code="X", description="test", severity="medium", occurred_at=time, status=status)
    e=event("2026-09-14T09:00:00Z")
    r=assess_history(M, [], [e,e,event("2026-09-14T10:00:00Z", "resolved")], NOW)
    assert not r["findings"]
    r=assess_history(M, [], [e,event("2026-09-14T10:00:00Z")], NOW)
    assert r["findings"][0]["evidence"]["unique_events_7d"] == 2


def test_stale_is_not_mechanical_failure():
    old = TelemetrySnapshot(machine_id="E1", recorded_at="2026-01-01T00:00:00Z")
    r = assess_history(M, [old], [], NOW)
    assert r["findings"][0]["kind"] == "data_quality"
    assert r["idle_share"] is None


def test_operating_hours_do_not_require_idle_data():
    r = assess_history(M, [sample(10, 10, None), sample(12, 11.5, None)], [], NOW)
    assert r["operating_hours_delta"] == 1.5
    assert r["valid_intervals"] == 1
    assert r["idle_hours_delta"] is None and r["idle_share"] is None


def test_idle_only_sample_does_not_break_operating_series():
    r = assess_history(M, [sample(10, 10, None), sample(11, None, 2), sample(12, 11.5, None)], [], NOW)
    assert r["operating_hours_delta"] == 1.5
    assert r["idle_share"] is None


def test_partial_idle_is_not_divided_by_full_operating_increment():
    r = assess_history(M, [sample(10, 10, 2), sample(11, 11, 2.5), sample(12, 12, None)], [], NOW)
    assert r["operating_hours_delta"] == 2
    assert r["paired_idle_intervals"] == 1
    assert r["idle_share"] is None


def test_idle_reset_does_not_discard_valid_operating_increment():
    r = assess_history(M, [sample(10, 10, 2), sample(12, 12, 1)], [], NOW)
    assert r["operating_hours_delta"] == 2
    assert r["idle_share"] is None
    assert any(f["code"] == "invalid_idle_interval" for f in r["findings"])
