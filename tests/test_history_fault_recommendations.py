"""Historical suggestions stay source-bound and separate from current preparation."""
from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from app import fault_part_grounding as gate
from app import xgss_research_ai as ai
from app import xgss_research_store as store

VIN = 'XUGTEST000000001'
ASSET = '00000000-0000-0000-0000-000004760361'
MACHINE = 'local-machine-not-the-asset'
PAGE_ID = 'private-visible-row-id'
CAPTURE = 'a' * 64
SOURCE = 'xpart:' + CAPTURE + ':0'
IMAGE = 'b' * 64
PATH = ['XC948.00', '双变系统', '变速箱总成']


def event(status='CLOSED', description='Transmission / Manufacturer assignable SPN / Abnormal Update Rate'):
    return {'asset_id': ASSET, 'source_url': f'https://new.manager.trackunit.com/assets/{ASSET}/events',
            'page_event_id': PAGE_ID, 'description': description, 'code': '', 'spn': None, 'fmi': None, 'sa': None,
            'status': status, 'occurred_at': 'June 29, 2026, 9:06 AM', 'cleared_at': None,
            'observed_at': '2026-09-24T09:00:00Z', 'source': 'trackunit_visible_events_page',
            'coverage': 'selected_visible_event_only'}


def selected(status='CLOSED', **changes):
    return {'symptom': '页面所选变速箱通讯更新率异常，数字故障码未显示。', 'symptom_source': 'trackunit_page',
            'fault_context': {'trackunit_page': event(status), 'operator_supplement': '', 'manuals': []}, **changes}


def choice(source_id=SOURCE, **changes):
    return {'source_id': source_id, 'reason': '同系统部件，复发后核对实际线路及故障节点。',
            'replacement_condition': '复发时先排除供电、接地、线缆与配置问题，再确认该部件失效及适配后列入准备。',
            'fault_relation': 'direct', 'support': 'catalog_only', **changes}


def catalog(name='工作机线缆', **changes):
    return {'source_id': SOURCE, 'name': name, 'part_number': 'TEST-123', 'figure_ref': '8',
            'assembly_path': PATH, 'capture_id': CAPTURE, **changes}


def advice(choices=None):
    return ai.FaultAdvice.model_validate({'summary': '所选历史通讯事件已解除，以下为复发备件参考，须先核对线路。',
        'parts': [choice()] if choices is None else choices,
        'repair_steps': [{'instruction': '复发时先检查线缆与连接状态，再核对节点供电、接地和配置。',
                          'basis': 'ai_inspection_suggestion'}], 'missing_evidence': []})


def qualify(rows=None, record=None, choices=None):
    record = record or selected()
    checked = ai.validate_advice(advice(choices), rows or [catalog()], [], model='XC948U',
        symptom=record['symptom'], fault_context=record['fault_context'])
    return gate.qualify(checked, record, [])


def test_closed_selected_page_without_numeric_code_still_has_historical_spare_reference():
    result = qualify()
    assert result['analysis_scope'] == 'historical'
    assert result['parts'] == result['inspection_targets'] == []
    reference = result['historical_candidates'][0]
    assert reference['part_number'] == 'TEST-123' and reference['status'] == 'historical_reference'
    assert reference['preparation_condition'] == reference['replacement_condition']


@pytest.mark.parametrize('status', ['OPEN', 'UNKNOWN'])
def test_current_or_unknown_selected_page_does_not_borrow_resolved_machine_history(status):
    record = selected(status, machine_context={'faults': [event('CLOSED')]})
    result = qualify(record=record)
    assert result['analysis_scope'] == 'current'
    assert result['historical_candidates'] == result['parts'] == []
    assert result['inspection_targets'][0]['name'] == '工作机线缆'


def test_closed_selected_page_does_not_become_current_from_another_active_power_event():
    record = selected(machine_context={'faults': [{'spn': 444, 'fmi': 1, 'sa': 163, 'status': 'OPEN'}]})
    assert qualify(record=record)['analysis_scope'] == 'historical'
    assert not qualify([catalog('蓄电池')], record=record)['historical_candidates']


@pytest.mark.parametrize('description', ['Transmission / Abnormal Update Rate',
    'Transmission / AbnormalUpdateRate', 'Transmission / Abnormal-Update-Rate', '变速箱通讯异常'])
@pytest.mark.parametrize('name', ['蓄电池', '电源继电器', '保险盒'])
def test_history_communication_never_recommends_unrelated_power_parts(description, name):
    record = selected(symptom='页面所选历史事件。')
    record['fault_context']['trackunit_page']['description'] = description
    result = qualify([catalog(name)], record=record)
    assert result['parts'] == result['inspection_targets'] == result['historical_candidates'] == []


@pytest.mark.parametrize('name', ['控制器', 'TCU', '变速箱控制单元', '控制单元', 'Transmission Control Unit'])
def test_catalog_bound_transmission_node_is_later_reference_not_current_preparation(name):
    result = qualify([catalog(name)])
    assert result['parts'] == result['inspection_targets'] == []
    assert result['historical_candidates'][0]['evidence_level'] == 'historical_reference'
    assert result['historical_candidates'][0]['assembly_path'] == PATH


@pytest.mark.parametrize('path', [['驾驶室电气'], ['冷却系统'], []])
def test_controller_name_without_real_transmission_catalog_path_does_not_map(path):
    result = qualify([catalog('变速箱控制器', assembly_path=path)])
    assert result['historical_candidates'] == []


@pytest.mark.parametrize('name', ['发动机控制单元', 'Control Unit', 'TCU'])
def test_control_unit_synonyms_do_not_bypass_the_catalog_system_boundary(name):
    assert qualify([catalog(name, assembly_path=['发动机系统'])])['historical_candidates'] == []


@pytest.mark.parametrize('status', ['CLOSED', 'OPEN'])
@pytest.mark.parametrize('field', ['reason', 'replacement_condition'])
def test_no_current_qualified_part_means_unconditional_replacement_in_candidate_text_is_rejected(status, field):
    with pytest.raises(ValueError, match='尚无部件故障依据'):
        qualify([catalog('控制单元')], record=selected(status),
                choices=[choice(**{field: '建议更换控制单元。'})])


@pytest.mark.parametrize('field', ['reason', 'replacement_condition'])
@pytest.mark.parametrize('text', [
    '不建议更换控制单元，应先核对供电、接地及线缆。',
    '不要直接更换控制单元。',
    '若复发并排除供电、接地、线缆及配置问题，确认该控制单元损坏后，建议更换适配部件。',
])
def test_negative_and_conditional_history_candidate_wording_remains_usable(field, text):
    result = qualify([catalog('控制单元')], choices=[choice(**{field: text})])
    assert result['historical_candidates'][0][field] == text
    assert result['parts'] == []


def test_current_component_observation_that_already_qualifies_is_not_invalidated():
    quote = '检查确认变速箱控制单元外壳破损。'
    record = selected('OPEN', symptom=quote, symptom_source='operator_report')
    result = qualify([catalog('变速箱控制单元')], record=record, choices=[choice(
        support='component_observation', support_quote=quote,
        reason='该控制单元的破损已有现场检查记录。',
        replacement_condition='核对同 VIN 适配及故障回路，排除其他原因并确认损坏后，建议更换该控制单元。')])
    assert result['parts'][0]['evidence_level'] == 'conditional_candidate'
    assert result['historical_candidates'] == []


def test_model_prose_cannot_relabel_an_actual_power_row_as_a_transmission_node():
    result = qualify([catalog('蓄电池', assembly_path=['后车架电气'])],
        choices=[choice(reason='这个条目是变速箱控制器，属于通讯节点。')])
    assert result['historical_candidates'] == result['parts'] == []
    with pytest.raises(ValidationError):
        advice([choice(name='变速箱控制器', assembly_path=PATH)])
    with pytest.raises(ValueError, match='未读取的备件'):
        qualify(choices=[choice(source_id='unread-catalog-row')])


def cached_record():
    record = {'research_id': 'c' * 32, 'machine_id': MACHINE, 'vin': VIN, 'model': 'XC948U',
              'dataset_id': 'd' * 64, 'revision': 1, 'analysis_revision': 1,
              'analysis_mode': 'fault', 'advice_quality_version': gate.VERSION, **selected()}
    record['pages'] = [{'capture_id': CAPTURE, 'captured_at': '2026-09-24T09:10:00Z',
        'content': {'source': 'xgss_rendered_page', 'source_url': 'https://xgss.xcmg.com/', 'vin': VIN,
            'title': '合成变速箱图册', 'assembly_path': PATH, 'items': [{'name': '控制器',
            'part_number': 'TEST-123', 'figure_ref': '8', 'quantity': '1'}],
            'manual_sections': [], 'coverage': 'rendered_content_only'},
        'illustrations': [{'image_id': IMAGE, 'title': '合成变速箱图示', 'document_ref': 'fixture.svg',
                          'width': 200, 'height': 200, 'captured_at': '2026-09-24T09:10:00Z'}]}]
    sources = ai.research_evidence(record)
    record['advice'] = qualify(sources['parts'], record=record)
    return record


def test_restore_rebuilds_historical_part_identity_and_image_binding_from_catalog(monkeypatch):
    record = cached_record()
    forged = record['advice']['historical_candidates'][0]
    forged.update(name='伪造电源', part_number='FAKE-999', capture_id='fake-capture',
                  assembly_path=['其他系统'], figure_ref='999', image_url='https://attacker.example/fake.png')
    before = deepcopy(record)
    monkeypatch.setattr(ai, 'generate_structured_with_deepseek', lambda *a, **k: pytest.fail('No model on restore'))
    restored = ai.normalize_cached_advice(record)
    row = restored['advice']['historical_candidates'][0]
    assert (row['name'], row['part_number'], row['capture_id'], row['figure_ref']) == ('控制器', 'TEST-123', CAPTURE, '8')
    assert row['assembly_path'] == PATH and 'image_url' not in row
    bound = next(p for p in restored['pages'] if p['capture_id'] == row['capture_id'])
    assert bound['illustrations'][0]['image_id'] == IMAGE
    assert restored['advice']['parts'] == []
    assert ai.normalize_cached_advice(restored)['advice'] == restored['advice']
    assert record == before


def test_old_resolved_inspection_cache_migrates_to_history_without_billed_analysis(monkeypatch):
    record = cached_record()
    row = record['advice']['historical_candidates'].pop()
    row.update(status='inspection_only', evidence_level='inspection_only')
    record['advice']['inspection_targets'] = [row]
    record['advice'].pop('analysis_scope', None)
    monkeypatch.setattr(ai, 'generate_structured_with_deepseek', lambda *a, **k: pytest.fail('No model on migration'))
    restored = ai.normalize_cached_advice(record)
    assert restored['advice']['analysis_scope'] == 'historical'
    assert len(restored['advice']['historical_candidates']) == 1
    assert restored['advice']['parts'] == restored['advice']['inspection_targets'] == []


def test_forged_cached_node_name_cannot_override_actual_non_node_source():
    record = cached_record()
    record['pages'][0]['content']['assembly_path'] = ['后车架电气']
    record['pages'][0]['content']['items'][0]['name'] = '蓄电池'
    restored = ai.normalize_cached_advice(record)
    assert restored['advice']['historical_candidates'] == []


def test_both_model_passes_project_page_identity_out_and_keep_history_state(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(store, 'STORE', tmp_path / 'research')
    def model(messages, *args, **kwargs):
        data = json.loads(messages[1]['content']); sent.append(data)
        if 'parts' not in data:
            return json.dumps({'summary': '页面历史通讯事件已解除，检索复发时需核查的部件。',
                'directions': [{'component': '变速箱线缆', 'reason': '通讯异常需要核对同系统线路。',
                                'search_terms': ['变速箱 线缆']}], 'missing_evidence': []})
        return json.dumps(advice([choice(source_id=data['parts'][0]['source_id'])]).model_dump())
    monkeypatch.setattr(ai, 'generate_structured_with_deepseek', model)
    context = selected()['fault_context']
    context['operator_supplement'] = VIN + ' ' + MACHINE + ' https://private.example/?token=secret'
    frozen = deepcopy(context)
    planned = ai.plan(MACHINE, 'd' * 64, VIN, 'XC948U',
        ai.Symptom(symptom='所选变速箱历史通讯记录已解除，复发时准备哪些部件？', symptom_source='trackunit_page'),
        fault_context=context)
    captured = store.PageCapture(source='xgss_rendered_page', source_url='https://xgss.xcmg.com/', vin=VIN,
        title='合成同机变速箱图册', assembly_path=PATH, items=[{'name': '工作机线缆', 'part_number': 'TEST-123'}],
        coverage='rendered_content_only')
    store.append(planned['research_id'], captured)
    analyzed = ai.analyze(planned['research_id'])
    assert analyzed['advice']['analysis_scope'] == 'historical'
    assert len(sent) == 2
    for data in sent:
        serialized = json.dumps(data)
        for secret in (VIN, MACHINE, ASSET, PAGE_ID, 'private.example', 'source_url', 'asset_id', 'page_event_id'):
            assert secret not in serialized
        visible = data['fault_context']['trackunit_page']
        assert visible['status'] == 'CLOSED' and visible['occurred_at'] == frozen['trackunit_page']['occurred_at']
        assert visible['spn'] is None and visible['description'] == frozen['trackunit_page']['description']
    assert analyzed['fault_context'] == frozen
