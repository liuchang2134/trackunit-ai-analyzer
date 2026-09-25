"""Local-only, immutable rendered-page evidence for one device investigation.

Does not call a model or any external service. Never stores signed URLs.
"""
import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.xgss_catalog_context import CatalogRow
from app import xgss_research_images as images

STORE = Path(__file__).resolve().parents[1] / 'data/local/xgss-research'
LOCK = threading.RLock()
MAX_RESEARCH_PAGES = 8
MAX_ANALYSIS_PARTS = 400
MAX_ANALYSIS_MANUAL_CHARACTERS = 60000


class EvidenceLimitError(ValueError):
    """Evidence cannot fit one analysis; repeating the same request cannot fix it."""


def validate_analysis_capacity(pages):
    counts = (
        ('资料页数', len(pages), MAX_RESEARCH_PAGES),
        ('零件条目', sum(len(page['content']['items']) for page in pages), MAX_ANALYSIS_PARTS),
        ('手册字符', sum(len(section['text']) for page in pages for section in page['content']['manual_sections']),
         MAX_ANALYSIS_MANUAL_CHARACTERS),
    )
    exceeded = [f'{label} {count}/{limit}' for label, count, limit in counts if count > limit]
    if exceeded:
        raise EvidenceLimitError('资料总量超过单次分析范围（' + '；'.join(exceeded) +
                                 '）。请缩小检索分类并新建排查计划。已有资料仍保留。')


class ManualSection(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=180)
    text: str = Field(min_length=1, max_length=10000)


class PageCapture(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    source: Literal['xgss_rendered_page','xgss_api_catalog']
    source_url: Literal['https://xgss.xcmg.com/']
    vin: str = Field(pattern=r'^[A-Z0-9]{8,32}$')
    title: str = Field(min_length=1, max_length=200)
    assembly_path: list[str] = Field(default_factory=list, max_length=12)
    items: list[CatalogRow] = Field(default_factory=list, max_length=200)
    manual_sections: list[ManualSection] = Field(default_factory=list, max_length=12)
    coverage: Literal['rendered_content_only','api_selected_categories']
    illustrations: list[images.IllustrationCapture] = Field(default_factory=list, max_length=1)

    @model_validator(mode='after')
    def content_is_bounded(self):
        expected={'xgss_rendered_page':'rendered_content_only','xgss_api_catalog':'api_selected_categories'}
        if self.coverage!=expected[self.source]:
            raise ValueError('资料来源与采集范围不一致。')
        if not self.items and not self.manual_sections:
            raise ValueError('页面没有可提取的零件或手册内容。')
        if any(not p.strip() or len(p)>160 for p in self.assembly_path):
            raise ValueError('无效的分类路径。')
        if sum(len(p.text) for p in self.manual_sections)>30000:
            raise ValueError('单页手册摘录过长，请限定到相关章节。')
        return self


def _now():
    return datetime.now(timezone.utc).isoformat()


def _path(research_id):
    if not isinstance(research_id,str) or not re.fullmatch(r'[a-f0-9]{32}',research_id):
        raise ValueError('无效的资料收集编号。')
    return STORE/(research_id+'.json')


def _write_json(path,record):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as stream:
            temporary=stream.name
            json.dump(record,stream,ensure_ascii=False,indent=2)
        os.replace(temporary,path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _write(record):
    _write_json(_path(record['research_id']),record)


def create(machine_id,dataset_id,vin):
    record={'research_id':uuid.uuid4().hex,'machine_id':machine_id,'dataset_id':dataset_id,
            'vin':vin,'created_at':_now(),'pages':[],'revision':0}
    with LOCK:
        _write(record)
    return record


def canonical_content(page):
    # Transport-only PNGs must never change existing capture IDs or part references.
    return page.model_dump(exclude={'illustrations'})


def _digest(page):
    content={key:value for key,value in page.items() if key!='illustrations'}
    return hashlib.sha256(json.dumps(content,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def read(research_id):
    record=json.loads(_path(research_id).read_text(encoding='utf-8'))
    if record.get('research_id')!=research_id:
        raise ValueError('资料编号校验失败。')
    for stored in record['pages']:
        content=canonical_content(PageCapture.model_validate(stored['content']))
        if content['vin']!=record['vin'] or _digest(content)!=stored['capture_id']:
            raise ValueError('资料内容或设备校验失败。')
        if len(stored.get('illustrations',[]))>1:
            raise ValueError('单页图册图片数量超限。')
        for illustration in stored.get('illustrations',[]):
            images.IllustrationMetadata.model_validate(illustration)
        stored['content']=content
    return record


def latest(machine_id,dataset_id,vin):
    """Resume only a checked record for the exact device and data version."""
    paths=sorted(STORE.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    for path in paths:
        try:
            record=read(path.stem)
        except (ValueError,OSError,KeyError,TypeError):
            continue
        if (record.get('machine_id'),record.get('dataset_id'),record.get('vin'))==(machine_id,dataset_id,vin) and record.get('plan'):
            return record
    return None



class ActiveResearchConflict(ValueError):
    """Another request changed the active investigation for this exact scope."""


class _ActiveScope(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)
    machine_id: str = Field(min_length=1,max_length=200)
    dataset_id: str | None = Field(pattern=r'^[a-f0-9]{64}$')
    vin: str = Field(pattern=r'^[A-Z0-9]{8,32}$')


class _ActivePointer(_ActiveScope):
    research_id: str = Field(pattern=r'^[a-f0-9]{32}$')


def _active_scope(machine_id,dataset_id,vin):
    try:
        return _ActiveScope(machine_id=machine_id,dataset_id=dataset_id,vin=vin).model_dump()
    except ValueError:
        raise ValueError('当前排查的设备或数据版本无效。') from None


def _active_path(scope):
    key=hashlib.sha256(json.dumps(scope,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    # A separate directory keeps legacy latest() from treating pointers as records.
    return STORE/'active'/(key+'.json')


def _active_record(research_id,scope=None):
    try:
        record=read(research_id)
        record_scope=_active_scope(record['machine_id'],record['dataset_id'],record['vin'])
        if scope is not None and record_scope!=scope:
            raise ValueError('scope mismatch')
        if not isinstance(record.get('plan'),dict) or not record['plan']:
            raise ValueError('plan missing')
        return record
    except (ValueError,OSError,KeyError,TypeError,AttributeError):
        # Do not surface corrupt source content or authenticated URLs in errors.
        raise ValueError('当前排查记录无效、缺失或尚未生成计划，请重新建立排查计划。') from None


def _read_active_pointer(scope):
    try:
        raw=_active_path(scope).read_text(encoding='utf-8')
    except FileNotFoundError:
        return None
    except (OSError,ValueError):
        raise ValueError('当前排查指针无法读取，请核查本机记录。') from None
    try:
        pointer=_ActivePointer.model_validate_json(raw).model_dump()
        if {key:pointer[key] for key in scope}!=scope:
            raise ValueError('scope mismatch')
        return pointer
    except (ValueError,TypeError,KeyError):
        raise ValueError('当前排查指针校验失败，请核查本机记录。') from None


def active(machine_id,dataset_id,vin):
    """Read only an explicitly activated record; never fall back to history/latest."""
    scope=_active_scope(machine_id,dataset_id,vin)
    with LOCK:
        pointer=_read_active_pointer(scope)
        return None if pointer is None else _active_record(pointer['research_id'],scope)


def activate(research_id,expected_research_id):
    """CAS the scope pointer; retrying an already-active ID is idempotent."""
    if expected_research_id is not None:
        _path(expected_research_id)
    with LOCK:
        record=_active_record(research_id)
        scope=_active_scope(record['machine_id'],record['dataset_id'],record['vin'])
        # CAS compares pointer metadata, so an explicit new plan can replace a
        # missing/corrupt old record when the caller still knows its active ID.
        current=_read_active_pointer(scope)
        current_id=current['research_id'] if current is not None else None
        if current_id==research_id:
            return record
        if current_id!=expected_research_id:
            raise ActiveResearchConflict('当前排查已由其他请求更新，请读取当前状态后重试。')
        _write_json(_active_path(scope),{**scope,'research_id':research_id})
        return record


def append(research_id,page:PageCapture):
    with LOCK:
        record=read(research_id)
        if record['vin']!=page.vin:
            raise ValueError('XGSS 页面 VIN 与排查设备不一致，未导入。')
        content=canonical_content(page)
        capture_id=_digest(content)
        existing=next((item for item in record['pages'] if item['capture_id']==capture_id),None)
        target=existing if existing is not None else {'capture_id':capture_id,'captured_at':_now(),'content':content}
        prospective=record['pages'] if existing is not None else [*record['pages'],target]
        validate_analysis_capacity(prospective)
        prepared=[images.prepare(item) for item in page.illustrations]
        if existing is not None and not prepared:
            return record
        metadata=[]
        pending={}
        for data,item in prepared:
            previous=next((old for old in target.get('illustrations',[]) if all(old.get(key)==value for key,value in item.items())),None)
            metadata.append(previous or {**item,'captured_at':_now()})
            pending[item['image_id']]=data
        # Count retained and incoming bytes before writing any blob or record.
        if prepared:
            sizes={image_id:len(data) for image_id,data in pending.items()}
            for item in prospective:
                if item is target:continue
                for illustration in item.get('illustrations',[]):
                    image_id=illustration['image_id']
                    if image_id not in sizes:
                        sizes[image_id]=len(images.read_blob(STORE/'images',illustration))
            if sum(sizes.values())>images.MAX_RESEARCH_IMAGE_BYTES:
                raise images.ImageCaptureError('本次图册图片总量超过 8 MiB，未保存本页。请缩小检索分类并新建排查计划。')
            if existing is not None and metadata==target.get('illustrations',[]):
                # Still validate the stored blob rather than silently returning a broken image.
                for illustration in metadata:images.read_blob(STORE/'images',illustration)
                return record
        created=[]
        try:
            for image_id,data in pending.items():
                if images.write_blob(STORE/'images',image_id,data):created.append(image_id)
            if prepared:target['illustrations']=metadata
            if existing is None:
                record['pages'].append(target)
                record['revision']+=1
                for field in ('advice','analysis_revision','analyzed_at'):record.pop(field,None)
            _write(record)
        except Exception:
            # The lock prevents another record from referencing a newly created blob
            # before this metadata transaction is committed.
            for image_id in created:
                try:images.path_for(STORE/'images',image_id).unlink()
                except OSError:pass
            raise
        return record


def read_image(record,image_id):
    images.path_for(STORE/'images',image_id)
    for page in record['pages']:
        for illustration in page.get('illustrations',[]):
            if illustration['image_id']==image_id:
                return images.read_blob(STORE/'images',illustration)
    raise images.ImageCaptureError('当前设备资料中没有这张图册图片。')


def append_batch(research_id,pages,*,check_current,direct_collection):
    """Commit one bounded API collection atomically; retain all older evidence."""
    pages=[PageCapture.model_validate(page) for page in pages]
    if not pages:
        raise ValueError('没有可保存的图册资料。')
    with LOCK:
        record=read(research_id)
        check_current(record)
        pending={}
        changed_text=False
        for page in pages:
            if record['vin']!=page.vin:
                raise ValueError('XGSS 页面 VIN 与排查设备不一致，未导入。')
            content=canonical_content(page)
            capture_id=_digest(content)
            target=next((item for item in record['pages'] if item['capture_id']==capture_id),None)
            if target is None:
                target={'capture_id':capture_id,'captured_at':_now(),'content':content}
                record['pages'].append(target)
                record['revision']+=1
                changed_text=True
            if page.illustrations:
                metadata=[]
                for data,item in (images.prepare(capture) for capture in page.illustrations):
                    previous=next((old for old in target.get('illustrations',[])
                                   if all(old.get(key)==value for key,value in item.items())),None)
                    metadata.append(previous or {**item,'captured_at':_now()})
                    pending[item['image_id']]=data
                target['illustrations']=metadata
        validate_analysis_capacity(record['pages'])
        retained={}
        for page in record['pages']:
            for image in page.get('illustrations',[]):
                image_id=image['image_id']
                if image_id not in retained:
                    retained[image_id]=pending.get(image_id)
                    if retained[image_id] is None:
                        retained[image_id]=images.read_blob(STORE/'images',image)
        if sum(len(data) for data in retained.values())>images.MAX_RESEARCH_IMAGE_BYTES:
            raise images.ImageCaptureError('本次图册图片总量超过 8 MiB，未保存本次资料。请缩小检索分类并新建排查计划。')
        if changed_text:
            for field in ('advice','analysis_revision','analyzed_at'):record.pop(field,None)
        record['direct_collection']={**direct_collection,'revision':record['revision']}
        created=[]
        try:
            # Re-read the disk record for optimistic concurrency, not the staged revision.
            check_current(read(research_id))
            for image_id,data in pending.items():
                if image_id in retained and images.write_blob(STORE/'images',image_id,data):created.append(image_id)
            check_current(read(research_id))
            _write(record)
        except Exception:
            for image_id in created:
                try:images.path_for(STORE/'images',image_id).unlink()
                except OSError:pass
            raise
        return record


def evidence(record):
    """Produce exact source IDs; consumers must load through read() first."""
    parts,manuals=[],[]
    for page in record['pages']:
        content=page['content']
        common={'page_title':content['title'],'assembly_path':content['assembly_path'],
                'captured_at':page['captured_at'],'capture_id':page['capture_id']}
        parts.extend({**r,**common,'source_id':f"xpart:{page['capture_id']}:{i}"} for i,r in enumerate(content['items']))
        manuals.extend({**r,**common,'source_id':f"xmanual:{page['capture_id']}:{i}"} for i,r in enumerate(content['manual_sections']))
    return {'parts':parts,'manuals':manuals,'coverage':'captured_pages_only'}
