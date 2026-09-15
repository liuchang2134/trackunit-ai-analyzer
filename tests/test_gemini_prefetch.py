import json
import pytest
from app import local_assistant as agent
from app.models import Machine
from app.gemini_client import GeminiError
from app.deepseek_client import DeepSeekError


@pytest.fixture(params=['gemini', 'deepseek'])
def cloud_data(monkeypatch, request):
    monkeypatch.setenv('AI_PROVIDER',request.param)
    monkeypatch.setattr(agent,'find_machine',lambda _:Machine(machine_id='SIM-PREFETCH',serial_number='S1',model='DEMO-EXC',
        machine_type='excavator',customer='demo',location='demo',last_seen_at='2026-09-14T00:00:00Z'))
    monkeypatch.setattr(agent,'find_telemetry',lambda _:[])
    monkeypatch.setattr(agent,'find_faults',lambda _:[])
    monkeypatch.setattr(agent,'get_data_source',lambda:'mock')


@pytest.mark.parametrize('task,expected_tools',[
    ('overview',['snapshot']),('trends',['snapshot','trends']),
    ('parts',['snapshot','faults']),('comprehensive',['snapshot','faults','trends'])])
def test_explicit_task_evidence_precedes_ai_but_parts_component_stays_model_selected(cloud_data,monkeypatch,task,expected_tools):
    calls=[]
    component_queries=[]
    def search(*args, **kwargs):
        component_queries.append(args[3])
        return []
    monkeypatch.setattr(agent,'search_parts',search)
    def step(messages,allowed,timeout_seconds):
        calls.append((messages,allowed,timeout_seconds))
        evidence=[json.loads(m['content']) for m in messages if m['role']=='user' and '"tool_result"' in m['content']]
        if len(calls)==1:
            assert [r['source_id'].split(':')[-1] for r in evidence]==expected_tools
            assert 0 < timeout_seconds <= 60
        if 'parts' in agent.required_queries(request) and 'finish' not in allowed:
            return agent.Decision(action='parts',component='turbo')
        ids=[r['source_id'] for r in evidence]
        checks=messages[-1]['_decision_options']['next_check_ids']
        return agent.Decision(action='finish',summary='模拟数据不足，目录候选仍须人工核实。',evidence_ids=ids,
            next_check_ids=[c for c in checks if c in {'check:catalog-gap','check:trend-coverage'}])
    monkeypatch.setattr(agent,'model_step',step)
    request=agent.InvestigationRequest(machine_id='SIM-PREFETCH',question='检查所选设备',task=task)
    result=agent.investigate(request)
    assert result['status']=='completed'
    assert len(calls)==(2 if task in {'parts','comprehensive'} else 1)
    assert [t['trigger'] for t in result['tool_trace'][:len(expected_tools)]]==['task_required']*len(expected_tools)
    if task in {'parts','comprehensive'}:
        assert component_queries==['turbo']
        assert result['tool_trace'][-1]['trigger']=='model_selected'


def test_prefetched_evidence_does_not_bypass_report_validation(cloud_data,monkeypatch):
    summaries=iter(['设备运行状态正常。','模拟记录不足，无法确认设备健康状态。'])
    seen=[]
    def step(messages,allowed,timeout_seconds):
        seen.append(messages)
        return agent.Decision(action='finish',summary=next(summaries),evidence_ids=['tool:1:snapshot'])
    monkeypatch.setattr(agent,'model_step',step)
    result=agent.investigate(agent.InvestigationRequest(machine_id='SIM-PREFETCH',question='设备状态',task='overview'))
    assert result['summary'].startswith('模拟') and len(seen)==2
    assert 'Unsupported affirmative health claim' in str(seen[-1])


def test_cloud_overall_deadline_prevents_further_model_requests(cloud_data,monkeypatch):
    now=[0.0]
    monkeypatch.setattr(agent.time,'monotonic',lambda:now[0])
    calls=[]
    def step(messages,allowed,timeout_seconds):
        calls.append(timeout_seconds)
        now[0]=121
        return agent.Decision(action='finish',summary='设备运行状态正常。',evidence_ids=['tool:1:snapshot'])
    monkeypatch.setattr(agent,'model_step',step)
    with pytest.raises((GeminiError, DeepSeekError),match='time limit'):
        agent.investigate(agent.InvestigationRequest(machine_id='SIM-PREFETCH',question='设备状态',task='overview'))
    assert len(calls)==1
