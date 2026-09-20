"""The citation audit exists to catch the worst possible defect in a diagnostic
report: a conclusion citing material that does not exist. These tests pin both
halves — that a sound report is reported as sound, and that a dangling reference
is surfaced instead of silently ignored.
"""
import pytest

from app.citation_audit import audit_report


def report(**overrides):
    base = {
        'citations': ['tool:1:snapshot', 'manual:m1'],
        'evidence': {
            'tool:1:snapshot': {'method': 'snapshot'},
            'manual:m1': {'method': 'manual'},
            'tool:2:faults': {'method': 'faults'},
        },
        'component_hypotheses': [
            {'component': 'ECU 供电熔断器', 'reference_ids': ['manual:m1'],
             'checks': [{'text': '检查熔断器', 'evidence_ids': ['manual:m1']}]},
            {'component': 'ECU CAN 线束', 'reference_ids': ['manual:m1'],
             'checks': [{'text': '断电测量', 'evidence_ids': ['tool:1:snapshot']}]},
        ],
    }
    base.update(overrides)
    return base


def test_a_fully_grounded_report_is_reported_as_such():
    audit = audit_report(report())
    assert audit['verdict'] == 'all_references_resolved'
    assert audit['dangling_count'] == 0
    assert audit['dangling'] == {}
    # citations 2 + hypothesis refs 2 + check evidence 2
    assert audit['checked'] == 6 and audit['resolved'] == 6


def test_a_dangling_citation_is_surfaced_not_dropped():
    audit = audit_report(report(citations=['tool:1:snapshot', 'manual:does-not-exist']))
    assert audit['verdict'] == 'dangling_references_present'
    assert audit['dangling_count'] == 1
    assert audit['dangling']['citations'] == ['manual:does-not-exist']
    assert audit['citations'] == {'checked': 2, 'resolved': 1, 'dangling': ['manual:does-not-exist']}


def test_a_dangling_hypothesis_reference_is_surfaced():
    audit = audit_report(report(component_hypotheses=[
        {'component': '泵', 'reference_ids': ['manual:ghost'], 'checks': []},
    ]))
    assert audit['dangling']['hypothesis_references'] == ['manual:ghost']
    assert audit['verdict'] == 'dangling_references_present'


def test_a_dangling_check_evidence_id_is_surfaced():
    audit = audit_report(report(component_hypotheses=[
        {'component': '泵', 'reference_ids': ['manual:m1'],
         'checks': [{'text': 'x', 'evidence_ids': ['tool:ghost']}]},
    ]))
    assert audit['dangling']['check_evidence'] == ['tool:ghost']


def test_hypotheses_without_a_check_direction_are_counted_not_hidden():
    audit = audit_report(report(component_hypotheses=[
        {'component': 'A', 'reference_ids': ['manual:m1'], 'checks': [{'text': 'x', 'evidence_ids': []}]},
        {'component': 'B', 'reference_ids': ['manual:m1'], 'checks': []},
    ]))
    assert audit['hypotheses_with_checks'] == 1
    assert audit['hypotheses_without_checks'] == 1


def test_the_audit_summarises_where_the_evidence_came_from():
    audit = audit_report(report())
    assert audit['evidence_sources'] == 3
    assert audit['evidence_by_family'] == {'manual': 1, 'tool': 2}


def test_an_empty_or_non_report_yields_no_audit():
    assert audit_report(None) is None
    assert audit_report({}) is None
    assert audit_report('nope') is None


def test_malformed_rows_do_not_break_the_audit():
    audit = audit_report(report(
        citations=['ok', None, 5, ''],
        evidence={'ok': {}, 'tool:1': {}},
        component_hypotheses=[None, 'x', {'component': 'A', 'reference_ids': [None, 'ok'],
                                          'checks': [None, 'y', {'text': 'z', 'evidence_ids': [None, 'ok']}]}],
    ))
    # Non-string entries are not references and are not counted as dangling.
    assert audit['citations']['checked'] == 1 and audit['citations']['resolved'] == 1
    assert audit['hypothesis_references']['checked'] == 1
    assert audit['check_evidence']['checked'] == 1
    assert audit['dangling_count'] == 0


def test_a_report_without_evidence_is_reported_dangling_rather_than_passing():
    # Legacy records may predate the structured evidence map; every citation in
    # them is then unresolvable and must be reported as such, not assumed fine.
    audit = audit_report({'citations': ['tool:1:snapshot'], 'evidence': {},
                          'component_hypotheses': []})
    assert audit['checked'] == 1 and audit['resolved'] == 0
    assert audit['verdict'] == 'dangling_references_present'


@pytest.mark.parametrize('decisions', [0, 1, 3])
def test_the_audit_does_not_depend_on_how_many_decisions_were_taken(decisions):
    audit = audit_report(report(model_decisions=decisions))
    assert audit['verdict'] == 'all_references_resolved'
