"""One offline scripted case, kept separate from real assets and history."""
from __future__ import annotations

import json
from pathlib import Path

DEMO_PATH = Path(__file__).resolve().parents[1] / 'data/demo_case.json'
STAGES = ['symptom', 'evidence', 'analysis', 'checks', 'conclusion']


class DemoUnavailable(ValueError):
    def __init__(self):
        super().__init__('模拟案例暂不可用，请检查随项目提供的演示资料。')


def validate_demo(data: object) -> dict:
    """Fail closed if a demo loses its disclosure, references or scope markers."""
    try:
        if (not isinstance(data, dict) or data['schema_version'] != '1'
                or data['case_id'] != 'sim-tv12u-h10101-v1' or data['is_simulation'] is not True
                or data['source']['kind'] != 'scripted_demo' or data['source']['external_calls'] is not False
                or data['machine']['machine_id'] != 'SIM-TV12U-DEMO-001'
                or data['machine']['vin'] is not None or data['machine']['model'] != 'TV12U'
                or data['machine']['protocol_version'] != '260224'):
            raise DemoUnavailable()
        for text in (data['title'], data['disclaimer'], data['source']['label'], data['machine']['applicability'],
                     data['telemetry']['label'], data['conclusion']['status'], data['conclusion']['summary']):
            if not isinstance(text, str) or not text.strip():
                raise DemoUnavailable()
        if '模拟' not in data['disclaimer'] or '预设' not in data['source']['label'] or '模拟' not in data['telemetry']['label']:
            raise DemoUnavailable()
        evidence = data['evidence']
        if not isinstance(evidence, list) or not evidence:
            raise DemoUnavailable()
        ids = {item['id'] for item in evidence}
        if len(ids) != len(evidence) or 'protocol-h10101' not in ids:
            raise DemoUnavailable()
        for item in evidence:
            if any(not isinstance(item[k], str) or not item[k].strip() for k in ('id', 'kind', 'label', 'text', 'source_note')):
                raise DemoUnavailable()
        if [stage['id'] for stage in data['stages']] != STAGES:
            raise DemoUnavailable()
        for items, fields in ((data['stages'], ('label', 'title', 'summary')),
                              (data['checks'], ('id', 'title', 'action', 'simulated_result')),
                              (data['parts'], ('name', 'category', 'reason', 'status'))):
            if any(not isinstance(item[field], str) or not item[field].strip() for item in items for field in fields):
                raise DemoUnavailable()
        for lines in [data['telemetry']['assumptions'], data['conclusion']['limitations'],
                      *(stage['details'] for stage in data['stages'])]:
            if not isinstance(lines, list) or not lines or any(not isinstance(line, str) or not line.strip() for line in lines):
                raise DemoUnavailable()
        for item in [*data['stages'], *data['checks'], *data['parts']]:
            refs = item['evidence_ids']
            if not isinstance(refs, list) or not refs or not set(refs) <= ids:
                raise DemoUnavailable()
        if not data['checks'] or not data['parts']:
            raise DemoUnavailable()
        for part in data['parts']:
            if part['part_number'] is not None or part['stock'] is not None:
                raise DemoUnavailable()
        points = data['telemetry']['points']
        minutes = [point['minute'] for point in points]
        if len(points) < 3 or minutes != sorted(set(minutes)):
            raise DemoUnavailable()
        for point in points:
            if not isinstance(point['phase'], str) or not point['phase'].strip():
                raise DemoUnavailable()
            for name in ('minute', 'engine_rpm', 'system_voltage_v', 'hydraulic_oil_temperature_c',
                         'left_travel_command_percent', 'left_travel_response_percent'):
                value = point[name]
                if type(value) not in (int, float) or not 0 <= value < float('inf'):
                    raise DemoUnavailable()
            if any(not 0 <= point[k] <= 100 for k in ('left_travel_command_percent', 'left_travel_response_percent')):
                raise DemoUnavailable()
            if point['fault_code'] not in (None, 'H10101'):
                raise DemoUnavailable()
            if point['engine_rpm'] == 0 and (point['left_travel_command_percent'] or point['left_travel_response_percent']):
                raise DemoUnavailable()
    except (KeyError, TypeError, AttributeError):
        raise DemoUnavailable() from None
    return data


def load_demo() -> dict:
    try:
        with DEMO_PATH.open('rb') as handle:
            content = handle.read(100_001)
        if len(content) > 100_000:
            raise DemoUnavailable()
        return validate_demo(json.loads(content.decode('utf-8-sig')))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        raise DemoUnavailable() from None


def render_demo_report(data: dict) -> str:
    """Build a deterministic Markdown report without I/O or changing the case."""
    case = validate_demo(data)
    machine = case['machine']
    lines = [
        f"# {case['title']}", '', f"> {case['source']['label']}", '',
        '## 模拟声明', '', case['disclaimer'], '',
        f"- 案例编号：{case['case_id']}",
        f"- 演示设备：{machine['machine_id']} · {machine['model']}",
        f"- 协议版本：{machine['protocol_version']}",
        f"- 适用范围：{machine['applicability']}",
        '- 外部服务调用：无。此报告由已保存的模拟案例生成。', '',
        '## 五阶段排查过程', '',
    ]

    def references(item: dict) -> str:
        return '依据编号：' + '、'.join(item['evidence_ids']) + '（见文末证据与来源）。'

    for stage in case['stages']:
        lines.extend([f"### {stage['label']} · {stage['title']}", '', stage['summary'], ''])
        lines.extend(f'- {detail}' for detail in stage['details'])
        lines.extend(['', references(stage), ''])

    lines.extend(['## 检查记录与预设结果', ''])
    for check in case['checks']:
        lines.extend([f"### {check['title']}", '', f"记录项目：{check['action']}", '',
                      f"预设结果：{check['simulated_result']}", '', references(check), ''])

    lines.extend(['## 备件候选类型', '', '以下仅列部件类型；准确料号与整机适配需另行核对。', ''])
    for part in case['parts']:
        lines.extend([f"### {part['name']}", '', f"- 类型：{part['category']}",
                      f"- 候选依据：{part['reason']}", f"- 状态：{part['status']}",
                      '- 料号：未提供', '- 库存：未提供', '', references(part), ''])

    lines.extend(['## 模拟结论与限制', '', case['conclusion']['status'], '', case['conclusion']['summary'], ''])
    lines.extend(f'- {item}' for item in case['conclusion']['limitations'])
    lines.extend(['', '## 工况假设', '', case['telemetry']['label'], ''])
    lines.extend(f'- {item}' for item in case['telemetry']['assumptions'])
    lines.extend(['', '## 证据与来源', ''])
    for evidence in case['evidence']:
        lines.extend([f"### {evidence['id']} · {evidence['label']}", '', evidence['text'], '',
                      f"来源说明：{evidence['source_note']}", ''])
    return '\n'.join(lines)
