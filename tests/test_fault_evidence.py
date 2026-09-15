from datetime import datetime, timezone
from app.models import FaultCode
from app.fault_evidence import assess_fault_events


def event(at, **updates):
    return FaultCode(**{'machine_id':'D1','fault_code':'F1','description':'test',
        'severity':'medium','occurred_at':at,'status':'open',**updates})


def test_offsets_duplicates_conflicting_status_do_not_create_failures():
    faults=[event('2026-06-29T08:20:00Z'),event('2026-06-29T04:20:00-04:00'),
        event('2026-06-29T08:20:00Z',status='resolved'),event('2026-06-29T08:45:00Z')]
    facts=assess_fault_events('D1',faults,datetime(2026,6,29,9,tzinfo=timezone.utc))
    group=facts['groups'][0]
    assert group['unique_code_timestamp_records']==2
    assert group['first_to_last_minutes']==25
    assert group['consecutive_gaps_minutes']==[25]
    assert group['conflicting_status_timestamps']==1
    assert group['unresolved_code_timestamp_records']==1
    assert group['independent_failure_count'] is None


def test_foreign_future_naive_and_invalid_dates_are_excluded():
    faults=[event('bad'),event('2026-06-29T08:00:00'),event('2026-06-30T08:00:00Z'),
        event('2026-06-29T08:00:00Z',machine_id='D2'),event('2026-06-29T08:20:00Z')]
    facts=assess_fault_events('D1',faults,datetime(2026,6,29,9,tzinfo=timezone.utc))
    assert facts['excluded_records']=={'invalid_timestamp':2,'after_cutoff':1,'other_machine':1}
    assert facts['groups'][0]['first_to_last_minutes'] is None
    assert len(facts['events'])==1
