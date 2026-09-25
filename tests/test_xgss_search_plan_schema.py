"""Search-label schema/retry regressions; provider replies are local fixtures."""
import copy
import json

import pytest
from pydantic import ValidationError

from app import xgss_research_ai as ai


LONG_DEF_LABEL = 'DEF Tank Temperature 1 - Out of Calibration - Temperature Sensor'


def plan(terms):
    return {'summary': '历史尿素箱温度校准异常，先核实温度信号。',
            'directions': [{'component': '尿素箱温度检测',
                            'reason': LONG_DEF_LABEL + '；记录已解除，需核查传感器及接插件。',
                            'search_terms': terms}],
            'missing_evidence': ['原始数值故障码未提供。']}


def test_search_term_item_constraints_are_visible_in_json_schema():
    schema = ai.SearchPlan.model_json_schema()
    field = schema['$defs']['Direction']['properties']['search_terms']
    assert (field['minItems'], field['maxItems']) == (1, 4)
    assert (field['items']['minLength'], field['items']['maxLength']) == (1, 40)
    assert field['items']['pattern'] == r'^[^<>\r\n]+$'


def test_long_def_description_is_preserved_in_reason_with_short_english_catalog_terms():
    result = ai.SearchPlan.model_validate(plan([' 尿素箱 ', 'DEF tank', 'temperature sensor']))
    assert result.directions[0].search_terms == ['尿素箱', 'DEF tank', 'temperature sensor']
    assert LONG_DEF_LABEL in result.directions[0].reason


@pytest.mark.parametrize(('label', 'error_type'), [
    (LONG_DEF_LABEL, 'string_too_long'), ('   ', 'string_too_short'),
    ('DEF\ntank', 'string_pattern_mismatch'), ('DEF<tank>', 'string_pattern_mismatch'),
])
def test_invalid_terms_report_exact_item_without_truncating_or_rewriting(label, error_type):
    value = plan([label]); before = copy.deepcopy(value)
    with pytest.raises(ValidationError) as raised:
        ai.SearchPlan.model_validate(value)
    issue = raised.value.errors()[0]
    assert issue['loc'] == ('directions', 0, 'search_terms', 0)
    assert issue['type'] == error_type
    assert value == before


@pytest.mark.parametrize('label', ['https://example.com', 'HTTP://example.com'])
def test_url_labels_are_still_rejected(label):
    with pytest.raises(ValidationError, match='检索词不能包含网址'):
        ai.SearchPlan.model_validate(plan([label]))


@pytest.mark.parametrize('terms', [[], ['one', 'two', 'three', 'four', 'five']])
def test_search_term_count_bounds_remain_enforced(terms):
    with pytest.raises(ValidationError):
        ai.SearchPlan.model_validate(plan(terms))


@pytest.mark.parametrize('bad_label', [LONG_DEF_LABEL, 'https://example.com'])
def test_one_format_retry_provides_fixed_actionable_rules_and_accepts_short_terms(monkeypatch, bad_label):
    calls = []
    answers = iter([plan([bad_label]), plan(['尿素箱', 'DEF tank', 'temperature sensor'])])

    def provider(messages, schema, timeout_seconds):
        calls.append(copy.deepcopy(messages))
        assert 0 < timeout_seconds <= 60
        return json.dumps(next(answers), ensure_ascii=False)

    monkeypatch.setattr(ai, 'generate_structured_with_deepseek', provider)
    result = ai._call(ai.SearchPlan, ai.SEARCH_TERM_INSTRUCTIONS, {'symptom': '历史 DEF 温度故障'},
                      'TESTVIN', 'test-machine')
    assert len(calls) == 2
    correction = calls[1][-1]['content']
    assert '1–40' in correction and '1–4' in correction and 'reason' in correction
    assert result.directions[0].search_terms == ['尿素箱', 'DEF tank', 'temperature sensor']
    assert LONG_DEF_LABEL in result.directions[0].reason


def test_repeated_invalid_terms_fail_after_one_retry_instead_of_silent_truncation(monkeypatch):
    calls = []

    def provider(*args, **kwargs):
        calls.append(True)
        return json.dumps(plan([LONG_DEF_LABEL]))

    monkeypatch.setattr(ai, 'generate_structured_with_deepseek', provider)
    with pytest.raises(ValidationError):
        ai._call(ai.SearchPlan, '只生成检索计划。', {}, 'TESTVIN', 'test-machine')
    assert len(calls) == 2


def test_corrected_structure_still_runs_source_validation(monkeypatch):
    calls = []

    def provider(*args, **kwargs):
        calls.append(True)
        return json.dumps(plan(['DEF tank']))

    def reject_source(value):
        raise ValueError('AI 选择了未读取的备件。')

    monkeypatch.setattr(ai, 'generate_structured_with_deepseek', provider)
    with pytest.raises(ai.ModelOutputValidationError):
        ai._call(ai.SearchPlan, '只生成检索计划。', {}, 'TESTVIN', 'test-machine', validate=reject_source)
    assert len(calls) == 2
