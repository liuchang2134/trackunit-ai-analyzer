"""Direct collection integration uses only synthetic local responses, never XGSS or AI."""
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from io import BytesIO
import json
import sys
import threading
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from PIL import Image
from app import xgss_research_store as store,xgss_direct_collection as direct
from app.deepseek_client import InvestigationCancelled,cancellation_scope,reset_cancellation_scope

VIN='XUGTEST000000001'
_REAL_READER=direct._read_catalog


def page(title='双变系统',**changes):
    return store.PageCapture.model_validate({'source':'xgss_api_catalog','source_url':'https://xgss.xcmg.com/',
        'vin':VIN,'title':title,'assembly_path':['整机',title],
        'items':[{'name':'测试阀总成','part_number':'TEST-001'}],
        'manual_sections':[],'coverage':'api_selected_categories',**changes})


def image(color='red'):
    output=BytesIO();Image.new('RGB',(3,2),color).save(output,format='PNG')
    return {'data_url':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode(),
            'title':'同分类测试图','document_ref':'123.svg'}


def response(pages=None,**changes):
    return {'pages':[page()] if pages is None else pages,'status':'completed','unmatched_terms':[],
            'unresolved':[],**changes}


@pytest.fixture
def record(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    monkeypatch.setattr(direct,'_read_catalog',lambda *a,**k:response())
    current=store.create('fixture-machine','a'*64,VIN)
    current['plan']={'summary':'本地测试检索计划'};store._write(current)
    return current


def collect(record,terms=None,revision=None,**kwargs):
    request=direct.CollectRequest(expected_revision=record['revision'] if revision is None else revision,
                                  terms=terms or ['双变系统'])
    return direct.collect(record['research_id'],request,**kwargs)


@pytest.mark.parametrize('source,coverage,valid',[
    ('xgss_rendered_page','rendered_content_only',True),('xgss_api_catalog','api_selected_categories',True),
    ('xgss_rendered_page','api_selected_categories',False),('xgss_api_catalog','rendered_content_only',False)])
def test_source_and_scope_pairs_preserve_legacy_content_hash(record,source,coverage,valid):
    if not valid:
        with pytest.raises(ValidationError):page(source=source,coverage=coverage)
        return
    capture=page(source=source,coverage=coverage)
    saved=store.append(record['research_id'],capture)
    expected=hashlib.sha256(json.dumps(capture.model_dump(exclude={'illustrations'}),ensure_ascii=False,
                                      sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert saved['pages'][0]['capture_id']==expected
    assert store.read(record['research_id'])==saved


@pytest.mark.parametrize('body',[
    {'expected_revision':True,'terms':['双变系统']},{'expected_revision':-1,'terms':['双变系统']},
    {'expected_revision':0,'terms':[]},{'expected_revision':0,'terms':['https://example.test/']},
    {'expected_revision':0,'terms':['a'*41]},{'expected_revision':0,'terms':['双变系统'],'vin':VIN}])
def test_request_does_not_accept_urls_unbounded_terms_or_identity_override(body):
    with pytest.raises(ValidationError):direct.CollectRequest.model_validate(body)


def test_direct_commit_and_same_record_cache_preserve_advice_and_source_ids(record,monkeypatch):
    calls=[]
    monkeypatch.setattr(direct,'_read_catalog',lambda *a,**k:(calls.append((a,k)),response([page(illustrations=[image()])]))[1])
    saved=collect(record);assert saved['revision']==1
    assert saved['direct_collection']['cached'] is False
    assert saved['direct_collection']['capture_ids']==[saved['pages'][0]['capture_id']]
    saved.update(advice={'summary':'已有建议'},analysis_revision=1);store._write(saved)
    before=store._path(record['research_id']).read_bytes()
    cached=collect(saved)
    assert len(calls)==1 and cached['direct_collection']['cached'] is True
    assert cached['advice']==saved['advice']
    assert store._path(record['research_id']).read_bytes()==before
    assert calls[0][0][0]==VIN and calls[0][1]['max_pages']==6 and calls[0][1]['max_parts']==400
    assert 'data_url' not in json.dumps(saved)


def test_five_existing_pages_limit_new_read_to_three_and_partial_cache_does_not_grow(record,monkeypatch):
    for index in range(5):
        record=store.append(record['research_id'],page(str(index),source='xgss_rendered_page',coverage='rendered_content_only'))
    calls=[]
    def reader(*args,**kwargs):
        calls.append(kwargs)
        return response([page(f'新分类{i}') for i in range(3)],status='partial',unmatched_terms=['换挡系统'])
    monkeypatch.setattr(direct,'_read_catalog',reader)
    saved=collect(record,terms=['双变系统','换挡系统'])
    assert calls[0]['max_pages']==3 and calls[0]['max_parts']==395
    assert len(saved['pages'])==8 and saved['direct_collection']['status']=='partial'
    cached=collect(saved,terms=['双变系统','换挡系统'])
    assert len(calls)==1 and cached['direct_collection']['cached'] is True
    assert cached['direct_collection']['status']=='partial'
    with pytest.raises(store.EvidenceLimitError,match='新建排查'):collect(saved,terms=['另一个分类'])
    assert len(calls)==1


def test_batch_capacity_and_bad_second_page_leave_old_sources_advice_and_no_blobs(record,monkeypatch):
    original=store.append(record['research_id'],page('已有分类'))
    original.update(advice={'summary':'已有建议'},analysis_revision=1);store._write(original)
    before=store._path(record['research_id']).read_bytes()
    monkeypatch.setattr(direct,'_read_catalog',lambda *a,**k:response([page('新一',illustrations=[image()]),page('新二')]))
    monkeypatch.setattr(store,'MAX_ANALYSIS_PARTS',2)
    with pytest.raises(store.EvidenceLimitError):collect(original)
    assert store._path(record['research_id']).read_bytes()==before
    assert not (store.STORE/'images').exists()
    monkeypatch.setattr(store,'MAX_ANALYSIS_PARTS',400)
    bad=page('新二',illustrations=[{**image(),'data_url':'data:image/png;base64,PHN2Zy8+'}])
    monkeypatch.setattr(direct,'_read_catalog',lambda *a,**k:response([page('新一',illustrations=[image()]),bad]))
    with pytest.raises(store.images.ImageCaptureError):collect(original)
    assert store._path(record['research_id']).read_bytes()==before
    assert not (store.STORE/'images').exists()


def test_batch_metadata_failure_rolls_back_all_new_images(record,monkeypatch):
    before=store._path(record['research_id']).read_bytes()
    monkeypatch.setattr(direct,'_read_catalog',lambda *a,**k:response([page('一',illustrations=[image()]),page('二',illustrations=[image('blue')])]))
    def unavailable(_record):raise OSError('fixture save failure')
    monkeypatch.setattr(store,'_write',unavailable)
    with pytest.raises(OSError):collect(record)
    assert store._path(record['research_id']).read_bytes()==before
    assert list((store.STORE/'images').glob('*.png'))==[]


@pytest.mark.parametrize('change',['revision','active','cancel','deadline','identity'])
def test_commit_rechecks_revision_active_cancel_deadline_and_identity(record,monkeypatch,change):
    cancelled=False;clock=0;identity_calls=0
    monkeypatch.setattr(direct.time,'monotonic',lambda:clock)
    def reader(*args,**kwargs):
        nonlocal cancelled,clock
        if change=='revision':store.append(record['research_id'],page('其他窗口已保存'))
        elif change=='active':store.activate(record['research_id'],None)
        elif change=='cancel':cancelled=True
        elif change=='deadline':clock=100
        return response()
    def verify(_record):
        nonlocal identity_calls
        identity_calls+=1
        if change=='identity' and identity_calls>1:raise direct.DirectCollectionError('direct_scope_mismatch','fixture identity changed')
    monkeypatch.setattr(direct,'_read_catalog',reader)
    token=cancellation_scope(lambda:cancelled)
    try:
        with pytest.raises((direct.DirectCollectionError,InvestigationCancelled)):collect(record,verify_identity=verify)
    finally:reset_cancellation_scope(token)
    saved=store.read(record['research_id'])
    assert 'direct_collection' not in saved
    assert len(saved['pages'])==(1 if change=='revision' else 0)
    assert record['research_id'] not in direct.BUSY


def test_reject_stale_revision_other_active_or_missing_plan_before_upstream(record,monkeypatch):
    calls=[];monkeypatch.setattr(direct,'_read_catalog',lambda *a,**k:calls.append(1))
    with pytest.raises(direct.DirectCollectionError,match='已更新'):collect(record,revision=9)
    other=store.create(record['machine_id'],record['dataset_id'],VIN);other['plan']={'summary':'另一排查'};store._write(other)
    store.activate(other['research_id'],None)
    with pytest.raises(direct.DirectCollectionError,match='已切换'):collect(record)
    record.pop('plan');store._write(record)
    with pytest.raises(direct.DirectCollectionError,match='先生成'):collect(record)
    assert calls==[]


def test_busy_excludes_second_same_record_request_and_releases_after_success(record,monkeypatch):
    entered=threading.Event();release=threading.Event();calls=[]
    def reader(*args,**kwargs):
        calls.append(1);entered.set();assert release.wait(3);return response()
    monkeypatch.setattr(direct,'_read_catalog',reader)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending=executor.submit(collect,record);assert entered.wait(3)
        try:
            with pytest.raises(direct.DirectCollectionError) as failure:collect(record)
            assert failure.value.kind=='direct_busy'
        finally:release.set()
        assert pending.result()['revision']==1
    assert calls==[1] and record['research_id'] not in direct.BUSY


@pytest.mark.parametrize('bad,kind',[
    (response([]),'direct_no_match'),(response([page(vin='XUGOTHER000000001')]),'direct_scope_mismatch'),
    (response([page(source='xgss_rendered_page',coverage='rendered_content_only')]),'direct_scope_mismatch'),
    (response([{'cookie':'secret'}]),'direct_schema'),(response(unresolved=['https://example.test/?token=secret']),'direct_schema')])
def test_bad_reader_results_leave_record_unchanged(record,monkeypatch,bad,kind):
    before=store._path(record['research_id']).read_bytes()
    monkeypatch.setattr(direct,'_read_catalog',lambda *a,**k:bad)
    with pytest.raises(direct.DirectCollectionError) as failure:collect(record)
    assert failure.value.kind==kind and 'secret' not in str(failure.value)
    assert store._path(record['research_id']).read_bytes()==before


def test_reader_error_translation_does_not_expose_authenticated_urls(record,monkeypatch):
    class DirectReadError(Exception):
        kind='direct_auth';retryable=True;message='https://xgss.xcmg.com/?token=SECRET'
    def reader(*args,**kwargs):raise DirectReadError()
    monkeypatch.setitem(sys.modules,'app.xgss_direct_api',SimpleNamespace(collect_catalog=reader,DirectReadError=DirectReadError))
    monkeypatch.setattr(direct,'_read_catalog',_REAL_READER)
    with pytest.raises(direct.DirectCollectionError) as failure:collect(record)
    assert failure.value.kind=='direct_auth' and failure.value.retryable
    assert 'SECRET' not in str(failure.value)


def test_route_checks_identity_streams_direct_result_and_never_calls_model(record,monkeypatch):
    from fastapi import FastAPI,HTTPException
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    calls=[]
    def unexpected(*a,**k):raise AssertionError('Direct collection must not call AI')
    monkeypatch.setattr(routes.ai,'analyze',unexpected)
    monkeypatch.setattr(routes.ai,'plan',unexpected)
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:calls.append(a))
    def reader(*args,**kwargs):kwargs['progress']('PRIVATE upstream token');return response()
    monkeypatch.setattr(direct,'_read_catalog',reader)
    app=FastAPI();app.include_router(routes.router);client=TestClient(app)
    url=f"/assistant/xgss/research/{record['research_id']}/collect-direct"
    result=client.post(url,json={'expected_revision':0,'terms':['双变系统']})
    events=[json.loads(line[6:]) for line in result.text.splitlines() if line.startswith('data: ')]
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    assert events[-1]['type']=='result' and events[-1]['record']['direct_collection']['status']=='completed'
    assert events[-1]['record']['evidence']['parts'][0]['part_number']=='TEST-001'
    assert 'PRIVATE' not in result.text and calls[0]==(record['machine_id'],record['dataset_id'],VIN)
    def forbidden(*a):raise HTTPException(422,'fixture wrong device')
    monkeypatch.setattr(routes,'_verify_machine',forbidden)
    assert client.post(url,json={'expected_revision':1,'terms':['双变系统']}).status_code==422


def test_route_reports_specific_direct_error_and_no_false_result(record,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:None)
    def unavailable(*a,**k):raise direct.DirectCollectionError('direct_unavailable','暂不可用',retryable=True)
    monkeypatch.setattr(direct,'_read_catalog',unavailable)
    app=FastAPI();app.include_router(routes.router)
    result=TestClient(app).post(f"/assistant/xgss/research/{record['research_id']}/collect-direct",
                              json={'expected_revision':0,'terms':['双变系统']})
    events=[json.loads(line[6:]) for line in result.text.splitlines() if line.startswith('data: ')]
    assert events[-1]=={'type':'error','kind':'direct_unavailable','message':'暂不可用','retryable':True}
    assert not any(event['type']=='result' for event in events)


def test_route_cached_collection_still_validates_old_advice_without_dropping_collection_status(record,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    saved=collect(record)
    saved.update(advice={'summary':'invalid old advice'},analysis_revision=saved['revision']);store._write(saved)
    before=store._path(record['research_id']).read_bytes()
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:None)
    def invalid(_record):raise ValueError('fixture old source validation failure')
    monkeypatch.setattr(routes.ai,'normalize_cached_advice',invalid)
    def unexpected(*a,**k):raise AssertionError('Cache must not call upstream')
    monkeypatch.setattr(direct,'_read_catalog',unexpected)
    app=FastAPI();app.include_router(routes.router)
    result=TestClient(app).post(f"/assistant/xgss/research/{record['research_id']}/collect-direct",
                              json={'expected_revision':saved['revision'],'terms':['双变系统']})
    final=[json.loads(line[6:]) for line in result.text.splitlines() if line.startswith('data: ')][-1]
    assert final['type']=='result'
    assert final['record']['direct_collection']['cached'] is True
    assert final['record']['advice_error'] and 'advice' not in final['record']
    assert store._path(record['research_id']).read_bytes()==before


def test_browser_page_upload_cannot_claim_server_direct_source(record,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:None)
    app=FastAPI();app.include_router(routes.router);client=TestClient(app)
    url=f"/assistant/xgss/research/{record['research_id']}/pages"
    before=store._path(record['research_id']).read_bytes()
    assert client.post(url,json=page().model_dump()).status_code==422
    assert store._path(record['research_id']).read_bytes()==before
    assert client.post(url,json=page(source='xgss_rendered_page',coverage='rendered_content_only').model_dump()).status_code==200


def test_expired_partial_reuses_own_budget_to_add_missing_images_without_invalidating_advice(record,monkeypatch):
    for index in range(5):
        record=store.append(record['research_id'],page(str(index),source='xgss_rendered_page',coverage='rendered_content_only'))
    pages=[page(f'新分类{i}') for i in range(3)]
    monkeypatch.setattr(direct,'_read_catalog',lambda *a,**k:response(pages,status='partial',unresolved=['图示尚未取得']))
    saved=collect(record)
    saved.update(advice={'summary':'已有建议'},analysis_revision=saved['revision'])
    saved['direct_collection']['collected_at']=(datetime.now(timezone.utc)-timedelta(seconds=61)).isoformat()
    store._write(saved);calls=[]
    def reader(*a,**kwargs):
        calls.append(kwargs)
        return response([page(f'新分类{i}',illustrations=[image()]) for i in range(3)])
    monkeypatch.setattr(direct,'_read_catalog',reader)
    fixed=collect(saved)
    assert calls[0]['max_pages']==3 and calls[0]['max_parts']==395
    assert len(fixed['pages'])==8 and fixed['revision']==saved['revision']
    assert fixed['advice']==saved['advice'] and fixed['direct_collection']['status']=='completed'
    assert all(page['illustrations'] for page in fixed['pages'][5:])
    assert [page['capture_id'] for page in fixed['pages']]==[page['capture_id'] for page in saved['pages']]


def test_expired_partial_cannot_replace_or_overflow_existing_sources(record,monkeypatch):
    for index in range(5):record=store.append(record['research_id'],page(str(index)))
    monkeypatch.setattr(direct,'_read_catalog',lambda *a,**k:response([page(f'原分类{i}') for i in range(3)],status='partial'))
    saved=collect(record)
    saved['direct_collection']['collected_at']=(datetime.now(timezone.utc)-timedelta(seconds=61)).isoformat()
    store._write(saved);before=store._path(saved['research_id']).read_bytes()
    monkeypatch.setattr(direct,'_read_catalog',lambda *a,**k:response([page(f'不同分类{i}') for i in range(3)]))
    with pytest.raises(store.EvidenceLimitError):collect(saved)
    assert store._path(saved['research_id']).read_bytes()==before


def test_expired_partial_at_full_part_budget_can_re_read_same_rows(record,monkeypatch):
    parts=[{'name':f'测试阀{i}','part_number':f'TEST-{i:03d}'} for i in range(200)]
    pages=[page(str(i),items=parts) for i in range(2)]
    monkeypatch.setattr(direct,'_read_catalog',lambda *a,**k:response(pages,status='partial'))
    saved=collect(record)
    saved['direct_collection']['collected_at']=(datetime.now(timezone.utc)-timedelta(seconds=61)).isoformat()
    store._write(saved);calls=[]
    def reader(*a,**kwargs):calls.append(kwargs);return response(pages)
    monkeypatch.setattr(direct,'_read_catalog',reader)
    fixed=collect(saved)
    assert calls[0]['max_parts']==400
    assert fixed['revision']==saved['revision'] and len(fixed['pages'])==2


@pytest.fixture
def sensor_record(record,monkeypatch):
    from app import sensor_series
    seed={'series_id':'b'*64,'hypothesis_index':0,**direct._identity(record),
          'symptom_source':'user_question','symptom':'历史连续数据：核对变矩器出口油温。',
          'evidence_ids':['trend-oil'],'search_terms':['双变系统'],
          'window':{'start':'2026-09-18T00:00:00Z','end':'2026-09-25T00:00:00Z'}}
    record.update(symptom_source=seed['symptom_source'],symptom=seed['symptom'],analysis_mode='fault',
                  fault_context={'manual_fault':None,'engineering_fault':None,'manuals':[]})
    store._write(record)
    def handoff(series_id,machine_id,dataset_id,index):
        assert (series_id,machine_id,dataset_id,index)==('b'*64,record['machine_id'],record['dataset_id'],0)
        return json.loads(json.dumps(seed))
    monkeypatch.setattr(sensor_series,'parts_handoff',handoff)
    return record,seed


def collect_sensor(record,**kwargs):
    return direct.collect(record['research_id'],direct.CollectRequest(
        expected_revision=record['revision'],terms=['双变系统'],
        sensor_context={'series_id':'b'*64,'hypothesis_index':0}),**kwargs)


def homepage_for(record):
    home=store.create(record['machine_id'],record['dataset_id'],record['vin'])
    home.update(plan={'summary':'主页历史故障'},advice={'summary':'主页已有建议与估价'},analysis_revision=0)
    store._write(home);store.activate(home['research_id'],None)
    return home


@pytest.mark.parametrize('context',[
    {},{'series_id':'b'*64},{'series_id':'b'*64,'hypothesis_index':True},
    {'series_id':'b'*64,'hypothesis_index':'0'},{'series_id':'b'*64,'hypothesis_index':0.0},
    {'series_id':'b'*64,'hypothesis_index':-1},{'series_id':'b'*63,'hypothesis_index':0},
    {'series_id':'B'*64,'hypothesis_index':0},{'series_id':64,'hypothesis_index':0},
    {'series_id':'b'*64,'hypothesis_index':0,'vin':VIN},'not-an-object'])
def test_sensor_context_schema_is_strict(context):
    with pytest.raises(ValidationError):
        direct.CollectRequest(expected_revision=0,terms=['双变系统'],sensor_context=context)


def test_sensor_collection_and_cache_preserve_homepage_active_advice_and_record(sensor_record,monkeypatch):
    record,_seed=sensor_record;home=homepage_for(record)
    before=store._path(home['research_id']).read_bytes()
    def forbidden(*a,**k):raise AssertionError('Sensor collection must never activate a research')
    monkeypatch.setattr(store,'activate',forbidden)
    saved=collect_sensor(record)
    assert len(saved['pages'])==1 and saved['direct_collection']['cached'] is False
    assert direct._active_id(saved)==home['research_id']
    monkeypatch.setattr(direct,'_read_catalog',forbidden)
    cached=collect_sensor(saved)
    assert cached['direct_collection']['cached'] is True
    assert direct._active_id(saved)==home['research_id']
    assert store._path(home['research_id']).read_bytes()==before


@pytest.mark.parametrize('field,value',[
    ('machine_id','another-machine'),('dataset_id','c'*64),('vin','XUGOTHER000000001'),
    ('series_id','c'*64),('hypothesis_index',1),('symptom_source','operator_report'),
    ('symptom','另一个传感器分析问题')])
def test_sensor_seed_identity_or_question_mismatch_never_reaches_upstream(sensor_record,monkeypatch,field,value):
    record,seed=sensor_record;homepage_for(record);seed[field]=value
    def forbidden(*a,**k):raise AssertionError('Invalid seed must not query XGSS')
    monkeypatch.setattr(direct,'_read_catalog',forbidden)
    before=store._path(record['research_id']).read_bytes()
    with pytest.raises(direct.DirectCollectionError) as failure:collect_sensor(record)
    assert failure.value.kind=='direct_sensor_context_invalid'
    assert store._path(record['research_id']).read_bytes()==before


@pytest.mark.parametrize('field,value',[
    ('symptom_source','trackunit_page'),('symptom','人为改写的风险问题'),('analysis_mode','maintenance'),
    ('fault_event_id','d'*64),('source_report_id','e'*64),('manual_fault',{}),
    ('engineering_fault',{}),('page_fault',{}),('handoff_context',{}),('catalog_fault_code','E100'),
    ('manual_fault_reference',{}),('trackunit_page',{}),('trackunit_event',{}),
    ('fault_context',{'trackunit_page':{'status':'resolved'}})])
def test_sensor_question_cannot_mix_fault_or_old_report_context(sensor_record,monkeypatch,field,value):
    record,_seed=sensor_record;record[field]=value;store._write(record)
    def forbidden(*a,**k):raise AssertionError('Conflicting evidence must not query XGSS')
    monkeypatch.setattr(direct,'_read_catalog',forbidden)
    with pytest.raises(direct.DirectCollectionError) as failure:collect_sensor(record)
    assert failure.value.kind=='direct_sensor_context_invalid'


def test_sensor_fake_series_or_stale_analysis_rejected_even_before_cached_result(sensor_record,monkeypatch):
    from app import sensor_series
    record,_seed=sensor_record;home=homepage_for(record)
    saved=collect_sensor(record);before=store._path(saved['research_id']).read_bytes()
    def stale(*a,**k):raise ValueError('No current validated analysis for this series')
    monkeypatch.setattr(sensor_series,'parts_handoff',stale)
    def forbidden(*a,**k):raise AssertionError('Stale analysis must not query XGSS')
    monkeypatch.setattr(direct,'_read_catalog',forbidden)
    with pytest.raises(direct.DirectCollectionError) as failure:collect_sensor(saved)
    assert failure.value.kind=='direct_sensor_context_invalid'
    assert direct._active_id(saved)==home['research_id']
    assert store._path(saved['research_id']).read_bytes()==before


@pytest.mark.parametrize('change',['analysis','evidence','active','record_question','invalidate'])
def test_sensor_commit_rechecks_seed_and_homepage_active_without_partial_save(sensor_record,monkeypatch,change):
    from app import sensor_series
    record,seed=sensor_record;home=homepage_for(record)
    home_before=store._path(home['research_id']).read_bytes()
    def reader(*a,**k):
        if change=='analysis':seed['symptom']='新的传感器结论'
        elif change=='evidence':seed['evidence_ids']=['different-evidence']
        elif change=='active':store.activate(record['research_id'],home['research_id'])
        elif change=='record_question':
            changed=store.read(record['research_id']);changed['symptom']='其他问题';store._write(changed)
        else:
            def stale(*args,**kwargs):raise ValueError('Saved analysis invalidated during read')
            monkeypatch.setattr(sensor_series,'parts_handoff',stale)
        return response([page(illustrations=[image()])])
    monkeypatch.setattr(direct,'_read_catalog',reader)
    with pytest.raises(direct.DirectCollectionError) as failure:collect_sensor(record)
    assert failure.value.kind in ('direct_sensor_context_invalid','direct_sensor_context_changed','direct_active_changed')
    saved=store.read(record['research_id'])
    assert saved['pages']==[] and saved['revision']==0 and 'direct_collection' not in saved
    assert not (store.STORE/'images').exists()
    assert store._path(home['research_id']).read_bytes()==home_before
    assert direct._active_id(saved)==(record['research_id'] if change=='active' else home['research_id'])
