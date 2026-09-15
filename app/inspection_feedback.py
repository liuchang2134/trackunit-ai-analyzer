"""Append-only local inspection notes. Operator observations are not verified diagnoses."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator
from app.investigation_history import read_investigation

FEEDBACK_DIR=Path(__file__).resolve().parents[1]/'data/local/inspection-feedback'


class InspectionFeedback(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    check_id: str | None=Field(default=None,max_length=100)
    outcome: Literal['observed','not_observed','inconclusive']
    observed_at: datetime
    notes: str=Field(min_length=1,max_length=1000)

    @field_validator('observed_at')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None:raise ValueError('Observation time requires timezone')
        return value.astimezone(timezone.utc)


def save_feedback(record_id,payload):
    parent=read_investigation(record_id)
    if payload.observed_at>datetime.now(timezone.utc):raise ValueError('Observation time cannot be in the future')
    checks={c['check_id']:c for c in parent['report'].get('check_recommendations',[])}
    if payload.check_id and payload.check_id not in checks:raise ValueError('Check does not belong to this report')
    item={'record_id':record_id,'machine_id':parent['report']['machine_id'],
        **payload.model_dump(mode='json'),'check_text':checks[payload.check_id]['text'] if payload.check_id else None,
        'source':'unverified_operator_feedback','created_at':datetime.now(timezone.utc).isoformat()}
    content=json.dumps(item,ensure_ascii=False,sort_keys=True)
    feedback_id=hashlib.sha256(content.encode()).hexdigest()
    directory=FEEDBACK_DIR/record_id;directory.mkdir(parents=True,exist_ok=True)
    name=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=directory,delete=False) as stream:
            name=stream.name;stream.write(content)
        os.replace(name,directory/(feedback_id+'.json'))
    finally:
        if name and os.path.exists(name):os.unlink(name)
    return {'feedback_id':feedback_id,**item}


def list_feedback(record_id):
    parent=read_investigation(record_id)
    records=[]
    for path in (FEEDBACK_DIR/record_id).glob('*.json'):
        content=path.read_text(encoding='utf-8')
        if hashlib.sha256(content.encode()).hexdigest()!=path.stem:raise ValueError('Feedback integrity check failed')
        item=json.loads(content)
        if item['record_id']!=record_id or item['machine_id']!=parent['report']['machine_id']:
            raise ValueError('Feedback parent mismatch')
        records.append({'feedback_id':path.stem,**item})
    records.sort(key=lambda r:(r['observed_at'],r['created_at']))
    return {'records':records,'total':len(records)}


def feedback_context(feedback):
    """Keep the latest result of every supported check plus recent general notes."""
    latest_checks = {}
    for index, row in enumerate(feedback['records']):
        if row.get('check_id'):
            latest_checks[row['check_id']] = index
    included = set(latest_checks.values()) | set(range(max(0, len(feedback['records']) - 5), len(feedback['records'])))
    records = [row for index, row in enumerate(feedback['records']) if index in included]
    return {'total_records': feedback['total'], 'records': records,
            'selection': 'latest_per_check_plus_latest_five_records',
            'omitted_older_records': len(feedback['records']) - len(records),
            'source': 'unverified_operator_feedback'}
