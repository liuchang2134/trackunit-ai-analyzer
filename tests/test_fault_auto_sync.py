"""Bounded sync and durable authorization block; synthetic local clients only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import trackunit_events as events
from app.api import routes_fault_events as routes

NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)


def identity(number=1):
    asset = f'00000000-0000-0000-0000-{number:012d}'
    return {'machine_id': asset, 'trackunit_asset_id': asset, 'dataset_id': 'a'*64,
        'vin': f'XUGTEST{number:09d}', 'model': 'XE55U'}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(events, 'STORE', tmp_path/'events')
    monkeypatch.setattr(events, 'utcnow', lambda: NOW)
    monkeypatch.setattr(events.TrackunitClient, 'get_token', lambda *a, **k: pytest.fail('Unexpected network authentication'))


def page(rows=None, number=0, total_pages=0, total=0):
    rows = rows or []
    return {'content': rows, 'number': number, 'size': 1000, 'numberOfElements': len(rows),
        'totalPages': total_pages, 'totalElements': total}


def raw(number=1):
    return {'id': f'10000000-0000-0000-0000-{number:012d}', 'assetId': identity()['trackunit_asset_id'],
        'type': 'MACHINE_FAULT', 'status': 'OPEN', 'eventTime': NOW.isoformat(),
        'timeOn': NOW.isoformat(), 'timeOff': None, 'criticality': 'CRITICAL',
        'assetEventDomainDetails': {'eventTypeName': 'AssetEventMachineFaultDetails',
            'faultCode': 'E4030', 'description': '合成故障', 'j1939': None}}


class FakeClient:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def request(self, method, endpoint, **kwargs):
        self.calls.append((method, endpoint, kwargs))
        assert self.answers, 'Unexpected repeated request'
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


def legacy(number, checked, code, *, status=None, pages_read=0):
    device = identity(number)
    state = {**events.read_state(device), 'checked_at': checked, 'http_status': code,
        'status': status or {401: 'unauthorized', 403: 'forbidden', 200: 'empty'}.get(code, 'unavailable'),
        'pages_read': pages_read, 'coverage': 'queried_window' if code == 200 else 'unknown'}
    events._write(events._path(device['machine_id']), state)
    return state


def test_first_sync_requests_once_then_caches_same_machine_any_attempt():
    fake = FakeClient(page())
    first = events.refresh(identity(), automatic=True, client=fake, now=NOW)
    assert first['status'] == 'empty' and first['auto_sync']['status'] == 'attempted'
    cached = events.refresh(identity(), automatic=True, client=fake, now=NOW+timedelta(seconds=1))
    assert cached['auto_sync']['reason'] == 'recent_attempt' and cached['checked_at'] == first['checked_at']
    assert cached['auto_sync']['retry_after'] == (NOW+timedelta(minutes=30)).isoformat()
    assert len(fake.calls) == len(events._ledger()) == 1
    assert 'auto_sync' not in events.read_state(identity())


@pytest.mark.parametrize('failure', [events.TrackunitError('fixture', 500), RuntimeError('worker interrupted')])
def test_failed_or_interrupted_attempt_has_same_machine_cooldown(failure):
    fake = FakeClient(failure)
    if isinstance(failure, events.TrackunitError):
        events.refresh(identity(), automatic=True, client=fake, now=NOW)
    else:
        with pytest.raises(RuntimeError):
            events.refresh(identity(), automatic=True, client=fake, now=NOW)
    current = events.read_state(identity())
    result = events.refresh(identity(), automatic=True, client=fake, now=NOW+timedelta(seconds=1))
    assert result['auto_sync']['reason'] == 'recent_attempt'
    assert result['status'] == current['status'] and len(fake.calls) == 1


def test_legacy_401_records_bootstrap_global_block_and_do_not_expire():
    legacy(1, '2026-09-22T00:40:32-04:00', 401)
    legacy(2, '2026-09-22T01:10:54-04:00', 401)
    fake = FakeClient()
    for checked in [NOW, NOW+timedelta(days=40)]:
        result = events.refresh(identity(3), automatic=True, client=fake, now=checked)
        assert result['status'] == 'not_checked' and result['checked_at'] is None and result['http_status'] is None
        assert result['auto_sync']['reason'] == 'authorization_required'
        assert result['auto_sync']['retry_after'] is None and result['machine_id'] == identity(3)['machine_id']
    saved = json.loads((events.STORE/'authorization-state.json').read_text(encoding='utf-8'))
    assert saved['blocked_at'] == '2026-09-22T05:10:54+00:00'
    assert fake.calls == [] and events._ledger() == []


def test_authorization_block_precedes_recent_successful_device_cache():
    legacy(2, NOW.isoformat(), 200, pages_read=1)
    legacy(1, (NOW+timedelta(seconds=1)).isoformat(), 403)
    result = events.refresh(identity(2), automatic=True, client=FakeClient(), now=NOW+timedelta(seconds=2))
    assert result['status'] == 'empty' and result['http_status'] == 200
    assert result['auto_sync']['reason'] == 'authorization_required'


def test_later_legacy_manual_fault_success_releases_older_legacy_failure():
    legacy(1, '2026-09-22T01:10:54-04:00', 401)
    legacy(2, '2026-09-22T06:11:00+00:00', 200, pages_read=1)
    fake = FakeClient(page())
    result = events.refresh(identity(3), automatic=True, client=fake, now=NOW)
    assert result['auto_sync']['status'] == 'attempted' and len(fake.calls) == 1


@pytest.mark.parametrize('code', [401, 403])
def test_new_authorization_failure_blocks_all_devices_and_manual_success_clears(code):
    failed = FakeClient(events.TrackunitError('fixture', code))
    result = events.refresh(identity(), automatic=True, client=failed, now=NOW)
    assert result['http_status'] == code and result['auto_sync']['reason'] == 'authorization_required'
    blocked = FakeClient()
    assert events.refresh(identity(2), automatic=True, client=blocked, now=NOW+timedelta(days=1))['status'] == 'not_checked'
    manual = FakeClient(page())
    recovered = events.refresh(identity(), client=manual, now=NOW+timedelta(days=1))
    assert recovered['status'] == 'empty' and 'auto_sync' not in recovered
    allowed = FakeClient(page())
    assert events.refresh(identity(2), automatic=True, client=allowed, now=NOW+timedelta(days=1, seconds=1))['auto_sync']['status'] == 'attempted'
    assert len(failed.calls) == len(manual.calls) == len(allowed.calls) == 1 and blocked.calls == []


def test_non_fault_success_or_failed_manual_retry_does_not_clear_block():
    legacy(1, (NOW-timedelta(days=1)).isoformat(), 401)
    events._write(events.STORE/'aemp-status.json', {'http_status': 200, 'checked_at': NOW.isoformat()})
    failed = events.refresh(identity(2), client=FakeClient(events.TrackunitError('fixture', 500)), now=NOW)
    assert failed['status'] == 'unavailable'
    result = events.refresh(identity(3), automatic=True, client=FakeClient(), now=NOW+timedelta(seconds=1))
    assert result['auto_sync']['reason'] == 'authorization_required'


def test_partial_manual_200_success_can_clear_but_second_page_401_wins():
    legacy(1, (NOW-timedelta(days=1)).isoformat(), 401)
    first = FakeClient(page([raw()], total_pages=3, total=2001), events.TrackunitError('fixture', 401))
    result = events.refresh(identity(), client=first, now=NOW)
    assert result['pages_read'] == 1 and result['http_status'] == 401
    assert events.refresh(identity(2), automatic=True, client=FakeClient(), now=NOW)['auto_sync']['reason'] == 'authorization_required'
    later = NOW+timedelta(hours=1)
    second = FakeClient(page([raw()], total_pages=3, total=2001), page([raw(2)], number=1, total_pages=3, total=2001))
    recovered = events.refresh(identity(), client=second, now=later)
    assert recovered['status'] == 'partial' and recovered['http_status'] == 200
    # The two successful page requests still consume all available quota.
    limited = events.refresh(identity(2), automatic=True, client=FakeClient(), now=later)
    assert limited['status'] == 'not_checked' and limited['auto_sync']['reason'] == 'quota'


def test_global_quota_counts_auto_failures_and_preserves_new_device_status():
    events.refresh(identity(1), automatic=True, client=FakeClient(events.TrackunitError('fixture', 500)), now=NOW)
    events.refresh(identity(2), automatic=True, client=FakeClient(page()), now=NOW+timedelta(seconds=1))
    result = events.refresh(identity(3), automatic=True, client=FakeClient(), now=NOW+timedelta(seconds=2))
    assert result['auto_sync']['reason'] == 'quota' and result['status'] == 'not_checked'
    assert result['checked_at'] is None and result['auto_sync']['retry_after'] == (NOW+timedelta(minutes=30)).isoformat()
    assert len(events._ledger()) == 2


def test_simultaneous_syncs_share_lock_and_later_contender_uses_new_state():
    entered, release = Event(), Event()
    class HoldingClient(FakeClient):
        def request(self, *args, **kwargs):
            entered.set()
            assert release.wait(timeout=5)
            return super().request(*args, **kwargs)
    fake = HoldingClient(page())
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(events.refresh, identity(), automatic=True, client=fake, now=NOW)
        assert entered.wait(timeout=5)
        during = events.refresh(identity(), automatic=True, client=FakeClient(), now=NOW)
        assert during['auto_sync']['reason'] == 'refresh_in_progress'
        release.set()
        completed = first.result(timeout=5)
    again = events.refresh(identity(), automatic=True, client=FakeClient(), now=NOW+timedelta(seconds=1))
    assert completed['status'] == 'empty' and again['auto_sync']['reason'] == 'recent_attempt'
    assert len(fake.calls) == len(events._ledger()) == 1


def test_rereads_machine_state_after_acquiring_lock(monkeypatch):
    original = events._lock
    calls = []
    def changed_before_lock():
        lock = original()
        legacy(1, NOW.isoformat(), 500)
        calls.append('lock')
        return lock
    monkeypatch.setattr(events, '_lock', changed_before_lock)
    result = events.refresh(identity(), automatic=True, client=FakeClient(), now=NOW+timedelta(seconds=1))
    assert result['auto_sync']['reason'] == 'recent_attempt' and result['status'] == 'unavailable'
    assert calls == ['lock']


def test_get_remains_local_manual_refresh_explicit_and_sync_passes_automatic(monkeypatch):
    device = identity()
    def registered(machine_id, dataset_id=None, vin=None):
        if machine_id != device['machine_id'] or vin not in (None, device['vin']):
            raise ValueError('identity mismatch')
        return device
    monkeypatch.setattr(events, 'registered_machine', registered)
    calls = []
    monkeypatch.setattr(events, 'refresh', lambda identity, **kwargs: calls.append(kwargs) or events.read_state(identity))
    app = FastAPI(); app.include_router(routes.router); client = TestClient(app)
    body = {key: device[key] for key in ('machine_id', 'dataset_id', 'vin')}
    assert client.get('/assistant/fault-events', params=body).status_code == 200 and calls == []
    assert client.post('/assistant/fault-events/sync', json={**body, 'vin': 'XUGWRONG00000001'}).status_code == 422 and calls == []
    assert client.post('/assistant/fault-events/sync', json=body).status_code == 200 and calls == [{'automatic': True}]
    assert client.post('/assistant/fault-events/refresh', json=body).status_code == 200 and calls[-1] == {}


@pytest.mark.parametrize('recovered', [False, True])
def test_imported_probe_is_superseded_only_by_later_manual_fault_success(recovered):
    checked = NOW-timedelta(hours=2)
    legacy(1, (NOW-timedelta(hours=1)).isoformat(), 500)
    if recovered:
        events.refresh(identity(2), client=FakeClient(page()), now=NOW)
    summary = {'model': 'XE55U', 'checked_at': checked.isoformat(),
        'window_start': (checked-timedelta(days=7)).isoformat(), 'window_end': checked.isoformat(),
        'data_requests': [{'name': 'machine_fault_events', 'method': 'POST', 'http_status': 401}]}
    events.import_probe(identity(), summary, verified_asset_id=identity()['trackunit_asset_id'])
    fake = FakeClient(page()) if recovered else FakeClient()
    result = events.refresh(identity(3), automatic=True, client=fake, now=NOW+timedelta(seconds=1))
    assert result['auto_sync']['reason'] == ('requested' if recovered else 'authorization_required')
    assert len(fake.calls) == int(recovered)


def test_busy_and_quota_responses_preserve_saved_faults():
    earlier = NOW-timedelta(hours=1)
    saved = events.refresh(identity(), client=FakeClient(page([raw()], total_pages=1, total=1)), now=earlier)
    lock = events._lock()
    try:
        busy = events.refresh(identity(), automatic=True, client=FakeClient(), now=NOW)
    finally:
        events._unlock(lock)
    assert busy['auto_sync']['reason'] == 'refresh_in_progress'
    assert busy['status'] == saved['status'] and busy['events'] == saved['events']
    for number in (2, 3):
        events.refresh(identity(number), automatic=True, client=FakeClient(page()), now=NOW)
    limited = events.refresh(identity(), automatic=True, client=FakeClient(), now=NOW)
    assert limited['auto_sync']['reason'] == 'quota'
    assert limited['events'] == saved['events'] and limited['status'] == saved['status']
