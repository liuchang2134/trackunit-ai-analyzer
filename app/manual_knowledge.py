"""Version-scoped manufacturer excerpts for investigations.

Two locations are read, in order:

1. `data/local/manual-knowledge/` — the machine's own material, gitignored, normally the
   richer set.
2. `data/demo/manual-knowledge/` — a small distributable copy covering the pages the demo
   scenario cites, so a machine with no private material can still show what grounding an
   answer looks like.

The first existing file wins, so a machine holding the full material never silently falls
back to the subset. Entries are evidence, never executable instructions, and selecting a
configuration is not certification.
"""
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ROOT = Path(__file__).resolve().parents[1]
_PRIVATE_KNOWLEDGE = _ROOT / 'data/local/manual-knowledge/xe55u.json'
_PUBLIC_KNOWLEDGE = _ROOT / 'data/demo/manual-knowledge/xe55u.json'


def knowledge_path() -> Path:
    """The knowledge file to read, preferring the machine's own material."""
    return _PRIVATE_KNOWLEDGE if _PRIVATE_KNOWLEDGE.is_file() else _PUBLIC_KNOWLEDGE


# Kept for callers that read the path directly; resolved at import.
KNOWLEDGE_PATH = knowledge_path()
Configuration = Literal['unknown', 'XE55U.00III', 'XE55U.00VI']


class EngineeringFault(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    code: str = Field(pattern=r'^[A-Z][0-9]{3,6}$')
    model: Literal['XE55U']
    configuration: Configuration = 'unknown'
    source: Literal['test', 'operator_report']

    @field_validator('code', mode='before')
    @classmethod
    def normalize(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class ManualRecord(BaseModel):
    model_config = ConfigDict(extra='ignore', str_strip_whitespace=True)
    reference_id: str = Field(min_length=1, max_length=180, pattern=r'^[A-Za-z0-9:_-]+$')
    title: str = Field(min_length=1, max_length=500)
    model: Literal['XE55U']
    configuration: Literal['XE55U.00III', 'XE55U.00VI']
    version: str = Field(min_length=1, max_length=120)
    pdf_pages: list[int] = Field(min_length=1, max_length=20)
    section: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=18000)
    source_url: str = Field(min_length=1, max_length=4000)
    provenance: str | dict
    fault_codes: list[str] = Field(default_factory=list, max_length=100)

    @field_validator('pdf_pages')
    @classmethod
    def physical_pages(cls, values):
        if any(page < 1 for page in values):
            raise ValueError('PDF pages must be positive physical page numbers')
        return list(dict.fromkeys(values))

    @field_validator('source_url')
    @classmethod
    def safe_url(cls, value):
        parsed = urlparse(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Manual source must be an HTTPS document URL')
        return value


def retrieve_manuals(fault: EngineeringFault, machine_model: str) -> dict:
    if machine_model.strip().upper() != fault.model:
        raise ValueError('当前设备型号不是 XE55U，不能用于本次 XE55U 手册分析。')
    applicability = ('model_reference_only' if fault.configuration == 'unknown'
                     else 'configuration_selected_unverified')
    result = {'method': 'version_scoped_manual_retrieval_v1', 'records': [],
              'applicability': applicability, 'configuration': fault.configuration,
              'status': 'knowledge_unavailable'}
    # Read the module constant, not a fresh resolve: tests replace it to supply their own
    # knowledge file, and resolving again here would ignore that and read the real one.
    path = KNOWLEDGE_PATH
    if not path.is_file():
        return result
    if path.stat().st_size > 4_000_000:
        raise ValueError('Manual knowledge file exceeds supported size')
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    if payload.get('schema_version') != 1 or not isinstance(payload.get('records'), list):
        raise ValueError('Unsupported manual knowledge format')
    seen = set()
    for raw in payload['records']:
        record = ManualRecord.model_validate(raw)
        canonical_id = record.reference_id if record.reference_id.startswith('manual:') else 'manual:' + record.reference_id
        if canonical_id in seen:
            raise ValueError('Duplicate manual reference ID')
        seen.add(canonical_id)
        if record.model != fault.model or fault.code not in record.fault_codes:
            continue
        if fault.configuration != 'unknown' and record.configuration != fault.configuration:
            continue
        item = record.model_dump()
        item['reference_id'] = canonical_id
        item['applicability'] = applicability
        result['records'].append(item)
    # A small case library should never silently truncate relevant references.
    if len(result['records']) > 12:
        raise ValueError('Manual retrieval needs a narrower section scope')
    result['status'] = 'matched' if result['records'] else 'no_matching_code'
    return result


def engineering_fault_evidence(fault: EngineeringFault, retrieval: dict) -> dict:
    return {**fault.model_dump(), 'method': 'engineering_fault_input_v1',
            'observation_source': 'synthetic_test_input' if fault.source == 'test' else 'unverified_operator_report',
            'is_trackunit_event': False, 'applicability': retrieval['applicability'],
            'manual_status': retrieval['status'],
            'limitation': '测试输入，不代表机器实际发生此故障。' if fault.source == 'test' else '人工报告，尚未由 Trackunit 事件或现场检测验证。'}
