"""Replay one real saved investigation, with the AI's actual decisions shown.

This is the only thing the demo view presents. A scripted simulation used to sit beside
it — honest about being a simulation, but unable to show what the model does, and
sitting a preset walkthrough next to genuine output only weakens the genuine output. It
has been removed rather than hidden, so nothing here is a fallback to a preset case.

The replay is read-only and offline: nothing here calls a provider, and every statement
about the AI is counted from the record rather than described.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.ai_contribution import ai_contribution
from app.local_datasets import load_dataset

HISTORY_DIR = Path(__file__).resolve().parents[1] / "data/local/investigations"

# The replay is only offered for records that actually contain model decisions.
# A record without them would present program output as AI work.
MINIMUM_DECISIONS = 1


class ReplayUnavailable(ValueError):
    """The requested record cannot be replayed as an AI run."""


def _read(record_id: str) -> dict:
    if not isinstance(record_id, str) or not record_id or not record_id.isalnum():
        raise ReplayUnavailable('记录编号无效。')
    path = HISTORY_DIR / f'{record_id}.json'
    if not path.is_file():
        raise ReplayUnavailable('找不到该记录；它可能已被移动或删除。')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ReplayUnavailable(f'该记录无法读取：{error}') from None


def _real_ai_records() -> list[dict]:
    """Every saved record that contains real model decisions, newest first."""
    records = []
    for path in HISTORY_DIR.glob('*.json'):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        report = record.get('report')
        if not isinstance(report, dict):
            continue
        if int(report.get('model_decisions') or 0) < MINIMUM_DECISIONS:
            continue
        request = record.get('request') if isinstance(record.get('request'), dict) else {}
        fault = request.get('engineering_fault') if isinstance(request.get('engineering_fault'), dict) else {}
        device = _machine_identity(report, request)
        records.append({
            'record_id': path.stem,
            'generated_at': report.get('generated_at'),
            'machine_id': report.get('machine_id'),
            'machine_model': device['model'],
            'machine_serial': device['serial_number'],
            'ai_model': report.get('model'),
            'fault_code': fault.get('code'),
            'fault_source': fault.get('source'),
            'model_decisions': int(report.get('model_decisions') or 0),
            'duration_seconds': report.get('duration_seconds'),
            'hypothesis_count': len(report.get('component_hypotheses') or []),
            'question': (request.get('question') or '')[:160],
        })
    records.sort(key=lambda row: row.get('generated_at') or '', reverse=True)
    return records


def list_replays() -> dict:
    """Saved AI runs available to replay, with the disclosure the UI must show."""
    records = _real_ai_records()
    return {
        'records': records,
        'total': len(records),
        'scope': '本机已保存的真实 DeepSeek 排查记录；回放不调用模型、不产生费用。',
        'disclosure': [
            '以下是真实模型在过去的输出，不是实时推理，也不能代表当前服务可用性。',
            '记录中的故障码来自测试输入或人工报告，不等于设备实际发生该故障。',
            '可疑部件是待核查方向；部件出现在目录或图册中不代表它已损坏。',
        ],
    }


def _stage(stage_id: str, title: str, lines: list[str], origin: str, note: str = '') -> dict:
    return {'stage_id': stage_id, 'title': title, 'lines': [line for line in lines if line],
            'origin': origin, 'note': note}


def _machine_identity(report: dict, request: dict) -> dict:
    """The machine behind a report, as far as the record actually states it.

    A saved report carries the machine id but not always its model or serial. The
    local dataset can supply them; when it cannot, the identifiers stay empty
    rather than being guessed from anything else in the record.
    """
    identity = {'model': None, 'serial_number': None}
    dataset_id = request.get('dataset_id')
    if isinstance(dataset_id, str) and dataset_id:
        try:
            machine = load_dataset(dataset_id).machine
            identity['model'] = getattr(machine, 'model', None)
            identity['serial_number'] = getattr(machine, 'serial_number', None)
        except Exception:  # noqa: BLE001 - a missing dataset must not break a replay
            pass
    return identity


def _stages(report: dict, request: dict, summary: dict) -> list[dict]:
    ai = summary['ai']
    program = summary['program']
    fault = request.get('engineering_fault') if isinstance(request.get('engineering_fault'), dict) else {}
    code = fault.get('code')
    stages = []

    # 1. What was read, and which of those reads the model asked for itself.
    read_lines = [
        f"程序按证据规则读取 {program['reads_total']} 项：{'、'.join(sorted(set(program['evidence_by_family'])))}。",
        f"证据来源 {program['evidence_sources']} 处，整理成 {program['data_facts']} 条数据事实。",
    ]
    if ai['model_selected_actions']:
        read_lines.append(f"模型自己选择追加读取：{'、'.join(ai['model_selected_actions'])}"
                          f"（其余 {program['reads_by_task']} 项由任务规定，不计入模型的选择）。")
    else:
        read_lines.append('本次模型没有追加读取；全部读取由任务规定。')
    stages.append(_stage('read', '读取设备证据', read_lines, 'program',
                         '设备数据由程序计算，模型不直接看原始长数组。'))

    # 2. The model's component inference, with the manual page behind each one.
    hypothesis_lines = []
    for row in ai['hypotheses']:
        grounding = f"手册第 {'、'.join(str(page) for page in row['pdf_pages'])} 页" if row['pdf_pages'] else '未附页码'
        checks = f"{row['check_count']} 条检查方向" if row['check_count'] else '未给检查方向'
        hypothesis_lines.append(f"{row['component']} —— {grounding}；{checks}。{row['rationale']}")
    if not hypothesis_lines:
        hypothesis_lines = ['本次模型未给出部件假设（该任务不要求部件推断）。']
    stages.append(_stage('diagnose', '模型推断可疑部件', hypothesis_lines, 'ai',
                         '这些是待核查方向，不是已确认故障；配置未核实时仅作机型级参考。'))

    # 3. The check directions it proposed, quoting the manual material it used.
    check_lines = []
    for row in ai['hypotheses']:
        for check in (report.get('check_recommendations') or []):
            if isinstance(check, dict) and check.get('text') and row['component'] in (check.get('text') or ''):
                check_lines.append(f"{row['component']}：{check['text']}")
    if not check_lines:
        check_lines = [text for text in (report.get('next_checks') or []) if isinstance(text, str)][:8]
    stages.append(_stage('checks', '建议检查方向', check_lines, 'ai',
                         '需由现场人员按适用手册与整机配置核实后执行。'))

    # 4. The model's own wording, kept verbatim so the reader judges it directly.
    stages.append(_stage('summary', '模型给出的结论摘要（原文）',
                         [report.get('summary') or ''], 'ai',
                         '原文未改写；其中若有与实际不符之处，以此说明为准。'))

    # 5. The accounting, so the run cannot be read as more than it is.
    accounting = [
        f"模型决策 {ai['model_decisions']} 次，其中自选读取 {ai['model_selected_reads']} 项。",
        f"引用证据 {ai['citation_count']} 条；部件假设 {ai['hypothesis_count']} 个，检查方向 {ai['check_directions']} 条。",
    ]
    if ai['format_repair_attempts']:
        accounting.append(f"格式修正 {ai['format_repair_attempts']} 次：首次输出未满足约定，修正后才生成报告。")
    if code:
        accounting.append(f"故障码 {code} 来源为 {fault.get('source') or '未标注'}，"
                          f"{'不代表 Trackunit 上报' if fault.get('source') == 'test' else '由人工提供'}。")
    if not report.get('parts_candidates'):
        accounting.append('本次没有可展示的备件候选：该机尚无已读取的对应 VIN 图册条目。')
    stages.append(_stage('accounting', '本次运行的账目', accounting, 'mixed',
                         '把 AI 的贡献与程序的贡献分开计数，避免把程序读到的东西算成模型的功劳。'))
    return stages


def build_replay(record_id: str) -> dict:
    """Build the read-only replay payload for one real AI investigation."""
    record = _read(record_id)
    report = record.get('report')
    if not isinstance(report, dict):
        raise ReplayUnavailable('该记录缺少报告内容。')
    decisions = int(report.get('model_decisions') or 0)
    if decisions < MINIMUM_DECISIONS:
        # Refuse rather than dress program-only output up as an AI run.
        raise ReplayUnavailable('该记录没有模型决策，不能作为 AI 排查回放。')
    request = record.get('request') if isinstance(record.get('request'), dict) else {}
    summary = ai_contribution(report)
    # `model` in a report is the AI model, not the machine. Name both explicitly so
    # a reader cannot end up reading "deepseek-flash" as the equipment model.
    ai_model = report.get('model')
    device = _machine_identity(report, request)
    return {
        'schema_version': 1,
        'kind': 'real_ai_replay',
        'is_simulation': False,
        'record_id': record_id,
        'title': f"真实 AI 排查回放 · {(ai_model or '模型')}",
        'disclosure': '本页是已保存的真实模型输出回放，不是实时推理。回放不调用模型、不产生费用，也不代表当前服务可用。',
        'record': {
            'generated_at': report.get('generated_at'),
            'machine_id': report.get('machine_id'),
            'machine_model': device['model'],
            'machine_serial': device['serial_number'],
            'source': report.get('source'),
            'source_document': report.get('source_document'),
            'ai_model': ai_model,
            'provider': report.get('provider'),
            'inference_location': report.get('inference_location'),
            'dataset_id': request.get('dataset_id'),
            'question': request.get('question'),
            'observations': request.get('observations'),
            'prior_record_id': request.get('prior_record_id'),
            'fault': request.get('engineering_fault') or None,
            'task': request.get('task'),
        },
        'ai_contribution': summary,
        'stages': _stages(report, request, summary),
        'data_facts': [fact.get('text') for fact in (report.get('data_facts') or [])
                       if isinstance(fact, dict) and fact.get('text')],
    }

def _bullets(lines: list[str]) -> list[str]:
    """Bullet lines for extend(): returning one joined string would keep its
    newlines inside a single element and collapse the document to one character
    per line."""
    kept = [f'- {line}' for line in lines if line]
    return kept or ['- （无）']


def render_replay_report(data: dict) -> tuple[str, str]:
    """Render one replay as a portable Markdown evidence pack.

    The pack exists so a reviewer can check the claims away from the running app.
    It leads with the disclosure and the accounting, keeps the model's summary
    verbatim, and states what the run did not establish — a pack that only showed
    the conclusions would be a worse artefact than no pack at all.
    """
    record = data.get('record') or {}
    summary = data.get('ai_contribution') or {}
    ai = summary.get('ai') or {}
    program = summary.get('program') or {}
    lines: list[str] = []
    lines.append('# 机联智检 · AI 排查证据包')
    lines.append('')
    lines.append(f"> {data.get('disclosure') or ''}")
    lines.append('')
    lines.append('## 记录标识')
    lines.append('')
    identity = [
        ('记录编号', data.get('record_id')),
        ('生成时间', record.get('generated_at')),
        ('设备', record.get('machine_id')),
        ('数据来源', record.get('source')),
        ('数据版本', record.get('dataset_id') or '无（车队缓存）'),
        ('模型', ' / '.join(part for part in (record.get('provider'), record.get('model')) if part) or '未记录'),
        ('推理位置', record.get('inference_location')),
        ('分析任务', record.get('task')),
        ('本次提问', record.get('question')),
        ('承接记录', record.get('prior_record_id')),
    ]
    fault = record.get('fault') or {}
    if fault:
        identity.append(('故障输入', f"{fault.get('code')}（来源：{fault.get('source')}，配置：{fault.get('configuration') or '未核对'}）"))
    lines.extend(_bullets([f'{label}：{value}' for label, value in identity if value]))
    lines.append('')
    lines.append('## AI 在本次排查中的作用')
    lines.append('')
    lines.extend(_bullets([
        f"模型决策 {ai.get('model_decisions', 0)} 次",
        f"模型自己选择的读取：{'、'.join(ai.get('model_selected_actions') or []) or '无'}"
        f"（其余 {program.get('reads_by_task', 0)} 项读取由任务规定，不计入模型的选择）",
        f"推断的可疑部件 {ai.get('hypothesis_count', 0)} 个",
        f"提出的检查方向 {ai.get('check_directions', 0)} 条",
        f"引用证据 {ai.get('citation_count', 0)} 条",
        f"耗时 {ai.get('duration_seconds')} 秒" if ai.get('duration_seconds') is not None else '',
        f"格式修正 {ai.get('format_repair_attempts')} 次（首次输出未满足约定，修正后才生成报告）"
        if ai.get('format_repair_attempts') else '',
    ]))
    lines.append('')
    lines.append('### 程序侧（不计入 AI 贡献）')
    lines.append('')
    families = '，'.join(f'{name} {count}' for name, count in (program.get('evidence_by_family') or {}).items())
    lines.extend(_bullets([
        f"读取 {program.get('reads_total', 0)} 项",
        f"证据来源 {program.get('evidence_sources', 0)} 处" + (f"（{families}）" if families else ''),
        f"整理数据事实 {program.get('data_facts', 0)} 条",
        f"备件候选 {program.get('parts_candidates', 0)} 条",
    ]))
    lines.append('')
    audit = summary.get('audit') or {}
    if audit:
        lines.append('## 依据核对')
        lines.append('')
        if audit.get('dangling_count'):
            lines.extend(_bullets([
                f"共核对 {audit.get('checked', 0)} 条引用，其中 {audit['dangling_count']} 条找不到对应证据（见下）。",
            ]))
            for where, items in (audit.get('dangling') or {}).items():
                for ref in items:
                    lines.append(f"- 悬空：{where} → {ref}")
        else:
            lines.extend(_bullets([
                f"共核对 {audit.get('checked', 0)} 条引用（结论引用、部件引用、检查依据），全部指向已读取的证据，没有悬空引用。",
                f"其中引用 {audit.get('citations', {}).get('resolved', 0)} 条、部件手册引用 "
                f"{audit.get('hypothesis_references', {}).get('resolved', 0)} 条、检查依据 "
                f"{audit.get('check_evidence', {}).get('resolved', 0)} 条。",
                f"带检查方向的部件 {audit.get('hypotheses_with_checks', 0)} 个，"
                f"未给检查方向 {audit.get('hypotheses_without_checks', 0)} 个。",
            ]))
        lines.append('')
    lines.append('## 可疑部件与手册依据')
    lines.append('')
    if ai.get('hypotheses'):
        for row in ai['hypotheses']:
            grounding = f"手册第 {'、'.join(str(page) for page in row.get('pdf_pages') or [])} 页" if row.get('pdf_pages') else '未附页码'
            lines.append(f"### {row.get('component')}")
            lines.append('')
            lines.append(f"- 依据：{grounding}")
            lines.append(f"- 检查方向：{row.get('check_count', 0)} 条")
            if row.get('search_terms'):
                lines.append(f"- 图册检索词：{'、'.join(row['search_terms'])}")
            if row.get('reference_ids'):
                lines.append(f"- 引用来源：{'、'.join(row['reference_ids'])}")
            if row.get('rationale'):
                lines.append(f"- 推理说明：{row['rationale']}")
            if row.get('part_candidate_count'):
                lines.append(f"- 目录候选：{row['part_candidate_count']} 条（候选不等于已确认装机件）")
            lines.append('')
    else:
        lines.append('- 本次模型未给出部件假设（该任务不要求部件推断）。')
        lines.append('')
    lines.append('## 建议检查方向')
    lines.append('')
    checks = []
    for stage in data.get('stages') or []:
        if stage.get('stage_id') == 'checks':
            checks.extend(stage.get('lines') or [])
    lines.extend(_bullets(checks))
    lines.append('')
    lines.append('## 模型结论摘要（原文，未改写）')
    lines.append('')
    for stage in data.get('stages') or []:
        if stage.get('stage_id') == 'summary':
            for line in stage.get('lines') or []:
                lines.append(line)
    lines.append('')
    lines.append('## 数据事实')
    lines.append('')
    lines.extend(_bullets(data.get('data_facts') or []))
    lines.append('')
    lines.append('## 本次运行没有确立的事情')
    lines.append('')
    lines.extend(_bullets(summary.get('boundary') or []))
    lines.append('')
    lines.append('本证据包由本机保存的记录生成，回放不调用模型、不产生费用；它证明的是当时的模型行为，'
                 '不代表当前服务可用性，也不代表诊断准确率。维护决策需由工程师结合额外测量与检查历史确认。')
    lines.append('')
    filename = f"jilian-ai-replay-{(data.get('record_id') or 'record')[:12]}.md"
    return '\n'.join(lines), filename
