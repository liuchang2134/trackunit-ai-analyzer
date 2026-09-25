"""Same-device, selected Trackunit page observations; never official API events."""
from datetime import datetime
import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UUID_PATTERN = r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'
PAGE_PATH = re.compile(r'^/assets/(' + UUID_PATTERN + r')/events/?$')


class PageFault(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    asset_id: str = Field(pattern=r'^' + UUID_PATTERN + r'$')
    source_url: str = Field(min_length=1, max_length=240)
    observed_at: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=1000)
    code: str = Field(default='', max_length=128)
    spn: int | None = Field(default=None, ge=0, le=524287)
    fmi: int | None = Field(default=None, ge=0, le=31)
    sa: int | None = Field(default=None, ge=0, le=255)
    status: Literal['OPEN', 'CLOSED', 'UNKNOWN'] = 'UNKNOWN'
    occurred_at: str | None = Field(default=None, max_length=120)
    cleared_at: str | None = Field(default=None, max_length=120)
    page_event_id: str | None = Field(default=None, max_length=200)

    @field_validator('asset_id')
    @classmethod
    def canonical_asset(cls, value):
        return str(UUID(value))

    @field_validator('observed_at')
    @classmethod
    def iso_observation(cls, value):
        if not re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value):
            raise ValueError('页面读取时间必须为带时区的 ISO 时间。')
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError('页面读取时间必须包含时区。')
        return value

    @field_validator('source_url')
    @classmethod
    def allowed_page(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or parsed.netloc not in
                ('new.manager.trackunit.com', 'manager.trackunit.com') or
                parsed.query or parsed.fragment or not PAGE_PATH.fullmatch(parsed.path)):
            raise ValueError('页面来源必须是无查询参数的 Trackunit 同机 Events 页面。')
        return value

    @field_validator('description', 'code', 'occurred_at', 'cleared_at', 'page_event_id')
    @classmethod
    def visible_text(cls, value):
        if value is not None and re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', value):
            raise ValueError('页面字段包含无效控制字符。')
        return value

    @model_validator(mode='after')
    def page_identity(self):
        match = PAGE_PATH.fullmatch(urlsplit(self.source_url).path)
        if str(UUID(match.group(1))) != self.asset_id:
            raise ValueError('页面地址与所选故障的设备不一致。')
        return self


def validate_request(body):
    """Do not let a page selection borrow another source's authority or scope."""
    if (getattr(body, 'symptom_source', None) != 'trackunit_page' or
            getattr(body, 'analysis_mode', 'fault') != 'fault' or
            getattr(body, 'automatic', False) or
            any(getattr(body, key, None) is not None for key in
                ('fault_event_id', 'source_report_id', 'manual_fault', 'engineering_fault'))):
        raise ValueError('页面故障应单独分析，不能混入接口事件、旧报告、其他故障或保养任务。')


def plan_context(body, machine=None):
    """Freeze the selected observation after checking the server's machine map."""
    validate_request(body)
    page = PageFault.model_validate(body.page_fault)
    if machine is None:
        # Reuse the existing local-only registry when called outside the route.
        from app.trackunit_events import registered_machine
        identity = registered_machine(body.machine_id, body.dataset_id, body.vin)
        asset_id = identity['trackunit_asset_id']
    else:
        if (getattr(machine, 'machine_id', None) != body.machine_id or
                getattr(machine, 'serial_number', '').strip().upper() != body.vin):
            raise ValueError('页面故障与已验证设备身份不一致。')
        asset_id = getattr(machine, 'trackunit_asset_id', None) or machine.machine_id
    try:
        expected = str(UUID(asset_id))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('已验证设备没有有效的 Trackunit 设备映射。') from None
    if page.asset_id != expected:
        raise ValueError('页面故障不属于当前设备。')
    frozen = page.model_dump()
    frozen.update(source='trackunit_visible_events_page', coverage='selected_visible_event_only')
    identifiers = []
    if page.code:
        identifiers.append(page.code)
    for key in ('spn', 'fmi', 'sa'):
        if getattr(page, key) is not None:
            identifiers.append(f'{key.upper()} {getattr(page, key)}')
    code = ' / '.join(identifiers) or '页面未显示具体故障码'
    status = {'OPEN': '活动', 'CLOSED': '已解除（历史记录）', 'UNKNOWN': '未知'}[page.status]
    symptom = (f'Trackunit 页面所选故障：{code}；页面记录状态 {page.status}（{status}）。'
               f'页面描述：{page.description}。')
    if page.occurred_at:
        symptom += f'页面原时间：{page.occurred_at}（时间含义及所在时区以原页为准）。'
    if page.cleared_at:
        symptom += f'页面原解除时间：{page.cleared_at}。'
    symptom += f'页面读取时间：{page.observed_at}。仅为所选页面记录，未通过故障 API 核验完整历史。'
    return {'fault_event_id': None, 'symptom': symptom, 'symptom_source': 'trackunit_page',
            'source_report_id': None, 'handoff_context': None, 'manual_fault': None,
            'engineering_fault': None, 'catalog_fault_code': None,
            'fault_context': {'trackunit_page': frozen, 'operator_supplement': body.symptom.strip(),
                              'manual_fault': None, 'engineering_fault': None, 'manuals': []}}
