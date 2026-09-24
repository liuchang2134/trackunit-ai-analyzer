"""Summarise what the AI actually contributed to one investigation.

Every field here is read back from a saved report; nothing is inferred or
invented. The summary deliberately separates two things a reader must not
confuse:

* what the model decided — how many decisions it took, which reads it chose
  itself, which components it put forward, which manual pages and quotes it cited,
  which check directions it proposed, and whether its output needed a format
  repair;
* what the program computed — how many evidence sources were read, how many
  data facts were rendered, and how many of the reads were forced by the task
  rather than chosen by the model.

Attribution matters for a competition demo: claiming the whole report as "AI
output" would overstate it, and claiming only the summary sentence would
understate it. A component that exists in the catalog is evidence, not a
diagnosis, and this module never presents it as one.
"""
from __future__ import annotations

from typing import Any

# Evidence key prefixes produced by the investigation loop, mapped to a readable
# label. Keys outside this map are still counted, under their raw prefix.
_EVIDENCE_LABELS = {
    'tool': '设备数据读取',
    'manual': '适用手册摘录',
    'operator': '人工提供',
    'xgss': '官方图册条目',
    'fault': '故障记录',
    'catalog': '本地备件目录',
}


def _evidence_family(key: str) -> str:
    return key.split(':', 1)[0] if isinstance(key, str) and ':' in key else 'other'


def _read_actions(report: dict) -> list[dict]:
    """The reads the investigation performed, with who asked for each one."""
    actions = []
    for row in report.get('tool_trace') or []:
        if not isinstance(row, dict):
            continue
        actions.append({'action': row.get('action'), 'source_id': row.get('source_id'),
                        'trigger': row.get('trigger') or 'unknown',
                        'selected_by': 'model' if row.get('trigger') == 'model_selected' else 'task'})
    return actions


def _manual_references(report: dict) -> list[dict]:
    """Manual material the model leaned on, with its stated source and quote."""
    seen, references = set(), []
    for row in report.get('manual_references') or []:
        if not isinstance(row, dict):
            continue
        key = json_key(row)
        if key in seen:
            continue
        seen.add(key)
        references.append({
            'source_document': row.get('source_document') or '',
            'pdf_pages': sorted({int(page) for page in row.get('pdf_pages') or []
                                 if isinstance(page, (int, float))}),
            'configuration': row.get('configuration') or '',
            'quote': (row.get('source_quote') or '')[:400],
        })
    return references


def json_key(row: dict) -> str:
    return '|'.join(str(row.get(field) or '') for field in ('source_document', 'configuration'))


def _hypotheses(report: dict) -> list[dict]:
    """The components the model put forward, with the checks it attached."""
    out = []
    for row in report.get('component_hypotheses') or []:
        if not isinstance(row, dict):
            continue
        component = (row.get('component') or '').strip()
        if not component:
            continue
        checks = [check for check in (row.get('checks') or []) if isinstance(check, dict) and check.get('text')]
        pages = sorted({int(page) for check in checks for page in (check.get('pdf_pages') or [])
                        if isinstance(page, (int, float))})
        out.append({
            'component': component,
            'status': row.get('status') or 'hypothesis_requires_inspection',
            'rationale': (row.get('rationale') or '')[:400],
            'search_terms': [term for term in (row.get('search_terms') or []) if isinstance(term, str)][:8],
            'reference_ids': [ref for ref in (row.get('reference_ids') or []) if isinstance(ref, str)],
            'check_count': len(checks),
            'pdf_pages': pages,
            # A candidate present in the catalog is evidence for a hypothesis, never
            # proof that the component is fitted to this machine or that it failed.
            'part_candidate_count': len([item for item in (row.get('part_candidate_ids') or []) if item]),
        })
    return out


def ai_contribution(report: dict | None) -> dict | None:
    """Describe the AI's contribution to one investigation, or None without one."""
    if not isinstance(report, dict) or not report:
        return None
    actions = _read_actions(report)
    evidence = report.get('evidence') if isinstance(report.get('evidence'), dict) else {}
    families: dict[str, int] = {}
    for key in evidence:
        family = _evidence_family(key)
        families[family] = families.get(family, 0) + 1
    hypotheses = _hypotheses(report)
    citations = [ref for ref in (report.get('citations') or []) if isinstance(ref, str)]
    # The model's own selection is the interesting part; task-forced reads are not
    # a model achievement, so they are counted separately rather than merged.
    model_selected = [row for row in actions if row['selected_by'] == 'model']
    from app.citation_audit import audit_report
    return {
        'ai': {
            'model_decisions': int(report.get('model_decisions') or 0),
            'model_selected_reads': len(model_selected),
            'model_selected_actions': [row['action'] for row in model_selected],
            'hypothesis_count': len(hypotheses),
            'hypotheses': hypotheses,
            'check_directions': sum(row['check_count'] for row in hypotheses),
            'citation_count': len(citations),
            'manual_references': _manual_references(report),
            'search_terms': sorted({term for row in hypotheses for term in row['search_terms']}),
            'format_repair_attempts': int(report.get('format_repair_attempts') or 0),
            'duration_seconds': report.get('duration_seconds'),
        },
        # Whether every reference the report makes actually resolves. Reported here
        # so a reader can tell a grounded conclusion from a plausible-sounding one.
        'audit': audit_report(report),
        'program': {
            'reads_total': len(actions),
            'reads_by_task': len(actions) - len(model_selected),
            'evidence_sources': len(evidence),
            'evidence_by_family': {_EVIDENCE_LABELS.get(family, family): count
                                   for family, count in sorted(families.items())},
            'data_facts': len(report.get('data_facts') or []),
            'parts_candidates': len(report.get('parts_candidates') or []),
        },
        'boundary': [
            '可疑部件是待核查方向，不是已确认故障；部件存在于图册也不代表它已损坏。',
            '检查步骤需由现场人员按适用手册与整机配置核实后执行。',
        ],
        'model': {key: report.get(key) for key in ('provider', 'model', 'inference_location', 'thinking_mode')
                  if report.get(key) is not None},
    }
