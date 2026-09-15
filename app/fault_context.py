"""Source-backed fault and catalog lookup. This does not generate an AI diagnosis."""
from datetime import datetime, timezone

from app.data_store import get_data_source
from app.fault_evidence import assess_fault_events
from app.local_datasets import load_dataset
from app.parts_catalog import search_parts
from app.services.machine_service import find_machine, find_faults
from app.telemetry_evidence import timestamp


def get_fault_context(machine_id: str, fault_code: str, dataset_id: str | None = None) -> dict:
    cutoff = datetime.now(timezone.utc)
    source_document = None
    if dataset_id:
        try:
            dataset = load_dataset(dataset_id)
        except ValueError:
            raise LookupError('Dataset not found or invalid') from None
        machine, faults = dataset.machine, dataset.faults
        if machine.machine_id != machine_id:
            raise LookupError('Dataset machine mismatch')
        source = 'imported_' + dataset.provenance
        cutoff = dataset.replay_at or cutoff
        source_document = dataset.source_document
    else:
        machine = find_machine(machine_id)
        if machine is None:
            raise LookupError('Machine not found')
        faults, source = find_faults(machine_id), get_data_source()

    matching = [row for row in faults if row.fault_code.casefold() == fault_code.casefold()]
    facts = assess_fault_events(machine_id, matching, cutoff)
    valid = [(instant, row) for row in matching
        if row.machine_id == machine_id and (instant := timestamp(row.occurred_at)) is not None and instant <= cutoff]
    if not valid:
        raise LookupError('No accepted record for this device and fault code')
    latest = max(instant for instant, _ in valid)
    latest_statuses = sorted({row.status for instant, row in valid if instant == latest})
    diagnostics = {}
    candidates = search_parts(machine.model, machine.serial_number, [fault_code],
        include_demo=source in {'mock', 'imported_synthetic'}, diagnostics=diagnostics)
    return {'machine_id': machine_id, 'dataset_id': dataset_id, 'source': source,
        'model': machine.model, 'serial_number': machine.serial_number,
        'source_document': source_document, 'fault_code': fault_code,
        'as_of': cutoff.isoformat(), 'record_facts': facts,
        'latest_record_at': latest.isoformat(), 'latest_record_statuses': latest_statuses,
        'latest_record_status': latest_statuses[0] if len(latest_statuses) == 1 else 'conflicting',
        'parts_candidates': candidates, 'search_diagnostics': diagnostics,
        'lookup_method': 'exact_fault_code_model_serial_v1',
        'manual': {'status': 'not_integrated', 'provider': 'XGSS',
            'reason': '故障码字段、请求模式及获准调用身份待确认；尚未取得对应官方手册。'},
        'ai_used': False, 'upstream_sync_performed': False,
        'limitations': ['Local catalog lookup, not an AI diagnosis or fault confirmation.',
            'Catalog applicability does not certify machine configuration. No stock or price query was performed.']}
