"""Local device/version discovery; supplied fault records are not a health score."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import re

from app import data_store, local_datasets
from app.telemetry_evidence import timestamp

SEVERITY = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}


def summarize_faults(machine_id, faults, cutoff):
    latest = {}
    excluded = Counter()
    valid = 0
    for fault in faults:
        instant = timestamp(fault.occurred_at)
        if fault.machine_id != machine_id:
            excluded['other_machine'] += 1
        elif instant is None:
            excluded['invalid_timestamp'] += 1
        elif instant > cutoff:
            excluded['after_cutoff'] += 1
        else:
            valid += 1
            previous = latest.get(fault.fault_code)
            pair = (fault.status, fault.severity)
            if previous is None or instant > previous[0]:
                latest[fault.fault_code] = (instant, {pair})
            elif instant == previous[0]:
                previous[1].add(pair)
    unresolved = []
    conflicting = 0
    for _, pairs in latest.values():
        if len(pairs) > 1:
            conflicting += 1
        else:
            status, severity = next(iter(pairs))
            if status != 'resolved':
                unresolved.append(severity)
    state = ('conflicting' if conflicting else 'unresolved' if unresolved else
             'resolved_records' if latest else 'no_records')
    return {'state': state, 'unresolved_codes': len(unresolved),
            'conflicting_codes': conflicting,
            'highest_severity': max(unresolved, key=SEVERITY.get) if unresolved else None,
            'latest_record_at': max(row[0] for row in latest.values()).isoformat() if latest else None,
            'valid_records': valid, 'excluded_records': dict(excluded),
            'as_of': cutoff.isoformat()}


def device_index():
    now = datetime.now(timezone.utc)
    source = data_store.get_data_source()
    warnings, devices = [], []
    try:
        fleet = data_store.load_machines()
    except (OSError, ValueError, TypeError):
        fleet = []
        warnings.append('车队设备缓存无法读取；下方仍显示可用的导入数据。')
    try:
        fleet_faults = data_store.load_faults()
    except (OSError, ValueError, TypeError):
        fleet_faults = None
        warnings.append('车队故障缓存无法读取；未将其视作无故障。')
    by_machine = defaultdict(list)
    for fault in fleet_faults or []:
        by_machine[fault.machine_id].append(fault)
    for machine in fleet:
        summary = summarize_faults(machine.machine_id, by_machine[machine.machine_id], now)
        if fleet_faults is None:
            summary['state'] = 'unavailable'
        devices.append({**machine.model_dump(), 'selection_id': 'fleet:' + machine.machine_id,
                        'source': source, 'fault_summary': summary})
    unreadable = 0
    for path in sorted(local_datasets.DATASETS.glob('*.json')):
        if not re.fullmatch(r'[0-9a-f]{64}', path.stem):
            continue
        try:
            dataset = local_datasets.load_dataset(path.stem)
            metadata = local_datasets.dataset_summary(path.stem, dataset)
        except (OSError, ValueError, TypeError):
            unreadable += 1
            continue
        devices.append({**metadata.pop('machine'), **metadata,
                        'selection_id': 'dataset:' + path.stem,
                        'dataset_name': metadata['name'],
                        'source': 'imported_' + dataset.provenance,
                        'fault_summary': summarize_faults(dataset.machine.machine_id, dataset.faults,
                                                         dataset.replay_at or now)})
    if unreadable:
        warnings.append(f'{unreadable} 份导入数据无法读取，未列入结果；请核对导入文件。')
    return {'devices': devices, 'data_source': source, 'as_of': now.isoformat(),
            'warnings': warnings, 'ai_used': False, 'upstream_sync_performed': False}
