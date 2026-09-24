"""Explicit, asset-scoped manufacturer identity corrections; never alter old imports."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

STATE_DIR = Path(__file__).resolve().parents[1] / 'data/local/xgss-identities'
SOURCE_NOTE = 'VIN/PIN: user confirmed; XGSS catalog accepted'


def source_document(value):
    """Keep the API evidence source separate from a locally confirmed identity."""
    text = str(value or '').strip()
    if SOURCE_NOTE in text:
        return text[:300]
    suffix = '; ' + SOURCE_NOTE
    return text[:300-len(suffix)].rstrip() + suffix


def normalized(value):
    return str(value or '').strip().upper()


def valid_vin(value):
    return bool(re.fullmatch(r'[A-Z0-9]{8,32}', normalized(value)))


def _path(machine_id):
    return STATE_DIR / (hashlib.sha256(machine_id.encode('utf-8')).hexdigest() + '.json')


def binding(machine):
    try:
        value = json.loads(_path(machine.machine_id).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or value.get('machine_id') != machine.machine_id:
        return None
    if (value.get('equipment_id') != normalized(machine.equipment_id)
            or value.get('model') != normalized(machine.model)
            or not valid_vin(value.get('vin'))
            or not isinstance(value.get('original_serial'), str)
            or normalized(machine.serial_number) not in (value['original_serial'], value['vin'])):
        return None
    if not all(re.fullmatch(r'[a-f0-9]{64}', str(value.get(key, '')))
               for key in ('source_dataset_id', 'replacement_dataset_id')):
        return None
    return value


def apply_binding(machine):
    verified = binding(machine)
    return machine.model_copy(update={'serial_number': verified['vin']}) if verified else machine


def needs_verification(machine):
    vin = normalized(machine.serial_number)
    verified = binding(machine)
    if verified and vin == verified['vin']:
        return False
    # Do not reject every numeric PIN. This specific collision indicates an
    # equipment identifier was reused as the manufacturer's serial number.
    return (not valid_vin(vin) or
            (vin.isdigit() and len(vin) < 17 and vin == normalized(machine.equipment_id)))


def status(machine, dataset_id=None):
    pending = needs_verification(machine)
    result = dict(status='vin_required' if pending else 'ready', needs_verification=pending,
                  machine_id=machine.machine_id, dataset_id=dataset_id,
                  vin=normalized(machine.serial_number), equipment_id=machine.equipment_id,
                  message=('当前资料只有设备编号，尚未核实整机 VIN/PIN。请核对铭牌或 Trackunit 的 Serial Number (VIN)，再查询 XGSS。'
                           if pending else '设备标识可用于查询 XGSS。'))
    verified = binding(machine)
    if verified and dataset_id == verified['source_dataset_id']:
        from app.local_datasets import load_dataset
        try:
            replacement = load_dataset(verified['replacement_dataset_id'])
            updated = replacement.machine
            if (replacement.provenance == 'user_supplied' and updated.machine_id == machine.machine_id
                    and normalized(updated.serial_number) == verified['vin']
                    and normalized(updated.equipment_id) == normalized(machine.equipment_id)
                    and normalized(updated.model) == normalized(machine.model)):
                result['replacement_dataset_id'] = verified['replacement_dataset_id']
        except (ValueError, OSError):
            pass
    return result


def save_binding(machine, source_dataset_id, new_vin, replacement_dataset_id):
    if not valid_vin(new_vin):
        raise ValueError('Invalid manufacturer VIN/PIN')
    value = dict(machine_id=machine.machine_id, original_serial=normalized(machine.serial_number),
                 equipment_id=normalized(machine.equipment_id), model=normalized(machine.model),
                 vin=normalized(new_vin), source_dataset_id=source_dataset_id,
                 replacement_dataset_id=replacement_dataset_id,
                 verified_at=datetime.now(timezone.utc).isoformat(),
                 verification='user_confirmed_and_xgss_catalog_accepted')
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=STATE_DIR, delete=False) as handle:
            temporary = handle.name
            json.dump(value, handle, ensure_ascii=False)
        os.replace(temporary, _path(machine.machine_id))
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return value
