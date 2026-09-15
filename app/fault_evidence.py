"""Timestamp-aware event facts; record repetition does not establish recurrence."""
from collections import Counter, defaultdict
from app.telemetry_evidence import timestamp


def assess_fault_events(machine_id, faults, now):
    excluded = Counter()
    grouped = defaultdict(dict)
    valid_rows = []
    for fault in faults:
        instant = timestamp(fault.occurred_at)
        if fault.machine_id != machine_id:
            excluded['other_machine'] += 1
        elif instant is None:
            excluded['invalid_timestamp'] += 1
        elif instant > now:
            excluded['after_cutoff'] += 1
        else:
            grouped[fault.fault_code].setdefault(instant, set()).add(fault.status)
            valid_rows.append((instant, fault))
    groups = []
    for code, instants in sorted(grouped.items()):
        ordered = sorted(instants)
        groups.append({'fault_code': code, 'unique_code_timestamp_records': len(ordered),
            'first_record_at': ordered[0].isoformat(), 'last_record_at': ordered[-1].isoformat(),
            'first_to_last_minutes': (ordered[-1]-ordered[0]).total_seconds()/60 if len(ordered)>1 else None,
            'consecutive_gaps_minutes': [(b-a).total_seconds()/60 for a,b in zip(ordered,ordered[1:])][-20:],
            'conflicting_status_timestamps': sum(len(statuses)>1 for statuses in instants.values()),
            'unresolved_code_timestamp_records': sum('resolved' not in statuses for statuses in instants.values()),
            'independent_failure_count': None})
    valid_rows.sort(key=lambda pair: pair[0])
    return {'method':'fault_record_facts_v1', 'as_of':now.isoformat(),
        'total_loaded_events':len(faults), 'valid_loaded_records':len(valid_rows),
        'excluded_records':dict(excluded), 'displayed_events_limit':20,
        'events':[f.model_dump(exclude={'raw_payload'}) for _,f in valid_rows[-20:]],
        'groups':groups[:20], 'total_fault_code_groups':len(groups),
        'limitation':'Only supplied records before cutoff. Code/time uniqueness does not prove separate failures; time span is not a recurrence period. Fault codes are not part numbers or component IDs. Empty events do not prove health.'}
