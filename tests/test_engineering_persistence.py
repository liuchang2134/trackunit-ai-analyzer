from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import investigation_drafts as drafts
from app import investigation_history as history


FAULT = {'model': 'XE55U', 'code': 'E4030', 'configuration': 'unknown', 'source': 'test'}


def test_test_fault_survives_history_without_becoming_a_recorded_event(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'HISTORY_DIR', tmp_path)
    report = {'status': 'completed', 'machine_id': 'TEST-A', 'source': 'imported_synthetic',
              'engineering_fault': FAULT, 'summary': '测试故障排查', 'faults': []}
    saved = history.save_investigation(report, {'machine_id': 'TEST-A', 'engineering_fault': FAULT})
    restored = history.read_investigation(saved['record_id'])
    assert restored['request']['engineering_fault'] == FAULT
    assert restored['report']['faults'] == []
    assert restored['report']['engineering_fault']['source'] == 'test'


def test_code_only_engineering_draft_is_model_scoped_and_can_be_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(drafts, 'DRAFT_DIR', tmp_path)
    machine = SimpleNamespace(machine_id='TEST-A', model='XE55U', serial_number='TEST-XE55U')
    monkeypatch.setattr(drafts, 'find_machine', lambda _: machine)
    monkeypatch.setattr(drafts, 'get_data_source', lambda: 'mock')
    request = drafts.DraftSaveRequest(machine_id='TEST-A', source='mock',
                                      content={'engineering_fault': FAULT})
    saved = drafts.save_draft(request)['draft']
    restored = drafts.read_draft('TEST-A', None, 'mock')['draft']
    assert restored['content']['engineering_fault'] == FAULT
    machine.model = 'TV12U'
    with pytest.raises(drafts.DraftScopeError):
        drafts.save_draft(request.model_copy(update={'expected_revision': saved['revision']}))
    machine.model = 'XE55U'
    clean = drafts.DraftSaveRequest(machine_id='TEST-A', source='mock',
        expected_revision=saved['revision'], content={'question': '继续查看设备', 'engineering_fault': None})
    assert 'engineering_fault' not in drafts.save_draft(clean)['draft']['content']


def test_two_protocol_contexts_cannot_share_one_draft():
    with pytest.raises(ValidationError):
        drafts.DraftContent(engineering_fault=FAULT, manual_fault={
            'model': 'TV12U', 'version': '260224', 'code': 'H10101', 'applicability_confirmed': True})
