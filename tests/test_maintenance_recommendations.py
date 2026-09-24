"""Synthetic maintenance fixtures; no model, XGSS or SMTP network calls."""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import maintenance_recommendations as maintenance
from app import xgss_research_ai as ai, xgss_research_store as store, research_email
from app.api import routes_xgss_research as routes

VIN = 'XUGTEST000000001'
IDENTITY = {'machine_id': 'fixture-machine', 'dataset_id': 'a' * 64, 'vin': VIN}


def final(response):
    assert response.status_code == 200, response.text
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['type'] == 'result', events
    return events[-1]['record']


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(store, 'STORE', tmp_path / 'research')
    context = {'source': 'trackunit_cache', 'sample_count': 3,
               'last_sample_at': '2026-01-01T00:00:00+00:00',
               'metrics': {'operating_hours': {'value': 419.73, 'unit': 'h',
                   'observed_at': '2026-01-01T00:00:00+00:00', 'age_hours': 200,
                   'stale_after_24h': True}},
               'faults': [{'fault_code': 'OLD-FAULT-999'}]}
    monkeypatch.setattr(routes, '_verify_machine', lambda *a: None)
    monkeypatch.setattr(routes, 'load_dataset', lambda *a: SimpleNamespace(machine=SimpleNamespace(model='XC948U')))
    monkeypatch.setattr(routes, 'loaded_context', lambda *a: context)
    sent = []

    def model(messages, *a, **kw):
        payload = json.loads(messages[1]['content'])
        sent.append(payload)
        assert VIN not in messages[1]['content']
        assert IDENTITY['machine_id'] not in messages[1]['content']
        assert 'OLD-FAULT-999' not in messages[1]['content']
        if 'parts' not in payload:
            return json.dumps({'summary': '结合历史工时，先检查适用滤芯并核对保养记录。',
                'directions': [{'component': '滤清器', 'reason': '核对滤芯使用情况', 'search_terms': ['滤清器', '滤芯']}],
                'missing_evidence': ['上次保养记录']})
        return json.dumps({'summary': '按419.73小时的历史工时筛选滤芯检查候选，保养周期需核实。',
            'parts': [{'source_id': payload['parts'][0]['source_id'], 'part_role': 'maintenance',
                'reason': '滤芯承担过滤作用，应结合工时核对保养记录和堵塞情况。',
                'replacement_condition': '核实适用手册和保养记录，并确认堵塞或损坏后考虑更换。'}],
            'repair_steps': [{'instruction': '核对滤芯保养记录和可见状态。', 'basis': 'ai_inspection_suggestion'}],
            'missing_evidence': ['适用保养周期']})

    monkeypatch.setattr(ai, 'generate_structured_with_deepseek', model)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), context, sent


def start(client, **changes):
    return client.post('/assistant/xgss/research/plan', json={**IDENTITY,
        'analysis_mode': 'maintenance', 'symptom_source': 'user_question', 'symptom': '', **changes})


def add_page(record):
    return store.append(record['research_id'], store.PageCapture(source='xgss_rendered_page',
        source_url='https://xgss.xcmg.com/', vin=VIN, title='测试滤清器图册', assembly_path=['测试动力系统'],
        items=[{'name': '测试滤芯', 'part_number': 'TEST-001', 'figure_ref': '3'}],
        manual_sections=[], coverage='rendered_content_only'))


def test_empty_maintenance_question_and_two_pass_frozen_hours(setup):
    client, context, sent = setup
    planned = final(start(client))
    assert planned['analysis_mode'] == 'maintenance'
    assert '保养件' in planned['symptom']
    assert 'faults' not in planned['machine_context']
    assert planned['maintenance_context']['operating_hours']['value'] == 419.73
    assert planned['maintenance_context']['service_history_status'] == 'unknown'
    assert planned['machine_type'] == '轮式装载机'
    assert sent[0]['machine_type'] == '轮式装载机'
    add_page(planned)
    context['metrics']['operating_hours']['value'] = 999
    result = final(client.post('/assistant/xgss/research/' + planned['research_id'] + '/analyze'))
    assert sent[0]['machine_context'] == sent[1]['machine_context'] == result['machine_context']
    assert sent[1]['maintenance_context']['operating_hours']['value'] == 419.73
    assert result['advice']['parts'][0]['part_number'] == 'TEST-001'
    assert result['advice']['parts'][0]['figure_ref'] == '3'
    restored = client.get('/assistant/xgss/research/' + planned['research_id']).json()
    assert restored['advice'] == result['advice']
    assert len(sent) == 2


@pytest.mark.parametrize('changes', [
    {'fault_event_id': 'b' * 64}, {'source_report_id': 'c' * 64},
    {'symptom_source': 'simulation', 'symptom': '模拟故障现象'},
    {'symptom_source': 'trackunit_event'},
])
def test_maintenance_refuses_fault_associations_before_model(setup, changes):
    client, context, sent = setup
    assert start(client, **changes).status_code == 422
    assert sent == []


def test_empty_fault_question_remains_invalid(setup):
    assert start(setup[0], analysis_mode='fault').status_code == 422
    assert setup[2] == []


def test_known_loader_plan_cannot_claim_machine_type_is_missing():
    plan={'summary':'机型未提供，按通用分类检索。',
          'directions':[{'component':'空滤芯','reason':'核对进气系统','search_terms':['空滤']}],
          'missing_evidence':[]}
    with pytest.raises(ValueError, match='机型类别已确认'):
        maintenance.validate_plan(plan, model='XC948U')


@pytest.mark.parametrize('value, expected', [(None, None), (0, 0), (419.73, 419.73), (-1, None), (True, None), (float('nan'), None)])
def test_hour_context_preserves_zero_and_independent_sampling(value, expected):
    context = maintenance.build_context({'metrics': {'operating_hours': {
        'value': value, 'observed_at': '2020-01-01T00:00:00Z', 'stale_after_24h': True}}})
    assert context['operating_hours']['value'] == expected
    assert context['operating_hours']['observed_at'] == '2020-01-01T00:00:00Z'
    assert context['operating_hours']['stale_after_24h'] is True
    assert context['last_service_hours'] is None
    assert context['interval_status'] == 'unverified'


def test_old_advice_without_new_fields_still_restores(setup):
    planned = final(start(setup[0]))
    add_page(planned)
    record = final(setup[0].post('/assistant/xgss/research/' + planned['research_id'] + '/analyze'))
    record.pop('analysis_mode')
    record.pop('maintenance_context')
    record['advice']['parts'][0].pop('part_role')
    checked = ai.normalize_cached_advice(record)
    assert checked['advice']['parts'][0]['part_role'] == 'repair'


@pytest.mark.parametrize('replacement', ['每500小时更换滤芯。', '再运行80.27小时保养。'])
def test_unsupported_intervals_are_rejected_in_fresh_and_cached_output(setup, replacement):
    planned = final(start(setup[0]))
    add_page(planned)
    record = final(setup[0].post('/assistant/xgss/research/' + planned['research_id'] + '/analyze'))
    record['advice']['parts'][0]['replacement_condition'] = replacement
    with pytest.raises(ValueError, match='周期'):
        ai.normalize_cached_advice(record)


def test_maintenance_roles_and_unread_parts_cannot_bypass_validation(setup):
    planned = final(start(setup[0]))
    add_page(planned)
    record = final(setup[0].post('/assistant/xgss/research/' + planned['research_id'] + '/analyze'))
    record['advice']['parts'][0]['part_role'] = 'repair'
    with pytest.raises(ValueError, match='保养件'):
        ai.normalize_cached_advice(record)
    record['advice']['parts'][0]['part_role'] = 'wear'
    record['advice']['parts'][0]['source_id'] = 'invented'
    with pytest.raises(ValueError, match='未读取'):
        ai.normalize_cached_advice(record)


def test_maintenance_email_describes_hours_and_check_conditions_without_faults(setup):
    planned = final(start(setup[0]))
    add_page(planned)
    record = final(setup[0].post('/assistant/xgss/research/' + planned['research_id'] + '/analyze'))
    subject, body, numbers, path = research_email._body(record, ai.research_evidence(record))
    assert 'AI 工时保养' in subject
    assert '保养依据' in body and '419.73' in body and '2026-01-01' in body
    assert '类别：保养件' in body and '更换条件' in body
    assert '故障背景' not in body and 'OLD-FAULT-999' not in body
    assert '不是到期通知' in body
    assert numbers == ['TEST-001']
