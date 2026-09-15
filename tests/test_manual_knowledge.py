import json

import pytest
from pydantic import ValidationError

from app import manual_knowledge as knowledge


def record(configuration='XE55U.00III', reference_id='fixture-iii'):
    return {'reference_id': reference_id, 'title': 'Synthetic test reference, not a manufacturer manual',
            'model': 'XE55U', 'configuration': configuration, 'version': 'fixture-v1',
            'pdf_pages': [2], 'section': 'Test fixture',
            'text': 'Fixture symptom: communication unavailable. Inspect the harness connector for looseness.',
            'source_url': 'https://example.org/synthetic-test.pdf', 'provenance': 'synthetic_test_fixture',
            'fault_codes': ['E4030']}


@pytest.fixture
def knowledge_file(tmp_path, monkeypatch):
    path = tmp_path / 'manual.json'
    monkeypatch.setattr(knowledge, 'KNOWLEDGE_PATH', path)
    path.write_text(json.dumps({'schema_version': 1, 'records': [record(), record('XE55U.00VI', 'fixture-vi')]}), encoding='utf-8')
    return path


def fault(**changes):
    return knowledge.EngineeringFault(**({'code': 'E4030', 'model': 'XE55U', 'source': 'test'} | changes))


def test_unknown_configuration_retains_distinct_unverified_references(knowledge_file):
    result = knowledge.retrieve_manuals(fault(), 'XE55U')
    assert result['status'] == 'matched'
    assert {r['configuration'] for r in result['records']} == {'XE55U.00III', 'XE55U.00VI'}
    assert all(r['applicability'] == 'model_reference_only' for r in result['records'])
    assert len({r['reference_id'] for r in result['records']}) == 2


def test_selected_configuration_excludes_other_version(knowledge_file):
    result = knowledge.retrieve_manuals(fault(configuration='XE55U.00VI'), 'XE55U')
    assert [r['reference_id'] for r in result['records']] == ['manual:fixture-vi']
    assert result['applicability'] == 'configuration_selected_unverified'


def test_unrecognized_code_and_absent_library_do_not_substitute_known_case(knowledge_file):
    assert knowledge.retrieve_manuals(fault(code='E9999'), 'XE55U')['status'] == 'no_matching_code'
    knowledge_file.unlink()
    assert knowledge.retrieve_manuals(fault(), 'XE55U')['status'] == 'knowledge_unavailable'


def test_non_matching_machine_rejected_before_loading(knowledge_file):
    with pytest.raises(ValueError, match='XE55U'):
        knowledge.retrieve_manuals(fault(), 'TV12U')


def test_test_code_evidence_is_explicitly_not_trackunit_event(knowledge_file):
    selected = fault(code=' e4030 ')
    evidence = knowledge.engineering_fault_evidence(selected, knowledge.retrieve_manuals(selected, 'XE55U'))
    assert evidence['code'] == 'E4030'
    assert evidence['source'] == 'test'
    assert evidence['observation_source'] == 'synthetic_test_input'
    assert evidence['is_trackunit_event'] is False


@pytest.mark.parametrize('change', [{'source_url': 'javascript:alert(1)'}, {'pdf_pages': [0]}, {'reference_id': 'bad <id>'}])
def test_malformed_reference_rejected(knowledge_file, change):
    knowledge_file.write_text(json.dumps({'schema_version': 1, 'records': [record() | change]}), encoding='utf-8')
    with pytest.raises(ValidationError):
        knowledge.retrieve_manuals(fault(), 'XE55U')
