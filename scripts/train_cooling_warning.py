"""Episode-isolated early-warning training and event-aware synthetic evaluation."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from app.cooling_warning import CoolingWindow, FEATURES, HORIZON, predict_prefix, model_score

TARGET=ROOT/'data/cooling_warning_v1'


def load_split(split):
    result=[]
    for path in sorted((TARGET/'observations'/split).glob('*.csv.gz')):
        eid=path.name[:-7]
        with gzip.open(path,'rt',encoding='utf-8') as stream: rows=list(csv.DictReader(stream))
        event=json.loads((TARGET/'evaluator_only'/split/eid/'event.json').read_text())
        window=CoolingWindow(); x=[]; labels=[]; indices=[]
        for i,row in enumerate(rows):
            features=window.add(row)
            # Tail without a full horizon is censored. Post-event or already-high
            # readings are current detection, not credited as early prediction.
            if (features is None or float(row['coolant_c'])>=100 or i+HORIZON>=len(rows)
                    or event['event_index'] is not None and i>=event['event_index']): continue
            x.append(features);indices.append(i)
            labels.append(int(event['event_index'] is not None and 0<event['event_index']-i<=HORIZON))
        result.append(dict(episode_id=eid,rows=rows,x=x,y=labels,indices=indices,event=event))
    return result


def persistent_flags(values):
    run=0; result=[]
    for value in values:
        run=run+1 if value else 0
        result.append(run>=2)
    return result


def evaluate(episodes, model):
    reports={}
    for method in ('random_forest','temperature_95c'):
        tp=fp=tn=fn=0; eligible_hours=0.; negative_hours=0.; false_episodes=0; leads=[]; per_episode=[]
        events=0
        for episode in episodes:
            rows=episode['rows']; eid=episode['episode_id']
            if method=='random_forest':
                flags=[p['status']=='warning' for p in predict_prefix(model,rows)]
            else:
                features=CoolingWindow()
                values=[features.add(row) is not None and 95<=float(row['coolant_c'])<100 for row in rows]
                flags=persistent_flags(values)
            eligible=dict(zip(episode['indices'],episode['y']))
            event=episode['event']['event_index']; found=[]; false_active=False; false_count=0
            for i in range(len(rows)):
                if i not in eligible:
                    false_active=False; continue
                y=eligible[i]; flag=flags[i]
                eligible_hours+=1/60
                if not y: negative_hours+=1/60
                tp+=int(y and flag); fn+=int(y and not flag)
                fp+=int(not y and flag); tn+=int(not y and not flag)
                false=bool(flag and not y)
                if false and not false_active: false_count+=1
                false_active=false
                if y and flag: found.append(event-i)
            has_event=event is not None
            events+=has_event
            lead=max(found) if found else None
            if lead is not None: leads.append(lead)
            false_episodes+=false_count
            per_episode.append(dict(episode_id=eid,scenario=episode['event']['scenario'],event_index=event,
                lead_minutes=lead,false_alert_episodes=false_count,eligible_minutes=len(eligible)))
        reports[method]={'events':events,'detected_events':len(leads),
            'event_recall':len(leads)/events if events else None,
            'lead_minutes_detected':leads,'median_lead_minutes':float(np.median(leads)) if leads else None,
            'false_alert_episodes':false_episodes,'eligible_hours':eligible_hours,'negative_eligible_hours':negative_hours,
            'false_alert_episodes_per_eligible_hour':false_episodes/eligible_hours if eligible_hours else None,
            'window_counts':{'tp':tp,'fp':fp,'tn':tn,'fn':fn},
            'window_precision':tp/(tp+fp) if tp+fp else None,'window_recall':tp/(tp+fn) if tp+fn else None,
            'per_episode':per_episode}
    return reports


def main():
    train=load_split('train'); val=load_split('validation')
    x=np.asarray([f for e in train for f in e['x']],dtype=np.float32)
    y=np.asarray([v for e in train for v in e['y']])
    estimator=RandomForestClassifier(n_estimators=48,max_depth=8,min_samples_leaf=10,
        class_weight='balanced',random_state=20260914,n_jobs=4)
    estimator.fit(x,y)
    model={'format':'cooling_forest_v1','feature_names':FEATURES,'classes':estimator.classes_.tolist(),
        'provenance':'synthetic_only','horizon_minutes':HORIZON,'alarm_threshold':.5,'trees':[]}
    for tree_estimator in estimator.estimators_:
        t=tree_estimator.tree_
        model['trees'].append(dict(left=t.children_left.tolist(),right=t.children_right.tolist(),
            feature=t.feature.tolist(),threshold=t.threshold.tolist(),values=t.value[:,0,:].tolist()))
    trials=[]
    for threshold in (.3,.4,.5,.6,.7,.8,.9):
        model['alarm_threshold']=threshold
        metrics=evaluate(val,model)['random_forest']
        trials.append({'threshold':threshold,**{k:metrics[k] for k in
            ('event_recall','median_lead_minutes','false_alert_episodes_per_eligible_hour','window_precision')}})
    acceptable=[r for r in trials if r['false_alert_episodes_per_eligible_hour']<=.1]
    # Fixed before seeing test labels: recall first within the validation false-alert
    # budget, then lead time, then fewer false episodes; strictest threshold breaks ties.
    candidates=acceptable or trials
    winner=max(candidates,key=lambda r:(r['event_recall'] or 0,r['median_lead_minutes'] or 0,
        -r['false_alert_episodes_per_eligible_hour'],r['threshold'])) if acceptable else min(candidates,key=lambda r:r['false_alert_episodes_per_eligible_hour'])
    model['alarm_threshold']=winner['threshold']
    model_path=TARGET/'model.json'
    model_path.write_text(json.dumps(model,separators=(',',':')),encoding='utf-8')
    # Model is now frozen; only now load/evaluate test episodes.
    test=load_split('test')
    groups=[set(e['episode_id'] for e in es) for es in (train,val,test)]
    assert all(not groups[a]&groups[b] for a,b in [(0,1),(0,2),(1,2)])
    probes=np.asarray([f for e in test for f in e['x']][::43],dtype=np.float32)
    expected=estimator.predict_proba(probes)[:,1]
    actual=np.asarray([model_score(model,p) for p in probes])
    parity=float(np.max(np.abs(expected-actual)))
    assert parity<1e-10
    report={'scope':'Synthetic thermal-event warning only; no real failure validation',
        'sklearn_version':sklearn.__version__,'model_sha256':hashlib.sha256(model_path.read_bytes()).hexdigest(),
        'manifest_sha256':hashlib.sha256((TARGET/'manifest.json').read_bytes()).hexdigest(),
        'parameters':{'trees':48,'max_depth':8,'min_samples_leaf':10,'class_weight':'balanced','random_state':20260914},
        'validation_selection':{'false_alert_budget_per_eligible_hour':.1,'trials':trials,'selected_threshold':winner['threshold'],
                                'budget_met':bool(acceptable)},
        'split_counts':{s:len(es) for s,es in [('train',train),('validation',val),('test',test)]},
        'training_windows':len(y),'training_positive_windows':int(y.sum()),'export_max_error':parity,
        'definitions':{'false_alert_episode':'Contiguous confirmed-alert minutes outside the preceding 15-minute event window; separated by an eligible non-alert or ineligible minute.',
                       'lead':'Minutes between the first confirmed alert within the preceding window and event confirmation, at minute resolution; only while observed coolant is below 100C.',
                       'censoring':'Last 15 minutes, post-event samples, stopped/warmup/invalid windows and already-high observations are excluded.',
                       'exposure':'Eligible sampled minutes / 60. Not wall-clock fleet hours. Scenarios intentionally balanced, not real event prevalence.'},
        'validation':evaluate(val,model),'test':evaluate(test,model)}
    (TARGET/'evaluation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (TARGET/'runtime.json').write_text(json.dumps({k:report[k] for k in ('model_sha256','manifest_sha256')},indent=2),encoding='utf-8')
    for name,metrics in report['test'].items():
        print(name,json.dumps({k:v for k,v in metrics.items() if k!='per_episode'}),flush=True)
    print('threshold',winner['threshold'],'parity',parity,flush=True)


if __name__=='__main__':main()
