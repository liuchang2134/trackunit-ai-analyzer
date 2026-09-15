"""Manual OEM definitions stay separate from telemetry and survive the report loop.

The optional installed user reference is read locally; all AI transport is mocked.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import fault_reference, inspection_feedback, investigation_history
from app import local_assistant as agent
from app.gemini_client import GeminiError
from app.main import app
from app.models import FaultCode, Machine


@pytest.fixture
def setup(monkeypatch, tmp_path):
    reference_path = Path(fault_reference.REFERENCE_PATH)
    if not reference_path.is_file():
        pytest.skip('The private user-supplied TV12U reference is not installed')
    raw = json.loads(reference_path.read_text(encoding='utf-8-sig'))
    raw['source_path'] = 'C:/PRIVATE_TEST_SOURCE/DO_NOT_EXPOSE.xlsx'
    raw['raw_fault_sheet'] = {'private': 'DO_NOT_EXPOSE'}
    installed = tmp_path / 'reference.json'
    installed.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setenv('TV12U_FAULT_REFERENCE_PATH', str(installed))
    monkeypatch.setenv('AI_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_API_KEY', 'fake-unit-test-key')
    monkeypatch.setattr(investigation_history, 'HISTORY_DIR', tmp_path / 'history')
    monkeypatch.setattr(inspection_feedback, 'FEEDBACK_DIR', tmp_path / 'feedback')
    machine = Machine(machine_id='UNIT-TV12U', serial_number='UNIT-SERIAL', model='TV12U',
                      machine_type='skid_steer_loader', customer='fixture', location='fixture',
                      last_seen_at='2026-01-01T00:00:00Z')
    events = []
    monkeypatch.setattr(agent, 'find_machine', lambda _: machine)
    monkeypatch.setattr(agent, 'find_telemetry', lambda _: [])
    monkeypatch.setattr(agent, 'find_faults', lambda _: events)
    monkeypatch.setattr(agent, 'get_data_source', lambda: 'trackunit_cache')

    def forbidden(*args, **kwargs):
        pytest.fail('External or unexpected model call is forbidden')
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    monkeypatch.setattr(agent, 'generate_structured_with_gemini', forbidden)
    return {'client': TestClient(app), 'machine': machine, 'events': events,
            'reference_path': installed, 'raw_reference': raw}


def payload(**changes):
    result = {'machine_id': 'UNIT-TV12U', 'question': '请解释人工填报的故障代码。',
              'task': 'overview', 'language': 'zh', 'manual_fault': {
                  'code': 'H10101', 'model': 'TV12U', 'version': '260224',
                  'applicability_confirmed': True}}
    result.update(changes)
    return result


def transport(monkeypatch, *, omit_manual=False):
    captured = []

    def generate(messages, schema, **kwargs):
        captured.append(deepcopy(messages))
        props = schema['properties']
        if 'finish' not in props['action']['enum']:
            assert 'parts' in props['action']['enum']
            return json.dumps({'action': 'parts', 'component': '', 'summary': '',
                               'evidence_ids': [], 'next_check_ids': []})
        refs = props['evidence_ids']['items']['enum']
        checks = props['next_check_ids']['items']['enum']
        if omit_manual:
            refs = [ref for ref in refs if ref != 'operator:manual-fault']
        return json.dumps({'action': 'finish', 'component': '',
                           'summary': '人工报告 H10101，原表描述左泵前进比例阀短路；是否仍显示及实际原因尚待核实。',
                           'evidence_ids': refs,
                           'next_check_ids': [c for c in checks if c in {
                               'check:manual-fault', 'check:catalog-gap'}]}, ensure_ascii=False)
    monkeypatch.setattr(agent, 'generate_structured_with_gemini', generate)
    return captured


@pytest.mark.parametrize('changes', [
    {'code': 'H99999'}, {'code': 'SPN10101'}, {'model': 'XE55U'},
    {'version': '250224'}, {'applicability_confirmed': False},
    {'applicability_confirmed': None}, {'applicability_confirmed': 'true'},
    {'applicability_confirmed': 1}, {'applicability_confirmed': 1.0},
])
def test_invalid_or_unconfirmed_manual_fault_is_rejected_before_ai(setup, changes):
    request = payload()
    request['manual_fault'].update(changes)
    response = setup['client'].post('/assistant/investigate', json=request)
    assert response.status_code == 422
    assert not list(investigation_history.HISTORY_DIR.glob('*.json'))


def test_missing_confirmation_and_wrong_device_model_rejected_before_ai(setup):
    request = payload()
    del request['manual_fault']['applicability_confirmed']
    assert setup['client'].post('/assistant/investigate', json=request).status_code == 422
    setup['machine'].model = 'XE55U'
    response = setup['client'].post('/assistant/investigate', json=payload())
    assert response.status_code == 422 and 'TV12U' in response.json()['detail']


def test_missing_reference_returns_503_without_model_or_private_path(setup):
    setup['reference_path'].unlink()
    result = setup['client'].post('/assistant/investigate', json=payload())
    assert result.status_code == 503 and '参考资料' in result.json()['detail']
    assert str(setup['reference_path']) not in result.text
    assert result.headers['cache-control'] == 'no-store'


def test_manual_definition_citations_and_history_do_not_fabricate_events(setup, monkeypatch):
    captured = transport(monkeypatch)
    request = payload()
    request['manual_fault']['code'] = ' h10101 '
    response = setup['client'].post('/assistant/investigate', json=request)
    assert response.status_code == 200, response.text
    report = response.json()
    manual = report['evidence']['operator:manual-fault']
    assert manual['code'] == 'H10101'
    assert manual['observation_source'] == 'unverified_operator_report'
    assert manual['model'] == 'TV12U' and manual['version'] == '260224'
    assert manual['definition']['description'] == '左泵前进比例阀短路'
    assert manual['definition']['source_row'] == 66
    assert manual['source']['sha256'] == fault_reference.SOURCE_SHA256
    assert 'operator:manual-fault' in report['citations']
    event_evidence = next(e for e in report['evidence'].values()
                          if e.get('method') == 'fault_record_facts_v1')
    assert event_evidence['total_loaded_events'] == 0
    assert event_evidence['events'] == [] and event_evidence['groups'] == []
    assert setup['events'] == []
    fact = next(f for f in report['data_facts'] if 'operator:manual-fault' in f['evidence_ids'])
    assert '原表定义：左泵前进比例阀短路' in fact['text']
    assert '第 66 行' in fact['text'] and '不是风险等级' in fact['text']
    check = next(c for c in report['check_recommendations'] if c['check_id'] == 'check:manual-fault')
    assert check['evidence_ids'] == ['operator:manual-fault']
    saved = investigation_history.read_investigation(report['record_id'])
    assert saved['request']['manual_fault'] == {**request['manual_fault'], 'code': 'H10101'}
    assert saved['request']['dataset_id'] is None
    assert saved['report']['source'] == 'trackunit_cache'
    exposed = json.dumps([report, saved, captured], ensure_ascii=False)
    for forbidden in ('source_path', 'raw_fault_sheet', 'PRIVATE_TEST_SOURCE', 'DO_NOT_EXPOSE'):
        assert forbidden not in exposed


@pytest.mark.parametrize('already_recorded', [False, True])
def test_manual_code_reaches_scoped_parts_search_without_event_mutation(setup, monkeypatch, already_recorded):
    setup['events'].append(FaultCode(machine_id='UNIT-TV12U', fault_code='E10101', description='historical fixture',
                                    severity='low', occurred_at='2026-01-01T00:00:00Z', status='resolved'))
    if already_recorded:
        setup['events'].append(FaultCode(machine_id='UNIT-TV12U', fault_code='H10101', description='fixture event',
                                        severity='low', occurred_at='2026-01-01T01:00:00Z', status='open'))
    original_events = deepcopy(setup['events'])
    calls = []

    def search(*args, **kwargs):
        calls.append((args, kwargs))
        return []
    monkeypatch.setattr(agent, 'search_parts', search)
    transport(monkeypatch)
    report = agent.investigate(agent.InvestigationRequest(**payload(task='parts')))
    assert len(calls) == 1
    args, options = calls[0]
    assert args[:3] == ('TV12U', 'UNIT-SERIAL', ['H10101'])
    assert options['include_demo'] is False
    assert report['machine_id'] == 'UNIT-TV12U' and report['source'] == 'trackunit_cache'
    assert setup['events'] == original_events
    assert 'operator:manual-fault' in report['citations']


def test_imported_device_version_is_preserved_for_manual_fault_diagnosis(setup, monkeypatch):
    dataset_id = 'b' * 64
    dataset = SimpleNamespace(machine=setup['machine'], telemetry=[], faults=[],
                              provenance='user_supplied', source_document='User equipment fixture',
                              replay_at=datetime(2026, 1, 2, tzinfo=timezone.utc), cooling_reference=None)
    monkeypatch.setattr(agent, 'load_dataset', lambda requested: dataset if requested == dataset_id else None)
    captured = transport(monkeypatch)
    request = payload(dataset_id=dataset_id)
    response = setup['client'].post('/assistant/investigate', json=request)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['dataset_id'] == dataset_id and report['source'] == 'imported_user_supplied'
    saved = investigation_history.read_investigation(report['record_id'])
    assert saved['request']['dataset_id'] == dataset_id
    assert saved['request']['manual_fault'] == request['manual_fault']
    assert captured
    with pytest.raises(ValueError, match='Dataset machine mismatch'):
        agent.investigate(agent.InvestigationRequest(**{**request, 'machine_id': 'UNIT-OTHER'}))


def test_manual_code_is_required_in_final_citations_not_just_available(setup, monkeypatch):
    captured = transport(monkeypatch, omit_manual=True)
    with pytest.raises(GeminiError, match='step limit'):
        agent.investigate(agent.InvestigationRequest(**payload()))
    assert len(captured) == 6
    assert not list(investigation_history.HISTORY_DIR.glob('*.json'))


def test_feedback_retains_latest_per_check_outside_recent_five_without_mutation():
    records = [
        {'check_id': 'check:a', 'notes': '旧结果A', 'outcome': 'inconclusive'},
        {'check_id': 'check:b', 'notes': '已目视检查接头，尚未测量。', 'outcome': 'not_observed'},
        {'check_id': 'check:a', 'notes': '最新结果A，测量仍未完成。', 'outcome': 'observed'},
        *[{'check_id': None, 'notes': f'一般补充{n}', 'outcome': 'inconclusive'} for n in range(6)],
    ]
    original = deepcopy(records)
    context = inspection_feedback.feedback_context({'records': records, 'total': 9})
    assert [r['notes'] for r in context['records']] == [
        '已目视检查接头，尚未测量。', '最新结果A，测量仍未完成。',
        *[f'一般补充{n}' for n in range(1, 6)]]
    assert context['total_records'] == 9 and context['omitted_older_records'] == 2
    assert context['source'] == 'unverified_operator_feedback'
    assert records == original


def test_feedback_recent_check_is_not_duplicated_and_empty_is_explicit():
    row = {'check_id': 'check:a', 'notes': '最新检查', 'outcome': 'inconclusive'}
    context = inspection_feedback.feedback_context({'records': [row], 'total': 1})
    assert context['records'] == [row] and context['omitted_older_records'] == 0
    assert inspection_feedback.feedback_context({'records': [], 'total': 0})['records'] == []
