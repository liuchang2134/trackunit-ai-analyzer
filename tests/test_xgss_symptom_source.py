"""Source-label regressions, using only synthetic records and mocked output."""
import copy
import json
import pytest
from app import xgss_research_ai as ai,xgss_research_store as store

PLAN={'summary':'人工报告，待核实：显示通讯故障，先检查通讯相关部件。',
      'directions':[{'component':'通讯线束','reason':'按人工报告查找通讯连接部件。','search_terms':['电气系统','通讯线束']}],
      'missing_evidence':['实际故障码与现场测量']}


@pytest.mark.parametrize('field',['summary','reason'])
def test_operator_report_is_corrected_without_relabeling_as_simulation(monkeypatch,tmp_path,field):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    invalid=copy.deepcopy(PLAN)
    if field=='summary':invalid['summary']='模拟现象为显示通讯故障，属操作员报告。'
    else:invalid['directions'][0]['reason']='模拟的通讯故障需检查线束。'
    calls=[]
    def model(messages,*a,**k):
        calls.append(copy.deepcopy(messages))
        return json.dumps(invalid if len(calls)==1 else PLAN,ensure_ascii=False)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    result=ai.plan('fixture-machine',None,'XUGTEST000000001','XE80U',
        ai.Symptom(symptom='显示通讯故障',symptom_source='operator_report'))
    assert len(calls)==2
    assert '当前 symptom_source=operator_report' in calls[0][0]['content']
    assert '必须明确写“模拟”' not in calls[0][0]['content']
    assert '人工报告' in calls[1][-1]['content']
    assert result['plan']==PLAN and result['symptom_source']=='operator_report'


def test_operator_report_source_error_remains_bounded(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    invalid={**PLAN,'summary':'模拟现象为显示通讯故障。'}
    calls=[]
    def model(*a,**k):calls.append(1);return json.dumps(invalid)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    with pytest.raises(ai.ModelOutputValidationError,match='人工报告') as exc:
        ai.plan('fixture-machine',None,'XUGTEST000000001','XE80U',
            ai.Symptom(symptom='显示通讯故障',symptom_source='operator_report'))
    assert exc.value.kind=='symptom_source' and len(calls)==2
    assert not list(store.STORE.glob('*.json'))


@pytest.mark.parametrize('summary',[
    '人工报告，待核实：不是模拟场景。',
    '操作员反映通讯故障，需现场确认，并非模拟现象。',
])
def test_explicit_negation_of_simulation_is_allowed(summary):
    ai._validate_symptom_source(summary,[],'operator_report')


def test_simulation_label_is_still_required_and_can_be_corrected(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    calls=[]
    def model(messages,*a,**k):
        calls.append(messages[0]['content'])
        return json.dumps({**PLAN,'summary':'通讯故障待检查。' if len(calls)==1 else '模拟通讯故障，现场情况未知。'},ensure_ascii=False)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    result=ai.plan('fixture-machine',None,'XUGTEST000000001','XE80U',
        ai.Symptom(symptom='模拟通讯故障',symptom_source='simulation'))
    assert len(calls)==2 and '必须明确写“模拟”' in calls[0]
    assert result['plan']['summary'].startswith('模拟')


def test_question_source_does_not_require_simulation_label():
    instructions=ai._symptom_source_instructions('user_question')
    assert '用户提出的问题' in instructions and '必须明确写“模拟”' not in instructions
