"""Causal sensor features and numeric-tree inference for synthetic work-state demo."""
from collections import deque
from datetime import datetime
import math
import struct

CHANNELS = ('engine_rpm','hydraulic_pressure_bar','hydraulic_flow_lpm','speed_kmh')
FEATURES = [f'{c}_{kind}' for kind in ('current','mean3','delta3') for c in CHANNELS]
LIMITS = ((0,2500),(0,400),(0,500),(0,6))
LABELS = ('dig','swing','dump','idle','travel','off')


class FeatureWindow:
    def __init__(self):
        self.rows=deque(maxlen=3)
        self.last_at=None

    def add(self, row):
        try:
            instant=datetime.fromisoformat(row['recorded_at'].replace('Z','+00:00'))
            if instant.tzinfo is None: raise ValueError('timezone required')
            values=[float(row[c]) for c in CHANNELS]
            if any(isinstance(row[c],bool) for c in CHANNELS): raise ValueError('boolean sensor')
            if any(not math.isfinite(v) or not low<=v<=high for v,(low,high) in zip(values,LIMITS)): raise ValueError('sensor range')
            if self.last_at is not None and instant<=self.last_at: raise ValueError('non-increasing time')
        except (KeyError,ValueError,TypeError,AttributeError,OverflowError):
            self.rows.clear();self.last_at=None
            return None
        if self.last_at is not None and (instant-self.last_at).total_seconds()>15:
            self.rows.clear()
        self.last_at=instant;self.rows.append(values)
        means=[sum(r[i] for r in self.rows)/len(self.rows) for i in range(len(CHANNELS))]
        deltas=[v-self.rows[0][i] for i,v in enumerate(values)]
        return values+means+deltas


def predict_features(model, features):
    if features is None:
        return {'state':'unknown','reason':'missing_invalid_or_unordered_sensor_data','score':None}
    if model.get('feature_names')!=FEATURES or model.get('format')!='numeric_random_forest_v1':
        raise ValueError('Unsupported model feature contract')
    # sklearn's tree prediction consumes float32 features.
    values=[struct.unpack('f',struct.pack('f',v))[0] for v in features]
    probabilities=[0.0]*len(model['classes'])
    for tree in model['trees']:
        node=0
        while tree['left'][node]!=-1:
            node=tree['left'][node] if values[tree['feature'][node]]<=tree['threshold'][node] else tree['right'][node]
        weights=tree['values'][node];total=sum(weights)
        for i,v in enumerate(weights): probabilities[i]+=v/total/len(model['trees'])
    best=max(range(len(probabilities)),key=probabilities.__getitem__)
    score=probabilities[best]
    return {'state':model['classes'][best] if score>=model['abstain_below'] else 'unknown',
        'candidate_state':model['classes'][best], 'score':score,
        'scores':dict(zip(model['classes'],probabilities)),
        'reason':'synthetic_model_only' if score>=model['abstain_below'] else 'low_model_score',
        'limitation':'Model vote scores are not calibrated probabilities; synthetic-only validation.'}
