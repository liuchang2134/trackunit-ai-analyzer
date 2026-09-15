"""Bounded read-only import for the asset currently open in Trackunit.

Endpoint contracts were checked against the official OpenAPI specifications:
https://developers.trackunit.com/openapi/assets.json
https://developers.trackunit.com/openapi/aemp-iso-api.json
Only the selected asset is stored. Fleet caches and fault endpoints are untouched.
"""
from datetime import datetime, timezone
from copy import deepcopy
import json
import hashlib
import math
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import quote, urlparse

from app.local_datasets import LocalDataset, load_dataset, save_dataset
from app.normalizer import normalize_trackunit_machine, normalize_trackunit_telemetry_series
from app.telemetry_evidence import timestamp
from app.trackunit_client import TrackunitClient, TrackunitError

STATE_DIR = Path(__file__).resolve().parents[1] / 'data/local/platform-assets'
ASSET_ENDPOINT = 'https://iris.trackunit.com/api/asset/v2/assets/'
SNAPSHOT_ENDPOINT = 'https://iris.trackunit.com/public/api/aemp/v2/15143/-3/Fleet/Equipment/ID/'
UUID_PATTERN = r'^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$'
EQUIPMENT_HINT_PATTERN = r'^[A-Za-z0-9._ -]{1,100}$'
SUCCESS_TTL = 300
FAILURE_TTL = 60
REQUEST_BUDGET = 30
CACHE_VERSION = 2
MAX_FLEET_PAGES = 3
FLEET_PATH = '/public/api/aemp/v2/15143/-3/Fleet/'


class BoundedAssetClient(TrackunitClient):
    """Avoid waiting indefinitely on another worker's OAuth refresh."""
    def get_token(self):
        lock = self.__class__._token_lock
        if not lock.acquire(timeout=self.timeout_seconds):
            raise TrackunitError('Trackunit token refresh is busy')
        try:
            try:
                return self._get_token_locked()
            except TrackunitError as exc:
                exc.phase = 'authentication'
                raise
        finally:
            lock.release()


def canonical_asset(value):
    if not isinstance(value, str) or not re.fullmatch(UUID_PATTERN, value):
        raise ValueError('A canonical Trackunit asset UUID is required')
    return value.lower()


def _authorization_context():
    values = [os.getenv(key, '') for key in ('TRACKUNIT_AUTH_URL', 'TRACKUNIT_CLIENT_ID',
              'TRACKUNIT_CLIENT_SECRET', 'TRACKUNIT_SCOPE', 'TRACKUNIT_USERNAME', 'TRACKUNIT_PASSWORD')]
    return hashlib.sha256(json.dumps(values).encode('utf-8')).hexdigest()


def _snapshot_metadata(snapshot, asset_id):
    header = snapshot.get('EquipmentHeader') or {}
    return {'machine_id': asset_id, 'trackunit_asset_id': asset_id,
            'model': header.get('Model') or '未提供',
            'serial_number': header.get('PIN') or header.get('VIN') or header.get('SerialNumber') or '未提供',
            'machine_type': snapshot.get('type') or snapshot.get('assetType') or '未提供'}


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
            name = f.name
            json.dump(value, f, ensure_ascii=False)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def _unavailable(asset_id, status, message, **extra):
    return {'state': 'unavailable', 'asset_id': asset_id, 'dataset_id': None,
            'status': status, 'sample_count': 0, 'fault_status': 'not_checked',
            'message': message, **extra}


def _metadata(payload, asset_id):
    if not isinstance(payload, dict) or canonical_asset(payload.get('id')) != asset_id:
        raise ValueError('Asset metadata does not match requested UUID')
    text = lambda key, default: str(payload.get(key) or default).strip()[:256]
    machine = {'machine_id': asset_id, 'trackunit_asset_id': asset_id,
               'model': text('model', '未提供'), 'serial_number': text('serialNumber', '未提供'),
               'machine_type': text('type', '未提供'), 'name': text('name', '未提供')}
    identifiers = []
    if payload.get('serialNumber'):
        identifiers.append(str(payload['serialNumber']).strip())
    for device in payload.get('telematicsDevices', []) or []:
        if isinstance(device, dict) and device.get('serialNumber'):
            identifiers.append(str(device['serialNumber']).strip())
    identifiers = [v for v in dict.fromkeys(identifiers) if re.fullmatch(r'[A-Za-z0-9._ -]{1,100}', v)]
    return machine, identifiers[:2]


def _snapshot_item(payload, asset_id):
    if isinstance(payload, dict):
        values = payload.get('equipment', payload.get('Equipment'))
        if values is None and 'EquipmentHeader' in payload:
            values = [payload]
    else:
        values = payload
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError('Unexpected single-equipment snapshot format')
    matching = []
    for item in values:
        if not isinstance(item, dict):
            raise ValueError('Invalid snapshot item')
        metadata = item.get('metadata') or item.get('Metadata') or {}
        identity = metadata.get('assetId') if isinstance(metadata, dict) else None
        if identity and canonical_asset(str(identity)) == asset_id:
            for key in ('assetId', 'id'):
                top_id = item.get(key)
                if top_id and re.fullmatch(UUID_PATTERN, str(top_id)) and canonical_asset(str(top_id)) != asset_id:
                    raise ValueError('Conflicting asset identities in snapshot')
            matching.append(item)
    if len(matching) != 1:
        raise ValueError('Snapshot UUID was missing, conflicting or did not match')
    clean = deepcopy(matching[0])
    clean['assetId'] = asset_id  # Canonical identity is verified metadata, never an unrelated top-level ID.
    for key in ('operating_hours', 'idle_hours', 'fuel_remaining_percent', 'latitude', 'longitude', 'recordedAt', 'location'):
        clean.pop(key, None)
    # Check original numeric types before Pydantic can coerce bool into a number.
    for channel, key, lower, upper in (
        ('CumulativeOperatingHours', 'Hour', 0, math.inf), ('CumulativeIdleHours', 'Hour', 0, math.inf),
        ('FuelRemaining', 'Percent', 0, 100), ('Location', 'Latitude', -90, 90), ('Location', 'Longitude', -180, 180)):
        value = clean.get(channel)
        if not isinstance(value, dict):
            clean.pop(channel, None)
            continue
        if channel == 'Location':
            value.pop(key.lower(), None)
        number = value.get(key)
        if type(number) not in (int, float) or not math.isfinite(number) or not lower <= number <= upper:
            value.pop(key, None)
    return clean


def _fleet_endpoint():
    endpoint = os.getenv('TRACKUNIT_FLEET_SNAPSHOT_ENDPOINT', '')
    if endpoint == FLEET_PATH + '{page}':
        return 'https://iris.trackunit.com' + endpoint
    if endpoint == 'https://iris.trackunit.com' + FLEET_PATH + '{page}':
        return endpoint
    raise TrackunitError('AEMP Fleet endpoint is missing or unsupported')


def _fleet_fallback(asset_id, get, stats):
    """Inspect at most three pages in memory; only the exact target can be saved."""
    endpoint = _fleet_endpoint()
    page = 1
    stats.update(lookup_route='aemp_fleet', searched_pages=0, identity_matches=0)
    for _ in range(MAX_FLEET_PAGES):
        try:
            payload = get(endpoint.replace('{page}', str(page)), params={'addMetadata': 'true'})
        except TrackunitError as exc:
            status = 'upstream_unauthorized' if exc.status_code in {401, 403} else 'upstream_error'
            return _unavailable(asset_id, status, 'AEMP 设备快照暂不可读取；未关联其他设备，故障数据未读取。', http_status=exc.status_code)
        stats['searched_pages'] += 1
        values = payload.get('equipment', payload.get('Equipment')) if isinstance(payload, dict) else None
        if not isinstance(values, list) or len(values) > 100:
            raise ValueError('Unexpected bounded Fleet page format')
        matches = []
        for item in values:
            metadata = (item.get('metadata') or item.get('Metadata') or {}) if isinstance(item, dict) else {}
            identity = metadata.get('assetId') if isinstance(metadata, dict) else None
            if isinstance(identity, str) and identity.lower() == asset_id:
                matches.append(item)
        stats['identity_matches'] += len(matches)
        if matches:
            snapshot = _snapshot_item({'equipment': matches}, asset_id)
            return _save_snapshot(asset_id, snapshot, _snapshot_metadata(snapshot, asset_id),
                                  'Trackunit AEMP Fleet snapshot; exact metadata.assetId match; API read-only import; fault events not requested.')
        links = payload.get('links', payload.get('Links', []))
        if not isinstance(links, list):
            raise ValueError('Unexpected Fleet links')
        next_links = [link for link in links if isinstance(link, dict) and link.get('rel') == 'next']
        if not next_links:
            return _unavailable(asset_id, 'limited_search',
                                '当前账户返回的设备快照中未找到此设备，不能据此判断设备是否存在或是否有故障。', search_complete=True)
        if len(next_links) != 1:
            raise ValueError('Conflicting Fleet pagination')
        href = urlparse(str(next_links[0].get('href', '')))
        match = re.fullmatch(re.escape(FLEET_PATH) + r'(\d+)', href.path)
        if (href.scheme and href.scheme != 'https') or (href.netloc and href.netloc != 'iris.trackunit.com') or not match:
            raise ValueError('Unsupported Fleet next-page URL')
        next_page = int(match.group(1))
        if next_page != page + 1:
            raise ValueError('Nonsequential Fleet page')
        page = next_page
    return _unavailable(asset_id, 'limited_search',
                        '已查询前 3 页设备快照，未找到当前设备；本次未覆盖整个车队，未关联其他设备。', search_complete=False)


def _fetch_asset(asset_id, skip_asset_status=None, equipment_id_hint=None):
    deadline = time.monotonic() + REQUEST_BUDGET
    client = BoundedAssetClient(timeout_seconds=8, retries=0)
    stats = {'api_request_count': 0, 'lookup_route': 'assets_single_snapshot', 'identity_matches': 0}
    def get(url, **kwargs):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TrackunitError('Bounded asset import deadline reached')
        # The first call can include token acquisition plus the data request.
        client.timeout_seconds = min(8.0, remaining / 2)
        stats['api_request_count'] += 1
        value = client.request('GET', url, **kwargs)
        if time.monotonic() > deadline:
            raise TrackunitError('Bounded asset import deadline reached')
        return value

    try:
        if equipment_id_hint:
            stats['lookup_route'] = 'aemp_equipment_hint'
            try:
                payload = get(SNAPSHOT_ENDPOINT + quote(equipment_id_hint, safe=''), params={'addMetadata': 'true'})
                # A title/DOM identifier is only a lookup hint. The API UUID is
                # the identity authority, including when a stale title is sent.
                snapshot = _snapshot_item(payload, asset_id)
                stats['identity_matches'] = 1
                return {**_save_snapshot(asset_id, snapshot, _snapshot_metadata(snapshot, asset_id),
                        'Trackunit AEMP single-equipment snapshot; equipment ID lookup hint and exact metadata.assetId match; API read-only import; fault events not requested.'), **stats}
            except TrackunitError as exc:
                if exc.status_code != 404:
                    status = 'upstream_unauthorized' if exc.status_code in {401, 403} else 'upstream_error'
                    return _unavailable(asset_id, status, '当前设备编号的快照暂不可读取；未关联其他设备，故障数据未读取。',
                                        http_status=exc.status_code, failure_phase=getattr(exc, 'phase', 'snapshot'), **stats)
                stats['hint_status'] = 'not_found'
                stats['lookup_route'] = 'assets_single_snapshot'
        if skip_asset_status in {401, 403}:
            stats.update(asset_endpoint_status=skip_asset_status, asset_endpoint_skipped=True)
            return {**_fleet_fallback(asset_id, get, stats), **stats}
        try:
            metadata, identifiers = _metadata(get(ASSET_ENDPOINT + asset_id), asset_id)
        except TrackunitError as exc:
            stats['asset_endpoint_status'] = exc.status_code
            if getattr(exc, 'phase', None) == 'authentication':
                return _unavailable(asset_id, 'upstream_unauthorized', 'Trackunit 身份验证失败，尚未读取设备或故障数据。',
                                    http_status=exc.status_code, failure_phase='authentication', **stats)
            if exc.status_code in {401, 403}:
                return {**_fleet_fallback(asset_id, get, stats), **stats}
            status = 'not_found' if exc.status_code == 404 else 'upstream_error'
            return _unavailable(asset_id, status, '暂时无法读取这台设备的 Trackunit 资料；请核对账户访问权限或稍后重试。', http_status=exc.status_code, **stats)
    except TrackunitError as exc:
        return _unavailable(asset_id, 'upstream_error', '设备读取未能完成，请稍后重试；未关联其他设备。', http_status=exc.status_code, **stats)
    if not identifiers:
        return _unavailable(asset_id, 'metadata_only', '已识别设备，但接口没有提供可用于查询遥测的设备串号。', machine=metadata)
    snapshot = None
    for identifier in identifiers:
        try:
            payload = get(SNAPSHOT_ENDPOINT + quote(identifier, safe=''), params={'addMetadata': 'true'})
            snapshot = _snapshot_item(payload, asset_id)
            break
        except TrackunitError as exc:
            if exc.status_code == 404:
                continue
            return _unavailable(asset_id, 'metadata_only', '已识别设备，但遥测接口暂不可访问；故障数据未读取。',
                                machine=metadata, telemetry_status='unauthorized' if exc.status_code in {401, 403} else 'error', http_status=exc.status_code)
    if snapshot is None:
        return _unavailable(asset_id, 'metadata_only', '已识别设备，但未找到与该设备匹配的遥测快照。', machine=metadata, telemetry_status='not_found')
    stats['identity_matches'] = 1
    return {**_save_snapshot(asset_id, snapshot, metadata,
                            'Trackunit Assets API v2 + AEMP single-equipment snapshot; API read-only import; fault events not requested.'), **stats}


def _save_snapshot(asset_id, snapshot, metadata, source_document):
    machine = normalize_trackunit_machine(snapshot)
    if metadata['model'] != '未提供' and machine.model != 'Data not available' and metadata['model'].casefold() != machine.model.casefold():
        raise ValueError('Asset metadata and telemetry snapshot models conflict')
    machine = machine.model_copy(update={
        'model': metadata['model'] if metadata['model'] != '未提供' else machine.model,
        'machine_type': metadata['machine_type'], 'customer': 'Trackunit 已授权设备',
        'serial_number': (snapshot.get('EquipmentHeader', {}).get('PIN') or snapshot.get('EquipmentHeader', {}).get('VIN')
                          or metadata['serial_number'])})
    now = datetime.now(timezone.utc)
    rows = []
    excluded = 0
    for row in normalize_trackunit_telemetry_series(snapshot):
        instant = timestamp(row.recorded_at)
        useful = any(getattr(row, key) is not None for key in ('operating_hours', 'idle_hours', 'fuel_remaining_percent', 'engine_status', 'latitude', 'longitude'))
        if instant is None or instant > now or not useful:
            excluded += 1
            continue
        rows.append(row.model_copy(update={'raw_payload': None}))
    if not rows:
        return _unavailable(asset_id, 'metadata_only', '已识别设备，但没有带有效采样时间的遥测；未生成工时或诊断数据。',
                            machine=metadata, telemetry_status='missing_valid_samples', excluded_records=excluded)
    machine = machine.model_copy(update={'last_seen_at': max(row.recorded_at for row in rows)})
    missing = [field for field in ('operating_hours', 'idle_hours', 'fuel_remaining_percent') if not any(getattr(row, field) is not None for row in rows)]
    dataset = LocalDataset(name=f'{machine.model} · Trackunit 实测快照',
        source_document=source_document,
        provenance='user_supplied', machine=machine, telemetry=rows, faults=[])
    saved = save_dataset(dataset)
    return {'state': 'loaded', 'asset_id': asset_id, 'dataset_id': saved['dataset_id'],
            'status': 'imported_snapshot', 'sample_count': len(rows), 'machine': machine.model_dump(),
            'fault_status': 'not_checked', 'telemetry_status': 'data', 'missing_fields': missing,
            'excluded_records': excluded, 'message': '已读取当前设备的实测快照；故障数据未读取，缺失指标不按零处理。'}


def load_platform_asset(asset_id, equipment_id_hint=None):
    asset_id = canonical_asset(asset_id)
    if isinstance(equipment_id_hint, str):
        equipment_id_hint = equipment_id_hint.strip()
    if equipment_id_hint is not None and (not isinstance(equipment_id_hint, str)
            or not re.fullmatch(EQUIPMENT_HINT_PATTERN, equipment_id_hint)):
        raise ValueError('Invalid equipment ID lookup hint')
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / (asset_id + '.json')
    now = time.time()
    auth_context = _authorization_context()
    skip_asset_status = None
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        result = record['result']
        remaining = record['expires_at'] - now
        # One-time migration: the prior implementation's only unauthorized stage
        # was Assets. Avoid repeating that just-failed read during this upgrade.
        # Never renew this hint from a version-2 fallback result.
        if (record.get('cache_version', 1) == 1 and result.get('asset_id') == asset_id
                and result.get('status') == 'upstream_unauthorized' and result.get('http_status') in {401, 403}
                and -3600 < remaining <= FAILURE_TTL):
            skip_asset_status = result['http_status']
        if (record.get('cache_version') == CACHE_VERSION and record.get('authorization_context') == auth_context
                and record.get('equipment_id_hint') == equipment_id_hint
                and result['asset_id'] == asset_id and remaining > 0):
            if result['state'] == 'loaded':
                dataset = load_dataset(result['dataset_id'])
                if dataset.machine.machine_id != asset_id or dataset.provenance != 'user_supplied':
                    raise ValueError('Cached dataset identity mismatch')
            return {**result, 'cache_hit': True, 'retry_after_seconds': math.ceil(remaining)}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    lock = path.with_suffix('.lock')
    if lock.exists() and now - lock.stat().st_mtime > 120:
        lock.unlink(missing_ok=True)
    try:
        with lock.open('x', encoding='utf-8') as stream:
            stream.write(str(now))
    except FileExistsError:
        return _unavailable(asset_id, 'busy', '当前设备正在读取中，请稍后刷新。', retry_after_seconds=3)
    try:
        try:
            result = _fetch_asset(asset_id, skip_asset_status, equipment_id_hint)
        except (ValueError, TypeError, KeyError):
            result = _unavailable(asset_id, 'invalid_response', '返回资料与当前设备不一致或格式不完整，未关联其他设备。')
        ttl = SUCCESS_TTL if result['state'] == 'loaded' else FAILURE_TTL
        result = {**result, 'fetched_at': datetime.now(timezone.utc).isoformat(), 'cache_hit': False, 'retry_after_seconds': ttl}
        _write(path, {'cache_version': CACHE_VERSION, 'authorization_context': auth_context,
                      'equipment_id_hint': equipment_id_hint,
                      'expires_at': time.time() + ttl, 'result': result})
        return result
    finally:
        lock.unlink(missing_ok=True)
