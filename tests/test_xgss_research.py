"""Local synthetic fixtures only; no XGSS or model requests."""
import json
import pytest
from pydantic import ValidationError
from app import xgss_research_store as store

VIN='XUGTEST000000001'


@pytest.fixture
def research(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    return store.create('fixture-machine','a'*64,VIN)


def page(**changes):
    return store.PageCapture.model_validate(dict(source='xgss_rendered_page',source_url='https://xgss.xcmg.com/',
        vin=VIN,title='测试图册',assembly_path=['测试冷却系统'],items=[{'name':'测试散热器','part_number':'TEST-001'}],
        manual_sections=[],coverage='rendered_content_only',**changes))


def test_pages_accumulate_without_replacing_previous_evidence(research):
    first=store.append(research['research_id'],page())
    second=store.PageCapture.model_validate({**page().model_dump(),'title':'测试维修说明','items':[],
        'manual_sections':[{'title':'维修条件','text':'测试手册摘录，仅用于自动测试。'}]})
    result=store.append(research['research_id'],second)
    assert result['pages'][0]==first['pages'][0]
    assert result['revision']==2
    evidence=store.evidence(store.read(research['research_id']))
    assert len(evidence['parts'])==len(evidence['manuals'])==1
    assert evidence['parts'][0]['part_number']=='TEST-001'
    assert evidence['manuals'][0]['source_id'].startswith('xmanual:')


def test_duplicate_capture_is_idempotent(research):
    first=store.append(research['research_id'],page())
    assert store.append(research['research_id'],page())==first


def test_cross_vin_capture_does_not_mutate_sources(research):
    other=store.PageCapture.model_validate({**page().model_dump(),'vin':'XUGOTHER000000001'})
    with pytest.raises(ValueError):store.append(research['research_id'],other)
    assert store.read(research['research_id'])['pages']==[]


def test_session_url_unknown_fields_empty_capture_and_tampering_rejected(research):
    for changes in [{'source_url':'https://xgss.xcmg.com/?token=TEST'},{'cookie':'TEST'},{'items':[],'manual_sections':[]}]:
        with pytest.raises(ValidationError):store.PageCapture.model_validate({**page().model_dump(),**changes})
    stored=store.append(research['research_id'],page())
    stored['pages'][0]['content']['items'][0]['part_number']='TEST-FAKE'
    store._path(research['research_id']).write_text(json.dumps(stored),encoding='utf-8')
    with pytest.raises(ValueError):store.read(research['research_id'])


def test_bounded_pages_and_path_validation(research):
    for i in range(8):
        store.append(research['research_id'],store.PageCapture.model_validate({**page().model_dump(),'title':f'测试第{i}页'}))
    with pytest.raises(ValueError):store.append(research['research_id'],page())
    with pytest.raises(ValueError):store.read('../credentials')


def test_routes_verify_identity_and_refuse_synthetic_vehicle(research,monkeypatch):
    from fastapi import FastAPI,HTTPException
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    calls=[]
    def verify(machine,dataset,vin):
        calls.append((machine,dataset,vin))
        if machine=='synthetic':raise HTTPException(422,'fixture forbidden')
    monkeypatch.setattr(routes,'_verify_machine',verify)
    app=FastAPI();app.include_router(routes.router);client=TestClient(app)
    assert client.post('/assistant/xgss/research',json={'machine_id':'synthetic','vin':VIN}).status_code==422
    created=client.post('/assistant/xgss/research',json={'machine_id':'fixture-machine','vin':VIN})
    assert created.status_code==200 and created.headers['cache-control']=='no-store'
    rid=created.json()['research_id']
    captured=client.post(f'/assistant/xgss/research/{rid}/pages',json=page().model_dump())
    assert captured.status_code==200 and len(captured.json()['evidence']['parts'])==1
    assert client.get(f'/assistant/xgss/research/{rid}').status_code==200
    assert len(calls)==4


def test_read_and_resume_never_expose_advice_rejected_by_current_validation(research,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    record=store.append(research['research_id'],page())
    record.update(plan={'summary':'模拟计划'},advice={'summary':'invalid old advice'},analysis_revision=record['revision'])
    store._write(record)
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:None)
    def invalid(*a):raise ValueError('provider output must not be exposed')
    monkeypatch.setattr(routes.ai,'normalize_cached_advice',invalid)
    app=FastAPI();app.include_router(routes.router);client=TestClient(app)
    responses=[client.get('/assistant/xgss/research/'+record['research_id']),
        client.post('/assistant/xgss/research/latest',json={'machine_id':record['machine_id'],'dataset_id':record['dataset_id'],'vin':VIN})]
    for response in responses:
        assert response.status_code==200
        assert 'advice' not in response.json() and response.json()['advice_error']
        assert len(response.json()['evidence']['parts'])==1
        assert 'provider output' not in response.text


def test_machine_context_is_local_only_and_never_calls_ai(research,monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:None)
    monkeypatch.setattr(routes,'load_dataset',lambda *a:SimpleNamespace(telemetry=[],faults=[]))
    def unexpected(*a,**k):raise AssertionError('Local context must not invoke a cloud model')
    monkeypatch.setattr(routes.ai,'plan',unexpected)
    monkeypatch.setattr(routes.ai,'analyze',unexpected)
    app=FastAPI();app.include_router(routes.router);client=TestClient(app)
    response=client.post('/assistant/xgss/research/machine-context',json={'machine_id':research['machine_id'],'dataset_id':research['dataset_id'],'vin':VIN})
    assert response.status_code==200
    body=response.json()
    assert body['destination']=='local_only' and body['context']['source']=='imported_user_supplied'
    assert body['context']['fault_coverage']=='unknown'
    assert research['machine_id'] not in response.text and VIN not in response.text


@pytest.mark.parametrize('imported',[True,False])
def test_two_passes_use_same_server_derived_private_field_free_snapshot(research,monkeypatch,imported):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    from app.models import TelemetrySnapshot,FaultCode
    telemetry=[TelemetrySnapshot(machine_id=research['machine_id'],recorded_at='2020-01-01T12:00:00Z',
        operating_hours=123.5,latitude=12.345678,longitude=56.789012,raw_payload={'private':'SECRET_FIXTURE'})]
    faults=[FaultCode(machine_id=research['machine_id'],fault_code='FAULT-008',spn=100,fmi=4,
        description='PRIVATE_DESCRIPTION',severity='medium',status='open',occurred_at='2020-01-01T12:00:00Z')]
    machine=SimpleNamespace(model='XC948U',customer='PRIVATE_CUSTOMER',location='PRIVATE_LOCATION')
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:None)
    monkeypatch.setattr(routes,'load_dataset',lambda *a:SimpleNamespace(machine=machine,telemetry=telemetry,faults=faults))
    monkeypatch.setattr(routes,'find_machine',lambda *a:machine)
    monkeypatch.setattr(routes,'find_telemetry',lambda *a:telemetry)
    monkeypatch.setattr(routes,'find_faults',lambda *a:faults)
    sent=[]
    def model(messages,*args,**kwargs):
        payload=json.loads(messages[1]['content']);sent.append(payload)
        if 'parts' not in payload:
            return json.dumps({'summary':'模拟温升排查','directions':[{'component':'散热器','reason':'检查散热能力','search_terms':['散热器']}],'missing_evidence':['当前温度']})
        return json.dumps({'summary':'模拟温升仍需现场核实；历史记录有 FAULT-008，不能单凭工时确诊。',
            'parts':[{'source_id':payload['parts'][0]['source_id'],'reason':'实际图册候选','replacement_condition':'检查后确认'}],
            'repair_steps':[{'instruction':'核实现场现象。','basis':'ai_inspection_suggestion'}], 'missing_evidence':['当前测量']})
    monkeypatch.setattr(routes.ai,'generate_structured_with_deepseek',model)
    app=FastAPI();app.include_router(routes.router);client=TestClient(app)
    identity={'machine_id':research['machine_id'],'vin':VIN,'dataset_id':research['dataset_id'] if imported else None}
    def final(response):
        events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert events[-1]['type']=='result',events
        return events[-1]['record']
    request={**identity,'symptom':'模拟冷却液温升，需要检查。','symptom_source':'simulation'}
    assert client.post('/assistant/xgss/research/plan',json={**request,'machine_context':{'forged':True}}).status_code==422
    planned=final(client.post('/assistant/xgss/research/plan',json=request))
    rid=planned['research_id'];context=planned['machine_context']
    assert context['metrics']['operating_hours']['value']==123.5
    assert context['metrics']['operating_hours']['stale_after_24h'] is True
    assert context['metrics']['fuel_remaining_percent']['value'] is None
    assert context['source']==('imported_user_supplied' if imported else 'trackunit_cache')
    assert context['faults'][0]['fault_code']=='FAULT-008'
    client.post(f'/assistant/xgss/research/{rid}/pages',json=page().model_dump())
    telemetry[0].operating_hours=999 # Later local changes cannot rewrite the plan's evidence.
    analyzed=final(client.post(f'/assistant/xgss/research/{rid}/analyze'))
    assert analyzed['machine_context']==sent[0]['machine_context']==sent[1]['machine_context']==context
    serialized=json.dumps(sent)
    for private in [VIN,research['machine_id'],'PRIVATE_DESCRIPTION','PRIVATE_CUSTOMER','PRIVATE_LOCATION','SECRET_FIXTURE','12.345678','56.789012']:
        assert private not in serialized
    restored=client.get(f'/assistant/xgss/research/{rid}').json()
    assert restored['advice']==analyzed['advice'] and len(sent)==2



@pytest.mark.parametrize('kind',['parts','manuals'])
def test_append_capacity_is_shared_with_analysis_and_preserves_existing_advice(research,kind):
    contents=[]
    for index in range(2):
        content={**page().model_dump(),'title':f'边界资料{index}'}
        if kind=='parts':
            content['items']=[{'name':f'测试部件{i}','part_number':f'TEST-{index}-{i:03d}'} for i in range(200)]
        else:
            content.update(items=[],manual_sections=[{'title':f'测试章节{i}','text':'原'*10000} for i in range(3)])
        contents.append(content)
        current=store.append(research['research_id'],store.PageCapture.model_validate(content))
    store.validate_analysis_capacity(current['pages'])
    current.update(advice={'summary':'已有建议'},analysis_revision=current['revision'])
    store._write(current)
    before=store._path(research['research_id']).read_bytes()
    duplicate=store.append(research['research_id'],store.PageCapture.model_validate(contents[-1]))
    assert duplicate['advice']==current['advice']
    overflow={**page().model_dump(),'title':'超限资料'}
    if kind=='manuals':overflow.update(items=[],manual_sections=[{'title':'增加一字','text':'新'}])
    with pytest.raises(store.EvidenceLimitError,match='缩小检索分类并新建排查计划'):
        store.append(research['research_id'],store.PageCapture.model_validate(overflow))
    assert store._path(research['research_id']).read_bytes()==before
    assert store.read(research['research_id'])['analysis_revision']==current['revision']


def test_page_route_reports_capacity_and_preserves_saved_sources(research,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    monkeypatch.setattr(store,'MAX_ANALYSIS_PARTS',1)
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:None)
    store.append(research['research_id'],page())
    before=store._path(research['research_id']).read_bytes()
    app=FastAPI();app.include_router(routes.router)
    response=TestClient(app).post('/assistant/xgss/research/'+research['research_id']+'/pages',
                                 json={**page().model_dump(),'title':'第二页'})
    assert response.status_code==422
    assert '本页未导入' in response.json()['detail']
    assert '零件条目 2/1' in response.json()['detail']
    assert store._path(research['research_id']).read_bytes()==before


def test_legacy_over_capacity_analysis_has_actionable_stream_error_without_model(research,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    monkeypatch.setattr(store,'MAX_ANALYSIS_PARTS',1)
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:None)
    current=store.append(research['research_id'],page())
    content=store.PageCapture.model_validate({**page().model_dump(),'title':'旧记录第二页'}).model_dump()
    current['pages'].append({'capture_id':store._digest(content),'captured_at':store._now(),'content':content})
    current.update(plan={'summary':'模拟旧计划'},revision=2)
    store._write(current)
    before=store._path(research['research_id']).read_bytes()
    def unexpected(*a,**k):raise AssertionError('Over-capacity evidence must not invoke a model')
    monkeypatch.setattr(routes.ai,'generate_structured_with_deepseek',unexpected)
    app=FastAPI();app.include_router(routes.router)
    response=TestClient(app).post('/assistant/xgss/research/'+research['research_id']+'/analyze')
    events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['type']=='error' and events[-1]['kind']=='evidence_limit'
    assert '缩小检索分类并新建排查计划' in events[-1]['message']
    assert '请重试' not in events[-1]['message']
    assert store._path(research['research_id']).read_bytes()==before
    assert research['research_id'] not in routes.ai.BUSY
    # An idempotent capture of a legacy oversized record must not report success.
    with pytest.raises(store.EvidenceLimitError):store.append(research['research_id'],page())
