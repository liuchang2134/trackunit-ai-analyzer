"""Unsupported maintenance claims: synthetic records and mocked model output only."""
import copy
import json

import pytest

from app import maintenance_recommendations as maintenance
from app import xgss_research_ai as ai, xgss_research_store as store


VIN = 'XUGTEST000000001'
PLAN = {'summary': '结合历史工时核对滤芯状态和保养记录。',
        'directions': [{'component': '滤清器', 'reason': '先核对保养记录与堵塞情况。',
                        'search_terms': ['滤清器', '滤芯']}],
        'missing_evidence': ['适用保养周期', '上次保养记录']}


@pytest.mark.parametrize('claim', [
    '每500小时更换滤芯。', '再运行80.27小时保养。',
    '建议在500小时更换滤芯。', '达到500工时应安排保养。',
    '建议500h保养。', '保养已到期，应更换滤芯。',
    '滤芯已经超期。', '预计即将到期。',
])
def test_common_unsupported_periods_and_due_claims_are_rejected(claim):
    with pytest.raises(ValueError, match='周期'):
        maintenance.validate_prose([claim])


@pytest.mark.parametrize('text', [
    '不能按每500小时更换滤芯。',
    '无法判断是否已经到期。',
    '现有工时不足以认定保养已到期。',
    '尚未确认每500小时更换的周期是否适用。',
    '每500小时的周期尚未核实。',
    '建议核对滤芯是否已经到期。',
    '累计工时419.73小时，应先检查保养记录和可见状态。',
    '具体保养周期和上次保养工时未知，不能判断是否到期。',
])
def test_explicit_uncertainty_and_observed_hours_remain_valid(text):
    maintenance.validate_prose([text])


@pytest.mark.parametrize('text', [
    '无法判断是否已经到期，但建议在500小时更换滤芯。',
    '上次保养记录尚未核实；每500小时更换滤芯。',
    '不能按通用周期判断，因此建议500h保养。',
])
def test_earlier_disclaimer_does_not_hide_an_affirmative_schedule(text):
    with pytest.raises(ValueError, match='周期'):
        maintenance.validate_prose([text])


@pytest.mark.parametrize('field', ['summary', 'component', 'reason', 'search_terms', 'missing_evidence'])
def test_plan_validates_every_model_authored_text_field(field):
    plan = copy.deepcopy(PLAN)
    claim = '建议在500小时更换滤芯。'
    if field == 'summary':
        plan[field] = claim
    elif field == 'missing_evidence':
        plan[field] = [claim]
    elif field == 'search_terms':
        plan['directions'][0][field] = [claim]
    else:
        plan['directions'][0][field] = claim
    with pytest.raises(ValueError, match='周期'):
        maintenance.validate_plan(plan)


@pytest.fixture
def local_model(monkeypatch, tmp_path):
    monkeypatch.setattr(store, 'STORE', tmp_path / 'research')
    calls = []
    output = {'value': copy.deepcopy(PLAN)}

    def model(messages, *args, **kwargs):
        calls.append(json.loads(messages[1]['content']))
        return json.dumps(output['value'], ensure_ascii=False)

    monkeypatch.setattr(ai, 'generate_structured_with_deepseek', model)
    return output, calls


def start():
    return ai.plan('fixture-machine', 'a' * 64, VIN, 'XC948U',
                   ai.Symptom(symptom=maintenance.default_question(), symptom_source='user_question'),
                   machine_context={'metrics': {'operating_hours': {
                       'value': 419.73, 'observed_at': '2020-01-01T00:00:00Z',
                       'unit': 'h', 'stale_after_24h': True}}}, analysis_mode='maintenance')


def add_page(record):
    return store.append(record['research_id'], store.PageCapture(
        source='xgss_rendered_page', source_url='https://xgss.xcmg.com/', vin=VIN,
        title='测试滤清器图册', items=[{'name': '测试滤芯', 'part_number': 'TEST-001'}],
        manual_sections=[], coverage='rendered_content_only'))


def draft(record):
    source_id = store.evidence(record)['parts'][0]['source_id']
    return {'summary': '按历史工时核对保养记录，无法判断是否已经到期。',
            'parts': [{'source_id': source_id, 'part_role': 'maintenance',
                       'reason': '滤芯承担过滤作用，应核对保养记录与堵塞情况。',
                       'replacement_condition': '核实适用周期和保养记录后决定是否更换。'}],
            'repair_steps': [{'instruction': '检查滤芯可见状态并核对保养记录。',
                              'basis': 'ai_inspection_suggestion'}],
            'missing_evidence': ['适用保养周期', '上次保养记录']}


def test_first_model_plan_with_unsupported_period_is_not_saved(local_model):
    output, calls = local_model
    output['value']['summary'] = '建议在500小时更换滤芯。'
    with pytest.raises(ValueError, match='周期'):
        start()
    assert len(calls) == 2  # One bounded correction; both invalid drafts stay unsaved.
    assert not list(store.STORE.glob('*.json'))


def test_first_advice_with_unsupported_period_is_not_saved(local_model):
    output, calls = local_model
    record = add_page(start())
    output['value'] = draft(record)
    output['value']['parts'][0]['replacement_condition'] = '建议500h保养。'
    with pytest.raises(ValueError, match='周期'):
        ai.analyze(record['research_id'])
    assert len(calls) == 3  # Plan plus two bounded advice attempts.
    assert 'advice' not in store.read(record['research_id'])
    assert record['research_id'] not in ai.BUSY


def test_negated_due_claim_survives_both_passes_and_cache(local_model):
    output, calls = local_model
    output['value']['summary'] = '历史工时不能证明保养已到期，先核对滤芯保养记录。'
    record = add_page(start())
    output['value'] = draft(record)
    analyzed = ai.analyze(record['research_id'])
    restored = ai.normalize_cached_advice(store.read(record['research_id']))
    assert restored['advice'] == analyzed['advice']
    assert len(calls) == 2
