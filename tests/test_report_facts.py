from copy import deepcopy
from app.report_facts import build_report_facts


def test_source_and_distinct_times_are_rendered_without_ai_or_mutation():
    evidence = {'tool:1:snapshot': {'telemetry': [{'recorded_at': '2026-06-29T08:45:00Z'}]}}
    original = deepcopy(evidence)
    facts = build_report_facts('imported_synthetic', '2026-06-29T08:55:00Z', evidence)
    assert '模拟数据' in facts[0]['text']
    assert '08:55:00' in facts[1]['text'] and '08:45:00' in facts[2]['text']
    assert all(set(fact['evidence_ids']) <= set(evidence) for fact in facts)
    assert evidence == original


def test_one_sample_preserves_unavailable_metrics_and_counts():
    facts = build_report_facts('mock', None, {'tool:2:trends': {'method': 'time_window_rules_v1',
        'operating_hours_delta': None, 'idle_share': None, 'valid_counter_sample_counts': {'operating': 1, 'idle': 1}}}, 'en')
    assert 'unavailable' in facts[-1]['text'] and '1/1' in facts[-1]['text']
    assert '0%' not in facts[-1]['text']


def test_zero_idle_is_not_treated_as_missing():
    facts = build_report_facts('mock', None, {'tool:2:trends': {'method': 'time_window_rules_v1',
        'operating_hours_delta': 1.5, 'idle_share': 0}}, 'en')
    assert '0.00%' in facts[-1]['text'] and '1.5 h' in facts[-1]['text']


def test_matched_and_empty_catalog_cannot_share_conclusions():
    def result(code):
        return build_report_facts('mock', None, {'tool:3:parts': {'search_diagnostics': {'reason_code': code}}}, 'en')[-1]['text']
    assert 'candidates were found' in result('matched') and 'is empty' not in result('matched')
    assert 'is empty' in result('catalog_empty') and 'candidates were found' not in result('catalog_empty')
    assert 'equipment model' in result('model_not_in_catalog')


def test_real_source_is_not_labelled_simulated_even_with_cutoff():
    facts = build_report_facts('imported_user_supplied', '2026-06-29T08:55:00Z', {'tool:1:snapshot': {}}, 'en')
    assert 'simulated' not in str(facts)


def test_feedback_retains_original_notes_and_does_not_infer_inspection_result():
    notes = '目视未发现接头松脱；尚未测量压力信号，无法确认传感器损坏。'
    evidence = {'operator:feedback': {'records': [
        {'feedback_id': 'a', 'observed_at': '2026-06-29T08:50:00Z',
         'outcome': 'not_observed', 'notes': notes},
        {'feedback_id': 'b', 'observed_at': '2026-06-29T09:00:00Z',
         'outcome': 'inconclusive', 'notes': '尚未完成测量。'}]}}
    original = deepcopy(evidence)
    for language in ['zh', 'en']:
        facts = build_report_facts('mock', None, evidence, language)
        rows = [f for f in facts if f['fact_id'].startswith('operator-feedback:')]
        assert len(rows) == 2
        assert notes in rows[0]['text']
        assert '2026-06-29T08:50:00Z' in rows[0]['text']
        assert rows[0]['evidence_ids'] == ['operator:feedback']
        assert ('未经验证' if language == 'zh' else 'unverified') in rows[0]['text']
        assert ('未观察到' if language == 'zh' else 'Not observed') in rows[0]['text']
        assert ('不能排除' if language == 'zh' else 'does not exclude') in rows[0]['text']
    assert evidence == original


def test_empty_feedback_does_not_create_an_observation():
    facts = build_report_facts('mock', None, {'operator:feedback': {'records': []}})
    assert not any(f['fact_id'].startswith('operator-feedback:') for f in facts)
