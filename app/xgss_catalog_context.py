"""Device-bound snapshots of user-visible XGSS rows, stored only in data/local.

This module does not call XGSS, fabricate a BOM, or interpret a capture as a repair
recommendation. Source rows are immutable references for the inference layer.
"""
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STORE = Path(__file__).resolve().parents[1] / 'data/local/xgss-catalog-context'


class CatalogRow(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=240)
    part_number: str = Field(min_length=3, max_length=64, pattern=r'^[A-Za-z0-9][A-Za-z0-9._/-]{2,63}$')
    figure_ref: str | None = Field(default=None, max_length=80)
    quantity: str | None = Field(default=None, max_length=40)

    @field_validator('part_number')
    @classmethod
    def requires_number(cls, value):
        if not any(c.isdigit() for c in value):
            raise ValueError('Expected a material code, not a column label')
        return value


class CatalogCapture(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    schema_version: Literal[1]
    source: Literal['xgss_visible_dom']
    # A session URL must never enter storage or be forwarded to AI.
    source_url: Literal['https://xgss.xcmg.com/']
    vin: str | None = Field(default=None, pattern=r'^[A-Z0-9]{8,32}$')
    model: str | None = Field(default=None, max_length=80)
    configuration: str | None = Field(default=None, max_length=80)
    assembly_path: list[str] = Field(default_factory=list, max_length=12)
    items: list[CatalogRow] = Field(default_factory=list, max_length=200)
    capture_status: Literal['visible_rows','no_visible_rows','unrecognized_table','vin_missing','ambiguous_vin']
    visible_rows: int = Field(ge=0, le=200, strict=True)
    skipped_rows: int = Field(default=0, ge=0, le=100000, strict=True)
    coverage: Literal['visible_rows_only']
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def check_capture(self):
        if self.visible_rows != len(self.items):
            raise ValueError('Visible row count does not match items')
        if any(not value.strip() or len(value)>160 for value in self.assembly_path):
            raise ValueError('Invalid assembly path')
        if any(len(value)>300 for value in self.warnings):
            raise ValueError('Invalid capture warning')
        return self


def _scope(dataset_id, vin, machine_id):
    if dataset_id is not None and not re.fullmatch(r'[a-f0-9]{64}', dataset_id):
        raise ValueError('Invalid dataset identifier')
    if not isinstance(vin,str) or not re.fullmatch(r'[A-Z0-9]{8,32}',vin):
        raise ValueError('Invalid VIN')
    if not dataset_id and (not isinstance(machine_id,str) or not 1<=len(machine_id)<=200):
        raise ValueError('A machine identifier is required without a dataset')
    scope={'dataset_id':dataset_id,'vin':vin,'machine_id':machine_id if not dataset_id else None}
    return hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()


def save_catalog_context(capture: CatalogCapture, *, dataset_id=None, machine_id):
    if capture.capture_status!='visible_rows' or not capture.items or not capture.vin:
        raise ValueError('图册未读取到可确认 VIN 的有效条目。请打开零件明细并重新读取。')
    scope = _scope(dataset_id,capture.vin,machine_id)
    content=capture.model_dump()
    content.update(machine_id=machine_id,dataset_id=dataset_id)
    capture_id=hashlib.sha256(json.dumps(content,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    now=datetime.now(timezone.utc).isoformat()
    result={**content,'status':'captured','capture_id':capture_id,'captured_at':now,
            'items':[{**row,'source_id':f'xgss:{capture_id}:{i+1}'} for i,row in enumerate(content['items'])]}
    STORE.mkdir(parents=True,exist_ok=True)
    snapshot_path=STORE/f'{capture_id}.json'
    if snapshot_path.exists():
        # Identical source rows retain the original immutable reference and timestamp.
        result=json.loads(snapshot_path.read_text(encoding='utf-8'))
    else:
        _atomic_write(snapshot_path,result)
    _atomic_write(STORE/f'scope-{scope}.json',{'capture_id':capture_id})
    return result


def _atomic_write(path, value):
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=STORE,delete=False) as stream:
            temporary=stream.name
            json.dump(value,stream,ensure_ascii=False,indent=2)
        os.replace(temporary,path)
    finally:
        if temporary and os.path.exists(temporary): os.unlink(temporary)


def load_catalog_context(dataset_id=None, vin=None, machine_id=None):
    absent={'status':'not_captured','machine_id':machine_id,'dataset_id':dataset_id,'vin':vin,'items':[]}
    if not vin or (not dataset_id and not machine_id): return absent
    scope=_scope(dataset_id,vin,machine_id)
    pointer=STORE/f'scope-{scope}.json'
    if not pointer.is_file(): return absent
    capture_id=json.loads(pointer.read_text(encoding='utf-8')).get('capture_id')
    if not isinstance(capture_id,str) or not re.fullmatch(r'[a-f0-9]{64}',capture_id):
        raise ValueError('Invalid capture index')
    result=json.loads((STORE/f'{capture_id}.json').read_text(encoding='utf-8'))
    if result.get('vin')!=vin or result.get('dataset_id')!=dataset_id or (machine_id and result.get('machine_id')!=machine_id):
        raise ValueError('Capture does not match selected machine')
    # Revalidate stored rows before allowing them to become AI evidence.
    fields={k:result[k] for k in CatalogCapture.model_fields}
    fields['items']=[{k:v for k,v in row.items() if k!='source_id'} for row in result['items']]
    capture=CatalogCapture.model_validate(fields)
    if capture.capture_status!='visible_rows': raise ValueError('Invalid stored capture')
    canonical={**capture.model_dump(),'machine_id':result.get('machine_id'),'dataset_id':result.get('dataset_id')}
    expected=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if expected!=capture_id or result.get('capture_id')!=capture_id:
        raise ValueError('Capture content does not match its reference')
    if any(row.get('source_id')!=f'xgss:{capture_id}:{i+1}' for i,row in enumerate(result['items'])):
        raise ValueError('Invalid source row identifier')
    return result
