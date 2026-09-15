"""Explicit local drafts, independent of successful reports or AI availability."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.data_store import get_data_source
from app.investigation_history import read_investigation
from app.local_datasets import load_dataset
from app.local_assistant import ManualFault
from app.services.machine_service import find_machine

DRAFT_DIR = Path(__file__).resolve().parents[1]/'data/local/investigation-drafts'
_lock = RLock()
Source = Literal['mock','trackunit_cache','imported_synthetic','imported_user_supplied']


class DraftScopeError(ValueError):
    pass


class DraftConflict(ValueError):
    pass


class DraftContent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(default='', max_length=3000)
    observations: str = Field(default='', max_length=4000)
    task: Literal['auto','overview','trends','parts','comprehensive'] = 'comprehensive'
    language: Literal['zh','en'] = 'zh'
    prior_record_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    manual_fault: ManualFault | None = None

    @model_validator(mode='after')
    def has_content(self):
        if not (self.question.strip() or self.observations.strip() or self.prior_record_id or self.manual_fault):
            raise ValueError('Draft needs a question, observations or a manual fault code')
        return self


class DraftSaveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    machine_id: str = Field(min_length=1, max_length=200)
    dataset_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    source: Source
    expected_revision: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    content: DraftContent


def _scope(machine_id, dataset_id, source, content=None):
    try:
        if dataset_id:
            data=load_dataset(dataset_id)
            machine=data.machine
            actual_source='imported_'+data.provenance
        else:
            machine=find_machine(machine_id)
            actual_source=get_data_source()
        if machine is None or machine.machine_id!=machine_id or actual_source!=source:
            raise DraftScopeError('Draft device, dataset or source mismatch')
        if content and content.manual_fault and machine.model.strip().upper()!=content.manual_fault.model:
            raise DraftScopeError('Draft fault reference does not match the equipment model')
    except ValueError:
        raise DraftScopeError('Draft device, dataset or source mismatch') from None
    return {'machine_id':machine_id,'serial_number':machine.serial_number,
            'dataset_id':dataset_id,'source':source}


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
                                    separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _validate_prior(content, scope):
    if content.prior_record_id:
        try:
            prior=read_investigation(content.prior_record_id)
            if (prior['report']['machine_id']!=scope['machine_id'] or
                prior['report']['source']!=scope['source'] or
                prior['request'].get('dataset_id')!=scope['dataset_id']):
                raise ValueError('Prior report mismatch')
        except (ValueError, KeyError):
            raise DraftScopeError('Prior report does not belong to this scope') from None


def _read(scope):
    path=DRAFT_DIR/(_digest(scope)+'.json')
    try:
        raw=path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        if len(raw)>65536:raise ValueError('Oversized record')
        record=json.loads(raw)
        revision=record.pop('revision')
        if revision!=_digest(record) or record['schema_version']!=1 or record['scope']!=scope:
            raise ValueError('Draft integrity mismatch')
        if record['source_kind']!='unverified_operator_draft':raise ValueError('Invalid source')
        saved_at=datetime.fromisoformat(record['saved_at'])
        if saved_at.tzinfo is None:raise ValueError('Missing timezone')
        DraftContent.model_validate(record['content'])
        return {**record,'revision':revision}
    except (ValueError, KeyError, TypeError, AttributeError):
        raise OSError('Local draft cannot be verified') from None


def read_draft(machine_id, dataset_id, source):
    scope=_scope(machine_id,dataset_id,source)
    with _lock:
        record=_read(scope)
    if record:_validate_prior(DraftContent.model_validate(record['content']),scope)
    return {'draft':record,'ai_used':False}


def save_draft(request):
    scope=_scope(request.machine_id,request.dataset_id,request.source,request.content)
    _validate_prior(request.content,scope)
    with _lock:
        previous=_read(scope)
        if (previous['revision'] if previous else None)!=request.expected_revision:
            raise DraftConflict('A newer draft exists')
        content=request.content.model_dump(mode='json')
        if content['manual_fault'] is None:
            content.pop('manual_fault')  # Preserve the existing shape of code-free drafts.
        record={'schema_version':1,'scope':scope,'source_kind':'unverified_operator_draft',
                'saved_at':datetime.now(timezone.utc).isoformat(),
                'content':content}
        record['revision']=_digest(record)
        DRAFT_DIR.mkdir(parents=True,exist_ok=True)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=DRAFT_DIR,delete=False) as stream:
                temporary=stream.name
                json.dump(record,stream,ensure_ascii=False)
                stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,DRAFT_DIR/(_digest(scope)+'.json'))
        finally:
            if temporary and os.path.exists(temporary):os.unlink(temporary)
    return {'draft':record,'ai_used':False}
