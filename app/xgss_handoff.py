"""XGSS authenticated page handoff; never claims to retrieve manual text or a BOM."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'data/local/xgss-config.json'
AUTH_URL = 'https://xgss.xcmg.com/api/thrid/crm/auth'
FIELDS = {'username', 'orderId', 'accountId', 'terminal', 'systemCode', 'lang', 'type', 'vin', 'data'}


class XGSSUnavailable(ValueError):
    pass


class XGSSUpstreamError(RuntimeError):
    pass


def configuration():
    path = Path(os.getenv('XGSS_CONFIG_PATH') or CONFIG_PATH)
    try:
        config = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        raise XGSSUnavailable('XGSS 联调配置尚未完成。') from None
    if not isinstance(config, dict) or config.get('query_mode_confirmed') is not True:
        raise XGSSUnavailable('尚未确认 XGSS 查询模式及获准身份。')
    identity = config.get('identity')
    if not isinstance(identity, dict) or set(identity) - {'username', 'orderId', 'accountId'}:
        raise XGSSUnavailable('XGSS 身份与业务编号配置无效。')
    if any(not isinstance(identity.get(k), str) or not identity[k].strip() for k in ('username', 'orderId')):
        raise XGSSUnavailable('尚未配置获准的 XGSS 用户名及业务编号。')
    if any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in identity.values()):
        raise XGSSUnavailable('XGSS 身份字段格式无效。')
    if type(config.get('type')) is not int or config['type'] not in (1, 2):
        raise XGSSUnavailable('尚未配置接口方确认的 XGSS type 值。')
    field = config.get('fault_code_field')
    if field is not None and (not isinstance(field, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', field) or field in FIELDS):
        raise XGSSUnavailable('XGSS 故障码字段配置无效。')
    # The field's location must be confirmed; the source document does not define it.
    if field and config.get('fault_code_location') not in ('encrypted_payload', 'outer_body'):
        raise XGSSUnavailable('尚未确认故障码字段位于加密明文还是请求外层。')
    try:
        from app.xgss_crypto import read_public_key
        key_path = Path(config['public_key_path'])
        key = read_public_key(key_path if key_path.is_absolute() else path.parent/key_path)
    except (ImportError, KeyError, TypeError, ValueError, OSError):
        raise XGSSUnavailable('XGSS 公钥或加密组件尚未配置正确。') from None
    return config, key


def readiness():
    try:
        config, _ = configuration()
        fault_ready = bool(config.get('fault_code_field'))
        return dict(provider='XGSS', catalog_ready=True, fault_ready=fault_ready,
                    reason='可请求 XGSS 页面；实际连接及手册是否存在需以返回页面为准。' if fault_ready else '通用图册入口已配置，故障码字段尚待确认。',
                    live_verified=False)
    except XGSSUnavailable as error:
        return dict(provider='XGSS', catalog_ready=False, fault_ready=False, reason=str(error), live_verified=False)


def valid_destination(value):
    if not isinstance(value, str) or len(value) > 16384 or any(ord(c) <= 32 or ord(c) == 127 for c in value) or '\\' in value:
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and url.hostname == 'xgss.xcmg.com' and url.port in (None, 443)
                and not url.username and not url.password)
    except ValueError:
        return False


def request_page(vin, fault_code=None, language='zh'):
    if not isinstance(vin, str) or not re.fullmatch(r'[A-Z0-9]{8,32}', vin):
        raise ValueError('请核对真实整机 VIN/PIN，不能使用模拟编号或平台 UUID。')
    if language not in ('zh', 'en'):
        raise ValueError('Unsupported XGSS language')
    if fault_code is not None and (not isinstance(fault_code, str) or not fault_code.strip() or len(fault_code) > 100 or any(ord(c)<32 for c in fault_code)):
        raise ValueError('Invalid fault code')
    config, key = configuration()
    field = config.get('fault_code_field')
    if fault_code and not field:
        raise XGSSUnavailable('故障码字段尚未确认；不能将本次故障查询静默改成通用图册查询。')
    from app.xgss_crypto import encrypt_payload
    plaintext = {**config['identity'], 'terminal':'t4', 'systemCode':'iov', 'type':config['type'], 'vin':vin, 'lang':language}
    if fault_code and config['fault_code_location'] == 'encrypted_payload':
        plaintext[field] = fault_code
    body = encrypt_payload(plaintext, key)
    if fault_code and config['fault_code_location'] == 'outer_body':
        body[field] = fault_code
    try:
        # Exactly one auth call, no redirect following or automatic retry.
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.post(AUTH_URL, json=body)
            if response.status_code != 200:
                raise XGSSUpstreamError(f'XGSS 请求失败（HTTP {response.status_code}），未获得页面地址。')
            result = response.json()
    except (httpx.HTTPError, ValueError):
        raise XGSSUpstreamError('XGSS 网络连接失败或响应格式无效，未获得页面地址。') from None
    if not isinstance(result, dict) or result.get('success') is not True or not valid_destination(result.get('data')):
        raise XGSSUpstreamError('XGSS 未返回有效的官方页面地址；这不等于没有对应手册。')
    return dict(provider='XGSS', url=result['data'], vin=vin, fault_code=fault_code,
                destination='manual_or_catalog' if fault_code else 'catalog',
                manual_match_verified=False, manual_content_loaded=False,
                message='已取得 XGSS 页面入口。有对应手册时进入排查手册，否则进入该整机图册。' if fault_code else '已取得该整机的 XGSS 图册入口。')
