"""Bounded direct-XGSS collection, separate from model analysis and browser capture."""
import re
import threading
import time
from copy import deepcopy
from datetime import datetime,timezone
from typing import Annotated

from pydantic import BaseModel,ConfigDict,Field,StringConstraints,ValidationError,field_validator

from app import xgss_research_store as store
from app.deepseek_client import _check_cancelled

BUSY=set()
BUSY_LOCK=threading.Lock()
DEADLINE_SECONDS=90
PARTIAL_CACHE_SECONDS=60


class DirectCollectionError(ValueError):
    def __init__(self,kind,message,*,retryable=False):
        super().__init__(message)
        self.kind=kind
        self.message=message
        self.retryable=retryable


SearchTerm=Annotated[str,StringConstraints(strip_whitespace=True,min_length=2,max_length=40,
                                          pattern=r'^[^<>\r\n]+$')]


class SensorContext(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    series_id:str=Field(pattern=r'^[a-f0-9]{64}$')
    hypothesis_index:int=Field(ge=0,strict=True)


class CollectRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:int=Field(ge=0,strict=True)
    terms:list[SearchTerm]=Field(min_length=1,max_length=12)
    sensor_context:SensorContext|None=None
    force_refresh:bool=Field(default=False,strict=True)

    @field_validator('terms')
    @classmethod
    def labels_only(cls,values):
        if any(re.search(r'https?://',term,re.I) for term in values):
            raise ValueError('请使用部件名称，不能使用网址。')
        return list(dict.fromkeys(values))


def _identity(record):
    return {key:record[key] for key in ('machine_id','dataset_id','vin')}


def _active_id(record):
    active=store.active(**_identity(record))
    return active['research_id'] if active else None


def _sensor_seed(record,context):
    """Authorize an isolated risk lookup from the saved same-device AI result."""
    if context is None:return None
    # Sensor questions must never borrow fault evidence or a prior report.
    conflicts=('fault_event_id','source_report_id','manual_fault','engineering_fault',
               'page_fault','handoff_context','catalog_fault_code','manual_fault_reference',
               'trackunit_page','trackunit_event')
    fault_context=record.get('fault_context')
    empty_fault_context={'manual_fault':None,'engineering_fault':None,'manuals':[]}
    if (record.get('symptom_source')!='user_question'
        or record.get('analysis_mode','fault')!='fault'
        or any(record.get(key) is not None for key in conflicts)
        or fault_context not in (None,{},empty_fault_context)):
        raise DirectCollectionError('direct_sensor_context_invalid','连续数据排查与故障上下文不一致，请重新选择风险方向。')
    # Lazy import keeps the ordinary fault-collection path independent.
    from app.sensor_series import parts_handoff
    try:
        seed=parts_handoff(context.series_id,record['machine_id'],record['dataset_id'],context.hypothesis_index)
        valid=(isinstance(seed,dict) and _identity(seed)==_identity(record)
               and seed.get('series_id')==context.series_id
               and type(seed.get('hypothesis_index')) is int
               and seed['hypothesis_index']==context.hypothesis_index
               and seed.get('symptom_source')=='user_question'
               and isinstance(seed.get('symptom'),str) and bool(seed['symptom'])
               and seed['symptom']==record.get('symptom'))
    except (ValueError,OSError,KeyError,TypeError):
        valid=False
    if not valid:
        raise DirectCollectionError('direct_sensor_context_invalid','连续数据分析已变化或与当前设备不一致，请重新选择风险方向。')
    return deepcopy(seed)


def _previous_api_pages(record,terms):
    meta=record.get('direct_collection')
    if not isinstance(meta,dict) or meta.get('terms')!=terms:return []
    capture_ids=meta.get('capture_ids')
    if (not isinstance(capture_ids,list) or not capture_ids
        or not all(isinstance(value,str) and re.fullmatch(r'[a-f0-9]{64}',value) for value in capture_ids)):
        return []
    pages={page['capture_id']:page for page in record['pages']}
    selected=[pages.get(capture_id) for capture_id in dict.fromkeys(capture_ids)]
    if any(not page or page['content']['source']!='xgss_api_catalog' for page in selected):return []
    return selected


def _cache(record,terms):
    meta=record.get('direct_collection')
    if (not isinstance(meta,dict) or meta.get('status') not in ('completed','partial') or meta.get('terms')!=terms
        or meta.get('revision')!=record['revision']):
        return None
    if meta['status']=='partial':
        try:age=(datetime.now(timezone.utc)-datetime.fromisoformat(meta['collected_at'])).total_seconds()
        except (ValueError,TypeError,KeyError):return None
        if not 0<=age<PARTIAL_CACHE_SECONDS:return None
    pages=_previous_api_pages(record,terms)
    if not pages:return None
    for page in pages:
        for image in page.get('illustrations',[]):store.read_image(record,image['image_id'])
    return {**record,'direct_collection':{**meta,'cached':True}}


def _read_catalog(vin,terms,*,check_cancelled,progress,max_pages,max_parts):
    # Lazy import keeps the application and existing browser path independent
    # of optional direct-reader dependencies.
    from app.xgss_direct_api import collect_catalog,DirectReadError
    try:
        return collect_catalog(vin,terms,check_cancelled=check_cancelled,progress=progress,
                               max_pages=max_pages,max_parts=max_parts)
    except DirectReadError as error:
        kind=error.kind if re.fullmatch(r'direct_[a-z_]{1,50}',str(error.kind)) else 'direct_unavailable'
        message=str(getattr(error,'message',error))[:400]
        # Provider URLs, cookies or exception dumps are never public progress.
        if re.search(r'https?://|token|cookie|authorization',message,re.I):
            message='XGSS 直接读取未完成，已有资料保持不变。'
        raise DirectCollectionError(kind,message,retryable=bool(error.retryable)) from None


def collect(research_id,request:CollectRequest,*,progress=lambda _message:None,verify_identity=None):
    request=CollectRequest.model_validate(request)
    started=time.monotonic()
    def check_cancelled():
        _check_cancelled()
        if time.monotonic()-started>=DEADLINE_SECONDS:
            raise DirectCollectionError('direct_timeout','XGSS 读取超过等待时间，已有资料保持不变。',retryable=True)
    with BUSY_LOCK:
        if research_id in BUSY:
            raise DirectCollectionError('direct_busy','本次资料正在读取，请等待完成。')
        BUSY.add(research_id)
    try:
        with store.LOCK:
            check_cancelled()
            original=store.read(research_id)
            if verify_identity:verify_identity(original)
            if not isinstance(original.get('plan'),dict) or not original['plan']:
                raise DirectCollectionError('direct_plan_missing','请先生成部件检索计划，再读取图册。')
            if original['revision']!=request.expected_revision:
                raise DirectCollectionError('direct_revision_changed','资料已更新，请读取当前排查后继续。')
            sensor_seed=_sensor_seed(original,request.sensor_context)
            initial_active=_active_id(original)
            if sensor_seed is None and initial_active not in (None,research_id):
                raise DirectCollectionError('direct_active_changed','当前排查已切换，请读取当前排查后继续。')
            cached=None if request.force_refresh else _cache(original,request.terms)
            if cached:return cached
            previous_pages=_previous_api_pages(original,request.terms)
            # A retry may re-read its own captured pages to recover missing
            # pictures. The atomic store still checks the deduplicated total.
            max_pages=min(6,store.MAX_RESEARCH_PAGES-len(original['pages'])+len(previous_pages))
            max_parts=(store.MAX_ANALYSIS_PARTS-sum(len(page['content']['items']) for page in original['pages'])
                       +sum(len(page['content']['items']) for page in previous_pages))
            if max_pages<=0 or max_parts<=0:
                raise store.EvidenceLimitError('当前排查的资料容量已满，已有资料与建议保持不变。请缩小检索分类并新建排查计划。')
        identity=_identity(original)
        def check_current(current):
            check_cancelled()
            if _identity(current)!=identity or current['revision']!=request.expected_revision:
                raise DirectCollectionError('direct_revision_changed','资料已更新，未保存本次读取结果。')
            if _active_id(current)!=initial_active:
                raise DirectCollectionError('direct_active_changed','当前排查已切换，未保存本次读取结果。')
            if request.sensor_context is not None and _sensor_seed(current,request.sensor_context)!=sensor_seed:
                raise DirectCollectionError('direct_sensor_context_changed','连续数据分析已变化，未保存本次读取结果。请重新选择风险方向。')
            if verify_identity:verify_identity(current)
        # Progress content is fixed here; reader response bodies never reach SSE.
        response=_read_catalog(original['vin'],request.terms,check_cancelled=check_cancelled,
                               progress=lambda *_args,**_kwargs:progress('正在直接读取 XGSS 分类、零件和图示…'),
                               max_pages=max_pages,max_parts=max_parts)
        check_cancelled()
        if not isinstance(response,dict) or response.get('status') not in ('completed','partial'):
            raise DirectCollectionError('direct_schema','XGSS 返回资料格式无法核对，未保存本次结果。')
        raw_pages=response.get('pages')
        if not isinstance(raw_pages,list):
            raise DirectCollectionError('direct_schema','XGSS 返回资料格式无法核对，未保存本次结果。')
        if not raw_pages:
            raise DirectCollectionError('direct_no_match','未找到本次检索词对应的图册资料。')
        if len(raw_pages)>max_pages:
            raise store.EvidenceLimitError('本次返回的图册超过剩余资料容量，未保存。请缩小检索分类并新建排查计划。')
        try:
            pages=[store.PageCapture.model_validate(page) for page in raw_pages]
        except ValidationError:
            raise DirectCollectionError('direct_schema','XGSS 返回的零件或图示格式无法核对，未保存本次结果。') from None
        if any(page.source!='xgss_api_catalog' or page.vin!=original['vin'] for page in pages):
            raise DirectCollectionError('direct_scope_mismatch','XGSS 资料来源或整机身份不一致，未保存。')
        unmatched=response.get('unmatched_terms',[])
        unresolved=response.get('unresolved',[])
        if (not isinstance(unmatched,list) or not all(isinstance(term,str) and term in request.terms for term in unmatched)
            or not isinstance(unresolved,list) or len(unresolved)>40
            or not all(isinstance(term,str) and 0<len(term)<=200 and not re.search(r'https?://|token|cookie',term,re.I) for term in unresolved)):
            raise DirectCollectionError('direct_schema','XGSS 资料范围无法核对，未保存本次结果。')
        meta={'status':'partial' if unmatched or unresolved else response['status'],
              'terms':request.terms,'capture_ids':list(dict.fromkeys(store._digest(store.canonical_content(page)) for page in pages)),
              'unmatched_terms':unmatched,'unresolved':unresolved,'cached':False,'collected_at':store._now()}
        current=store.append_batch(research_id,pages,check_current=check_current,direct_collection=meta)
        progress('XGSS 资料已保存，可继续生成备件建议。')
        return current
    finally:
        with BUSY_LOCK:BUSY.discard(research_id)
