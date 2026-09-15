"""Causal minute-sensor model. This predicts a synthetic thermal event, not damage."""
from collections import deque
from datetime import datetime
import math
import struct

CHANNELS = ('coolant_c', 'ambient_c', 'engine_rpm', 'hydraulic_pressure_bar', 'hydraulic_flow_lpm')
RANGES = ((-20, 130), (-20, 50), (0, 2500), (0, 400), (0, 500))
FEATURES = ['coolant_current', 'ambient_current', 'rpm_current', 'hydraulic_kw_current',
            'coolant_mean5', 'coolant_mean10', 'coolant_delta1', 'coolant_delta5',
            'coolant_delta10', 'hydraulic_kw_mean5', 'hydraulic_kw_mean10', 'rpm_mean10']
HORIZON = 15
EVENT_TEMPERATURE = 100


def sensor_values(row):
    try:
        instant = datetime.fromisoformat(row['recorded_at'].replace('Z', '+00:00'))
        if instant.tzinfo is None: return None
        values = [float(row[c]) for c in CHANNELS]
        if any(isinstance(row[c], bool) for c in CHANNELS): return None
        if any(not math.isfinite(v) or not lo <= v <= hi for v, (lo, hi) in zip(values, RANGES)): return None
        return instant, values
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
        return None


class CoolingWindow:
    def __init__(self):
        self.rows = deque(maxlen=11)
        self.last_at = None
        self.reason = 'insufficient_history'

    def add(self, row):
        parsed = sensor_values(row)
        self.reason = 'invalid_sensor'
        if parsed is None:
            self.rows.clear(); self.last_at = None
            return None
        instant, values = parsed
        if self.last_at is not None and (instant - self.last_at).total_seconds() != 60:
            self.rows.clear()
            if instant <= self.last_at:
                self.last_at = None
                self.reason = 'unordered_time'
                return None
        self.last_at = instant
        if values[2] < 500:
            self.rows.clear(); self.reason = 'engine_stopped'
            return None
        self.rows.append(values)
        if len(self.rows) < 11:
            self.reason = 'insufficient_history'
            return None
        data = list(self.rows)
        temps = [r[0] for r in data]
        if max(temps) == min(temps):
            self.reason = 'constant_temperature_sensor'
            return None
        loads = [r[3] * r[4] / 600 for r in data]
        self.reason = 'synthetic_model_only'
        return [*values[:3], loads[-1], sum(temps[-5:])/5, sum(temps[-10:])/10,
                temps[-1]-temps[-2], temps[-1]-temps[-6], temps[-1]-temps[-11],
                sum(loads[-5:])/5, sum(loads[-10:])/10, sum(r[2] for r in data[-10:])/10]


def model_score(model, features):
    values = [struct.unpack('f', struct.pack('f', v))[0] for v in features]
    score = 0.
    for tree in model['trees']:
        node = 0
        while tree['left'][node] != -1:
            node = tree['left'][node] if values[tree['feature'][node]] <= tree['threshold'][node] else tree['right'][node]
        weights = tree['values'][node]
        score += weights[1] / sum(weights) / len(model['trees'])
    return score


def predict_prefix(model, rows):
    confirmation = model.get('alarm_consecutive_minutes', 2)
    if (model.get('format') != 'cooling_forest_v1' or model.get('feature_names') != FEATURES
            or model.get('classes') != [0, 1] or model.get('provenance') != 'synthetic_only'
            or model.get('horizon_minutes') != HORIZON or not model.get('trees')
            or not 0 < model.get('alarm_threshold', 0) <= 1
            or type(confirmation) is not int or confirmation not in (2, 3, 4)):
        raise ValueError('Unsupported cooling model contract')
    window = CoolingWindow(); consecutive = 0; result = []
    for index, row in enumerate(rows):
        features = window.add(row); parsed = sensor_values(row)
        score = None; status = 'unknown'; reason = window.reason
        if parsed and reason != 'unordered_time' and parsed[1][0] >= EVENT_TEMPERATURE:
            status = 'current_high'; reason = 'observed_experimental_threshold'
        elif reason == 'engine_stopped':
            status = 'stopped'
        elif features is not None:
            score = model_score(model, features)
            consecutive = consecutive+1 if score >= model['alarm_threshold'] else 0
            status = 'warning' if consecutive >= confirmation else 'watch' if consecutive else 'below_threshold'
        if score is None: consecutive = 0
        result.append({'sample_index': index, 'recorded_at': row['recorded_at'], 'status': status,
                       'score': score, 'reason': reason,
                       'coolant_delta10': features[8] if features else None,
                       'hydraulic_kw_mean10': features[10] if features else None})
    return result
