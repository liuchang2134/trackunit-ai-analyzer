"""Frozen-model stress evaluation on held-out synthetic episodes; never retrains."""
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.work_state import CHANNELS,LABELS,FeatureWindow,predict_features

VARIANTS=('baseline','missing_pressure_20pct','additional_noise','pressure_freeze')
STATE_MAP={'loaded_swing':'swing','return_swing':'swing','warmup':'idle',**{s:s for s in LABELS}}


def stress_row(row,index,variant,rng,held):
    changed=dict(row);affected=False
    if variant=='missing_pressure_20pct' and index%5==0:
        changed['hydraulic_pressure_bar']=None;affected=True
    elif variant=='additional_noise':
        for channel,sigma in zip(CHANNELS,[60,max(6,float(row[CHANNELS[1]])*.24),max(3,float(row[CHANNELS[2]])*.24),.24]):
            changed[channel]=max(0,float(row[channel])+rng.gauss(0,sigma))
        affected=True
    elif variant=='pressure_freeze':
        if index%720==120: held=float(row['hydraulic_pressure_bar'])
        if 120<=index%720<360:
            changed['hydraulic_pressure_bar']=held;affected=True
    return changed,affected,held


def summary(counts):
    total=counts['total'];accepted=counts['accepted'];high=counts['high_score']
    return {**counts,'coverage':accepted/total if total else None,
        'accepted_accuracy':counts['correct']/accepted if accepted else None,
        'unknown_fraction':counts['unknown']/total if total else None,
        'high_score_error_fraction':counts['high_score_wrong']/high if high else None}


def score(counts,prediction,truth):
    counts['total']+=1
    if prediction['state']=='unknown':counts['unknown']+=1
    else:
        counts['accepted']+=1
        counts['correct']+=prediction['state']==truth
    if prediction['score'] is not None and prediction['score']>=.9:
        counts['high_score']+=1
        counts['high_score_wrong']+=prediction['candidate_state']!=truth


def run():
    base=ROOT/'data/work_state_v1'
    raw=(base/'model.json').read_bytes();model=json.loads(raw)
    digest=hashlib.sha256(raw).hexdigest()
    assert digest==json.loads((base/'evaluation.json').read_text(encoding='utf-8'))['model_sha256']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'scope':'Frozen-model synthetic stress tests, not field performance',
        'model_sha256':digest,'seed':20260914,'assumptions':{
            'missing_pressure_20pct':'Every fifth pressure observation is missing; no imputation.',
            'additional_noise':'Independent extra Gaussian noise: rpm60, pressure max(6bar,24%observed), flow max(3lpm,24%observed), speed0.24km/h; floor zero.',
            'pressure_freeze':'Hold pressure at minute10 value through minute30 of each hour. Other sensors remain observed. Affected rows reported separately.'},
        'input_hashes':{},'code_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['app/work_state.py','scripts/stress_work_state.py']},'results':{}}
    episodes=[]
    for path in sorted((base/'observations/test').glob('*.csv.gz')):
        eid=path.name.removesuffix('.csv.gz')
        label_path=ROOT/'data/synthetic_diagnostics_v1/evaluator_only/test'/eid/'physical_truth.csv.gz'
        with gzip.open(path,'rt',newline='') as stream:rows=list(csv.DictReader(stream))
        with gzip.open(label_path,'rt',newline='') as stream:truth=list(csv.DictReader(stream))
        assert len(rows)==len(truth)
        assert all(r['recorded_at']==t['timestamp'] for r,t in zip(rows,truth))
        for p in (path,label_path):report['input_hashes'][str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
        episodes.append((eid,rows,[STATE_MAP[t['work_state']] for t in truth]))
    for variant in VARIANTS:
        all_counts=Counter();affected_counts=Counter();per_class={s:Counter() for s in LABELS};examples=[]
        for eid,rows,truth in episodes:
            rng=random.Random(int(hashlib.sha256(eid.encode()).hexdigest()[:16],16)+20260914)
            window=FeatureWindow();held=None
            for index,(row,label) in enumerate(zip(rows,truth)):
                altered,affected,held=stress_row(row,index,variant,rng,held)
                pred=predict_features(model,window.add(altered))
                score(all_counts,pred,label);score(per_class[label],pred,label)
                if affected:score(affected_counts,pred,label)
                if affected and pred['state']!='unknown' and pred['state']!=label and (pred['score'] or 0)>=.9 and len(examples)<12:
                    examples.append({'episode_id':eid,'sample_index':index,'true_state':label,'prediction':pred,'observations':altered})
        report['results'][variant]={'all':summary(all_counts),'affected_only':summary(affected_counts),
            'per_class':{s:summary(c) for s,c in per_class.items()},'high_score_error_examples':examples}
        print(variant,json.dumps(report['results'][variant]['all']),flush=True)
    destination=ROOT/'docs/evaluation'/('work-state-stress-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved '+destination.name,flush=True)


if __name__=='__main__':run()
