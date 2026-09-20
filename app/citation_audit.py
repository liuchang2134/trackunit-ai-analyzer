"""Audit whether the AI's citations actually point at material that exists.

The investigation loop already refuses a decision whose evidence ids are not in
the allowed set (`local_assistant.py`), but that guard is invisible: nothing
reports whether a saved report's citations resolve, and a reader has no way to
tell a grounded conclusion from a plausible-sounding one.

This module closes that gap by resolving every reference a report makes — the
citations list, each hypothesis's manual reference ids, and each check's evidence
ids — against the evidence the report actually recorded. A reference that does not
resolve is reported as dangling rather than quietly dropped, because a citation
that points at nothing would be the single most damaging defect a diagnostic
report could have.
"""
from __future__ import annotations


def _as_list(value) -> list:
    return [item for item in value] if isinstance(value, list) else []


def _family(key: str) -> str:
    return key.split(':', 1)[0] if isinstance(key, str) and ':' in key else 'other'


def _resolve(references: list, evidence: set) -> dict:
    """Split a reference list into the ones that resolve and the ones that do not."""
    checked = [ref for ref in references if isinstance(ref, str) and ref]
    resolved = [ref for ref in checked if ref in evidence]
    return {'checked': len(checked), 'resolved': len(resolved),
            'dangling': [ref for ref in checked if ref not in evidence]}


def audit_report(report: dict | None) -> dict | None:
    """Report how well one saved report's citations are grounded."""
    if not isinstance(report, dict) or not report:
        return None
    evidence = report.get('evidence') if isinstance(report.get('evidence'), dict) else {}
    known = set(evidence)

    citations = _resolve(_as_list(report.get('citations')), known)

    hypothesis_refs, check_refs = [], []
    addressed = unaddressed = 0
    for row in _as_list(report.get('component_hypotheses')):
        if not isinstance(row, dict):
            continue
        hypothesis_refs.extend(_as_list(row.get('reference_ids')))
        checks = [check for check in _as_list(row.get('checks')) if isinstance(check, dict)]
        if checks:
            addressed += 1
        else:
            unaddressed += 1
        for check in checks:
            check_refs.extend(_as_list(check.get('evidence_ids')))

    hypotheses = _resolve(hypothesis_refs, known)
    checks = _resolve(check_refs, known)

    dangling = {
        'citations': citations['dangling'],
        'hypothesis_references': hypotheses['dangling'],
        'check_evidence': checks['dangling'],
    }
    total_dangling = sum(len(items) for items in dangling.values())
    total_checked = citations['checked'] + hypotheses['checked'] + checks['checked']

    families: dict[str, int] = {}
    for key in known:
        family = _family(key)
        families[family] = families.get(family, 0) + 1

    return {
        'checked': total_checked,
        'resolved': total_checked - total_dangling,
        'dangling_count': total_dangling,
        'dangling': {name: items for name, items in dangling.items() if items},
        'citations': citations,
        'hypothesis_references': hypotheses,
        'check_evidence': checks,
        # A conclusion without a check direction is not wrong, but it is weaker
        # evidence of care, so it is counted rather than hidden.
        'hypotheses_with_checks': addressed,
        'hypotheses_without_checks': unaddressed,
        'evidence_sources': len(known),
        'evidence_by_family': dict(sorted(families.items())),
        'verdict': 'all_references_resolved' if total_dangling == 0 else 'dangling_references_present',
    }
