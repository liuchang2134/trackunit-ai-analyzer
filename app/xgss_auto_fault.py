"""Local, fail-closed claims for one automatic plan per official fault event.

Claims precede model calls and survive refreshes or worker termination. A pending
or failed claim requires an explicit manual retry; it is never expired or deleted.
"""
from datetime import datetime
import hashlib
import json

from app import trackunit_events as events
from app import xgss_research_store as store


class AutoFaultError(ValueError):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def _error(kind, message):
    raise AutoFaultError(kind, message)


def _scope(body):
    return {name: getattr(body, name) for name in ('machine_id', 'dataset_id', 'vin', 'fault_event_id')}


def _claim_path(scope):
    key = hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return store.STORE / 'automatic-faults' / (key + '.json')


def _eligible(body):
    if (body.analysis_mode != 'fault' or body.symptom_source != 'trackunit_event' or not body.fault_event_id
            or body.symptom.strip() or body.source_report_id or body.manual_fault or body.engineering_fault):
        _error('auto_fault_invalid', '自动分析只能使用已保存的单个真实故障事件；补充现象或更改背景后请手动分析。')
    try:
        identity = events.registered_machine(body.machine_id, body.dataset_id, body.vin)
        state = events.read_state(identity)
        event = events.load_event(body.fault_event_id, body.machine_id, body.dataset_id, body.vin)
        checked = datetime.fromisoformat(events._stamp(state.get('checked_at')))
        age = (events.utcnow() - checked).total_seconds()
        opened = [row for row in state['events'] if row['status'] == 'OPEN']
        eligible = (state['status'] == 'data' and state['coverage'] == 'queried_window'
            and state.get('http_status') == 200 and 0 <= age <= 1800 and len(opened) == 1
            and opened[0] == event and not event.get('cleared_at')
            and event['source'] == 'trackunit_asset_event_v3'
            and event['trackunit_asset_id'] == identity['trackunit_asset_id']
            and datetime.fromisoformat(events._stamp(event['observed_at'])) == checked)
    except (ValueError, KeyError, TypeError, OSError):
        eligible = False
    if not eligible:
        _error('auto_fault_ineligible', '当前故障未满足新鲜、完整且唯一未解除事件的自动分析条件；已保留记录，请核对后手动分析。')


def _completed(claim, scope):
    if not isinstance(claim, dict) or claim.get('scope') != scope:
        _error('auto_fault_corrupt', '自动分析状态无法核验，未重新调用 AI；请手动分析。')
    status = claim.get('status')
    if status == 'planning':
        _error('auto_fault_pending', '此故障已启动自动分析，可能仍在其他工作区进行；请等待，若已中断请手动分析。')
    if status == 'failed':
        _error('auto_fault_failed', '此故障上次自动分析未完成，未自动重试；请手动分析。')
    if status != 'completed':
        _error('auto_fault_corrupt', '自动分析状态无法核验，未重新调用 AI；请手动分析。')
    try:
        record = store.read(claim['research_id'])
        if (any(record.get(name) != value for name, value in scope.items())
                or not isinstance(record.get('plan'), dict) or not record['plan']
                or record.get('analysis_mode') != 'fault' or record.get('symptom_source') != 'trackunit_event'
                or any(record.get(name) for name in ('source_report_id', 'manual_fault', 'engineering_fault'))
                or (record.get('fault_context') or {}).get('operator_supplement')):
            raise ValueError('claim record mismatch')
        return record
    except (ValueError, KeyError, TypeError, OSError):
        _error('auto_fault_corrupt', '自动分析记录无法核验，未重新调用 AI；请手动分析。')


def _check_active(scope, allowed_id=None):
    try:
        active = store.active(**{name: scope[name] for name in ('machine_id', 'dataset_id', 'vin')})
    except (ValueError, KeyError, TypeError, OSError):
        _error('auto_fault_active', '当前排查无法核验，未自动替换；请核对后手动分析。')
    if active is not None and active['research_id'] != allowed_id:
        _error('auto_fault_active', '当前设备已有活动排查，未自动替换；请核对后手动分析。')


def plan(body, call):
    """Run a validated automatic request at most once; `call` creates its plan."""
    _eligible(body)
    scope = _scope(body)
    path = _claim_path(scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The process lock orders this check against local activations; exclusive
    # creation additionally prevents duplicate model calls across processes.
    with store.LOCK:
        if path.exists():
            try:
                claim = json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                _error('auto_fault_corrupt', '自动分析状态无法读取，未重新调用 AI；请手动分析。')
            record = _completed(claim, scope)
            _check_active(scope, record['research_id'])
            return record
        _check_active(scope)
        claim = {'scope': scope, 'status': 'planning'}
        try:
            with path.open('x', encoding='utf-8') as handle:
                json.dump(claim, handle, ensure_ascii=False)
        except FileExistsError:
            _error('auto_fault_pending', '此故障已由其他工作区启动自动分析；请等待，若已中断请手动分析。')
    try:
        record = call()
        completed = {**claim, 'status': 'completed', 'research_id': record['research_id']}
        # Validate the saved record before the claim can authorize reuse.
        _completed(completed, scope)
        store._write_json(path, completed)
        return record
    except BaseException:
        # Cancellation and failures are terminal for automatic execution. If
        # this write also fails, the original pending claim still blocks retry.
        try:
            store._write_json(path, {**claim, 'status': 'failed'})
        except OSError:
            pass
        raise
