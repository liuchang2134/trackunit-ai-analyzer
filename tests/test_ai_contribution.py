"""The AI contribution summary must describe only what the record actually shows.

These tests read the shape a real investigation writes, so a change to the report
schema that would silently empty this summary fails here instead of quietly
understating the AI on the demo screen.
"""
import json

import pytest

from app.ai_contribution import ai_contribution


def report(**overrides):
    base = {
        'provider': 'deepseek', 'model': 'deepseek-flash', 'inference_location': 'cloud',
        'thinking_mode': 'disabled', 'model_decisions': 2, 'duration_seconds': 6.44,
        'format_repair_attempts': 0,
        'tool_trace': [
            {'action': 'snapshot', 'source_id': 'tool:1:snapshot', 'trigger': 'task_required'},
            {'action': 'faults', 'source_id': 'tool:2:faults', 'trigger': 'task_required'},
            {'action': 'trends', 'source_id': 'tool:3:trends', 'trigger': 'task_required'},
            {'action': 'parts', 'source_id': 'tool:4:parts', 'trigger': 'model_selected'},
        ],
        'evidence': {
            'tool:1:snapshot': {'method': 'snapshot'},
            'manual:xe55u-e4030-286': {'method': 'manual'},
            'operator:engineering-fault': {'method': 'operator'},
            'xgss:catalog-context': {'method': 'xgss'},
        },
        'citations': ['tool:1:snapshot', 'manual:xe55u-e4030-286'],
        'data_facts': [{'text': 'a'}, {'text': 'b'}, {'text': 'c'}],
        'parts_candidates': [{'part_number': 'TEST-001'}],
        'manual_references': [
            {'source_document': 'XE55U SHOP MANUAL', 'pdf_pages': [286, 287], 'configuration': 'XE55U.00III',
             'source_quote': 'Possible cause 1: Fuse blow.'},
        ],
        'component_hypotheses': [
            {'component': 'ECU 供电熔断器', 'status': 'hypothesis_requires_inspection',
             'rationale': '手册列为可能原因', 'search_terms': ['ECU fuse', 'E4030'],
             'reference_ids': ['manual:xe55u-e4030-286'], 'part_candidate_ids': [],
             'checks': [{'text': '检查熔断器', 'pdf_pages': [286]}]},
            {'component': 'ECU CAN 线束', 'status': 'hypothesis_requires_inspection',
             'rationale': '导线断路需测量', 'search_terms': ['CANH2', 'E4030'],
             'reference_ids': ['manual:xe55u-e4030-287'], 'part_candidate_ids': ['p1'],
             'checks': [{'text': '断电测量', 'pdf_pages': [287]}, {'text': '检查短路', 'pdf_pages': [287]}]},
        ],
    }
    base.update(overrides)
    return base


def test_the_summary_counts_what_the_model_actually_decided():
    out = ai_contribution(report())
    ai = out['ai']
    assert ai['model_decisions'] == 2
    # Only the read the model chose counts as a model achievement.
    assert ai['model_selected_reads'] == 1
    assert ai['model_selected_actions'] == ['parts']
    assert ai['hypothesis_count'] == 2
    assert ai['check_directions'] == 3
    assert ai['citation_count'] == 2
    assert ai['duration_seconds'] == 6.44


def test_program_work_is_reported_separately_from_model_work():
    out = ai_contribution(report())
    program = out['program']
    assert program['reads_total'] == 4
    assert program['reads_by_task'] == 3, 'task-forced reads must not be credited to the model'
    assert program['evidence_sources'] == 4
    assert program['evidence_by_family'] == {'设备数据读取': 1, '官方图册条目': 1, '人工提供': 1, '适用手册摘录': 1}
    assert program['data_facts'] == 3
    assert program['parts_candidates'] == 1


def test_each_hypothesis_keeps_its_manual_grounding_and_search_terms():
    hypothesis = ai_contribution(report())['ai']['hypotheses'][0]
    assert hypothesis['component'] == 'ECU 供电熔断器'
    assert hypothesis['pdf_pages'] == [286], 'the manual page it came from must survive'
    assert hypothesis['check_count'] == 1
    assert hypothesis['search_terms'] == ['ECU fuse', 'E4030']
    assert hypothesis['reference_ids'] == ['manual:xe55u-e4030-286']
    assert hypothesis['status'] == 'hypothesis_requires_inspection'


def test_a_catalog_hit_is_evidence_not_a_confirmed_part():
    hypothesis = ai_contribution(report())['ai']['hypotheses'][1]
    assert hypothesis['part_candidate_count'] == 1
    # The summary states the boundary so the count cannot be read as "this failed".
    boundary = ' '.join(ai_contribution(report())['boundary'])
    assert '不是已确认故障' in boundary
    assert '不代表它已损坏' in boundary


def test_manual_references_carry_pages_and_the_quoted_source():
    reference = ai_contribution(report())['ai']['manual_references'][0]
    assert reference['pdf_pages'] == [286, 287]
    assert reference['source_document'] == 'XE55U SHOP MANUAL'
    assert 'Fuse blow' in reference['quote']


def test_a_format_repair_is_disclosed_not_hidden():
    # A repair means the model's first answer did not satisfy the contract; the
    # demo must be able to say so rather than present a clean run.
    assert ai_contribution(report(format_repair_attempts=1))['ai']['format_repair_attempts'] == 1


def test_a_run_without_model_decisions_reports_zero_ai_work():
    # Records produced without a model call still carry reads and citations; the
    # summary must not attribute any of that to the AI.
    out = ai_contribution(report(model_decisions=0, tool_trace=[
        {'action': 'snapshot', 'source_id': 'tool:1:snapshot', 'trigger': 'task_required'},
    ], component_hypotheses=[], citations=['tool:1:snapshot']))
    assert out['ai']['model_decisions'] == 0
    assert out['ai']['model_selected_reads'] == 0
    assert out['ai']['hypothesis_count'] == 0
    assert out['ai']['citation_count'] == 1, 'citations are still reported, just not as AI work'
    assert out['program']['reads_total'] == 1


@pytest.mark.parametrize('value', [None, {}, 'not-a-report', []])
def test_no_report_yields_no_summary(value):
    assert ai_contribution(value) is None


def test_malformed_nested_rows_do_not_break_the_summary():
    out = ai_contribution(report(
        tool_trace=[None, 'x', {'action': 'parts', 'trigger': 'model_selected'}],
        component_hypotheses=[None, {'component': '  '}, {'component': '泵', 'checks': [None, {'text': 'x'}],
                                                           'search_terms': [None, 'a']}],
        evidence={'tool:1': {}, 'unprefixed': {}},
        manual_references=[None, {'source_document': 'M'}],
    ))
    assert out['ai']['model_selected_actions'] == ['parts']
    assert out['ai']['hypothesis_count'] == 1
    assert out['ai']['search_terms'] == ['a']
    assert out['program']['evidence_by_family']['设备数据读取'] == 1
    assert out['program']['evidence_by_family']['other'] == 1


def test_the_summary_is_json_serialisable_for_the_report_payload():
    json.dumps(ai_contribution(report()))
