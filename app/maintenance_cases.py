"""Local operator case tracking; never changes machine faults or AI reports."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.device_index import device_index
from app.investigation_drafts import Source
from app.investigation_history import read_investigation

CASE_DB = Path(__file__).resolve().parents[1] / 'data/local/maintenance-cases.sqlite3'
State = Literal['open', 'in_progress', 'waiting', 'archived']
LABELS = {'open': '待开始', 'in_progress': '排查中', 'waiting': '待补充', 'archived': '已归档'}


class CaseMissing(ValueError):
    pass


class CaseConflict(ValueError):
    pass


class CaseScopeError(ValueError):
    pass


class CreateCase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    machine_id: str = Field(min_length=1, max_length=200)
    source: Source
    dataset_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    title: str = Field(min_length=1, max_length=120)
    note: str = Field(default='', max_length=4000)

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Title is empty')
        return value.strip()


class CaseEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1, strict=True)
    state: State
    note: str = Field(min_length=1, max_length=4000)
    report_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')

    @field_validator('note')
    @classmethod
    def note_not_blank(cls, value):
        if not value.strip():
            raise ValueError('A handling note is required')
        return value


@contextmanager
def database():
    CASE_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = None
    try:
        connection = sqlite3.connect(CASE_DB, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY, scope_key TEXT NOT NULL, scope_json TEXT NOT NULL,
                machine_id TEXT NOT NULL, source TEXT NOT NULL, dataset_id TEXT,
                title TEXT NOT NULL, state TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS active_case_scope
                ON cases(scope_key) WHERE state != 'archived';
            CREATE TABLE IF NOT EXISTS case_events (
                case_id TEXT NOT NULL REFERENCES cases(case_id), revision INTEGER NOT NULL,
                kind TEXT NOT NULL, from_state TEXT, to_state TEXT NOT NULL,
                note TEXT NOT NULL, report_id TEXT, created_at TEXT NOT NULL,
                PRIMARY KEY(case_id, revision));
        ''')
        yield connection
    except sqlite3.Error:
        raise OSError('Local case storage unavailable') from None
    finally:
        if connection is not None:
            connection.close()


def _scope(machine_id, dataset_id, source):
    for item in device_index()['devices']:
        if (item['machine_id'] == machine_id and item.get('dataset_id') == dataset_id
                and item['source'] == source):
            identity = {key: item.get(key) for key in ('machine_id', 'serial_number', 'source', 'dataset_id')}
            key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            snapshot = {**identity, **{name: item.get(name) for name in (
                'model', 'selection_id', 'dataset_name', 'last_seen_at', 'fault_summary')}}
            return key, snapshot
    raise CaseScopeError('Device scope is unavailable')


def _record(connection, case_id, events=True):
    if not re.fullmatch(r'[0-9a-f]{32}', case_id):
        raise CaseMissing('Invalid case ID')
    row = connection.execute('SELECT * FROM cases WHERE case_id=?', (case_id,)).fetchone()
    if row is None:
        raise CaseMissing('Case unavailable')
    value = dict(row)
    try:
        value['scope'] = json.loads(value.pop('scope_json'))
        if value['state'] not in LABELS or not isinstance(value['scope'], dict):
            raise ValueError('Invalid case record')
    except (ValueError, TypeError):
        raise OSError('Case record cannot be read') from None
    value.pop('scope_key')
    value['source_kind'] = 'unverified_operator_case'
    if events:
        value['events'] = [dict(event) for event in connection.execute(
            'SELECT revision,kind,from_state,to_state,note,report_id,created_at FROM case_events '
            'WHERE case_id=? ORDER BY revision', (case_id,))]
        if len(value['events']) != value['revision'] or any(
                event['revision'] != index for index, event in enumerate(value['events'], 1)):
            raise OSError('Case history is incomplete')
    return value


def read_case(case_id):
    with database() as connection:
        # Keep summary and event history in the same read snapshot.
        connection.execute('BEGIN')
        return _record(connection, case_id)


def current_case(machine_id, dataset_id, source):
    key, _ = _scope(machine_id, dataset_id, source)
    with database() as connection:
        connection.execute('BEGIN')
        row = connection.execute("SELECT case_id FROM cases WHERE scope_key=? AND state!='archived'", (key,)).fetchone()
        return _record(connection, row['case_id']) if row else None


def create_case(request):
    key, scope = _scope(request.machine_id, request.dataset_id, request.source)
    now = datetime.now(timezone.utc).isoformat()
    with database() as connection:
        connection.execute('BEGIN IMMEDIATE')
        existing = connection.execute("SELECT case_id FROM cases WHERE scope_key=? AND state!='archived'", (key,)).fetchone()
        if existing:
            return {'case': _record(connection, existing['case_id']), 'created': False, 'ai_used': False}
        case_id = uuid4().hex
        connection.execute('INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?)', (
            case_id, key, json.dumps(scope, ensure_ascii=False), request.machine_id, request.source,
            request.dataset_id, request.title, 'open', now, now, 1))
        connection.execute('INSERT INTO case_events VALUES (?,?,?,?,?,?,?,?)', (
            case_id, 1, 'created', None, 'open', request.note, None, now))
        result = _record(connection, case_id)
        connection.commit()
    return {'case': result, 'created': True, 'ai_used': False}


def append_event(case_id, request):
    with database() as connection:
        connection.execute('BEGIN IMMEDIATE')
        previous = _record(connection, case_id)
        if previous['revision'] != request.expected_revision:
            raise CaseConflict('A newer case revision exists')
        if request.report_id:
            try:
                report = read_investigation(request.report_id)
                if (report['report']['machine_id'] != previous['machine_id'] or
                        report['report']['source'] != previous['source'] or
                        report['request'].get('dataset_id') != previous['dataset_id']):
                    raise ValueError('Report scope mismatch')
            except (ValueError, KeyError, TypeError):
                raise CaseScopeError('Report belongs to a different device or data version') from None
        if previous['state'] == 'archived' and request.state != 'archived':
            other = connection.execute("SELECT case_id FROM cases WHERE machine_id=? AND source=? "
                                       "AND dataset_id IS ? AND state!='archived' AND case_id!=?", (
                previous['machine_id'], previous['source'], previous['dataset_id'], case_id)).fetchone()
            if other:
                raise CaseConflict('Another active case already exists for this device version')
        now = datetime.now(timezone.utc).isoformat()
        revision = previous['revision'] + 1
        connection.execute('INSERT INTO case_events VALUES (?,?,?,?,?,?,?,?)', (
            case_id, revision, 'operator_update', previous['state'], request.state, request.note, request.report_id, now))
        connection.execute('UPDATE cases SET state=?,updated_at=?,revision=? WHERE case_id=?', (
            request.state, now, revision, case_id))
        result = _record(connection, case_id)
        connection.commit()
    return {'case': result, 'ai_used': False}


def list_cases(state='active', limit=20, offset=0, machine_id=None, real_only=False):
    conditions, args = [], []
    if state == 'active':
        conditions.append("state!='archived'")
    elif state == 'archived':
        conditions.append("state='archived'")
    if machine_id is not None:
        conditions.append('machine_id=?')
        args.append(machine_id)
    if real_only:
        conditions.append("source IN ('trackunit_cache','imported_user_supplied')")
    where = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
    with database() as connection:
        connection.execute('BEGIN')
        total = connection.execute('SELECT COUNT(*) FROM cases' + where, args).fetchone()[0]
        rows = connection.execute('SELECT case_id FROM cases' + where +
                                  ' ORDER BY updated_at DESC,case_id LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
        return {'cases': [_record(connection, row['case_id'], events=False) for row in rows],
                'total': total, 'limit': limit, 'offset': offset, 'ai_used': False}


def export_case(case_id):
    case = read_case(case_id)
    fence_text = '\n'.join([case['title'], *(event['note'] for event in case['events'])])
    fence = '`' * max(3, max((len(s) + 1 for s in re.findall(r'`+', fence_text)), default=3))
    lines = ['# 本机设备排查记录', '',
             '人工记录未经验证；归档仅表示本次任务归档，不代表设备已修复。', '',
             f'任务编号：{case_id}', f'当前进度：{LABELS[case["state"]]}',
             f'设备：{case["machine_id"]}', f'来源：{case["source"]}',
             f'数据版本：{case["dataset_id"] or "建立时的缓存摘要"}', '',
             '## 任务与建立时设备摘要', fence,
             case['title'], json.dumps(case['scope'], ensure_ascii=False, indent=2), fence, '', '## 处理历史']
    for event in case['events']:
        lines += ['', f'### 记录 {event["revision"]} · {LABELS[event["to_state"]]}',
                  f'保存时间：{event["created_at"]}', fence, event['note'], fence]
        if event['report_id']:
            lines += ['关联 AI 报告：' + event['report_id']]
    return ('\n'.join(lines) + '\n').encode('utf-8'), f'maintenance-case-{case_id}.md'
