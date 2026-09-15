"""Read-only playback of held-out synthetic sensor observations, never label files."""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
from app.work_state import CHANNELS, FeatureWindow, predict_features

ROOT=Path(__file__).resolve().parents[1]/'data/work_state_v1'


def list_episodes():
    directory=ROOT/'observations/test'
    return [{'episode_id':p.name.removesuffix('.csv.gz'),'source':'synthetic_held_out_sensors'}
        for p in sorted(directory.glob('EP-*.csv.gz'))
        if re.fullmatch(r'EP-[0-9a-f]{12}\.csv\.gz',p.name) and p.resolve().parent==directory.resolve()]


def replay_episode(episode_id, start=0, count=360):
    if not re.fullmatch(r'EP-[0-9a-f]{12}',episode_id): raise ValueError('Invalid episode ID')
    if type(start) is not int or type(count) is not int or not 0<=start<=5759 or not 1<=count<=720:
        raise ValueError('Invalid replay window')
    directory=ROOT/'observations/test'
    path=directory/(episode_id+'.csv.gz')
    if path.resolve().parent!=directory.resolve(): raise ValueError('Invalid source path')
    raw=(ROOT/'model.json').read_bytes()
    expected=json.loads((ROOT/'evaluation.json').read_text(encoding='utf-8'))['model_sha256']
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=expected: raise ValueError('Model artifact hash mismatch')
    model=json.loads(raw)
    if model.get('provenance')!='synthetic_only': raise ValueError('Unexpected model scope')
    with gzip.open(path,'rt',encoding='utf-8',newline='') as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=['recorded_at',*CHANNELS]: raise ValueError('Unexpected sensor schema')
        rows=list(reader)
    if start>=len(rows): raise ValueError('Replay start outside observations')
    features=FeatureWindow();output=[]
    for index in range(max(0,start-2),min(start+count,len(rows))):
        row=rows[index]
        vector=features.add(row)
        if index<start: continue
        result=predict_features(model,vector)
        sensors={c:float(row[c]) for c in CHANNELS}
        if any(not math.isfinite(v) for v in sensors.values()): raise ValueError('Non-finite sensor value')
        output.append({'sample_index':index,'recorded_at':row['recorded_at'],
            'sensors':sensors,'state':result['state'],
            'candidate_state':result.get('candidate_state'),'score':result['score'],'reason':result['reason']})
    return {'episode_id':episode_id,'source':'synthetic_held_out_sensors','model_sha256':digest,
        'total_samples':len(rows),'start':start,'sample_interval_seconds':5,'abstain_below':model['abstain_below'],
        'samples':output,'real_trackunit_supported':False,
        'limitation':'Synthetic-only model. Required rpm/pressure/flow/speed channels are unavailable in current real Trackunit import. Scores are not calibrated probabilities.'}
