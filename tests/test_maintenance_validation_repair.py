"""Regressions for unknown machine type, catalog roots, and bounded AI repair."""
import copy
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import maintenance_recommendations as maintenance
from app import xgss_research_ai as ai, xgss_research_store as store
from app.api import routes_xgss_research as routes


VIN='XUGTEST000000001'
PLAN={'summary':'根据当前工时，查阅适用滤清器并核对保养记录。',
      'directions':[{'component':'滤清器','reason':'核对保养记录和滤芯状态。','search_terms':['保养','滤清器']}],
      'missing_evidence':['上次保养记录']}


@pytest.fixture
def record(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    value=store.create('fixture-machine','a'*64,VIN)
    value.update(model='Data not available',machine_type='Telescopic Truck-Mounted Crane',
                 symptom=maintenance.default_question(),symptom_source='user_question',
                 analysis_mode='maintenance',plan=copy.deepcopy(PLAN),machine_context={
                     'metrics':{'operating_hours':{'value':9.38,'observed_at':'2026-09-22T03:00:21+00:00'}}})
    store._write(value)
    return store.append(value['research_id'],store.PageCapture(
        source='xgss_rendered_page',source_url='https://xgss.xcmg.com/',vin=VIN,title='测试起重机目录',
        assembly_path=['越野轮胎起重机'],items=[{'name':'越野轮胎起重机','part_number':'TEST-001'}],
        manual_sections=[],coverage='rendered_content_only'))


def empty_advice():
    return {'summary':'当前工时9.38小时，已读取的是整机目录。请读取该设备的保养分类后筛选具体备件。',
            'parts':[],'repair_steps':[],'missing_evidence':['适用滤芯与润滑保养分类','保养周期与记录']}


def test_unknown_model_has_no_loader_assumption():
    assert '该轮式装载机' not in maintenance.PLAN_INSTRUCTIONS
    wrong=copy.deepcopy(PLAN)
    wrong['directions'][0].update(component='铲斗刃板',search_terms=['铲斗','刃板'])
    for machine_type in ('','Telescopic Truck-Mounted Crane'):
        with pytest.raises(ValueError,match='专属部件'):
            maintenance.validate_plan(wrong,model='Data not available',machine_type=machine_type)
    maintenance.validate_plan(wrong,model='XC948U',machine_type='Wheel loader')


def test_crane_directions_can_follow_explicit_type():
    plan=copy.deepcopy(PLAN)
    plan['directions'][0].update(component='吊钩',search_terms=['吊钩'])
    maintenance.validate_plan(plan,model='Data not available',machine_type='Crane')


def test_checked_catalog_part_can_support_type_without_model():
    maintenance.validate_machine_scope(['检查吊钩外观。'],parts=[{'name':'吊钩','assembly_path':['越野轮胎起重机']}])


def test_machine_type_is_frozen_and_sent_in_plan(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    seen=[]
    def model(messages,*a,**kw):
        seen.append(json.loads(messages[1]['content']))
        return json.dumps(PLAN,ensure_ascii=False)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    result=ai.plan('fixture-machine','a'*64,VIN,'Data not available',
        ai.Symptom(symptom=maintenance.default_question(),symptom_source='user_question'),
        machine_type='Crane',analysis_mode='maintenance')
    assert result['machine_type']==seen[0]['machine_type']=='Crane'
    assert VIN not in json.dumps(seen)


def test_whole_machine_is_not_recommended_and_semantic_retry_can_return_empty(record,monkeypatch):
    invalid=empty_advice()
    invalid['parts']=[{'source_id':store.evidence(record)['parts'][0]['source_id'],
        'part_role':'maintenance','reason':'保养候选','replacement_condition':'核对后更换'}]
    calls=[]
    def model(messages,schema,**kwargs):
        calls.append(copy.deepcopy(messages))
        assert 'MaintenancePartChoice' in schema['$defs']
        return json.dumps(invalid if len(calls)==1 else empty_advice(),ensure_ascii=False)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    result=ai.analyze(record['research_id'])
    assert len(calls)==2
    assert '整机目录' in calls[1][-1]['content']
    assert result['advice']['parts']==result['advice']['repair_steps']==[]
    assert ai.normalize_cached_advice(store.read(record['research_id']))['advice']==result['advice']


def test_empty_maintenance_sources_do_not_force_invented_steps(record,monkeypatch):
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',lambda *a,**k:json.dumps(empty_advice(),ensure_ascii=False))
    result=ai.analyze(record['research_id'])
    assert result['advice']['repair_steps']==[]
    assert result['advice']['parts']==[]


def test_unread_part_semantic_retry_remains_rejected_and_unsaved(record,monkeypatch):
    invalid=empty_advice()
    invalid['parts']=[{'source_id':'invented','part_role':'maintenance','reason':'候选','replacement_condition':'检查后'}]
    calls=[]
    def model(*a,**k):calls.append(1);return json.dumps(invalid)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    with pytest.raises(ai.ModelOutputValidationError,match='未读取') as failure:
        ai.analyze(record['research_id'])
    assert failure.value.kind=='source_validation'
    assert len(calls)==2
    assert 'advice' not in store.read(record['research_id'])
    assert record['research_id'] not in ai.BUSY


def test_schema_and_semantic_corrections_share_one_retry_budget(record,monkeypatch):
    calls=[]
    invalid=empty_advice();invalid['summary']='建议500h保养。'
    def model(*a,**k):calls.append(1);return '{}' if len(calls)==1 else json.dumps(invalid)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    with pytest.raises(ai.ModelOutputValidationError,match='周期') as failure:
        ai.analyze(record['research_id'])
    assert len(calls)==2 and failure.value.kind=='maintenance_interval'
    assert 'advice' not in store.read(record['research_id'])


def test_known_observation_iso_time_is_not_a_part_number(record):
    draft=empty_advice();draft['summary']='累计工时9.38h，采样于2026-09-22T03:00:21Z。'
    ai.validate_advice(ai.MaintenanceAdvice.model_validate(draft),[],[],machine_context=record['machine_context'])
    draft['summary']='核对未读取料号 FAKE-999。'
    with pytest.raises(ValueError,match='料号'):
        ai.validate_advice(ai.MaintenanceAdvice.model_validate(draft),[],[],machine_context=record['machine_context'])


@pytest.mark.parametrize('message,kind',[
    ('当前读取的是整机目录，不能作为保养备件；请继续读取下级分类。','catalog_incomplete'),
    ('机型资料不支持该专属部件，请按已确认设备类型检索。','machine_scope'),
    ('缺少适用保养周期或历史依据，不能生成量化更换周期或到期结论。','maintenance_interval'),
])
def test_sse_reports_safe_specific_validation_reason(record,monkeypatch,message,kind):
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:None)
    def fail(*a):raise ai.ModelOutputValidationError(message,kind)
    monkeypatch.setattr(ai,'analyze',fail)
    app=FastAPI();app.include_router(routes.router)
    response=TestClient(app).post('/assistant/xgss/research/'+record['research_id']+'/analyze')
    last=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')][-1]
    assert last=={'type':'error','message':message,'kind':kind}


def test_unknown_validation_reason_does_not_expose_model_content(record,monkeypatch):
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:None)
    def fail(*a):raise ValueError('PRIVATE_PROVIDER_OUTPUT_WITH_SECRET')
    monkeypatch.setattr(ai,'analyze',fail)
    app=FastAPI();app.include_router(routes.router)
    response=TestClient(app).post('/assistant/xgss/research/'+record['research_id']+'/analyze')
    assert 'PRIVATE_PROVIDER' not in response.text
    assert 'evidence_validation' in response.text
