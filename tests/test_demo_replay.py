"""A replay may only be offered for a record that really contains model work.

The scripted demo case is required by its own validator to admit it is a
simulation. This replay is the opposite promise: everything shown about the AI has
to come from a saved run, and a record without model decisions must be refused
rather than dressed up as one.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app import demo_replay
from app.main import app


@pytest.fixture
def history(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_replay, 'HISTORY_DIR', tmp_path)
    return tmp_path


def write_record(directory, record_id, *, decisions=2, dataset_id=None, **report_overrides):
    report = {
        'status': 'completed', 'machine_id': 'M-1', 'source': 'imported_user_supplied',
        'model': 'deepseek-flash', 'provider': 'deepseek', 'inference_location': 'cloud',
        'model_decisions': decisions, 'duration_seconds': 6.44, 'format_repair_attempts': 0,
        'summary': '这是一个测试摘要。',
        'tool_trace': [
            {'action': 'snapshot', 'source_id': 'tool:1:snapshot', 'trigger': 'task_required'},
            {'action': 'parts', 'source_id': 'tool:2:parts', 'trigger': 'model_selected'},
        ],
        'evidence': {'tool:1:snapshot': {}, 'manual:m1': {}},
        'citations': ['tool:1:snapshot', 'manual:m1'],
        'data_facts': [{'text': '事实一'}],
        'parts_candidates': [], 'next_checks': [],
        'check_recommendations': [{'text': 'ECU 供电熔断器：检查熔断器', 'check_id': 'c1'}],
        'component_hypotheses': [
            {'component': 'ECU 供电熔断器', 'status': 'hypothesis_requires_inspection',
             'rationale': '手册列为可能原因', 'search_terms': ['E4030'],
             'reference_ids': ['manual:m1'], 'part_candidate_ids': [],
             'checks': [{'text': '检查熔断器', 'pdf_pages': [286]}]},
        ],
    }
    report.update(report_overrides)
    record = {'schema_version': 1, 'request': {'machine_id': 'M-1', 'question': '排查 E4030',
                                               'dataset_id': dataset_id,
                                               'engineering_fault': {'code': 'E4030', 'model': 'XE55U',
                                                                     'source': 'test', 'configuration': 'XE55U.00III'}},
              'report': report}
    (directory / f'{record_id}.json').write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
    return record


def test_a_replay_says_it_is_a_recording_not_a_live_run(history):
    write_record(history, 'rec1')
    data = demo_replay.build_replay('rec1')
    assert data['kind'] == 'real_ai_replay'
    assert data['is_simulation'] is False
    assert '不是实时推理' in data['disclosure']
    assert '不调用模型' in data['disclosure']


def test_a_record_without_model_decisions_is_refused(history):
    write_record(history, 'plain', decisions=0)
    with pytest.raises(demo_replay.ReplayUnavailable, match='没有模型决策'):
        demo_replay.build_replay('plain')
    # And it is not listed as an available replay either.
    assert demo_replay.list_replays()['records'] == []


def test_the_replay_credits_only_the_reads_the_model_chose(history):
    write_record(history, 'rec1')
    stage = demo_replay.build_replay('rec1')['stages'][0]
    assert stage['origin'] == 'program'
    joined = ' '.join(stage['lines'])
    assert '模型自己选择追加读取：parts' in joined
    assert '其余 1 项由任务规定' in joined, 'task-forced reads must not be credited to the model'


def test_each_hypothesis_keeps_its_manual_page_and_stays_a_direction(history):
    write_record(history, 'rec1')
    stage = next(item for item in demo_replay.build_replay('rec1')['stages'] if item['stage_id'] == 'diagnose')
    assert 'ECU 供电熔断器' in stage['lines'][0]
    assert '手册第 286 页' in stage['lines'][0]
    assert '待核查方向' in stage['note']
    assert '不是已确认故障' in stage['note']


def test_a_format_repair_and_a_missing_catalog_are_disclosed(history):
    write_record(history, 'rec1', format_repair_attempts=1)
    accounting = next(item for item in demo_replay.build_replay('rec1')['stages']
                      if item['stage_id'] == 'accounting')
    joined = ' '.join(accounting['lines'])
    assert '格式修正 1 次' in joined
    assert '没有可展示的备件候选' in joined, 'an empty result must be stated, not implied'


def test_the_model_summary_is_reproduced_verbatim(history):
    write_record(history, 'rec1', summary='原样保留的摘要，含 0 条记录与配置未知。')
    stage = next(item for item in demo_replay.build_replay('rec1')['stages'] if item['stage_id'] == 'summary')
    assert stage['lines'] == ['原样保留的摘要，含 0 条记录与配置未知。']
    assert '原文未改写' in stage['note']


def test_a_test_fault_code_is_marked_as_not_a_reported_event(history):
    write_record(history, 'rec1')
    accounting = next(item for item in demo_replay.build_replay('rec1')['stages']
                      if item['stage_id'] == 'accounting')
    assert any('不代表 Trackunit 上报' in line for line in accounting['lines'])


def test_the_listing_is_newest_first_and_carries_the_disclosure(history):
    write_record(history, 'old', generated_at='2026-09-14T10:00:00Z')
    write_record(history, 'new', generated_at='2026-09-15T10:00:00Z')
    write_record(history, 'no_ai', decisions=0)
    listing = demo_replay.list_replays()
    assert [row['record_id'] for row in listing['records']] == ['new', 'old']
    assert listing['total'] == 2
    assert any('不等于设备实际发生' in line for line in listing['disclosure'])


@pytest.mark.parametrize('record_id', ['', '../escape', 'not/valid', 'x' * 4 + '/../y', None, 123])
def test_malformed_record_ids_are_rejected(history, record_id):
    with pytest.raises(demo_replay.ReplayUnavailable):
        demo_replay.build_replay(record_id)


def test_a_missing_record_is_reported_as_not_found(history):
    with pytest.raises(demo_replay.ReplayUnavailable, match='找不到该记录'):
        demo_replay.build_replay('doesnotexist')


def test_unreadable_records_are_skipped_and_do_not_break_the_listing(history):
    write_record(history, 'good')
    (history / 'broken.json').write_text('{not json', encoding='utf-8')
    listing = demo_replay.list_replays()
    assert [row['record_id'] for row in listing['records']] == ['good']


def test_the_api_exposes_replay_without_running_anything(history):
    write_record(history, 'rec1')
    client = TestClient(app)
    listing = client.get('/assistant/demo-replay')
    assert listing.status_code == 200
    assert listing.headers['cache-control'] == 'no-store'
    assert listing.json()['total'] == 1

    detail = client.get('/assistant/demo-replay/rec1')
    assert detail.status_code == 200
    assert detail.json()['kind'] == 'real_ai_replay'

    assert client.get('/assistant/demo-replay/plain').status_code == 404
    assert client.get('/assistant/demo-replay/nope').status_code == 404


# The evidence pack is the artefact a reviewer keeps, so its structure matters as
# much as its content. A joined bullet string once collapsed the whole document to
# one character per line; these tests fail loudly if that returns.
def pack_for(history, record_id='rec1', **overrides):
    write_record(history, record_id, **overrides)
    data = demo_replay.build_replay(record_id)
    return demo_replay.render_replay_report(data)


def test_the_pack_is_real_markdown_not_one_character_per_line(history):
    text, filename = pack_for(history)
    lines = text.split('\n')
    assert filename == 'jilian-ai-replay-rec1.md'
    # A sane document: headings are whole lines, and no line is a lone character.
    assert any(line.startswith('# ') for line in lines)
    assert sum(1 for line in lines if line.strip()) < 200, 'the pack must not explode into single characters'
    assert not [line for line in lines if len(line.strip()) == 1 and line.strip() not in '-,>'], \
        'a lone character on its own line means the bullet list was joined instead of extended'
    assert '- 记录编号：rec1' in text


def test_the_pack_leads_with_the_disclosure_and_ends_with_the_limits(history):
    text, _ = pack_for(history)
    assert '不是实时推理' in text.split('\n')[2]
    assert '本次运行没有确立的事情' in text
    assert '不代表诊断准确率' in text
    assert '不代表它已损坏' in text


def test_the_pack_separates_ai_work_from_program_work(history):
    text, _ = pack_for(history)
    assert '模型自己选择的读取：parts' in text
    assert '不计入模型的选择' in text
    assert '### 程序侧（不计入 AI 贡献）' in text


def test_the_pack_carries_manual_grounding_and_search_terms(history):
    text, _ = pack_for(history)
    assert '### ECU 供电熔断器' in text
    assert '手册第 286 页' in text
    assert '图册检索词：E4030' in text
    assert 'manual:m1' in text


def test_the_pack_discloses_a_format_repair_and_an_empty_catalog(history):
    text, _ = pack_for(history, format_repair_attempts=2)
    assert '格式修正 2 次' in text
    assert '备件候选 0 条' in text


def test_the_pack_keeps_the_model_summary_verbatim(history):
    text, _ = pack_for(history, summary='原样摘要：空记录不能证明设备健康。')
    assert '原样摘要：空记录不能证明设备健康。' in text


def test_the_pack_api_serves_a_download_with_a_safe_filename(history):
    write_record(history, 'rec1')
    client = TestClient(app)
    response = client.get('/assistant/demo-replay/rec1/report.md')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/markdown')
    disposition = response.headers['content-disposition']
    assert 'attachment;' in disposition and 'jilian-ai-replay-rec1.md' in disposition
    assert '/' not in disposition.split('filename=')[1]
    assert '# 机联智检 · AI 排查证据包' in response.text
    # A record that cannot be replayed must not produce a pack either.
    write_record(history, 'plain', decisions=0)
    assert client.get('/assistant/demo-replay/plain/report.md').status_code == 404


def test_every_bullet_helper_call_is_extended_not_appended():
    # _bullets returns a list, so appending it puts a list inside the document and
    # '\n'.join then fails. This was written wrong twice; the source is checked
    # directly so a third time cannot reach a release.
    import re
    from pathlib import Path
    source = Path(demo_replay.__file__).read_text(encoding='utf-8')
    assert re.findall(r'lines\.append\(_bullets', source) == [], \
        'use lines.extend(_bullets(...)) so bullet lines stay separate strings'


def test_the_pack_carries_the_citation_audit(history):
    text, _ = pack_for(history)
    assert '## 依据核对' in text
    assert '全部指向已读取的证据，没有悬空引用' in text
    assert '带检查方向的部件 1 个' in text


def test_the_pack_surfaces_a_dangling_reference_instead_of_hiding_it(history):
    # A conclusion citing material that does not exist is the worst defect a
    # diagnostic report can carry, so the pack names it instead of staying quiet.
    # The override goes through pack_for: writing the record separately would be
    # overwritten by pack_for's own write and the test would pass on a clean pack.
    text, _ = pack_for(history, citations=['tool:1:snapshot', 'manual:ghost'])
    assert '悬空：citations → manual:ghost' in text
    assert '找不到对应证据' in text


def test_the_audit_travels_with_the_replay_payload(history):
    write_record(history, 'rec1')
    audit = demo_replay.build_replay('rec1')['ai_contribution']['audit']
    assert audit['verdict'] == 'all_references_resolved'
    assert audit['checked'] > 0


# A report's `model` field is the AI model, not the machine. Showing
# "deepseek-flash" under 设备 would be a real misreading, so the two are named
# separately and the machine name is resolved from the dataset when possible.
def test_the_machine_and_the_ai_model_are_named_separately(history):
    write_record(history, 'rec1', model='deepseek-flash')
    record = demo_replay.build_replay('rec1')['record']
    assert record['ai_model'] == 'deepseek-flash'
    assert record['machine_model'] != record['ai_model']
    assert 'model' not in record, 'the ambiguous combined field must be gone'


def test_the_machine_name_comes_from_the_local_dataset_when_available(history, monkeypatch):
    class Machine:
        model = 'XE55U'
        serial_number = 'XUGC055UARKA02003'
    # Patch the name demo_replay actually calls: it imported load_dataset into its
    # own namespace, so patching app.local_datasets would have no effect.
    monkeypatch.setattr(demo_replay, 'load_dataset', lambda _: type('D', (), {'machine': Machine})())
    write_record(history, 'rec1', dataset_id='b' * 64)
    record = demo_replay.build_replay('rec1')['record']
    assert record['machine_model'] == 'XE55U'
    assert record['machine_serial'] == 'XUGC055UARKA02003'


def test_a_missing_dataset_leaves_the_machine_name_empty_rather_than_guessed(history, monkeypatch):
    def explode(_):
        raise OSError('dataset gone')
    monkeypatch.setattr(demo_replay, 'load_dataset', explode)
    write_record(history, 'rec1', dataset_id='c' * 64)
    record = demo_replay.build_replay('rec1')['record']
    # The AI model must never be substituted for the machine.
    assert record['machine_model'] is None
    assert record['ai_model'] == 'deepseek-flash'


def test_the_listing_carries_a_readable_machine_and_the_ai_model(history):
    write_record(history, 'rec1', model='deepseek-flash')
    row = demo_replay.list_replays()['records'][0]
    assert row['ai_model'] == 'deepseek-flash'
    assert 'model' not in row
    assert 'machine_model' in row and 'machine_serial' in row


def test_the_pack_keeps_the_full_identifiers_for_traceability(history):
    # The screen shortens identifiers; the exported pack must not, or a reviewer
    # could not trace a conclusion back to the record it came from.
    text, _ = pack_for(history, record_id='identity', dataset_id='d' * 64)
    assert 'd' * 64 in text
    assert '记录编号：identity' in text
    assert '设备：M-1' in text
