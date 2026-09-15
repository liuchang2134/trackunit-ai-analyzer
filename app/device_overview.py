"""Selected-device evidence for the UI; no AI call and no upstream synchronization."""
from datetime import datetime, timezone
from hashlib import sha256
import json

from app.data_store import get_data_source
from app.local_datasets import load_dataset
from app.services.machine_service import find_machine, find_telemetry, find_faults
from app.telemetry_evidence import assess_history, ordered_samples, number
from app.fault_evidence import assess_fault_events


def build_overview(machine, telemetry, faults, *, source, cutoff, dataset_id=None, max_points=720):
    ordered, excluded = ordered_samples(machine.machine_id, telemetry, cutoff)
    total = len(ordered)
    indices = list(range(total)) if total <= max_points else sorted({
        round(i * (total - 1) / (max_points - 1)) for i in range(max_points)})
    points = []
    for index in indices:
        instant, sample = ordered[index]
        row = {'recorded_at': instant.isoformat()}
        for field in ('operating_hours','idle_hours','fuel_remaining_percent'):
            value = getattr(sample, field)
            row[field] = value if number(value) and value >= 0 and (field != 'fuel_remaining_percent' or value <= 100) else None
        points.append(row)
    trend = assess_history(machine, telemetry, faults, now=cutoff)
    plot_identity = {'machine_id': machine.machine_id, 'dataset_id': dataset_id,
                     'source': source, 'model': machine.model,
                     'serial_number': machine.serial_number, 'series': points,
                     'sampled_for_display': total > max_points}
    plot_revision = sha256(json.dumps(plot_identity, sort_keys=True, ensure_ascii=False,
                                      separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
    return {'machine_id':machine.machine_id, 'dataset_id':dataset_id, 'source':source,
            'plot_revision':plot_revision,
            'model':machine.model, 'serial_number':machine.serial_number,
            'as_of':cutoff.isoformat(), 'trend':trend,
            'faults':assess_fault_events(machine.machine_id,faults,cutoff),
            'series':points, 'loaded_samples':len(telemetry), 'valid_timestamp_samples':total,
            'excluded_samples':dict(excluded), 'displayed_samples':len(points),
            'sampled_for_display':total>max_points,
            'ai_used':False, 'upstream_sync_performed':False,
            'limit':'Observed counter values only; missing values are gaps. Statistics use all accepted intervals, not the display sample.'}


def device_overview(machine_id: str, dataset_id: str | None = None):
    if dataset_id:
        data = load_dataset(dataset_id)
        if data.machine.machine_id != machine_id:
            raise ValueError('Dataset machine mismatch')
        return build_overview(data.machine,data.telemetry,data.faults,
            source='imported_'+data.provenance,cutoff=data.replay_at or datetime.now(timezone.utc),dataset_id=dataset_id)
    machine = find_machine(machine_id)
    if machine is None:
        raise ValueError('Machine not found')
    return build_overview(machine,find_telemetry(machine_id),find_faults(machine_id),
        source=get_data_source(),cutoff=datetime.now(timezone.utc))
