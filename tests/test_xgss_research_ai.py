"""Synthetic unit fixtures; no external service calls."""
import json
import pytest
from app import xgss_research_ai as ai,xgss_research_store as store
from app.deepseek_client import InvestigationCancelled

VIN='XUGTEST000000001'
PLAN={'summary':'模拟冷却异常需检查散热器。','directions':[{'component':'散热器','reason':'模拟温升现象，需要检查散热能力。','search_terms':['冷却系统','散热器']}],'missing_evidence':['现场检查']}


@pytest.fixture
def prepared(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',lambda *a,**k:json.dumps(PLAN,ensure_ascii=False))
    record=ai.plan('fixture-machine','a'*64,VIN,'XC948U',ai.Symptom(symptom='模拟 SPN 110 / FMI 0 冷却液温升，需要检查。',symptom_source='simulation'))
    page=store.PageCapture(source='xgss_rendered_page',source_url='https://xgss.xcmg.com/',vin=VIN,title='测试资料',
        items=[{'name':'测试散热器','part_number':'TEST-001'}],manual_sections=[{'title':'测试检查','text':'SPN 110 / FMI 0：检查测试散热器。停止设备，待系统冷却后进行外观检查。'}],coverage='rendered_content_only')
    return store.append(record['research_id'],page)


def advice(record):
    evidence=store.evidence(record)
    return {'summary':'模拟场景下，散热器是待检查候选，并未确认损坏。',
        'parts':[{'source_id':evidence['parts'][0]['source_id'],'reason':'位于相关冷却分类','replacement_condition':'检查确认无法修复后再核对配置',
                  'fault_relation':'direct','support':'manual_mapping','support_source_id':evidence['manuals'][0]['source_id'],
                  'support_quote':'SPN 110 / FMI 0：检查测试散热器。'}],
        'repair_steps':[{'instruction':'停止设备，待系统冷却后进行外观检查。','basis':'manual_excerpt',
            'source_id':evidence['manuals'][0]['source_id'],'source_quote':'待系统冷却后进行外观检查。'}],
        'missing_evidence':['实际检查结果']}


def test_plan_and_advice_only_send_relevant_content_without_vehicle_identity(prepared,monkeypatch):
    sent=[]
    def model(messages,schema,**kwargs):
        sent.extend(messages);return json.dumps(advice(prepared),ensure_ascii=False)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    result=ai.analyze(prepared['research_id'])
    assert result['advice']['parts'][0]['part_number']=='TEST-001'
    assert result['analysis_revision']==result['revision']
    serialized=json.dumps(sent,ensure_ascii=False)
    assert VIN not in serialized and 'fixture-machine' not in serialized
    assert 'TEST-001' in serialized and '外观检查' in serialized
    # Same-source repeat reads the saved advice without another billed call.
    count=len(sent);assert ai.analyze(prepared['research_id'])==result;assert len(sent)==count


def test_unread_part_and_fabricated_manual_quote_are_rejected(prepared):
    sources=store.evidence(prepared)
    for change in ['part','quote']:
        draft=advice(prepared)
        if change=='part':draft['parts'][0]['source_id']='invented'
        if change=='quote':draft['repair_steps'][0]['source_quote']='原文没有的句子'
        with pytest.raises(ValueError):ai.validate_advice(ai.FaultAdvice.model_validate(draft),sources['parts'],sources['manuals'])


@pytest.mark.parametrize('instruction',['立即打开热机冷却系统加注盖。','扭矩调整到 100 Nm。','换装料号 FAKE-999。'])
def test_manual_instruction_is_reconstructed_from_checked_quote(prepared,instruction):
    draft=advice(prepared);draft['repair_steps'][0]['instruction']=instruction
    evidence=store.evidence(prepared)
    result=ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'])
    step=result['repair_steps'][0]
    assert step['instruction']==evidence['manuals'][0]['text']
    assert step['source_quote']==evidence['manuals'][0]['text']
    assert instruction not in json.dumps(result,ensure_ascii=False)


@pytest.mark.parametrize('code',['80354043','803540413','FAKE-999'])
@pytest.mark.parametrize('field',['summary','reason','replacement_condition','instruction','missing_evidence'])
def test_unread_catalog_codes_cannot_enter_free_text(prepared,code,field):
    draft=advice(prepared);text=f'建议核对部件 {code}。'
    if field=='summary':draft['summary']=text
    elif field in ('reason','replacement_condition'):draft['parts'][0][field]=text
    elif field=='missing_evidence':draft['missing_evidence']=[text]
    else:draft['repair_steps']=[{'instruction':text,'basis':'ai_inspection_suggestion'}]
    evidence=store.evidence(prepared)
    with pytest.raises(ValueError,match='料号'):
        ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'])


def test_catalog_codes_and_original_model_fault_codes_and_dimensions_are_allowed(prepared):
    draft=advice(prepared)
    draft['summary']='模拟 XC-948U 出现原始故障 E4030、FAULT-008，需要核对。'
    draft['parts'][0]['reason']='核对资料中的料号 TEST-001，图中螺栓尺寸为 M10×25 mm。'
    draft['parts'][0]['replacement_condition']='需区分尺寸 20-30 mm 与 100000000 Pa 的单位含义。'
    evidence=store.evidence(prepared)
    result=ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'],
        model='XC-948U',symptom='模拟现场上报 E4030、FAULT-008。')
    assert result['summary']==draft['summary']
    assert result['parts'][0]['reason']==draft['parts'][0]['reason']


@pytest.mark.parametrize('claim',['料号：E4030','物料编码 FAULT-008','part number XC-948U','料号为 E4030','part number is XC-948U'])
def test_known_context_code_cannot_be_relabelled_as_a_part_number(prepared,claim):
    draft=advice(prepared);draft['parts'][0]['reason']=claim
    evidence=store.evidence(prepared)
    with pytest.raises(ValueError,match='料号'):
        ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'],
            model='XC-948U',symptom='原始故障码 E4030、FAULT-008。')


@pytest.mark.parametrize('fault',['SPN444/FMI1','SPN 444/FMI 1','SPN 444 / FMI 1','SPN444-FMI1','spn:444 / fmi:1'])
def test_existing_j1939_pair_formatting_is_not_an_unread_part_number(prepared,fault):
    draft=advice(prepared);draft['summary']=f'页面观察 {fault}（SA 163），需检查供电。'
    evidence=store.evidence(prepared)
    checked=ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'],
        symptom='Trackunit 页面显示 SPN 444 / FMI 1，SA 163。')
    assert checked['summary']==draft['summary']


@pytest.mark.parametrize('context',[{'machine_context':{'faults':[{'fault_code':'SPN 444 / FMI 1'}]}},
    {'fault_context':{'trackunit_event':{'code':None,'spn':444,'fmi':1,'sa':163}}}])
def test_existing_j1939_pair_can_come_from_loaded_fault_evidence(prepared,context):
    draft=advice(prepared);draft['parts'][0]['reason']='SPN444/FMI1 是已有故障，TEST-001 为已读图册料号。'
    evidence=store.evidence(prepared)
    checked=ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'],**context)
    assert checked['parts'][0]['part_number']=='TEST-001'


@pytest.mark.parametrize('fault',['SPN445/FMI1','SPN444/FMI2','SPN 444 / FMI 2','SPN444/FMI1-FAKE999','SPN444/FMI1/FAKE-999'])
def test_j1939_formatting_exception_does_not_authorize_new_faults_or_suffix_codes(prepared,fault):
    draft=advice(prepared);draft['summary']=f'需核对 {fault}。'
    evidence=store.evidence(prepared)
    with pytest.raises(ValueError,match='料号'):
        ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'],symptom='SPN 444 / FMI 1。')


def test_j1939_pairs_cannot_be_recombined_across_separate_input_faults(prepared):
    draft=advice(prepared);draft['summary']='检查 SPN444/FMI3。'
    evidence=store.evidence(prepared)
    with pytest.raises(ValueError,match='料号'):
        ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'],
            symptom='SPN 444 / FMI 1；SPN 2664 / FMI 3。')


@pytest.mark.parametrize('claim',['料号 SPN444/FMI1','订购料号 SPN 444/FMI 1','part number SPN 444 / FMI 1'])
def test_existing_j1939_fault_cannot_be_declared_as_orderable_part(prepared,claim):
    draft=advice(prepared);draft['parts'][0]['reason']=claim
    evidence=store.evidence(prepared)
    with pytest.raises(ValueError,match='声明了未读取的料号'):
        ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'],symptom='SPN 444 / FMI 1。')


def test_projected_fault_code_is_context_not_a_part_number(prepared):
    draft=advice(prepared);draft['summary']='模拟场景，历史记录含 FAULT-008，需现场核实。'
    evidence=store.evidence(prepared);context={'faults':[{'fault_code':'FAULT-008'}]}
    checked=ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'],machine_context=context)
    assert checked['summary']==draft['summary']
    draft['parts'][0]['reason']='订购料号 FAULT-008。'
    with pytest.raises(ValueError,match='料号'):
        ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'],machine_context=context)


def test_catalog_name_specification_can_be_discussed_but_is_not_a_material_code(prepared):
    evidence=store.evidence(prepared)
    evidence['parts'][0]['name']='3/4npt-M14接头'
    draft=advice(prepared);draft['parts'][0]['reason']='需核对 3/4npt-M14 接头的实际配置。'
    checked=ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'])
    assert checked['parts'][0]['reason']==draft['parts'][0]['reason']
    draft['parts'][0]['reason']='建议订购料号 3/4npt-M14。'
    with pytest.raises(ValueError,match='料号'):
        ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'])


def test_inspection_suggestion_cannot_claim_a_manual_reference(prepared):
    draft=advice(prepared);draft['repair_steps'][0]['basis']='ai_inspection_suggestion'
    evidence=store.evidence(prepared)
    with pytest.raises(ValueError):ai.validate_advice(ai.FaultAdvice.model_validate(draft),evidence['parts'],evidence['manuals'])


def test_changed_sources_cannot_receive_advice_from_older_revision(prepared,monkeypatch):
    def model(*args,**kwargs):
        page=store.PageCapture.model_validate({**prepared['pages'][0]['content'],'title':'新增测试资料'})
        store.append(prepared['research_id'],page)
        return json.dumps(advice(prepared),ensure_ascii=False)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    with pytest.raises(ValueError,match='更新'):ai.analyze(prepared['research_id'])
    assert 'advice' not in store.read(prepared['research_id'])
    assert prepared['research_id'] not in ai.BUSY


def test_cancellation_prevents_saved_recommendation(prepared,monkeypatch):
    def cancelled():raise InvestigationCancelled()
    monkeypatch.setattr(ai,'_check_cancelled',cancelled)
    with pytest.raises(InvestigationCancelled):ai.analyze(prepared['research_id'])
    assert 'advice' not in store.read(prepared['research_id'])
    assert prepared['research_id'] not in ai.BUSY


def test_plan_sanitizes_vin_machine_and_signed_url(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research');sent=[]
    def model(messages,*args,**kwargs):sent.extend(messages);return json.dumps(PLAN,ensure_ascii=False)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    ai.plan('fixture-machine',None,VIN,'XC948U',ai.Symptom(symptom=f'模拟现象 {VIN} fixture-machine https://xgss.xcmg.com/?token=SECRET',symptom_source='simulation'))
    content=json.dumps(sent)
    assert VIN not in content and 'fixture-machine' not in content and 'SECRET' not in content


def test_new_capture_invalidates_old_advice(prepared,monkeypatch):
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',lambda *a,**k:json.dumps(advice(prepared),ensure_ascii=False))
    analyzed=ai.analyze(prepared['research_id'])
    assert 'advice' in analyzed
    duplicate=store.append(prepared['research_id'],store.PageCapture.model_validate(prepared['pages'][0]['content']))
    assert 'advice' in duplicate
    updated=store.append(prepared['research_id'],store.PageCapture.model_validate({**prepared['pages'][0]['content'],'title':'补充图册'}))
    assert 'advice' not in updated and 'analysis_revision' not in updated


def test_schema_correction_is_bounded_and_keeps_original_sources(prepared,monkeypatch):
    calls=[]
    draft=advice(prepared);draft['parts']*=7
    def model(messages,*a,**k):
        calls.append(list(messages))
        return json.dumps(draft if len(calls)==1 else advice(prepared),ensure_ascii=False)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    result=ai.analyze(prepared['research_id'])
    assert len(calls)==2 and len(result['advice']['parts'])==1
    assert 'too_long' in calls[1][-1]['content']


def test_schema_correction_stops_after_one_retry(prepared,monkeypatch):
    calls=[]
    def model(*a,**k):calls.append(1);return '{}'
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    with pytest.raises(ai.ValidationError):ai.analyze(prepared['research_id'])
    assert len(calls)==2 and 'advice' not in store.read(prepared['research_id'])


def test_resume_requires_exact_device_dataset_and_vin(prepared):
    args=(prepared['machine_id'],prepared['dataset_id'],prepared['vin'])
    assert store.latest(*args)['research_id']==prepared['research_id']
    assert store.latest('other',args[1],args[2]) is None
    assert store.latest(args[0],'b'*64,args[2]) is None
    assert store.latest(args[0],args[1],'OTHERVIN00000') is None


def test_old_cached_advice_is_normalized_without_mutation_or_model_call(prepared,monkeypatch):
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',lambda *a,**k:json.dumps(advice(prepared),ensure_ascii=False))
    cached=ai.analyze(prepared['research_id'])
    cached['advice']['repair_steps'][0]['instruction']='立即打开热机冷却系统加注盖。'
    cached['advice']['parts'][0]['part_number']='FAKE-999'
    before=json.dumps(cached,ensure_ascii=False,sort_keys=True)
    checked=ai.normalize_cached_advice(cached)
    assert json.dumps(cached,ensure_ascii=False,sort_keys=True)==before
    assert checked['advice']['parts'][0]['part_number']=='TEST-001'
    assert checked['advice']['repair_steps'][0]['instruction']==checked['advice']['repair_steps'][0]['source_quote']
    store._write(cached)
    def unexpected(*a,**k):raise AssertionError('Cached validation must not call DeepSeek')
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',unexpected)
    assert ai.analyze(prepared['research_id'])==checked


def test_cached_unknown_part_claim_is_rejected_without_another_model_call(prepared,monkeypatch):
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',lambda *a,**k:json.dumps(advice(prepared),ensure_ascii=False))
    cached=ai.analyze(prepared['research_id'])
    cached['advice']['parts'][0]['reason']='订购料号 FAKE-999。'
    store._write(cached)
    def unexpected(*a,**k):raise AssertionError('Invalid cache must not trigger a billed retry')
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',unexpected)
    with pytest.raises(ValueError,match='料号'):ai.normalize_cached_advice(cached)
    with pytest.raises(ValueError,match='料号'):ai.analyze(prepared['research_id'])


def test_cached_long_official_excerpt_and_stale_revision(prepared):
    quote='停止设备，待系统冷却后进行外观检查。'*45
    content={**prepared['pages'][0]['content'],'manual_sections':[{'title':'长原文测试','text':quote}]}
    current=store.append(prepared['research_id'],store.PageCapture.model_validate(content))
    sources=store.evidence(current)
    draft=advice(current)
    draft['repair_steps'][0].update(source_id=sources['manuals'][-1]['source_id'],source_quote=quote)
    checked=ai.validate_advice(ai.FaultAdvice.model_validate(draft),sources['parts'],sources['manuals'])
    cached={**current,'advice':checked,'analysis_revision':current['revision'],'advice_quality_version':ai.grounding.VERSION}
    assert len(quote)>700 and ai.normalize_cached_advice(cached)['advice']['repair_steps'][0]['instruction']==quote
    assert 'advice' not in ai.normalize_cached_advice({**cached,'analysis_revision':0})



def test_partial_manual_quote_cannot_remove_prohibition_in_fresh_or_cached_advice(prepared,monkeypatch):
    original='严禁打开热机冷却系统加注盖。必须停机并等待系统冷却。'
    unsafe_quote='打开热机冷却系统加注盖。'
    content={**prepared['pages'][0]['content'],'title':'含完整约束的手册',
             'manual_sections':[{'title':'安全检查条件','text':original}]}
    current=store.append(prepared['research_id'],store.PageCapture.model_validate(content))
    draft=advice(current)
    draft['repair_steps'][0].update(source_id=store.evidence(current)['manuals'][-1]['source_id'],
                                   instruction=unsafe_quote,source_quote=unsafe_quote)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',lambda *a,**k:json.dumps(draft,ensure_ascii=False))
    fresh=ai.analyze(current['research_id'])
    step=fresh['advice']['repair_steps'][0]
    assert step['instruction']==step['source_quote']==original
    # The same normalization protects older records containing a partial quote.
    step.update(instruction=unsafe_quote,source_quote=unsafe_quote)
    store._write(fresh)
    def unexpected(*a,**k):raise AssertionError('Cached source correction must not call a model')
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',unexpected)
    restored=ai.analyze(current['research_id'])['advice']['repair_steps'][0]
    assert restored['instruction']==restored['source_quote']==original


def test_complete_manual_section_above_model_excerpt_length_can_be_cached(prepared,monkeypatch):
    original='严禁打开热机冷却系统加注盖。必须停机并等待系统冷却。'*100
    assert 1500<len(original)<=10000
    content={**prepared['pages'][0]['content'],'title':'长手册上下文',
             'manual_sections':[{'title':'完整操作条件','text':original}]}
    current=store.append(prepared['research_id'],store.PageCapture.model_validate(content))
    draft=advice(current)
    draft['repair_steps'][0].update(source_id=store.evidence(current)['manuals'][-1]['source_id'],
                                   instruction='等待系统冷却。',source_quote='必须停机并等待系统冷却。')
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',lambda *a,**k:json.dumps(draft,ensure_ascii=False))
    fresh=ai.analyze(current['research_id'])
    assert fresh['advice']['repair_steps'][0]['instruction']==original
    assert ai.normalize_cached_advice(store.read(current['research_id']))['advice']==fresh['advice']
