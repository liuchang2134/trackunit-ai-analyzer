"""Official Asset Event v3 normalization and bounded explicit refresh.

Reads never access the network. Refresh is restricted to one registered machine,
with a global two-request/1800-second ledger including failed requests and pages.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from app.local_datasets import load_dataset, list_datasets
from app.services.machine_service import find_machine
from app.data_store import get_data_source
from app.trackunit_client import TrackunitClient, TrackunitError

STORE = Path(__file__).resolve().parents[1] / 'data/local/fault-events'
ENDPOINT = 'https://iris.trackunit.com/public/api/eventlog/v3/asset-event/log'
PAGE_SIZE, MAX_PAGES, MAX_EVENTS = 1000, 2, 10000
QUOTA_WINDOW = timedelta(seconds=1800)


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError('事件时间缺失。')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('事件时间缺少时区。')
    return parsed.astimezone(timezone.utc).isoformat()


def event_key(asset_id, source_event_id):
    return hashlib.sha256(f'{asset_id}\n{source_event_id}'.encode()).hexdigest()


class FaultEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_event_id: str
    machine_id: str
    trackunit_asset_id: str
    vin: str
    code: str | None = Field(default=None, max_length=100)
    code_system: Literal['j1939', 'oem_unspecified', 'unknown']
    spn: int | None = Field(default=None, ge=0, strict=True)
    fmi: int | None = Field(default=None, ge=0, le=31, strict=True)
    sa: int | None = Field(default=None, ge=0, le=255, strict=True)
    description: str = Field(default='', max_length=1500)
    occurred_at: str
    event_time: str
    cleared_at: str | None = None
    status: Literal['OPEN', 'CLOSED', 'RESOLVED', 'DISMISSED', 'UNKNOWN']
    severity: str | None = Field(default=None, max_length=40)
    source: Literal['trackunit_asset_event_v3'] = 'trackunit_asset_event_v3'
    observed_at: str


def registered_machine(machine_id, dataset_id=None, vin=None):
    """A browser-supplied UUID alone never authorizes a network request."""
    if not isinstance(machine_id, str) or not 0 < len(machine_id) <= 200:
        raise ValueError('设备标识无效。')
    if dataset_id:
        dataset = load_dataset(dataset_id)
        if dataset.provenance != 'user_supplied' or dataset.machine.machine_id != machine_id:
            raise ValueError('请选择已登记的实测设备。')
        candidates = [dataset.machine]
    else:
        candidates = []
        if get_data_source() == 'trackunit_cache':
            machine = find_machine(machine_id)
            if machine:
                candidates.append(machine)
        for item in list_datasets():
            if item['provenance'] == 'user_supplied' and item['machine']['machine_id'] == machine_id:
                candidates.append(load_dataset(item['dataset_id']).machine)
    if not candidates:
        raise ValueError('未找到已登记的实测设备，请先读取设备。')
    identities = set()
    for machine in candidates:
        asset = str(UUID(machine.trackunit_asset_id or machine.machine_id))
        serial = machine.serial_number.strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{8,32}', serial):
            raise ValueError('已登记设备缺少可核对的 VIN/PIN。')
        identities.add((asset, serial))
    if len(identities) != 1:
        raise ValueError('本机保存的设备身份不一致，请核对 VIN/PIN。')
    asset, serial = identities.pop()
    if vin is not None and vin != serial:
        raise ValueError('VIN/PIN 与已登记设备不一致。')
    return {'machine_id': machine_id, 'dataset_id': dataset_id,
            'trackunit_asset_id': asset, 'vin': serial, 'model': candidates[0].model}


def _path(machine_id):
    return STORE / (hashlib.sha256(machine_id.encode()).hexdigest() + '.json')


def _write(path, value):
    STORE.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=STORE, delete=False) as handle:
            temporary = handle.name
            json.dump(value, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def read_state(identity):
    """Local only. A failure never erases known events or means no fault."""
    path = _path(identity['machine_id'])
    if not path.exists():
        return {**identity, 'status': 'not_checked', 'checked_at': None, 'last_success_at': None,
                'window_start': None, 'window_end': None, 'http_status': None,
                'coverage': 'unknown', 'message': '尚未读取该设备的故障事件。',
                'retry_after': None, 'events': [], 'pages_read': 0, 'retention_limit': MAX_EVENTS}
    if path.stat().st_size > 30_000_000:
        raise ValueError('本地故障记录超过读取范围。')
    state = json.loads(path.read_text(encoding='utf-8'))
    for key in ('machine_id', 'trackunit_asset_id', 'vin'):
        if state.get(key) != identity[key]:
            raise ValueError('本地故障记录与当前设备不一致。')
    events = []
    for raw in state['events']:
        event = FaultEvent.model_validate(raw).model_dump()
        if any(event[key] != identity[key] for key in ('machine_id', 'trackunit_asset_id', 'vin')):
            raise ValueError('故障记录设备不一致。')
        if event['event_id'] != event_key(identity['trackunit_asset_id'], str(UUID(event['source_event_id']))):
            raise ValueError('故障来源标识无效。')
        events.append(event)
    return {**state, 'dataset_id': identity['dataset_id'], 'events': events}


def normalize_event(raw, identity, observed_at):
    if not isinstance(raw, dict) or raw.get('type') != 'MACHINE_FAULT':
        raise ValueError('响应并非请求的故障事件。')
    asset_id, source_id = str(UUID(raw['assetId'])), str(UUID(raw['id']))
    if asset_id != identity['trackunit_asset_id']:
        raise ValueError('响应包含其他设备事件。')
    details = raw.get('assetEventDomainDetails')
    if not isinstance(details, dict) or details.get('eventTypeName') not in (None, 'AssetEventMachineFaultDetails'):
        raise ValueError('故障事件缺少规范化领域信息。')
    j1939 = details.get('j1939')
    if j1939 is not None and not isinstance(j1939, dict):
        raise ValueError('J1939 字段格式无效。')
    code = details.get('faultCode')
    if code is not None and (not isinstance(code, str) or len(code) > 100):
        raise ValueError('故障代码格式无效。')
    code = (code.strip() or None) if code is not None else None
    started = _stamp(raw.get('timeOn') or raw.get('eventTime'))
    ended = _stamp(raw['timeOff']) if raw.get('timeOff') is not None else None
    if ended and datetime.fromisoformat(ended) < datetime.fromisoformat(started):
        raise ValueError('事件解除时间早于发生时间。')
    return FaultEvent(event_id=event_key(asset_id, source_id), source_event_id=source_id,
        machine_id=identity['machine_id'], trackunit_asset_id=asset_id, vin=identity['vin'],
        code=code, code_system='j1939' if j1939 else 'oem_unspecified' if code else 'unknown',
        **{key: (j1939 or {}).get(key) for key in ('spn', 'fmi', 'sa')},
        description=details.get('description') or '', occurred_at=started,
        event_time=_stamp(raw['eventTime']), cleared_at=ended, status=raw.get('status', 'UNKNOWN'),
        severity=raw.get('criticality'), observed_at=observed_at).model_dump()


def _page(payload, requested_page, identity, now):
    if not isinstance(payload, dict) or not isinstance(payload.get('content'), list):
        raise ValueError('缺少事件分页集合。')
    for key in ('number', 'totalPages', 'totalElements'):
        if type(payload.get(key)) is not int or payload[key] < 0:
            raise ValueError('缺少可验证的分页边界。')
    content = payload['content']
    if (payload['number'] != requested_page or len(content) > PAGE_SIZE
        or payload['totalElements'] < len(content)
        or ('numberOfElements' in payload and payload['numberOfElements'] != len(content))
        or (payload['totalPages'] == 0 and (content or payload['totalElements']))
        or (payload['totalPages'] > 0 and requested_page >= payload['totalPages'])
        or (not content and payload['totalElements'] > 0)):
        raise ValueError('事件分页元数据不一致。')
    return [normalize_event(raw, identity, now) for raw in content], payload['totalPages']


def _ledger():
    path = STORE / 'request-ledger.json'
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    if not isinstance(data, list):
        raise ValueError('故障请求限频记录无效。')
    for item in data:
        _stamp(item['attempted_at'])
        if not isinstance(item.get('receipt_id'), str):
            raise ValueError('故障请求限频记录无效。')
    return data


def _quota(now):
    recent = sorted(datetime.fromisoformat(_stamp(item['attempted_at'])) for item in _ledger()
                    if datetime.fromisoformat(_stamp(item['attempted_at'])) > now - QUOTA_WINDOW)
    return (recent[-2] + QUOTA_WINDOW).isoformat() if len(recent) >= 2 else None


def _reserve(now, receipt_id):
    """Caller holds the cross-process global lock. Write before every POST."""
    retry_after = _quota(now)
    if retry_after:
        return retry_after
    rows = _ledger()
    rows = [item for item in rows if datetime.fromisoformat(_stamp(item['attempted_at'])) > now - timedelta(days=7)]
    rows.append({'attempted_at': now.isoformat(), 'receipt_id': receipt_id})
    _write(STORE / 'request-ledger.json', rows)
    return None


def _authorization_state():
    """Caller holds the refresh lock. Bootstrap pre-sync local fault outcomes."""
    path = STORE / 'authorization-state.json'
    if path.exists():
        state = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(state, dict) or state.get('schema_version') != 1
                or state.get('http_status') not in (None, 401, 403)
                or bool(state.get('blocked_at')) != (state.get('http_status') in (401, 403))):
            raise ValueError('自动故障读取授权状态无效。')
        for name in ('blocked_at', 'last_manual_success_at'):
            if state.get(name) is not None:
                _stamp(state[name])
        return state
    failures, successes = [], []
    # Only the exact hashed device-state namespace is eligible. These records
    # predate /sync, so a later successful fault query was an explicit refresh.
    for candidate in STORE.glob('*.json'):
        if not re.fullmatch(r'[a-f0-9]{64}\.json', candidate.name):
            continue
        raw = json.loads(candidate.read_text(encoding='utf-8'))
        if not isinstance(raw, dict) or not isinstance(raw.get('machine_id'), str):
            raise ValueError('历史故障读取状态无效。')
        if candidate != _path(raw['machine_id']):
            raise ValueError('历史故障设备标识无效。')
        identity = {name: raw[name] for name in ('machine_id', 'trackunit_asset_id', 'vin')}
        identity['dataset_id'] = raw.get('dataset_id')
        if str(UUID(identity['trackunit_asset_id'])) != identity['trackunit_asset_id'] or not re.fullmatch(r'[A-Z0-9]{8,32}', identity['vin']):
            raise ValueError('历史故障设备身份无效。')
        previous = read_state(identity)
        if not previous.get('checked_at'):
            continue
        checked = datetime.fromisoformat(_stamp(previous['checked_at']))
        code = previous.get('http_status')
        if code in (401, 403):
            failures.append((checked, code))
        elif code == 200 and previous.get('status') in ('data', 'empty', 'partial') and previous.get('pages_read', 0) > 0:
            successes.append(checked)
    failed = max(failures, default=None)
    succeeded = max(successes, default=None)
    blocked = failed is not None and (succeeded is None or failed[0] >= succeeded)
    state = {'schema_version': 1, 'blocked_at': failed[0].isoformat() if blocked else None,
        'http_status': failed[1] if blocked else None,
        'last_manual_success_at': succeeded.isoformat() if succeeded else None}
    _write(path, state)
    return state


def _authorization_outcome(state, *, automatic):
    """Only this official fault-query path can clear the authorization block."""
    authorization = _authorization_state()
    code = state.get('http_status')
    if code in (401, 403):
        authorization.update(blocked_at=_stamp(state['checked_at']), http_status=code)
    elif not automatic and code == 200 and state.get('pages_read', 0) > 0:
        authorization.update(blocked_at=None, http_status=None,
            last_manual_success_at=_stamp(state['checked_at']))
    else:
        return
    _write(STORE / 'authorization-state.json', authorization)


def _auto_result(state, status, reason, message, retry_after=None):
    return {**state, 'auto_sync': {'status': status, 'reason': reason,
        'message': message, 'retry_after': retry_after}}


def _authorization_paused(state):
    return _auto_result(state, 'paused', 'authorization_required',
        'Trackunit 故障 API 授权失败，已暂停 API 自动查询。Chrome 插件仍可读取当前设备 Events 页已显示的故障卡片；页面读取不包含未显示的历史记录。')


def _lock():
    STORE.mkdir(parents=True, exist_ok=True)
    path = STORE / 'refresh.lock'
    handle = path.open('a+b')
    if path.stat().st_size == 0:
        handle.write(b'0'); handle.flush()
    handle.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise FileExistsError('故障刷新正在运行。') from None
    return handle


def _unlock(handle):
    # Kernel locks disappear on process exit. Never delete an active lock by age.
    try:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def refresh(identity, *, client=None, now=None, automatic=False):
    """Bounded official POST; automatic reads also honor freshness and auth blocks."""
    fixed_now = now
    now = now or utcnow()
    state = read_state(identity)
    try:
        lock = _lock()
    except FileExistsError:
        if automatic:
            return _auto_result(state, 'busy', 'refresh_in_progress', '另一个故障读取正在进行，已保留本机已有记录。')
        return {**state, 'status': 'busy', 'message': '另一个故障刷新正在进行，请稍后重试。'}
    try:
        # A contender may have completed after the first local read but before
        # this process acquired the lock. Never decide from that old snapshot.
        state = read_state(identity)
        authorization = _authorization_state()
        if automatic:
            if authorization['blocked_at'] is not None:
                return _authorization_paused(state)
            if state.get('checked_at'):
                last_attempt = datetime.fromisoformat(_stamp(state['checked_at']))
                if last_attempt > now - QUOTA_WINDOW:
                    return _auto_result(state, 'cached', 'recent_attempt',
                        '该设备最近 30 分钟已尝试读取故障，正在使用已保存记录。',
                        (last_attempt + QUOTA_WINDOW).isoformat())
        retry_after = _quota(now)
        if retry_after:
            if automatic:
                return _auto_result(state, 'paused', 'quota', '已达到故障接口查询频率限制，已有事件仍可查看。', retry_after)
            return {**state, 'status': 'rate_limited', 'retry_after': retry_after,
                    'message': '已达到故障接口查询频率限制，已有事件仍可查看。'}
        end, start = now.isoformat(), (now - timedelta(days=7)).isoformat()
        state.update(status='busy', checked_at=end, window_start=start, window_end=end,
                     http_status=None, coverage='unknown', retry_after=None,
                     pages_read=0, message='正在读取故障事件。')
        _write(_path(identity['machine_id']), state)
        collected, total_pages, stopped_for_quota = {}, 0, False
        try:
            client = client or TrackunitClient(timeout_seconds=25, retries=0)
            if isinstance(client, TrackunitClient) and (client.auth_url != 'https://auth.trackunit.com/token/v2'
                    or client.grant_type != 'client_credentials' or client.retries != 0):
                raise ValueError('故障接入认证配置不符合指定契约。')
            for page in range(MAX_PAGES):
                attempt = fixed_now or utcnow()
                retry_after = _reserve(attempt, f"refresh:{identity['trackunit_asset_id']}:{end}:{page}")
                if retry_after:
                    state['retry_after'], stopped_for_quota = retry_after, True
                    break
                payload = client.request('POST', ENDPOINT, params={'page': page, 'size': PAGE_SIZE},
                    json={'fromTime': start, 'toTime': end, 'assetIds': [identity['trackunit_asset_id']],
                          'type': ['MACHINE_FAULT']}, follow_redirects=False)
                rows, page_total = _page(payload, page, identity, end)
                if page and page_total != total_pages:
                    raise ValueError('翻页期间事件总页数变化，请稍后刷新。')
                total_pages = page_total
                for row in rows:
                    existing = collected.get(row['event_id'])
                    if existing and existing != row:
                        raise ValueError('同一来源事件的重复记录不一致。')
                    collected[row['event_id']] = row
                state['pages_read'] = page + 1
                if page + 1 >= total_pages:
                    break
        except TrackunitError as exc:
            status = {401: 'unauthorized', 403: 'forbidden', 429: 'rate_limited'}.get(exc.status_code, 'unavailable')
            state.update(status=status, http_status=exc.status_code,
                message={'unauthorized': 'Trackunit 拒绝故障事件访问，请核对接口授权。',
                         'forbidden': '当前授权不能读取故障事件。',
                         'rate_limited': 'Trackunit 请求受限，请稍后重试。'}.get(status, '故障接口暂时不可用，未将失败视为无故障。'))
        except (ValueError, KeyError, TypeError, AttributeError):
            state.update(status='schema_error', message='故障响应或配置未通过契约校验，未将异常视为无故障。')
        else:
            partial = stopped_for_quota or total_pages > MAX_PAGES
            state.update(status='partial' if partial else 'data' if collected else 'empty',
                http_status=200, coverage='partial_window' if partial else 'queried_window',
                message='仅取得查询窗口内的部分事件。' if partial else '已读取查询窗口内的故障事件。' if collected
                    else '本次查询窗口未返回故障事件；不能据此判断设备无故障。')
        if state['pages_read']:
            state['last_success_at'] = end
            if state['status'] not in ('data', 'empty', 'partial'):
                state['coverage'] = 'partial_window'
        if collected:
            merged = {event['event_id']: event for event in state['events']}
            merged.update(collected)
            ordered = sorted(merged.values(), key=lambda row: row['occurred_at'], reverse=True)
            state['events'] = ordered[:MAX_EVENTS]
            if len(ordered) > MAX_EVENTS and state['status'] in ('data', 'empty'):
                state.update(status='partial', coverage='partial_window', message='部分事件超出本地保存范围。')
        state['retry_after'] = state['retry_after'] or _quota(fixed_now or utcnow())
        _authorization_outcome(state, automatic=automatic)
        _write(_path(identity['machine_id']), state)
        if automatic:
            if state.get('http_status') in (401, 403):
                return _authorization_paused(state)
            return _auto_result(state, 'attempted', 'requested', '已按受限自动读取规则查询故障接口。', state['retry_after'])
        return state
    finally:
        _unlock(lock)


def import_probe(identity, summary, *, verified_asset_id):
    """Import a reviewed unsuccessful probe, including its consumed request quota.

Caller must supply the UUID used in that probe's registered source, because older
redacted summaries contain only model and are insufficient to bind an identity.
This maintenance function is deliberately not exposed as an HTTP endpoint.
"""
    if str(UUID(verified_asset_id)) != identity['trackunit_asset_id'] or summary.get('model') != identity['model']:
        raise ValueError('核验所用设备与当前登记设备不一致。')
    requests = [row for row in summary['data_requests'] if row.get('name') == 'machine_fault_events']
    if len(requests) != 1 or requests[0].get('method') != 'POST' or requests[0].get('http_status') not in (401, 403, 429):
        raise ValueError('仅支持导入已复核的失败故障请求；成功事件应通过规范适配保存。')
    checked_at = _stamp(summary['checked_at'])
    start, end = _stamp(summary['window_start']), _stamp(summary['window_end'])
    receipt_id = 'probe:' + hashlib.sha256((verified_asset_id + checked_at).encode()).hexdigest()
    lock = _lock()
    try:
        authorization = _authorization_state()
        rows = _ledger()
        if not any(row['receipt_id'] == receipt_id for row in rows):
            rows.append({'attempted_at': checked_at, 'receipt_id': receipt_id})
            _write(STORE / 'request-ledger.json', rows)
        status_code = requests[0]['http_status']
        # A newer unsuccessful device state is not evidence of restored access.
        # Only a later successful manual fault query supersedes this probe.
        recovered = authorization.get('last_manual_success_at')
        blocked = authorization.get('blocked_at')
        if status_code in (401, 403) and all(stamp is None or
                datetime.fromisoformat(checked_at) >= datetime.fromisoformat(_stamp(stamp))
                for stamp in (recovered, blocked)):
            _authorization_outcome({'http_status': status_code, 'checked_at': checked_at}, automatic=True)
        state = read_state(identity)
        if state.get('checked_at') and datetime.fromisoformat(_stamp(state['checked_at'])) > datetime.fromisoformat(checked_at):
            return state
        state.update(status={401: 'unauthorized', 403: 'forbidden', 429: 'rate_limited'}[status_code],
            checked_at=checked_at, window_start=start, window_end=end, http_status=status_code,
            coverage='unknown', pages_read=0, retry_after=_quota(utcnow()),
            message='最近一次已保存核验未读通故障事件；不能据此判断设备无故障。')
        _write(_path(identity['machine_id']), state)
        return state
    finally:
        _unlock(lock)


def load_event(event_id, machine_id, dataset_id, vin):
    if not isinstance(event_id, str) or not re.fullmatch(r'[a-f0-9]{64}', event_id):
        raise ValueError('故障事件标识无效。')
    identity = registered_machine(machine_id, dataset_id, vin)
    event = next((row for row in read_state(identity)['events'] if row['event_id'] == event_id), None)
    if not event:
        raise ValueError('未找到当前设备的已保存真实故障事件。')
    if not event['code'] and (event['spn'] is None or event['fmi'] is None):
        raise ValueError('该事件未提供故障码或完整 SPN/FMI，暂不能分析。')
    return event
