"""Offline TV12U protocol lookup. Source text is evidence, never an instruction."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re

REFERENCE_PATH = Path(__file__).resolve().parents[1] / 'data/local/reference/tv12u-hmi-260224-faults.json'
REFERENCE_ID = 'xcmg-tv12u-hmi-260224'
MODEL, VERSION = 'TV12U', '260224'
SOURCE_FILE = 'TV12U_HMI协议_260224.xlsx'
SOURCE_SHEET = '故障诊断协议及处理'
SOURCE_SHA256 = '1cfc23dbfdbb97bcd624e3edeb081119644b4d25d924f1992222e31e9d13dba5'
CONTENT_SHA256 = '76a65e5089597643a5fa2356deeaead0d7b2fcfead864d63f72b969c94126f94'
REMINDER_MODES = {
    '1': '常显示代码，蜂鸣器不提醒',
    '2': '常显示代码，每次起动时蜂鸣器连续响3秒',
    '3': '常显示代码，蜂鸣器持续提醒',
}
SCOPE_NOTES = [
    '仅适用于 TV12U、260224 协议版本；不自动匹配其他机型或 VIN。',
    '提醒方式为原表定义，不代表经过验证的风险等级。',
    '故障码定义不等于已确认零件损坏，不包含厂家维修步骤或备件料号。',
    '不能据此推断 Trackunit SPN/FMI 或 XGSS 故障码别名。',
]
_TEXT_FIELDS = ('description', 'display_prompt', 'display_rule_raw', 'display_text_raw', 'reminder_description')


class ReferenceUnavailable(ValueError):
    """Only public, path-free diagnostics may be returned to clients."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__({
            'missing': '未安装 TV12U 故障码参考资料。',
            'invalid': 'TV12U 故障码参考资料校验失败，暂不可用于诊断。',
            'unreadable': '暂时无法读取 TV12U 故障码参考资料。',
        }[reason])


def validate_reference(raw: object) -> dict:
    """Validate and project only lookup fields, omitting source paths/raw sheets."""
    if not isinstance(raw, dict) or any(raw.get(key) != value for key, value in {
        'reference_id': REFERENCE_ID, 'model_from_filename': MODEL,
        'protocol_version_from_filename': VERSION, 'source_sheet': SOURCE_SHEET,
        'source_range': 'A1:H129', 'source_type': 'user_provided_protocol',
        'source_sha256': SOURCE_SHA256, 'reminder_modes': REMINDER_MODES,
    }.items()):
        raise ReferenceUnavailable('invalid')
    faults = raw.get('faults')
    if not isinstance(faults, list) or len(faults) != 72:
        raise ReferenceUnavailable('invalid')
    codes, positions, items = set(), set(), []
    for row in faults:
        if not isinstance(row, dict):
            raise ReferenceUnavailable('invalid')
        code = row.get('code')
        if not isinstance(code, str) or not re.fullmatch(r'[EH][0-9]{5}', code) or code in codes:
            raise ReferenceUnavailable('invalid')
        byte, bit, source_row = (row.get(k) for k in ('byte_index', 'bit_index', 'source_row'))
        if any(type(v) is not int for v in (byte, bit, source_row)) or not (0 <= byte <= 7 and 0 <= bit <= 7):
            raise ReferenceUnavailable('invalid')
        can_id, first_row = ('0x11F501A1', 2) if code.startswith('E') else ('0x11F501A2', 66)
        if row.get('can_id') != can_id or source_row != first_row + 8 * byte + bit:
            raise ReferenceUnavailable('invalid')
        position = (can_id, byte, bit)
        if position in positions:
            raise ReferenceUnavailable('invalid')
        if any(not isinstance(row.get(k), str) or not row[k].strip() or len(row[k]) > 1000 for k in _TEXT_FIELDS):
            raise ReferenceUnavailable('invalid')
        mode = row.get('reminder_mode')
        if (type(mode) is not int or str(mode) not in REMINDER_MODES
                or row['reminder_description'] != REMINDER_MODES[str(mode)]
                or row['display_rule_raw'] != '0/1'
                or row['display_text_raw'] != f'不显示/显示{code}'):
            raise ReferenceUnavailable('invalid')
        cells = row.get('source_cells')
        if not isinstance(cells, dict) or set(cells) != set('ABCDEFGH'):
            raise ReferenceUnavailable('invalid')
        for column, cell in cells.items():
            match = re.fullmatch(column + r'([1-9][0-9]{0,2})', cell) if isinstance(cell, str) else None
            if not match or not 1 <= int(match[1]) <= source_row:
                raise ReferenceUnavailable('invalid')
            if column in 'CDEFH' and int(match[1]) != source_row:
                raise ReferenceUnavailable('invalid')
        items.append({
            'code': code, **{k: row[k] for k in _TEXT_FIELDS}, 'reminder_mode': mode,
            'can_id': can_id, 'byte_index': byte, 'bit_index': bit,
            'source_sheet': SOURCE_SHEET, 'source_row': source_row, 'source_cells': dict(cells),
        })
        codes.add(code)
        positions.add(position)
    if sum(c.startswith('E') for c in codes) != 30:
        raise ReferenceUnavailable('invalid')
    items.sort(key=lambda item: item['source_row'])
    # The workbook hash identifies provenance; this separately checks the
    # extracted definitions so edited descriptions cannot keep that provenance.
    content = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(content).hexdigest() != CONTENT_SHA256:
        raise ReferenceUnavailable('invalid')
    return {
        'reference_id': REFERENCE_ID, 'model': MODEL, 'version': VERSION,
        'source': {'file_name': SOURCE_FILE, 'sheet': SOURCE_SHEET, 'range': 'A1:H129',
                   'sha256': SOURCE_SHA256, 'type': 'user_provided_protocol'},
        'scope_notes': list(SCOPE_NOTES),
        'indexing': 'byte 和 bit 均按源表 0 至 7 编号；0 不显示，1 显示对应代码。',
        'items': items,
    }


def load_reference(path: Path | str | None = None) -> dict:
    """Read installed local reference; never downloads or calls a cloud provider."""
    source = Path(path) if path is not None else Path(os.environ.get('TV12U_FAULT_REFERENCE_PATH') or REFERENCE_PATH)
    try:
        with source.open('rb') as handle:
            content = handle.read(1_000_001)
        if len(content) > 1_000_000:
            raise ReferenceUnavailable('invalid')
        return validate_reference(json.loads(content.decode('utf-8-sig')))
    except FileNotFoundError:
        raise ReferenceUnavailable('missing') from None
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ReferenceUnavailable('invalid') from None
    except OSError:
        raise ReferenceUnavailable('unreadable') from None


def reference_status() -> dict:
    result = {'reference_id': REFERENCE_ID, 'model': MODEL, 'version': VERSION, 'offline': True}
    try:
        reference = load_reference()
        return {**result, 'available': True, 'reason': 'ready', 'fault_count': len(reference['items']),
                'source': reference['source'], 'scope_notes': reference['scope_notes']}
    except ReferenceUnavailable as error:
        return {**result, 'available': False, 'reason': error.reason, 'message': str(error), 'fault_count': 0}


def _require_scope(reference: dict, model: str, version: str) -> None:
    if (model.strip().upper(), version.strip()) != (reference['model'], reference['version']):
        raise ValueError('资料仅适用于 TV12U、260224 协议版本，请核对机型与版本。')


def lookup_fault(reference: dict, *, model: str, version: str, code: str) -> dict | None:
    """Pure exact lookup for diagnosis context. No fuzzy code or model matching."""
    _require_scope(reference, model, version)
    normalized = code.strip().upper()
    if not re.fullmatch(r'[EH][0-9]{5}', normalized):
        raise ValueError('请输入完整故障码，例如 H10101。')
    return next((deepcopy(row) for row in reference['items'] if row['code'] == normalized), None)


def search_faults(reference: dict, *, model: str, version: str, q: str = '') -> list[dict]:
    """Pure case-insensitive substring search of code and original fault text."""
    _require_scope(reference, model, version)
    query = q.strip().casefold()
    if len(query) > 120:
        raise ValueError('搜索内容不能超过 120 个字符。')
    return [deepcopy(row) for row in reference['items'] if not query or any(
        query in row[key].casefold() for key in ('code', 'description', 'display_prompt')
    )]
