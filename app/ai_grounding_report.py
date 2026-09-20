"""Aggregate how well the saved AI runs are grounded, so the claim is re-runnable.

The numbers used to be produced by hand, which means nobody else could check
them. This module turns a directory of saved investigations into the same figures
deterministically, and the accompanying script writes them to disk.

Two honesty rules are built in rather than left to the caller:

* runs without model decisions are counted separately and excluded from the AI
  figures — mixing them in would inflate the sample with program-only output;
* the report states its own sample size and refuses to imply accuracy. Grounding
  and reference integrity are measurable from the records; diagnostic accuracy is
  not, and nothing here pretends otherwise.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.ai_contribution import ai_contribution
from app.citation_audit import audit_report

MINIMUM_DECISIONS = 1


def _load_reports(directory: Path) -> tuple[list[dict], int]:
    """Read every saved investigation; return the reports and the unreadable count."""
    reports, unreadable = [], 0
    for path in sorted(Path(directory).glob('*.json')):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            unreadable += 1
            continue
        report = record.get('report') if isinstance(record, dict) else None
        if not isinstance(report, dict):
            unreadable += 1
            continue
        reports.append({'record_id': path.stem, 'report': report,
                        'request': record.get('request') if isinstance(record.get('request'), dict) else {}})
    return reports, unreadable


def build_report(directory: Path) -> dict:
    """Measure reference grounding across the saved AI runs in one directory."""
    entries, unreadable = _load_reports(directory)
    with_model = [entry for entry in entries
                  if int(entry['report'].get('model_decisions') or 0) >= MINIMUM_DECISIONS]

    runs, totals = [], {'checked': 0, 'resolved': 0, 'dangling': 0,
                        'model_decisions': 0, 'hypotheses': 0, 'checks': 0,
                        'format_repairs': 0, 'durations': []}
    families: dict[str, int] = {}
    for entry in with_model:
        report = entry['report']
        audit = audit_report(report) or {}
        summary = ai_contribution(report) or {}
        ai = summary.get('ai') or {}
        program = summary.get('program') or {}
        for name, count in (audit.get('evidence_by_family') or {}).items():
            families[name] = families.get(name, 0) + count
        totals['checked'] += audit.get('checked', 0)
        totals['resolved'] += audit.get('resolved', 0)
        totals['dangling'] += audit.get('dangling_count', 0)
        totals['model_decisions'] += ai.get('model_decisions', 0)
        totals['hypotheses'] += ai.get('hypothesis_count', 0)
        totals['checks'] += ai.get('check_directions', 0)
        totals['format_repairs'] += ai.get('format_repair_attempts', 0)
        if isinstance(ai.get('duration_seconds'), (int, float)):
            totals['durations'].append(float(ai['duration_seconds']))
        runs.append({
            'record_id': entry['record_id'],
            'generated_at': report.get('generated_at'),
            'model': report.get('model'),
            'fault_code': (entry['request'].get('engineering_fault') or {}).get('code')
            if isinstance(entry['request'].get('engineering_fault'), dict) else None,
            'model_decisions': ai.get('model_decisions', 0),
            'model_selected_reads': ai.get('model_selected_reads', 0),
            'hypotheses': ai.get('hypothesis_count', 0),
            'checks': ai.get('check_directions', 0),
            'format_repairs': ai.get('format_repair_attempts', 0),
            'citation_count': ai.get('citation_count', 0),
            'references_checked': audit.get('checked', 0),
            'references_dangling': audit.get('dangling_count', 0),
            'hypotheses_with_checks': audit.get('hypotheses_with_checks', 0),
            'hypotheses_without_checks': audit.get('hypotheses_without_checks', 0),
            'verdict': audit.get('verdict'),
            'duration_seconds': ai.get('duration_seconds'),
        })

    durations = totals.pop('durations')
    totals['records_total'] = len(entries)
    totals['records_with_model'] = len(with_model)
    totals['records_without_model'] = len(entries) - len(with_model)
    totals['unreadable_records'] = unreadable
    totals['all_references_resolved'] = totals['dangling'] == 0
    totals['hypotheses_without_checks'] = sum(row['hypotheses_without_checks'] for row in runs)
    totals['duration_seconds_min'] = min(durations) if durations else None
    totals['duration_seconds_max'] = max(durations) if durations else None
    totals['evidence_by_family'] = dict(sorted(families.items()))

    return {
        'scope': '本机已保存的真实 AI 排查记录；只读扫描，不调用模型、不修改记录。',
        'method': [
            '对每条含模型决策的记录，把报告里的引用逐条对回该报告实际记录的证据集合。',
            '结论引用、部件的手册引用、检查步骤的依据分别统计，任一不解析即计入悬空。',
            '不含模型决策的记录单列，不计入 AI 的统计口径。',
        ],
        'boundaries': [
            '这里度量的是"引用是否指向存在的证据"，不是诊断正确率。',
            '诊断正确率需要带标签的验证集，本机没有，因此不作任何准确率声明。',
            '样本量很小，且多为同一台设备的测试输入；这些数字不能外推为通用结论。',
            '耗时来自历史记录，受当时网络与模型负载影响，不是性能基准。',
        ],
        'totals': totals,
        'runs': runs,
    }


def render_markdown(data: dict) -> str:
    totals = data['totals']
    lines = ['# AI 引用可核验性评估', '',
             f"> {data['scope']}", '',
             '## 口径', '']
    lines += [f'- {line}' for line in data['method']]
    lines += ['', '## 结果', '']
    lines += [
        f"- 扫描记录 {totals['records_total']} 条，其中含模型决策 {totals['records_with_model']} 条，"
        f"不含模型决策 {totals['records_without_model']} 条（不计入 AI 口径）；无法读取 {totals['unreadable_records']} 条。",
        f"- 共核对引用 **{totals['checked']}** 条，解析 **{totals['resolved']}** 条，"
        f"悬空 **{totals['dangling']}** 条。",
        f"- 模型决策合计 {totals['model_decisions']} 次；部件假设 {totals['hypotheses']} 个，"
        f"检查方向 {totals['checks']} 条。",
        f"- 未给检查方向的部件 {totals['hypotheses_without_checks']} 个；格式修正 {totals['format_repairs']} 次。",
    ]
    if totals['duration_seconds_min'] is not None:
        lines.append(f"- 单次耗时区间 {totals['duration_seconds_min']}–{totals['duration_seconds_max']} 秒（历史值）。")
    if totals['evidence_by_family']:
        families = '，'.join(f'{name} {count}' for name, count in totals['evidence_by_family'].items())
        lines.append(f"- 证据来源分布：{families}。")
    lines += ['', '## 逐条记录', '',
              '|记录|模型|决策|自选读取|部件|检查|引用核对|悬空|格式修正|',
              '|---|---|---|---|---|---|---|---|---|']
    for row in data['runs']:
        lines.append('|{id}|{model}|{decisions}|{selected}|{hypotheses}|{checks}|{checked}|{dangling}|{repairs}|'.format(
            id=row['record_id'][:12], model=row.get('model') or '—', decisions=row['model_decisions'],
            selected=row['model_selected_reads'], hypotheses=row['hypotheses'], checks=row['checks'],
            checked=row['references_checked'], dangling=row['references_dangling'],
            repairs=row['format_repairs']))
    lines += ['', '## 边界', '']
    lines += [f'- {line}' for line in data['boundaries']]
    lines += ['', '本页由脚本从本机记录生成，可重复运行以复核；记录内容变化会改变结果。']
    return '\n'.join(lines) + '\n'
