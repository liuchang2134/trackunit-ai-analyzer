"""Local capture replay and an entirely independent synthetic teaching scenario.

The real capture loader has NO cloud/AI call path. Synthetic values are generated
from constants only, never from a capture, VIN, profile workbook or private file.
"""
import json
import math
from pathlib import Path

REPLAY_PATH = Path(__file__).resolve().parents[1] / 'data/local/can-demo/replay.json'


def recorded_replay():
    return json.loads(REPLAY_PATH.read_text(encoding='utf-8'))


def synthetic_replay():
    """Illustrative generic loader, not an XC948U calibration or field failure."""
    definitions = [
        ('coolant', '冷却液温度', '°C', lambda t: 78 + min(max(t - 120, 0) * .1, 32)),
        ('rpm', '发动机转速', 'rpm', lambda t: 900 + 12 * math.sin(t / 12)),
        ('oil', '机油压力', 'kPa', lambda t: 220 + 8 * math.sin(t / 15)),
        ('voltage', '电源电压', 'V', lambda t: 27.5 + .1 * math.sin(t / 17)),
        ('load', '发动机负载', '%', lambda t: 45 + 4 * math.sin(t / 20)),
        ('fuel', '瞬时油耗', 'L/h', lambda t: 6 + .4 * math.sin(t / 20)),
        ('hours', '累计工时', 'h', lambda t: 50 + t / 3600),
    ]
    signals = [{'key': key, 'name': name, 'unit': unit, 'points': [
        {'t': t, 'value': round(fn(t), 3), 'line': None, 'raw': None, 'can_id': None}
        for t in range(481)]} for key, name, unit, fn in definitions]
    return {'scenario': 'synthetic', 'source_kind': 'synthetic', 'model': '装载机 · 模拟工况', 'vin': None,
            'capture_id': 'SIM-COOLING-001', 'duration': 480, 'frame_count': None, 'signals': signals,
            'diagnostics': [], 'sampling': '独立公式生成；1 秒采样。',
            'source_note': '教学假设：转速与负载基本稳定，冷却液逐步升温。全部数值为模拟，不对应真实车辆或厂商阈值。'}


def synthetic_evidence(at: int):
    """The only evidence source allowed for the synthetic AI demo."""
    data = synthetic_replay()
    rows = []
    for index, signal in enumerate(data['signals'], 1):
        points = [p for p in signal['points'] if max(0, at - 120) <= p['t'] <= at]
        values = [p['value'] for p in points]
        rows.append({'id': f'S{index}', 'name': signal['name'], 'unit': signal['unit'],
                     'start_s': points[0]['t'], 'end_s': points[-1]['t'], 'first': values[0], 'last': values[-1],
                     'min': min(values), 'max': max(values), 'samples': len(values)})
    return {'source_kind': 'synthetic', 'scenario': 'SIM-COOLING-001', 'at': at, 'window_seconds': 120,
            'description': data['source_note'], 'evidence': rows}
