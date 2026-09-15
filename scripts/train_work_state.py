"""Synthetic sensor training; episode split and labels never enter feature inputs."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score,classification_report,confusion_matrix,f1_score
from app.work_state import CHANNELS,FEATURES,LABELS,FeatureWindow,predict_features

SOURCE=ROOT/'data/synthetic_diagnostics_v1/evaluator_only'
TARGET=ROOT/'data/work_state_v1'
STATE_MAP={'loaded_swing':'swing','return_swing':'swing','warmup':'idle',**{s:s for s in LABELS}}


def sensor_row(row,rng):
    # Only physical sensor channels are observed. Labels, elapsed time, episode ID,
    # scenario, coordinates and latent power never enter the feature vector.
    rpm,pressure,flow,speed=(float(row[c]) for c in CHANNELS)
    return {'recorded_at':row['timestamp'],
        'engine_rpm':round(max(0,rpm+rng.gauss(0,20)),1),
        'hydraulic_pressure_bar':round(max(0,pressure+rng.gauss(0,max(2,pressure*.08))),2),
        'hydraulic_flow_lpm':round(max(0,flow+rng.gauss(0,max(1,flow*.08))),2),
        'speed_kmh':round(max(0,speed+rng.gauss(0,.08)),3)}


def load_split(split):
    X=[];y=[];episodes=[];hashes={};counts={}
    export=TARGET/'observations'/split;export.mkdir(parents=True,exist_ok=True)
    for path in sorted((SOURCE/split).glob('*/physical_truth.csv.gz')):
        eid=path.parent.name
        rng=random.Random(int(hashlib.sha256(eid.encode()).hexdigest()[:16],16)+946)
        window=FeatureWindow();n=0
        hashes[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
        with gzip.open(path,'rt',encoding='utf-8',newline='') as stream, gzip.open(export/(eid+'.csv.gz'),'wt',encoding='utf-8',newline='') as out:
            writer=csv.DictWriter(out,fieldnames=['recorded_at',*CHANNELS]);writer.writeheader()
            for row in csv.DictReader(stream):
                observation=sensor_row(row,rng);writer.writerow(observation)
                features=window.add(observation)
                if features is None: raise ValueError('Unexpected invalid generated sensor row')
                X.append(features);y.append(STATE_MAP[row['work_state']]);episodes.append(eid);n+=1
        counts[eid]=n
    if not X: raise ValueError('Missing synthetic input split')
    return np.asarray(X,dtype=np.float32),np.asarray(y),episodes,hashes,counts


def run():
    TARGET.mkdir(parents=True,exist_ok=True)
    datasets={s:load_split(s) for s in ('train','validation','test')}
    for a,b in [('train','validation'),('train','test'),('validation','test')]:
        assert not set(datasets[a][2]) & set(datasets[b][2])
    train_x,train_y=datasets['train'][:2]
    estimator=RandomForestClassifier(n_estimators=64,max_depth=10,min_samples_leaf=12,class_weight='balanced',random_state=20260914,n_jobs=4)
    estimator.fit(train_x,train_y)
    model={'format':'numeric_random_forest_v1','feature_names':FEATURES,'classes':estimator.classes_.tolist(),
        'abstain_below':.65,'provenance':'synthetic_only','trees':[]}
    for estimator_tree in estimator.estimators_:
        tree=estimator_tree.tree_
        model['trees'].append({'left':tree.children_left.tolist(),'right':tree.children_right.tolist(),
            'feature':tree.feature.tolist(),'threshold':tree.threshold.tolist(),'values':tree.value[:,0,:].tolist()})
    model_path=TARGET/'model.json';model_path.write_text(json.dumps(model,separators=(',',':')),encoding='utf-8')
    majority=Counter(train_y).most_common(1)[0][0]
    report={'scope':'Synthetic noisy sensor experiment, not real equipment accuracy','sklearn_version':sklearn.__version__,
        'features':FEATURES,'noise_assumptions':{'rpm_sigma':20,'pressure_sigma':'max(2bar,8%)','flow_sigma':'max(1lpm,8%)','speed_sigma_kmh':.08},
        'parameters':{'trees':64,'max_depth':10,'min_samples_leaf':12,'class_weight':'balanced','random_state':20260914,'abstain_below':.65},
        'label_mapping':STATE_MAP,'model_sha256':hashlib.sha256(model_path.read_bytes()).hexdigest(),
        'input_hashes':{k:v for data in datasets.values() for k,v in data[3].items()},'splits':{}}
    for split,(x,y,episodes,hashes,counts) in datasets.items():
        scores=estimator.predict_proba(x);pred=estimator.classes_[scores.argmax(axis=1)];accepted=scores.max(axis=1)>=.65
        result={'rows':len(y),'episodes':counts,'class_counts':dict(Counter(y)),
            'accuracy':float(accuracy_score(y,pred)),'macro_f1':float(f1_score(y,pred,average='macro')),
            'majority_baseline_accuracy':float(np.mean(y==majority)), 'accepted_coverage':float(accepted.mean()),
            'accepted_accuracy':float(accuracy_score(y[accepted],pred[accepted])) if accepted.any() else None,
            'class_order':estimator.classes_.tolist(),'confusion_matrix':confusion_matrix(y,pred,labels=estimator.classes_).tolist(),
            'per_class':classification_report(y,pred,output_dict=True,zero_division=0)}
        report['splits'][split]=result
        print(split,json.dumps({k:result[k] for k in ('rows','accuracy','macro_f1','accepted_coverage','accepted_accuracy')}),flush=True)
    # Numeric-tree export parity on 200 deterministically spaced held-out inputs.
    probes=datasets['test'][0][::max(1,len(datasets['test'][0])//200)][:200]
    expected=estimator.predict_proba(probes)
    actual=np.asarray([[predict_features(model,row)['scores'][c] for c in model['classes']] for row in probes])
    report['export_max_probability_error']=float(np.max(np.abs(expected-actual)))
    assert report['export_max_probability_error']<1e-10
    (TARGET/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved numeric model, sensor-only observations and evaluation',flush=True)


if __name__=='__main__': run()
