"""The grounding report is the artefact that lets someone else re-check the claim.

It must therefore be reproducible from records alone, must keep program-only runs
out of the AI figures, and must never read as an accuracy claim.
"""
import json

from app.ai_grounding_report import build_report, render_markdown


def write_record(directory, record_id, *, decisions=2, citations=None, evidence=None,
                 hypotheses=None, format_repairs=0, duration=6.0, model='deepseek-flash'):
    report = {
        'status': 'completed', 'machine_id': 'M-1', 'source': 'imported_user_supplied',
        'model': model, 'provider': 'deepseek', 'generated_at': '2026-09-15T10:00:00Z',
        'model_decisions': decisions, 'duration_seconds': duration,
        'format_repair_attempts': format_repairs,
        'summary': 's',
        'tool_trace': [
            {'action': 'snapshot', 'source_id': 'tool:1:snapshot', 'trigger': 'task_required'},
            {'action': 'parts', 'source_id': 'tool:2:parts', 'trigger': 'model_selected'},
        ],
        'evidence': evidence if evidence is not None else {'tool:1:snapshot': {}, 'manual:m1': {}},
        'citations': citations if citations is not None else ['tool:1:snapshot', 'manual:m1'],
        'data_facts': [{'text': 'f'}], 'parts_candidates': [], 'next_checks': [],
        'component_hypotheses': hypotheses if hypotheses is not None else [
            {'component': 'A', 'reference_ids': ['manual:m1'],
             'checks': [{'text': 'x', 'evidence_ids': ['manual:m1']}]},
        ],
    }
    (directory / f'{record_id}.json').write_text(
        json.dumps({'schema_version': 1, 'request': {'machine_id': 'M-1', 'question': 'q'},
                    'report': report}, ensure_ascii=False), encoding='utf-8')


def test_only_runs_with_model_decisions_enter_the_ai_figures(tmp_path):
    write_record(tmp_path, 'ai1')
    write_record(tmp_path, 'ai2')
    write_record(tmp_path, 'plain1', decisions=0, citations=['tool:1:snapshot'],
                 hypotheses=[], format_repairs=0)
    write_record(tmp_path, 'plain2', decisions=0, citations=['tool:1:snapshot'], hypotheses=[])
    data = build_report(tmp_path)
    totals = data['totals']
    assert totals['records_total'] == 4
    assert totals['records_with_model'] == 2
    assert totals['records_without_model'] == 2
    # The program-only runs must not contribute references or decisions.
    assert totals['model_decisions'] == 4
    # Each AI run checks 2 citations + 1 hypothesis reference + 1 check evidence id.
    assert totals['checked'] == 8, 'program-only runs must not contribute references'
    assert [row['record_id'] for row in data['runs']] == ['ai1', 'ai2']


def test_dangling_references_reduce_the_resolved_count(tmp_path):
    write_record(tmp_path, 'bad', citations=['tool:1:snapshot', 'manual:ghost'])
    totals = build_report(tmp_path)['totals']
    assert totals['checked'] == 4 and totals['resolved'] == 3
    assert totals['dangling'] == 1
    assert totals['all_references_resolved'] is False


def test_a_clean_run_reports_all_references_resolved(tmp_path):
    write_record(tmp_path, 'good')
    totals = build_report(tmp_path)['totals']
    assert totals['dangling'] == 0 and totals['all_references_resolved'] is True


def test_unreadable_and_shapeless_files_are_counted_not_fatal(tmp_path):
    write_record(tmp_path, 'good')
    (tmp_path / 'broken.json').write_text('{not json', encoding='utf-8')
    (tmp_path / 'shapeless.json').write_text(json.dumps({'no': 'report'}), encoding='utf-8')
    data = build_report(tmp_path)
    assert data['totals']['records_total'] == 1
    assert data['totals']['unreadable_records'] == 2


def test_hypotheses_without_a_check_direction_are_totalled(tmp_path):
    write_record(tmp_path, 'a', hypotheses=[
        {'component': 'A', 'reference_ids': ['manual:m1'], 'checks': []},
        {'component': 'B', 'reference_ids': ['manual:m1'], 'checks': [{'text': 'x', 'evidence_ids': []}]},
    ])
    assert build_report(tmp_path)['totals']['hypotheses_without_checks'] == 1


def test_durations_are_reported_as_a_range_not_a_benchmark(tmp_path):
    write_record(tmp_path, 'fast', duration=3.5)
    write_record(tmp_path, 'slow', duration=12.5)
    totals = build_report(tmp_path)['totals']
    assert totals['duration_seconds_min'] == 3.5
    assert totals['duration_seconds_max'] == 12.5
    assert 'durations' not in totals


def test_evidence_families_are_aggregated_across_runs(tmp_path):
    write_record(tmp_path, 'a')
    write_record(tmp_path, 'b')
    families = build_report(tmp_path)['totals']['evidence_by_family']
    assert families == {'manual': 2, 'tool': 2}


def test_format_repairs_are_totalled_rather_than_hidden(tmp_path):
    write_record(tmp_path, 'a', format_repairs=1)
    write_record(tmp_path, 'b', format_repairs=1)
    assert build_report(tmp_path)['totals']['format_repairs'] == 2


def test_an_empty_directory_yields_zeros_not_an_error(tmp_path):
    data = build_report(tmp_path)
    assert data['totals']['records_total'] == 0
    assert data['totals']['checked'] == 0
    assert data['totals']['all_references_resolved'] is True, 'zero dangling over zero references'
    assert data['runs'] == []


def test_the_report_states_that_it_is_not_an_accuracy_claim(tmp_path):
    write_record(tmp_path, 'a')
    data = build_report(tmp_path)
    boundaries = ' '.join(data['boundaries'])
    assert '不是诊断正确率' in boundaries
    assert '不作任何准确率声明' in boundaries
    assert '样本量很小' in boundaries
    markdown = render_markdown(data)
    assert '不是诊断正确率' in markdown


def test_the_markdown_lists_every_run_and_its_counts(tmp_path):
    write_record(tmp_path, 'a', duration=3.5)
    write_record(tmp_path, 'b', decisions=3, duration=12.5, format_repairs=1)
    markdown = render_markdown(build_report(tmp_path))
    assert '|记录|模型|决策|自选读取|部件|检查|引用核对|悬空|格式修正|' in markdown
    assert '|a|deepseek-flash|2|1|1|1|4|0|0|' in markdown
    assert '|b|deepseek-flash|3|1|1|1|4|0|1|' in markdown
    assert '扫描记录 2 条' in markdown


def test_the_report_is_json_serialisable(tmp_path):
    write_record(tmp_path, 'a')
    json.dumps(build_report(tmp_path))
