import pytest
from app import local_assistant as agent
from app.models import Machine
from app.ollama_client import OllamaError


@pytest.fixture(autouse=True)
def evidence(monkeypatch):
    monkeypatch.setattr(agent, "find_machine", lambda _: Machine(machine_id="D1", serial_number="S1", model="DEMO-EXC", machine_type="excavator", customer="demo", location="demo", last_seen_at="2026-06-02T12:00:00Z"))
    monkeypatch.setattr(agent, "find_telemetry", lambda _: [])
    monkeypatch.setattr(agent, "find_faults", lambda _: [])
    monkeypatch.setattr(agent, "get_data_source", lambda: "mock")


def test_tool_loop_and_sources(monkeypatch):
    responses = iter([agent.Decision(action="snapshot"), agent.Decision(action="faults"),
        agent.Decision(action="parts"), agent.Decision(action="finish", summary="数据不足，无法确认故障", evidence_ids=["tool:1:snapshot", "tool:3:parts"], next_check_ids=["check:snapshot"])])
    monkeypatch.setattr(agent, "model_step", lambda *args: next(responses))
    monkeypatch.setattr(agent, "search_parts", lambda *a, **kw: [])
    result = agent.investigate(agent.InvestigationRequest(machine_id="D1", question="检查故障"))
    assert [t["action"] for t in result["tool_trace"]] == ["snapshot", "faults", "parts"]
    assert result["parts_candidates"] == []
    assert result["provider"] == "ollama_local"


@pytest.mark.parametrize('persistent', [False, True])
def test_conflicting_feedback_summary_is_retried_or_rejected(tmp_path, monkeypatch, persistent):
    from app import investigation_history as history, inspection_feedback as feedback
    monkeypatch.setattr(history, 'HISTORY_DIR', tmp_path / 'history')
    monkeypatch.setattr(feedback, 'FEEDBACK_DIR', tmp_path / 'feedback')
    parent = history.save_investigation({'status': 'completed', 'machine_id': 'D1'}, {'machine_id': 'D1'})
    feedback.save_feedback(parent['record_id'], feedback.InspectionFeedback(
        outcome='not_observed', observed_at='2026-01-01T00:00:00Z', notes='目视未发现接头松脱；尚未测量压力信号。'))
    bad = agent.Decision(action='finish', summary='未检查线束和接头。', evidence_ids=['tool:1:snapshot'])
    good = agent.Decision(action='finish', summary='人工称目视未发现接头松脱；压力信号尚未测量。', evidence_ids=['operator:feedback'])
    responses = iter([agent.Decision(action='snapshot')] + ([bad] * 5 if persistent else [bad, good]))
    monkeypatch.setattr(agent, 'model_step', lambda *args: next(responses))
    request = agent.InvestigationRequest(machine_id='D1', question='继续', prior_record_id=parent['record_id'])
    if persistent:
        with pytest.raises(OllamaError, match='step limit'):
            agent.investigate(request)
    else:
        assert agent.investigate(request)['summary'] == good.summary


def test_continuation_scopes_feedback_to_original_device_and_dataset(tmp_path,monkeypatch):
    from app import investigation_history as history,inspection_feedback as feedback
    monkeypatch.setattr(history,'HISTORY_DIR',tmp_path/'history')
    monkeypatch.setattr(feedback,'FEEDBACK_DIR',tmp_path/'feedback')
    parent=history.save_investigation({'status':'completed','machine_id':'D1'}, {'machine_id':'D1'})
    for day in range(1,8):
        feedback.save_feedback(parent['record_id'],feedback.InspectionFeedback(
            outcome='inconclusive',observed_at=f'2026-01-0{day}T00:00:00Z',notes=f'Simulated observation {day}'))
    for changes in [{'machine_id':'D2'},{'dataset_id':'a'*64}]:
        request={'machine_id':'D1','question':'继续','prior_record_id':parent['record_id'],**changes}
        with pytest.raises(ValueError,match='mismatch'):agent.investigate(agent.InvestigationRequest(**request))
    decisions=iter([agent.Decision(action='snapshot'),agent.Decision(action='finish',summary='人工反馈仍待验证',
        evidence_ids=['tool:1:snapshot','operator:feedback'],next_check_ids=['check:snapshot'])])
    captured=[]
    def step(messages,*args):
        captured.append(messages[1]['content'])
        return next(decisions)
    monkeypatch.setattr(agent,'model_step',step)
    result=agent.investigate(agent.InvestigationRequest(machine_id='D1',question='继续',prior_record_id=parent['record_id']))
    source=result['evidence']['operator:feedback']
    assert source['total_records']==7 and len(source['records'])==5
    assert source['records'][0]['notes']=='Simulated observation 3'
    assert result['prior_record_id']==parent['record_id']
    assert 'Simulated observation 7' in captured[0]


def test_fabricated_sources_cannot_complete(monkeypatch):
    responses = iter([agent.Decision(action="snapshot")] + [agent.Decision(action="finish", summary="unsupported", evidence_ids=["fake-manual"])] * 5)
    monkeypatch.setattr(agent, "model_step", lambda *args: next(responses))
    with pytest.raises(OllamaError, match="step limit"):
        agent.investigate(agent.InvestigationRequest(machine_id="D1", question="检查"))


def test_no_fake_ai_fallback(monkeypatch):
    def unavailable(*args):
        raise OllamaError("unavailable")
    monkeypatch.setattr(agent, "model_step", unavailable)
    with pytest.raises(OllamaError):
        agent.investigate(agent.InvestigationRequest(machine_id="D1", question="检查"))


def test_remote_model_rejected(monkeypatch):
    monkeypatch.setattr(agent, "get_ollama_base_url", lambda: "https://example.com")
    with pytest.raises(OllamaError, match="loopback"):
        agent.model_step([])


@pytest.mark.parametrize('persistent', [False, True])
def test_incomplete_trends_require_source_supported_followup(monkeypatch, persistent):
    bad = agent.Decision(action='finish', summary='Only one reading; more data is needed.', evidence_ids=['tool:2:trends'])
    good = agent.Decision(action='finish', summary='Window metrics unavailable; obtain more timestamped records.',
        evidence_ids=['tool:2:trends'], next_check_ids=['check:trend-coverage'])
    replies = iter([agent.Decision(action='snapshot'), agent.Decision(action='trends')]
                   + ([bad] * 4 if persistent else [bad, good]))
    monkeypatch.setattr(agent, 'model_step', lambda *args: next(replies))
    request = agent.InvestigationRequest(machine_id='D1', question='Analyze trends', task='trends', language='en')
    if persistent:
        with pytest.raises(OllamaError, match='step limit'):agent.investigate(request)
    else:
        report = agent.investigate(request)
        assert report['check_recommendations'][0]['check_id'] == 'check:trend-coverage'
        assert report['check_recommendations'][0]['evidence_ids'] == ['tool:2:trends']
        assert report['next_checks'][0].startswith('Obtain and verify timestamped')


def test_trends_are_computed_from_frozen_evidence(monkeypatch):
    responses = iter([agent.Decision(action="snapshot"), agent.Decision(action="trends"),
        agent.Decision(action="finish", summary="历史数据不足", evidence_ids=["tool:2:trends"], next_check_ids=['check:trend-coverage'])])
    monkeypatch.setattr(agent, "model_step", lambda *args: next(responses))
    result = agent.investigate(agent.InvestigationRequest(machine_id="D1", question="分析历史风险"))
    trend = result["evidence"]["tool:2:trends"]
    assert trend["sample_count"] == 0
    assert trend["operating_hours_delta"] is None
    assert trend["method"] == "time_window_rules_v1"


def test_invented_percent_threshold_is_rejected(monkeypatch):
    responses=iter([agent.Decision(action="snapshot")]+[agent.Decision(action="finish",summary="正常怠速应低于20%",evidence_ids=["tool:1:snapshot"])]*5)
    monkeypatch.setattr(agent,"model_step",lambda *args:next(responses))
    with pytest.raises(OllamaError,match="step limit"):
        agent.investigate(agent.InvestigationRequest(machine_id="D1",question="怠速是否正常"))


@pytest.mark.parametrize("text", ["2485.58小时（约1年）", "数据已有一年", "about 1 year old", "3 months of missing data"])
def test_unsupported_calendar_duration(text):
    assert agent.unsupported_calendar_duration(text)


@pytest.mark.parametrize("text", ["2026年6月2日最后上报", "最新记录年龄2485.58小时", "check timestamps"])
def test_calendar_date_is_not_duration(text):
    assert not agent.unsupported_calendar_duration(text)


def test_duration_error_retries_before_returning(monkeypatch):
    responses = iter([agent.Decision(action="snapshot"),
        agent.Decision(action="finish", summary="最新记录约1年以前", evidence_ids=["tool:1:snapshot"]),
        agent.Decision(action="finish", summary="请核实最后上报时间，无法确认当前设备状态", evidence_ids=["tool:1:snapshot"])])
    monkeypatch.setattr(agent, "model_step", lambda *args: next(responses))
    result = agent.investigate(agent.InvestigationRequest(machine_id="D1", question="检查数据时效"))
    assert "约1年" not in result["summary"]
    assert result["summary"].startswith("请核实")


@pytest.mark.parametrize('text',[
    '设备运行状态正常，燃油剩余69.4%。','snapshot 显示机器状态正常。',
    'The machine is operating normally.', 'Equipment is healthy.',
    '无法确认根因，但设备运行状态正常。',
    'No evidence confirms the cause, but the machine is healthy.'])
def test_unsupported_affirmative_health_claim(text):
    assert agent.unsupported_health_claim(text)


@pytest.mark.parametrize('text',[
    '不能确认设备运行状态正常。','运行中不代表机器正常。',
    'No evidence proves the machine is healthy.', 'The machine is not healthy.',
    '设备状态为运行中，尚不能确认根因。','核查设备是否正常。'])
def test_health_uncertainty_is_not_rejected(text):
    assert not agent.unsupported_health_claim(text)


def test_health_claim_is_rewritten_before_return(monkeypatch):
    responses=iter([agent.Decision(action='snapshot'),
        agent.Decision(action='finish',summary='设备运行状态正常。',evidence_ids=['tool:1:snapshot']),
        agent.Decision(action='finish',summary='模拟记录显示运行中，无法确认设备健康状态。',evidence_ids=['tool:1:snapshot'])])
    monkeypatch.setattr(agent,'model_step',lambda *args:next(responses))
    report=agent.investigate(agent.InvestigationRequest(machine_id='D1',question='设备状态'))
    assert report['summary']=='模拟记录显示运行中，无法确认设备健康状态。'


def test_persistent_health_claim_does_not_produce_report(monkeypatch):
    responses=iter([agent.Decision(action='snapshot')]+[
        agent.Decision(action='finish',summary='设备运行状态正常。',evidence_ids=['tool:1:snapshot'])]*5)
    monkeypatch.setattr(agent,'model_step',lambda *args:next(responses))
    with pytest.raises(OllamaError,match='step limit'):
        agent.investigate(agent.InvestigationRequest(machine_id='D1',question='设备状态'))


def test_parts_request_cannot_finish_without_search(monkeypatch):
    responses=iter([agent.Decision(action="snapshot"), agent.Decision(action="finish",summary="premature",evidence_ids=["tool:1:snapshot"]),
        agent.Decision(action="faults"), agent.Decision(action="parts"),
        agent.Decision(action="finish",summary="目录无可用候选",evidence_ids=["tool:3:parts"],next_check_ids=['check:catalog-gap'])])
    seen=[]
    def step(messages,allowed):
        seen.append(allowed)
        return next(responses)
    monkeypatch.setattr(agent,"model_step",step)
    monkeypatch.setattr(agent,"search_parts",lambda *args,**kwargs:[])
    result=agent.investigate(agent.InvestigationRequest(machine_id="D1",question="查看告警并匹配备件"))
    assert "finish" not in seen[1]
    assert result["required_queries"]==["faults","parts","snapshot"]
    assert result["tool_trace"][-1]["action"]=="parts"


def test_explicit_task_controls_queries():
    assert agent.required_queries(agent.InvestigationRequest(machine_id="D1",question="help",task="comprehensive"))=={"snapshot","faults","parts","trends"}
    assert agent.required_queries(agent.InvestigationRequest(machine_id="D1",question="不用查备件",task="overview"))=={"snapshot"}


def test_actual_catalog_citation_satisfies_parts_result(monkeypatch):
    responses=iter([agent.Decision(action="snapshot"),agent.Decision(action="faults"),agent.Decision(action="parts"),
        agent.Decision(action="finish",summary="候选需检查",evidence_ids=["catalog:DEMO-P"])])
    monkeypatch.setattr(agent,"model_step",lambda *args:next(responses))
    monkeypatch.setattr(agent,"search_parts",lambda *args,**kwargs:[{"part_number":"DEMO-P","source_id":"catalog:DEMO-P"}])
    result=agent.investigate(agent.InvestigationRequest(machine_id="D1",question="查备件",task="parts"))
    assert result["parts_candidates"][0]["part_number"]=="DEMO-P"


def test_percentage_correction_is_trusted_and_identifies_rejected_value(monkeypatch):
    responses=iter([agent.Decision(action='snapshot'),
        agent.Decision(action='finish',summary='怠速占比12.5%',evidence_ids=['tool:1:snapshot']),
        agent.Decision(action='finish',summary='未计算窗口怠速占比，资料不足',evidence_ids=['tool:1:snapshot'])])
    captured=[]
    def step(messages,allowed):
        captured.append(list(messages))
        return next(responses)
    monkeypatch.setattr(agent,'model_step',step)
    result=agent.investigate(agent.InvestigationRequest(machine_id='D1',question='查看概况',task='overview'))
    assert '12.5%' not in result['summary']
    correction=captured[-1][-2]
    assert correction['role']=='system'
    assert '12.5' in correction['content']
    assert 'cumulative counters' in correction['content']
    assert not any(m['role']=='assistant' and '12.5%' in m['content'] for m in captured[-1])


def test_fabricated_check_cannot_escape_selected_source_options(monkeypatch):
    responses=iter([agent.Decision(action='snapshot'),
        agent.Decision(action='finish',summary='待核实',evidence_ids=['tool:1:snapshot'],next_check_ids=['replace:invented-pump']),
        agent.Decision(action='finish',summary='模拟片段待核实',evidence_ids=['tool:1:snapshot'],next_check_ids=['check:snapshot'])])
    monkeypatch.setattr(agent,'model_step',lambda *args:next(responses))
    result=agent.investigate(agent.InvestigationRequest(machine_id='D1',question='分析'))
    assert len(result['check_recommendations'])==1
    assert result['check_recommendations'][0]['evidence_ids']==['tool:1:snapshot']
    assert result['next_checks']==[result['check_recommendations'][0]['text']]
    assert 'pump' not in str(result['check_recommendations'])


def test_requested_parts_must_include_available_catalog_procedure(monkeypatch):
    part={'part_number':'DEMO-P','source_id':'catalog:DEMO-P','checks':['核对目录适用范围'],'provenance':'demo'}
    check_id=agent.build_check_options({'catalog:DEMO-P':part})[0]['check_id']
    replies=iter([agent.Decision(action='snapshot'),agent.Decision(action='faults'),agent.Decision(action='parts'),
        agent.Decision(action='finish',summary='候选待核实',evidence_ids=['tool:3:parts'],next_check_ids=['check:snapshot']),
        agent.Decision(action='finish',summary='目录候选待核实',evidence_ids=['tool:3:parts'],next_check_ids=[check_id])])
    monkeypatch.setattr(agent,'model_step',lambda *args:next(replies))
    monkeypatch.setattr(agent,'search_parts',lambda *args,**kwargs:[part])
    report=agent.investigate(agent.InvestigationRequest(machine_id='D1',question='查备件',task='parts'))
    assert report['summary']=='目录候选待核实'
    assert report['next_checks']==['核对目录适用范围']


def test_empty_parts_result_requires_catalog_gap_check_before_completion(monkeypatch):
    replies = iter([agent.Decision(action='snapshot'), agent.Decision(action='faults'), agent.Decision(action='parts'),
        agent.Decision(action='finish', summary='No catalog match.', evidence_ids=['tool:3:parts']),
        agent.Decision(action='finish', summary='No supported candidate. Documentation is needed.',
                       evidence_ids=['tool:3:parts'], next_check_ids=['check:catalog-gap'])])
    monkeypatch.setattr(agent, 'model_step', lambda *args: next(replies))
    monkeypatch.setattr(agent, 'search_parts', lambda *args, **kwargs: [])
    report = agent.investigate(agent.InvestigationRequest(machine_id='D1', question='Find parts', task='parts', language='en'))
    assert report['check_recommendations'][0]['check_id'] == 'check:catalog-gap'
    assert report['next_checks'][0].startswith('Obtain parts or service documentation')


def test_persistent_missing_catalog_gap_check_does_not_complete(monkeypatch):
    replies = iter([agent.Decision(action='snapshot'), agent.Decision(action='faults'), agent.Decision(action='parts')] +
        [agent.Decision(action='finish', summary='No catalog match.', evidence_ids=['tool:3:parts'], next_check_ids=['check:snapshot'])] * 3)
    monkeypatch.setattr(agent, 'model_step', lambda *args: next(replies))
    monkeypatch.setattr(agent, 'search_parts', lambda *args, **kwargs: [])
    with pytest.raises(OllamaError, match='step limit'):
        agent.investigate(agent.InvestigationRequest(machine_id='D1', question='Find parts', task='parts'))


@pytest.mark.parametrize('text', [
    '机器状态为运行中，工时和空闲时间正常。',
    '怠速时间正常。',
    'Operating hours and idle hours are normal.',
])
def test_counter_values_do_not_prove_normality(text):
    assert agent.unsupported_health_claim(text)


@pytest.mark.parametrize('text', [
    '无法确认工时和空闲时间正常。',
    'Cannot conclude that operating hours are normal.',
    '工时计数为 4858.2791，尚未判定是否异常。',
])
def test_counter_uncertainty_is_allowed(text):
    assert not agent.unsupported_health_claim(text)


def test_time_equality_is_rewritten_before_report_completion(monkeypatch):
    replies = iter([agent.Decision(action='snapshot'),
        agent.Decision(action='finish', summary='回放时间与采样时间一致。', evidence_ids=['tool:1:snapshot']),
        agent.Decision(action='finish', summary='请核对记录时间，当前证据不足。', evidence_ids=['tool:1:snapshot'])])
    captured = []
    def step(messages, allowed):
        captured.append(messages)
        return next(replies)
    monkeypatch.setattr(agent, 'model_step', step)
    report = agent.investigate(agent.InvestigationRequest(machine_id='D1', question='核对时间', task='overview'))
    assert '一致' not in report['summary']
    assert 'equality claim is not supported' in captured[-1][-2]['content']


def test_persistent_time_equality_error_cannot_complete(monkeypatch):
    replies = iter([agent.Decision(action='snapshot')] + [
        agent.Decision(action='finish', summary='Replay time matches sample timestamp.', evidence_ids=['tool:1:snapshot'])] * 5)
    monkeypatch.setattr(agent, 'model_step', lambda *args: next(replies))
    with pytest.raises(OllamaError, match='step limit'):
        agent.investigate(agent.InvestigationRequest(machine_id='D1', question='Review time', task='overview'))
