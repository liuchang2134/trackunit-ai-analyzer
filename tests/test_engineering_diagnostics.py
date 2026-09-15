import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app import local_assistant as agent, manual_knowledge, engineering_diagnostics as diagnostics
from app.models import Machine
from app.ollama_client import OllamaError


REFERENCE = {'reference_id': 'manual:fixture', 'title': 'Synthetic test manual excerpt',
    'model': 'XE55U', 'configuration': 'XE55U.00III', 'version': 'fixture', 'pdf_pages': [2],
    'section': 'Fixture only', 'text': 'Inspect the harness connector for looseness.',
    'source_url': 'https://example.org/test.pdf', 'provenance': 'synthetic_test_fixture',
    'fault_codes': ['E4030'], 'applicability': 'model_reference_only'}


def hypothesis(**changes):
    return {'component': '线束连接器', 'rationale': '资料提到连接器，需要检查后才能判断是否相关。',
        'reference_ids': ['manual:fixture'], 'search_terms': ['connector', '线束连接器'],
        'checks': [{'text': '核对适用手册并检查连接器有无松脱。', 'reference_id': 'manual:fixture',
                    'source_quote': 'Inspect the harness connector for looseness.'}],
        'ranked_parts': [], 'feedback_effect': '', **changes}


def test_hypothesis_without_part_number_still_produces_cited_check():
    hypotheses, checks, parts = diagnostics.validate_hypotheses([hypothesis()], [REFERENCE])
    assert hypotheses[0]['part_candidate_ids'] == []
    assert parts == []
    assert checks[0]['source_quote'] in REFERENCE['text']
    assert checks[0]['evidence_ids'] == ['manual:fixture']
    assert checks[0]['provenance'] == 'ai_inference_from_manual'


@pytest.mark.parametrize('change,match', [
    ({'reference_ids': ['manual:invented']}, 'unavailable'),
    ({'checks': [{'text': '检查连接器的状态。', 'reference_id': 'manual:fixture', 'source_quote': 'An invented manufacturer procedure.'}]}, 'not found'),
    ({'checks': [{'text': '测量是否为 120 欧姆。', 'reference_id': 'manual:fixture', 'source_quote': REFERENCE['text']}]}, 'numeric'),
    ({'ranked_parts': [{'source_id': 'xgss:invented', 'rationale': '看起来适用但实际没有读取。'}]}, 'not read'),
])
def test_fabricated_sources_thresholds_and_parts_are_rejected(change, match):
    with pytest.raises(ValueError, match=match):
        diagnostics.validate_hypotheses([hypothesis(**change)], [REFERENCE])


def test_ai_cannot_supply_a_part_number_in_hypothesis_schema():
    with pytest.raises(ValidationError):
        diagnostics.ComponentHypothesis.model_validate(hypothesis(part_number='FAKE-000'))


def test_selected_part_number_is_copied_only_from_actual_capture():
    rows = [{'source_id': 'xgss:fixture:1', 'part_number': 'CAPTURED-123', 'name': 'connector'}]
    drafts = [hypothesis(ranked_parts=[{'source_id': rows[0]['source_id'], 'rationale': '名称及结构分类相关，需核对适配。'}])]
    hypotheses, _, parts = diagnostics.validate_hypotheses(drafts, [REFERENCE], rows)
    assert parts[0]['part_number'] == 'CAPTURED-123'
    assert hypotheses[0]['part_candidate_ids'] == ['xgss:fixture:1']


def test_feedback_requires_explicit_effect_and_preserves_check_identity():
    feedback = {'records': [{'notes': '目视未发现松脱，尚未测量。'}]}
    with pytest.raises(ValueError, match='affect'):
        diagnostics.validate_hypotheses([hypothesis()], [REFERENCE], feedback=feedback)
    prior = diagnostics.validate_hypotheses([hypothesis()], [REFERENCE])[1]
    result = diagnostics.validate_hypotheses([hypothesis(feedback_effect='人工未见松脱，电气测量仍缺失，连接器问题尚未排除。')], [REFERENCE], feedback=feedback)
    assert result[1][0]['check_id'] == prior[0]['check_id']


@pytest.fixture
def investigation_fixture(tmp_path, monkeypatch):
    path = tmp_path / 'manual.json'
    path.write_text(json.dumps({'schema_version': 1, 'records': [REFERENCE]}), encoding='utf-8')
    monkeypatch.setattr(manual_knowledge, 'KNOWLEDGE_PATH', path)
    monkeypatch.setattr(agent, 'find_machine', lambda _: Machine(machine_id='M1', serial_number='TESTVIN',
        model='XE55U', machine_type='excavator', customer='fixture', location='fixture', last_seen_at='2026-01-01T00:00:00Z'))
    monkeypatch.setattr(agent, 'find_telemetry', lambda _: [])
    monkeypatch.setattr(agent, 'find_faults', lambda _: [])
    monkeypatch.setattr(agent, 'get_data_source', lambda: 'trackunit_cache')
    monkeypatch.setattr(agent, 'search_parts', lambda *a, **kw: [])
    from app import xgss_catalog_context
    monkeypatch.setattr(xgss_catalog_context, 'load_catalog_context', lambda **kw: {'status': 'not_captured', 'items': []})
    return agent.InvestigationRequest(machine_id='M1', question='E4030 测试排查', task='parts', engineering_fault={
        'model': 'XE55U', 'code': 'E4030', 'configuration': 'unknown', 'source': 'test'})


def finish(**changes):
    return agent.Decision(action='finish', summary='这是测试输入 E4030，非 Trackunit 实测事件。配置待核对；连接器是待检查方向，尚未定位料号。',
        evidence_ids=['operator:engineering-fault', 'tool:3:parts'], next_check_ids=['check:catalog-gap'],
        component_hypotheses=[hypothesis()], **changes)


def test_investigation_keeps_test_code_out_of_recorded_faults(investigation_fixture, monkeypatch):
    captured = []
    responses = iter([agent.Decision(action='snapshot'), agent.Decision(action='faults'), agent.Decision(action='parts'), finish()])
    def model(messages, *_):
        captured.append(messages)
        return next(responses)
    monkeypatch.setattr(agent, 'model_step', model)
    report = agent.investigate(investigation_fixture)
    faults = report['evidence']['tool:2:faults']
    assert 'E4030' not in json.dumps(faults)
    assert report['engineering_fault']['source'] == 'test'
    assert report['source'] == 'trackunit_cache'
    assert report['parts_candidates'] == []
    assert report['manual_references'][0]['applicability'] == 'model_reference_only'
    assert report['component_hypotheses'][0]['component'] == '线束连接器'
    assert any(c['check_id'].startswith('check:engineering:') for c in report['check_recommendations'])
    assert 'component_hypotheses' in captured[-1][-1]['content']


def test_no_static_hypotheses_on_model_failure(investigation_fixture, monkeypatch):
    def unavailable(*_):
        raise OllamaError('unavailable')
    monkeypatch.setattr(agent, 'model_step', unavailable)
    with pytest.raises(OllamaError, match='unavailable'):
        agent.investigate(investigation_fixture)


def test_prior_engineering_fault_cannot_change_under_same_feedback(investigation_fixture, tmp_path, monkeypatch):
    from app import investigation_history as history
    monkeypatch.setattr(history, 'HISTORY_DIR', tmp_path / 'history')
    saved = history.save_investigation({'status': 'completed', 'machine_id': 'M1'}, investigation_fixture.model_dump())
    request = investigation_fixture.model_copy(update={'prior_record_id': saved['record_id'],
        'engineering_fault': manual_knowledge.EngineeringFault(model='XE55U', code='E9999', source='test')})
    with pytest.raises(ValueError, match='fault or configuration mismatch'):
        agent.investigate(request)


def test_cloud_generation_receives_schema_and_real_document_evidence(investigation_fixture, monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'deepseek')
    received = []
    def generate(messages, schema, **kwargs):
        received.append((messages, schema))
        if 'parts' in schema['properties']['action']['enum']:
            return agent.Decision(action='parts').model_dump_json()
        return finish().model_dump_json()
    monkeypatch.setattr(agent, 'generate_structured_with_deepseek', generate)
    report = agent.investigate(investigation_fixture)
    assert report['model_decisions'] == 2
    assert report['provider'] == 'deepseek'
    assert received[-1][1]['properties']['component_hypotheses']['items']['$ref'].endswith('/ComponentHypothesis')
    assert any(REFERENCE['text'] in m['content'] for m in received[-1][0])
    assert 'operator:engineering-fault' in report['citations']


def test_feedback_round_trip_reaches_hypotheses_without_resetting_test_source(investigation_fixture, tmp_path, monkeypatch):
    from app import investigation_history as history, inspection_feedback
    monkeypatch.setattr(history, 'HISTORY_DIR', tmp_path / 'history')
    monkeypatch.setattr(inspection_feedback, 'FEEDBACK_DIR', tmp_path / 'feedback')
    responses = iter([agent.Decision(action='snapshot'), agent.Decision(action='faults'), agent.Decision(action='parts'), finish()])
    monkeypatch.setattr(agent, 'model_step', lambda *_: next(responses))
    report = agent.investigate(investigation_fixture)
    saved = history.save_investigation(report, investigation_fixture.model_dump())
    check = report['component_hypotheses'][0]['checks'][0]
    inspection_feedback.save_feedback(saved['record_id'], inspection_feedback.InspectionFeedback(
        check_id=check['check_id'], outcome='not_observed', observed_at='2026-01-01T10:00:00Z', notes='目视未见连接器松脱，尚未进行测量。'))
    next_finish = finish()
    next_finish.component_hypotheses[0].feedback_effect = '人工目视未见松脱，尚未进行测量，电气连接问题仍待确认。'
    responses = iter([agent.Decision(action='snapshot'), agent.Decision(action='faults'), agent.Decision(action='parts'), next_finish])
    captured = []
    def next_step(messages, *_):
        captured.append(messages)
        return next(responses)
    monkeypatch.setattr(agent, 'model_step', next_step)
    next_report = agent.investigate(investigation_fixture.model_copy(update={'prior_record_id': saved['record_id']}))
    assert '人工目视未见松脱' in next_report['component_hypotheses'][0]['feedback_effect']
    assert next_report['engineering_fault']['source'] == 'test'
    assert next_report['evidence']['operator:feedback']['records'][0]['check_id'] == check['check_id']
    assert 'prior_component_hypotheses' in captured[-1][1]['content']


def test_invalid_hypothesis_retried_without_becoming_prompt_exemplar(investigation_fixture, monkeypatch):
    bad = finish()
    bad.component_hypotheses[0].checks[0].source_quote = 'Invented evidence is not in the fixture.'
    responses = iter([agent.Decision(action='snapshot'), agent.Decision(action='faults'), agent.Decision(action='parts'), bad, finish()])
    captured = []
    def step(messages, *_):
        captured.append(messages)
        return next(responses)
    monkeypatch.setattr(agent, 'model_step', step)
    report = agent.investigate(investigation_fixture)
    assert report['status'] == 'completed'
    assert report['model_decisions'] == 5
    assert all('Invented evidence is not in the fixture.' not in m['content'] for m in captured[-1])


def test_known_numeric_threshold_is_not_applied_to_unknown_configuration():
    reference = {**REFERENCE, 'text': REFERENCE['text'] + ' Fixture measurement is 60 ohms.'}
    draft = hypothesis(checks=[{'text': '测量是否为 60 欧姆。', 'reference_id': 'manual:fixture', 'source_quote': 'Fixture measurement is 60 ohms.'}])
    with pytest.raises(ValueError, match='Unknown configuration'):
        diagnostics.validate_hypotheses([draft], [reference])


def test_invented_failure_probability_is_rejected():
    with pytest.raises(ValueError, match='percentage'):
        diagnostics.validate_hypotheses([hypothesis(rationale='连接器有 95% 的概率已经损坏。')], [REFERENCE])


@pytest.mark.parametrize('text', ['检查 E4030 显示和 ECU CANH2 / CANL2 连接器。', 'Inspect ECU CANH2 and CANL2 for code E4030.'])
def test_component_identifiers_are_not_numeric_thresholds(text):
    assert diagnostics.measurement_values(text) is False
    reference = {**REFERENCE, 'text': 'Fixture E4030: inspect ECU CANH2 and CANL2 connector.'}
    draft = hypothesis(checks=[{'text': text, 'reference_id': 'manual:fixture', 'source_quote': reference['text']}])
    assert diagnostics.validate_hypotheses([draft], [reference])[0]


@pytest.mark.parametrize('text', ['正常阻值为60', '电压应为24V', 'Resistance is 60 ohms', '电阻约为 60 欧姆'])
def test_unknown_configuration_measurement_values_are_recognized(text):
    assert diagnostics.measurement_values(text)


def test_threshold_cannot_be_borrowed_from_another_row_on_same_page():
    reference = {**REFERENCE, 'applicability': 'configuration_selected_unverified',
                 'text': 'Fixture circuit A threshold is 12 ohms. Fixture circuit B threshold is 60 ohms.'}
    draft = hypothesis(checks=[{'text': '检查回路 A 是否为 60 欧姆。', 'reference_id': 'manual:fixture',
                                'source_quote': 'Fixture circuit A threshold is 12 ohms.'}])
    with pytest.raises(ValueError, match='unsupported numeric'):
        diagnostics.validate_hypotheses([draft], [reference])


def test_engineering_report_does_not_retry_only_for_missing_legacy_gap_check(investigation_fixture, monkeypatch):
    done = finish()
    done.next_check_ids = []
    responses = iter([agent.Decision(action='snapshot'), agent.Decision(action='faults'), agent.Decision(action='parts'), done])
    monkeypatch.setattr(agent, 'model_step', lambda *_: next(responses))
    report = agent.investigate(investigation_fixture)
    assert report['model_decisions'] == 4
    follow_up = next(c for c in report['check_recommendations'] if c['check_id'] == 'check:catalog-gap')
    assert follow_up['selection_method'] == 'application_catalog_follow_up'
    assert 'XGSS' in follow_up['text']
    assert report['component_hypotheses']


def test_old_fleet_prompt_does_not_require_preexisting_fault_parts_map():
    from app.structured_context_builder import build_fleet_analyst_prompt
    prompt = build_fleet_analyst_prompt({}, 'zh')
    assert 'unavailable unless a mapping table is provided' not in prompt
    assert 'Specific part numbers require supplied catalog rows' in prompt


@pytest.mark.parametrize('failure', ['malformed_json', 'unknown_action', 'wrong_nested_type'])
def test_engineering_cloud_repairs_one_realistic_structured_output_error(investigation_fixture, monkeypatch, failure):
    monkeypatch.setenv('AI_PROVIDER', 'deepseek')
    calls = []
    def generate(messages, schema, **kwargs):
        calls.append((messages, schema))
        if len(calls) == 1:
            return agent.Decision(action='parts').model_dump_json()
        if len(calls) == 2:
            if failure == 'malformed_json':
                return '{"action":"finish","component_hypotheses":['
            malformed = finish().model_dump()
            if failure == 'unknown_action':
                malformed['action'] = 'diagnose_components'
            else:
                malformed['component_hypotheses'][0]['checks'] = malformed['component_hypotheses'][0]['checks'][0]
            return json.dumps(malformed, ensure_ascii=False)
        return finish().model_dump_json()
    monkeypatch.setattr(agent, 'generate_structured_with_deepseek', generate)
    report = agent.investigate(investigation_fixture)
    assert report['format_repair_attempts'] == 1
    assert report['model_decisions'] == 3
    assert len(calls) == 3
    assert [t['action'] for t in report['tool_trace']] == ['snapshot', 'faults', 'parts']
    assert any('Repair the format once' in m['content'] for m in calls[-1][0])
    assert report['component_hypotheses'][0]['checks'][0]['source_quote'] == REFERENCE['text']


def test_persistent_invalid_format_only_retries_once(investigation_fixture, monkeypatch):
    from app.deepseek_client import DeepSeekError
    monkeypatch.setenv('AI_PROVIDER', 'deepseek')
    calls = []
    def generate(*args, **kwargs):
        calls.append(1)
        return '{'
    monkeypatch.setattr(agent, 'generate_structured_with_deepseek', generate)
    with pytest.raises(DeepSeekError) as failure:
        agent.investigate(investigation_fixture)
    assert failure.value.kind == 'invalid_response'
    assert len(calls) == 2


@pytest.mark.parametrize('kind', ['authentication', 'insufficient_balance', 'rate_limit', 'timeout', 'network'])
def test_engineering_format_repair_never_retries_other_provider_failures(investigation_fixture, monkeypatch, kind):
    from app.deepseek_client import DeepSeekError
    monkeypatch.setenv('AI_PROVIDER', 'deepseek')
    calls = []
    def generate(*args, **kwargs):
        calls.append(1)
        raise DeepSeekError('Synthetic provider failure', kind=kind)
    monkeypatch.setattr(agent, 'generate_structured_with_deepseek', generate)
    with pytest.raises(DeepSeekError) as failure:
        agent.investigate(investigation_fixture)
    assert failure.value.kind == kind
    assert len(calls) == 1


def test_format_repair_does_not_extend_investigation_deadline(investigation_fixture, monkeypatch):
    from app.deepseek_client import DeepSeekError
    from types import SimpleNamespace
    monkeypatch.setenv('AI_PROVIDER', 'deepseek')
    clocks = iter([0.0, 0.0, 121.0])
    monkeypatch.setattr(agent, 'time', SimpleNamespace(monotonic=lambda: next(clocks)))
    calls = []
    def generate(*args, **kwargs):
        calls.append(1)
        return '{'
    monkeypatch.setattr(agent, 'generate_structured_with_deepseek', generate)
    with pytest.raises(DeepSeekError):
        agent.investigate(investigation_fixture)
    assert len(calls) == 1


def test_internal_implementation_fields_are_rewritten_before_report_completion(investigation_fixture, monkeypatch):
    bad = finish()
    bad.summary = '本场景为测试输入（engineering_fault.source=test）；operating_hours_delta不可用，idle_share不可用。'
    responses = iter([agent.Decision(action='snapshot'), agent.Decision(action='faults'), agent.Decision(action='parts'), bad, finish()])
    captured = []
    def step(messages, *_):
        captured.append(messages)
        return next(responses)
    monkeypatch.setattr(agent, 'model_step', step)
    report = agent.investigate(investigation_fixture)
    assert 'engineering_fault' not in report['summary']
    assert 'operating_hours_delta' not in report['summary']
    assert 'idle_share' not in report['summary']
    assert any('Write the summary for the user' in m['content'] for m in captured[-1])
