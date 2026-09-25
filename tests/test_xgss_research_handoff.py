"""Continuation uses immutable local fixtures; no API credentials or model calls."""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app import investigation_history as history, manual_knowledge as knowledge
from app import xgss_research_handoff as handoff, xgss_research_ai as ai, xgss_research_store as store
from app.api import routes_xgss_research as routes

IDENTITY={'machine_id':'fixture-machine','dataset_id':'a'*64,'vin':'XUGTEST000000001'}
FAULT={'code':'E4030','model':'XE55U','configuration':'XE55U.00III','source':'test'}
TEXT='停机并按适用手册检查线束连接器是否松脱。不得把外观检查当作电气测量。'
REFERENCE={'reference_id':'manual:fixture-iii','title':'合成测试手册','model':'XE55U',
    'configuration':'XE55U.00III','version':'fixture-v1','pdf_pages':[2],'section':'连接器检查',
    'text':TEXT,'source_url':'https://example.org/manual.pdf?token=PRIVATE_TOKEN',
    'provenance':{'local_path':'PRIVATE_PATH','secret':'PRIVATE_CREDENTIAL'},'fault_codes':['E4030'],
    'applicability':'configuration_selected_unverified'}


@pytest.fixture
def setup(monkeypatch,tmp_path):
    monkeypatch.setattr(history,'HISTORY_DIR',tmp_path/'history')
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    manual_path=tmp_path/'manuals.json'
    manual_path.write_text(json.dumps({'schema_version':1,'records':[REFERENCE]}),encoding='utf-8')
    monkeypatch.setattr(knowledge,'KNOWLEDGE_PATH',manual_path)
    machine=SimpleNamespace(model='XE55U')
    monkeypatch.setattr(routes,'load_dataset',lambda dataset:SimpleNamespace(machine=machine,telemetry=[],faults=[]))
    monkeypatch.setattr(routes,'find_machine',lambda machine_id:machine)
    def verify(machine_id,dataset_id,vin):
        if (machine_id,dataset_id,vin)!=(IDENTITY['machine_id'],IDENTITY['dataset_id'],IDENTITY['vin']):
            raise HTTPException(422,'fixture identity mismatch')
    monkeypatch.setattr(routes,'_verify_machine',verify)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',lambda *a,**k:pytest.fail('Unexpected model transport'))
    app=FastAPI();app.include_router(routes.router)
    return TestClient(app),machine


def saved_report(*,question='测试 E4030，需要先检查哪些部件？',fault=FAULT,request_changes=None,report_changes=None):
    request={**{key:IDENTITY[key] for key in ('machine_id','dataset_id')},'question':question,'engineering_fault':fault}
    report={'status':'completed','machine_id':IDENTITY['machine_id'],'dataset_id':IDENTITY['dataset_id'],
        'source':'imported_user_supplied','generated_at':'2026-09-22T04:00:00Z','summary':'AI 摘要绝不能代替用户问题',
        'manual_references':[REFERENCE] if fault else [],'evidence':{REFERENCE['reference_id']:REFERENCE} if fault else {},
        'citations':[REFERENCE['reference_id'],'operator:engineering-fault','missing:reference'],
        'component_hypotheses':[{'component':'线束连接器','rationale':'按原手册先检查线束连接状态。',
            'reference_ids':[REFERENCE['reference_id']],'search_terms':['线束','连接器'],
            'checks':[{'text':'检查连接器是否松脱','evidence_ids':[REFERENCE['reference_id']],'source_quote':TEXT}],
            'secret':'PRIVATE_HYPOTHESIS','ranked_parts':[{'part_number':'OLD-999'}]}] if fault else [],
        'parts_candidates':[{'part_number':'OLD-999'}],'secret':'PRIVATE_REPORT'}
    request.update(request_changes or {});report.update(report_changes or {})
    return history.save_investigation(report,request)


def handoff_body(saved):
    return {**IDENTITY,'source_report_id':saved['record_id']}


def plan_body(client,saved):
    response=client.post('/assistant/xgss/research/handoff',json=handoff_body(saved))
    assert response.status_code==200,response.text
    carried=response.json()
    return {**IDENTITY,**{key:carried[key] for key in ('source_report_id','symptom','symptom_source','manual_fault','engineering_fault')}}


def final_record(response):
    assert response.status_code==200,response.text
    events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['type']=='result',events
    return events[-1]['record']


def test_handoff_uses_original_question_and_only_valid_hypotheses_and_sources(setup):
    client,_=setup;saved=saved_report()
    result=client.post('/assistant/xgss/research/handoff',json=handoff_body(saved))
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    carried=result.json()
    assert carried['symptom']==saved['request']['question']
    assert carried['symptom_source']=='simulation' and carried['catalog_fault_code']=='E4030'
    context=carried['handoff_context']
    assert context['prior_analysis']['summary']==saved['report']['summary']
    assert context['prior_analysis']['provenance']=='prior_ai_inference'
    assert context['component_hypotheses'][0]['search_terms']==['线束','连接器']
    assert context['manuals'][0]['captured_at']==saved['report']['generated_at']
    assert context['manuals'][0]['source_kind']=='source_report_manual'
    assert 'missing:reference' not in context['citations']
    text=json.dumps(carried,ensure_ascii=False)
    for prohibited in ('PRIVATE_PATH','PRIVATE_CREDENTIAL','PRIVATE_TOKEN','PRIVATE_HYPOTHESIS','PRIVATE_REPORT','OLD-999'):
        assert prohibited not in text


@pytest.mark.parametrize('fault',[None,{**FAULT,'source':'operator_report'}])
def test_handoff_labels_questions_as_questions_not_observed_faults(setup,fault):
    client,_=setup;saved=saved_report(question='为什么？',fault=fault)
    carried=client.post('/assistant/xgss/research/handoff',json=handoff_body(saved)).json()
    assert carried['symptom']=='为什么？' and carried['symptom_source']=='user_question'
    assert routes.PlanRequest.model_validate({**IDENTITY,**{key:carried[key] for key in ('symptom','symptom_source')}})


@pytest.mark.parametrize('side,change',[
    ('request',{'dataset_id':'b'*64}),('report',{'dataset_id':'b'*64}),
    ('request',{'machine_id':'other'}),('report',{'machine_id':'other'})])
def test_handoff_rejects_any_request_or_report_identity_mismatch(setup,side,change):
    client,_=setup
    # Save a coherent completed fixture, then write another correctly hashed
    # historical record to exercise both identity checks without bypassing integrity.
    saved=saved_report();document={key:saved[key] for key in ('schema_version','request','report')}
    document[side].update(change)
    import hashlib
    content=json.dumps(document,ensure_ascii=False,sort_keys=True);record_id=hashlib.sha256(content.encode()).hexdigest()
    (history.HISTORY_DIR/(record_id+'.json')).write_text(content,encoding='utf-8')
    assert client.post('/assistant/xgss/research/handoff',json={**IDENTITY,'source_report_id':record_id}).status_code==422


def test_unfinished_tampered_or_foreign_manual_reports_cannot_be_continued(setup):
    client,_=setup;saved=saved_report()
    path=history.HISTORY_DIR/(saved['record_id']+'.json');path.write_text('{}',encoding='utf-8')
    assert client.post('/assistant/xgss/research/handoff',json=handoff_body(saved)).status_code==422
    wrong={**REFERENCE,'configuration':'XE55U.00VI'}
    saved=saved_report(report_changes={'manual_references':[wrong],'evidence':{wrong['reference_id']:wrong}})
    assert client.post('/assistant/xgss/research/handoff',json=handoff_body(saved)).status_code==422
    saved=saved_report();document={key:saved[key] for key in ('schema_version','request','report')};document['report']['status']='failed'
    import hashlib
    content=json.dumps(document,ensure_ascii=False,sort_keys=True);rid=hashlib.sha256(content.encode()).hexdigest()
    (history.HISTORY_DIR/(rid+'.json')).write_text(content,encoding='utf-8')
    assert client.post('/assistant/xgss/research/handoff',json={**IDENTITY,'source_report_id':rid}).status_code==422


def test_plan_reloads_history_and_rejects_forged_or_changed_context_before_model(setup):
    client,_=setup;body=plan_body(client,saved_report())
    for changed in ({'handoff_context':{'component_hypotheses':['forged']}},
                    {'symptom':'另一设备的新问题'}, {'symptom_source':'operator_report'},
                    {'engineering_fault':{**FAULT,'code':'E4999'}}):
        assert client.post('/assistant/xgss/research/plan',json={**body,**changed}).status_code==422
    path=history.HISTORY_DIR/(body['source_report_id']+'.json');path.write_text('{}',encoding='utf-8')
    assert client.post('/assistant/xgss/research/plan',json=body).status_code==422


def test_context_is_frozen_across_model_passes_and_inherited_parts_are_not_candidates(setup,monkeypatch):
    client,_=setup;saved=saved_report(question=f"测试 E4030 {IDENTITY['vin']} fixture-machine https://example.org/?token=HIDDEN_QUERY_TOKEN")
    body=plan_body(client,saved);sent=[]
    def model(messages,*args,**kwargs):
        data=json.loads(messages[1]['content']);sent.append(data)
        if 'parts' not in data:
            return json.dumps({'summary':'模拟故障仍须现场检查。','directions':[{'component':'连接器','reason':'沿用原报告检查方向。','search_terms':['连接器']}],'missing_evidence':[]})
        return json.dumps({'summary':'模拟故障下的条件性候选。','parts':[{'source_id':data['parts'][0]['source_id'],
            'fault_relation':'direct','support':'catalog_only',
            'reason':'本次图册实际条目。','replacement_condition':'现场确认损坏并核对配置后。'}],
            'repair_steps':[{'instruction':'检查连接器。','basis':'manual_excerpt','source_id':REFERENCE['reference_id'],'source_quote':TEXT}],
            'missing_evidence':[]})
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    planned=final_record(client.post('/assistant/xgss/research/plan',json=body))
    assert planned['source_report_id']==saved['record_id'] and planned['engineering_fault']==FAULT
    assert planned['catalog_fault_code']=='E4030'
    rid=planned['research_id']
    page=store.PageCapture(source='xgss_rendered_page',source_url='https://xgss.xcmg.com/',vin=IDENTITY['vin'],title='合成图册',
        items=[{'name':'线束','part_number':'NEW-001'}],coverage='rendered_content_only')
    response=client.post(f'/assistant/xgss/research/{rid}/pages',json=page.model_dump())
    assert response.status_code==200
    # Frozen sources survive later source-library edits; analysis is not a new
    # read of the mutable library and cannot swap the cited version.
    knowledge.KNOWLEDGE_PATH.write_text(json.dumps({'schema_version':1,'records':[]}),encoding='utf-8')
    analyzed=final_record(client.post(f'/assistant/xgss/research/{rid}/analyze'))
    assert sent[0]['handoff_context']==sent[1]['handoff_context']
    assert sent[0]['fault_context']==sent[1]['fault_context']
    assert analyzed['advice']['parts']==[]
    assert analyzed['advice']['inspection_targets'][0]['part_number']=='NEW-001'
    assert analyzed['advice']['repair_steps'][0]['instruction']==TEXT
    assert len(analyzed['pages'])==1 and len(analyzed['evidence']['manuals'])==1
    assert analyzed['evidence']['manuals'][0]['source_id']==REFERENCE['reference_id']
    assert client.get(f'/assistant/xgss/research/{rid}').json()['advice']==analyzed['advice']
    serialized=json.dumps(sent)
    for forbidden in ('XUGTEST000000001','fixture-machine','HIDDEN_QUERY_TOKEN','PRIVATE_CREDENTIAL','PRIVATE_TOKEN','OLD-999'):
        assert forbidden not in serialized
    sources=ai.research_evidence(analyzed)
    invalid=ai.Advice.model_validate({'summary':'模拟检查','parts':[{'source_id':'old-report-part','reason':'old','replacement_condition':'old'}],
        'repair_steps':[{'basis':'ai_inspection_suggestion','instruction':'核实现场现象。'}],'missing_evidence':[]})
    with pytest.raises(ValueError,match='未读取的备件'):
        ai.validate_advice(invalid,sources['parts'],sources['manuals'])


@pytest.mark.parametrize('changes',[
    {'engineering_fault':{**FAULT,'model':'XE99U'}},
    {'manual_fault':{'code':'H10101','model':'TV12U','version':'260224','applicability_confirmed':True}},
    {'engineering_fault':FAULT,'manual_fault':{'code':'H10101','model':'TV12U','version':'260224','applicability_confirmed':True}},
    {'engineering_fault':FAULT,'symptom_source':'operator_report'},
])
def test_direct_fault_context_rejects_wrong_model_mutual_inputs_and_lost_test_provenance(setup,changes):
    client,_=setup
    body={**IDENTITY,'symptom':'模拟新现象，需要核对。','symptom_source':'simulation',**changes}
    assert client.post('/assistant/xgss/research/plan',json=body).status_code==422


def test_unknown_configuration_keeps_reference_scope_and_does_not_send_catalog_code(setup):
    context=handoff.validate_fault_context('XE55U',engineering_fault={**FAULT,'configuration':'unknown'})
    assert context['catalog_fault_code'] is None
    assert context['fault_context']['manuals'][0]['applicability']=='model_reference_only'
    draft=ai.Advice.model_validate({'summary':'模拟检查','parts':[],
        'repair_steps':[{'basis':'manual_excerpt','instruction':'检查。','source_id':REFERENCE['reference_id'],'source_quote':TEXT}],
        'missing_evidence':[]})
    with pytest.raises(ValueError,match='配置'):
        ai.validate_advice(draft,[],context['fault_context']['manuals'],fault_context=context['fault_context'])


def test_valid_tv12u_context_uses_existing_definition_check_and_projects_no_source_paths(setup,monkeypatch):
    seen=[]
    def validate(manual,model):
        seen.append((manual.code,model))
        return {'method':'operator_code_reference_v1','code':manual.code,'model':model,'version':manual.version,
            'reference_id':'tv12u-fixture','observation_source':'unverified_operator_report','definition':{'code':manual.code,'description':'测试定义','secret':'DO_NOT_SEND'},
            'source':{'file_name':'PRIVATE_PATH'},'limitations':['人工报告，待核实。']}
    monkeypatch.setattr(handoff,'manual_fault_evidence',validate)
    result=handoff.validate_fault_context('TV12U',manual_fault={'code':'H10101','model':'TV12U','version':'260224','applicability_confirmed':True})
    assert seen==[('H10101','TV12U')] and result['catalog_fault_code']=='H10101'
    assert 'DO_NOT_SEND' not in json.dumps(result) and 'PRIVATE_PATH' not in json.dumps(result)


def test_active_route_is_explicit_scoped_and_compare_and_swap(setup):
    client,_=setup
    assert client.post('/assistant/xgss/research/active',json=IDENTITY).status_code==404
    first=store.create(IDENTITY['machine_id'],IDENTITY['dataset_id'],IDENTITY['vin'])
    second=store.create(IDENTITY['machine_id'],IDENTITY['dataset_id'],IDENTITY['vin'])
    for record in (first,second):
        record['plan']={'summary':'合成测试计划','directions':[]};store._write(record)
    assert client.post('/assistant/xgss/research/active',json=IDENTITY).status_code==404,'latest is not implicitly active'
    body={**IDENTITY,'expected_research_id':None}
    assert client.post(f"/assistant/xgss/research/{first['research_id']}/activate",json=body).status_code==200
    assert client.post('/assistant/xgss/research/active',json=IDENTITY).json()['research_id']==first['research_id']
    assert client.post(f"/assistant/xgss/research/{second['research_id']}/activate",json=body).status_code==409
    assert client.post(f"/assistant/xgss/research/{second['research_id']}/activate",json={**body,'expected_research_id':first['research_id']}).status_code==200
    assert client.post(f"/assistant/xgss/research/{second['research_id']}/activate",json={**body,'vin':'XUGOTHER000000001'}).status_code==422


def test_inherited_long_manual_keeps_complete_conditions_when_advice_is_restored(setup):
    manual=handoff.manual_projection({**REFERENCE,'text':TEXT+'条件原文。'*2300})
    record=store.create(IDENTITY['machine_id'],IDENTITY['dataset_id'],IDENTITY['vin'])
    record.update(model='XE55U',symptom='模拟 E4030 排查',symptom_source='simulation',fault_context={'manuals':[manual]},
        advice={'summary':'模拟方向待核实','parts':[],
            'repair_steps':[{'basis':'manual_excerpt','source_id':manual['source_id'],'source_quote':TEXT,'instruction':'待校验'}],
            'missing_evidence':[]},analysis_revision=record['revision'],advice_quality_version=ai.grounding.VERSION)
    restored=ai.normalize_cached_advice(record)
    assert len(restored['advice']['repair_steps'][0]['source_quote'])>10000
    assert ai.normalize_cached_advice(restored)['advice']['repair_steps'][0]['source_quote']==manual['text']


def test_ordinary_report_carries_prior_ai_judgement_without_inventing_manuals_or_inheriting_part_numbers(setup):
    client,machine=setup;machine.model='XC948U'
    saved=saved_report(question='需要优先排查哪里？',fault=None,report_changes={
        'summary':'原 AI 判断散热器为待检查方向，仍需确认。',
        'citations':['snapshot:fixture','missing:reference'],
        'evidence':{'snapshot:fixture':{'temperature':None,'secret':'PRIVATE_EVIDENCE'}},
        'parts_candidates':[{'name':'散热器','part_number':'OLD-999','source_url':'https://example.org/?token=PRIVATE'}]})
    carried=client.post('/assistant/xgss/research/handoff',json=handoff_body(saved)).json()
    assert carried['symptom']==saved['request']['question'] and carried['symptom_source']=='user_question'
    prior=carried['handoff_context']['prior_analysis']
    assert prior['summary']==saved['report']['summary'] and prior['provenance']=='prior_ai_inference'
    assert prior['citations']==['snapshot:fixture'] and prior['citation_scope']=='source_report_only_not_current_catalog'
    assert prior['directions']==[{'component':'散热器','search_terms':['散热器'],'provenance':'prior_ai_inference'}]
    assert carried['handoff_context']['manuals']==carried['fault_context']['manuals']==[]
    text=json.dumps(carried,ensure_ascii=False)
    assert 'OLD-999' not in text and 'PRIVATE' not in text
