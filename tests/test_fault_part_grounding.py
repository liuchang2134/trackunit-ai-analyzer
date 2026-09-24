"""Counterexamples for fault/part causality; all observations are synthetic."""
import json
import pytest
from app import fault_part_grounding as gate
from app import xgss_research_ai as ai


def part(name='蓄电池', **kw):
    return dict(source_id='p1', name=name, part_number='TEST-001', reason='相关部件，待核查',
                replacement_condition='现场检查后确认实际故障点', fault_relation='direct',
                support='catalog_only', support_quote='', support_source_id=None, **kw)


def check(row=None, symptom='SPN 639 / FMI 9 总线通讯异常', source='trackunit_page', manuals=(), **extra):
    rec={'symptom':symptom, 'symptom_source':source, **extra}
    return gate.qualify({'parts':[row or part()], 'repair_steps':[], 'summary':'合成场景'},rec,manuals)


@pytest.mark.parametrize('name',['蓄电池','电源继电器','保险盒','发动机控制器','Battery'])
def test_communication_does_not_recommend_power_or_ecu_from_catalog(name):
    result=check(part(name))
    assert result['parts']==result['inspection_targets']==[]


def test_can_harness_is_inspection_not_replacement_on_fault_code_alone():
    result=check(part('CAN 线束'))
    assert not result['parts']
    assert result['inspection_targets'][0]['evidence_level']=='inspection_only'


def test_low_voltage_is_not_a_failed_battery_or_a_known_power_input_wire():
    result=check(symptom='SPN 444 / FMI 1 电压偏低')
    assert not result['parts']
    assert result['inspection_targets'][0]['part_number']=='TEST-001'


def test_catalog_neighbor_is_not_a_candidate():
    row=part(); row['fault_relation']='unmapped'
    assert not check(row,symptom='冷却液升温')['inspection_targets']


def test_applicable_manual_mapping_retains_conditional_part_with_exact_source():
    quote='E4030 总线故障：检查蓄电池的供电状态，确认损坏后按适用配置更换。'
    row=part(); row.update(support='manual_mapping',support_source_id='m1',support_quote=quote)
    result=check(row,symptom='E4030 总线通讯故障',manuals=[{'source_id':'m1','text':quote}])
    assert result['parts'][0]['evidence_level']=='conditional_candidate'


@pytest.mark.parametrize('change',['different_fault','different_component','configuration_unknown','negative_context'])
def test_manual_quote_must_link_selected_fault_and_part_without_dropping_context(change):
    quote='E4030 总线故障：检查蓄电池并核实部件是否异常。'
    if change=='different_fault':quote=quote.replace('E4030','E4040')
    if change=='different_component':quote=quote.replace('蓄电池','CAN 线束')
    manual={'source_id':'m1','text':quote}
    if change=='configuration_unknown':manual['applicability']='model_reference_only'
    if change=='negative_context':manual['text']='不要更换蓄电池。'+quote
    row=part();row.update(support='manual_mapping',support_source_id='m1',support_quote=quote)
    assert not check(row,symptom='E4030 总线通讯故障',manuals=[manual])['parts']


def test_fabricated_support_quote_is_rejected():
    row=part();row.update(support='manual_mapping',support_source_id='m1',support_quote='E4030 蓄电池')
    with pytest.raises(ValueError,match='手册原文'):
        check(row,manuals=[{'source_id':'m1','text':'实际资料只有图册名称。'}])


def test_completed_component_observation_can_qualify_but_question_cannot():
    quote='检查确认蓄电池外壳破损泄漏。'
    row=part();row.update(support='component_observation',support_quote=quote)
    assert check(row,symptom=quote,source='operator_report')['parts']
    assert not check(row,symptom='如果'+quote,source='operator_report')['parts']
    assert not check(row,symptom=quote,source='user_question')['parts']


def test_other_or_historical_machine_fault_is_not_independent_power_evidence():
    history={'faults':[{'fault_code':'SPN444/FMI1','status':'cleared','occurred_at':'2025-01-01T00:00:00Z'}]}
    result=check(machine_context=history)
    assert result['parts']==result['inspection_targets']==[]


def test_legacy_result_is_hidden_without_deleting_source_or_calling_model(monkeypatch):
    record={'revision':1,'analysis_revision':1,'advice':{'parts':[part()]},'pages':[{'content':'original'}]}
    before=json.dumps(record)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',lambda *a,**kw:pytest.fail('No billed call during restore'))
    restored=ai.normalize_cached_advice(record)
    assert 'advice' not in restored and restored['advice_needs_refresh']
    assert restored['pages']==record['pages'] and json.dumps(record)==before


@pytest.mark.parametrize('quote',[
    'SPN 639/FMI 9：核查总线线束。SPN 444/FMI 1：检查蓄电池。',
    'E4030：核查总线线束。E4040：检查蓄电池。',
])
def test_mixed_fault_paragraphs_cannot_map_neighboring_power_part(quote):
    selected='SPN 639/FMI 9 总线通讯故障' if quote.startswith('SPN') else 'E4030 总线通讯故障'
    row=part();row.update(support='manual_mapping',support_source_id='m1',support_quote=quote)
    result=check(row,symptom=selected,manuals=[{'source_id':'m1','text':quote}])
    assert not result['parts']


@pytest.mark.parametrize('address',['SA 160',''])
def test_manual_source_address_must_confirm_the_selected_node(address):
    quote=f'{address} SPN 444/FMI 1：检查蓄电池。'
    row=part();row.update(support='manual_mapping',support_source_id='m1',support_quote=quote)
    result=check(row,symptom='SPN 444/FMI 1 SA 163',manuals=[{'source_id':'m1','text':quote}])
    assert not result['parts']
    assert result['inspection_targets'][0]['evidence_level']=='inspection_only'


def test_same_fault_and_source_address_can_still_qualify_manual_mapping():
    quote='SA 163 SPN 444/FMI 1：检查蓄电池。'
    row=part();row.update(support='manual_mapping',support_source_id='m1',support_quote=quote)
    assert check(row,symptom='SPN 444/FMI 1 SA 163',manuals=[{'source_id':'m1','text':quote}])['parts']


def test_structured_selected_event_sa_cannot_be_lost_when_symptom_omits_address():
    quote='SA 160 SPN 444/FMI 1：检查蓄电池。'
    row=part();row.update(support='manual_mapping',support_source_id='m1',support_quote=quote)
    result=check(row,symptom='当前电压故障',manuals=[{'source_id':'m1','text':quote}],
                 fault_context={'trackunit_event':{'spn':444,'fmi':1,'sa':163,'status':'OPEN'}})
    assert not result['parts']
    assert result['inspection_targets']


def test_another_component_damage_in_neighboring_clause_is_not_battery_damage():
    quote='已确认线束断路，蓄电池已经检查。'
    row=part();row.update(support='component_observation',support_quote=quote)
    result=check(row,symptom=quote,source='operator_report')
    assert not result['parts']
    assert result['inspection_targets']


@pytest.mark.parametrize('history',[
    '去年已确认蓄电池损坏并已更换',
    '上次已确认蓄电池损坏，已修复',
    '已确认蓄电池损坏，故障已解除',
])
def test_historical_or_processed_component_observation_cannot_prepare_parts(history):
    quote=history+'；本次SPN 639/FMI 9总线通讯故障。'
    row=part();row.update(support='component_observation',support_quote=quote)
    assert not check(row,symptom=quote,source='operator_report')['parts']


@pytest.mark.parametrize('status',['RESOLVED','CLEARED','INACTIVE','CLOSED'])
def test_resolved_selected_event_keeps_manual_mapping_as_inspection_only(status):
    quote='E4030 总线故障：检查风扇。'
    row=part('风扇');row.update(support='manual_mapping',support_source_id='m1',support_quote=quote)
    result=check(row,symptom='E4030 总线通讯故障',manuals=[{'source_id':'m1','text':quote}],
                 fault_context={'trackunit_event':{'code':'E4030','status':status}})
    assert not result['parts']
    assert result['inspection_targets'][0]['name']=='风扇'


def test_two_character_component_observation_is_not_dropped():
    quote='实测检查确认风扇叶片断裂。'
    row=part('风扇');row.update(support='component_observation',support_quote=quote)
    assert check(row,symptom=quote,source='operator_report')['parts'][0]['name']=='风扇'


@pytest.mark.parametrize('field',['summary','repair_steps'])
def test_unqualified_replacement_cannot_bypass_empty_candidate_list_in_prose(field):
    advice={'parts':[part('CAN 线束')], 'summary':'先核查通信线路。', 'repair_steps':[]}
    if field=='summary':advice[field]='建议更换电源。'
    else:advice[field]=[{'basis':'ai_inspection_suggestion','instruction':'请采购蓄电池。'}]
    with pytest.raises(ValueError,match='尚无部件故障依据'):
        gate.qualify(advice,{'symptom':'SPN639/FMI9 总线通讯异常','symptom_source':'trackunit_page'},[])


@pytest.mark.parametrize('text',[
    '不建议更换电源，应先检查线束。',
    '不要直接更换蓄电池。',
    '仅在检查确认线束损坏后，建议更换对应线束。',
])
def test_negative_and_conditional_replacement_wording_is_preserved(text):
    advice={'parts':[part('CAN 线束')], 'summary':text, 'repair_steps':[]}
    result=gate.qualify(advice,{'symptom':'SPN639/FMI9 总线通讯异常','symptom_source':'trackunit_page'},[])
    assert result['summary']==text
    assert not result['parts']
