"""Observation-only replay and a verified synthetic-device investigation handoff."""
import csv
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

from app.cooling_warning import CHANNELS, predict_prefix

ROOT=Path(__file__).resolve().parents[1]/'data/cooling_warning_v1'
OBS_FIELDS=['recorded_at',*CHANNELS,'operating_hours','idle_hours','fuel_percent']
LIMITATION='模拟热事件模型；未经实机验证。得分不是故障概率；100°C/180秒为本实验事件定义，不是制造商限值。'
EXTENDED_EVALUATION_SHA256='1a3cde3c2437005a3828751b7eb3a23c12367b03da6a56151b2eb8689efbb607'
EXTENDED_ORIGINAL_MODEL_SHA256='d62c4998a3557bb857c125fa61e316ff08115e460c72157fa938c3de460177bb'


def artifacts():
    runtime=json.loads((ROOT/'runtime.json').read_text(encoding='utf-8'))
    model_raw=(ROOT/'model.json').read_bytes(); manifest_raw=(ROOT/'manifest.json').read_bytes()
    if (hashlib.sha256(model_raw).hexdigest()!=runtime['model_sha256']
            or hashlib.sha256(manifest_raw).hexdigest()!=runtime['manifest_sha256']):
        raise ValueError('Cooling artifact hash mismatch')
    model=json.loads(model_raw); manifest=json.loads(manifest_raw)
    if manifest.get('source')!='synthetic_only' or manifest.get('sample_interval_seconds')!=60:
        raise ValueError('Cooling manifest contract mismatch')
    return model,manifest,runtime


def list_episodes():
    _,manifest,_=artifacts()
    return [{'episode_id':e['episode_id'],'samples':e['samples'],'source':'synthetic_only'}
            for e in manifest['episodes'] if e['split']=='test']


def prefix(episode_id, cursor):
    if not re.fullmatch(r'CW-[0-9a-f]{12}',episode_id) or type(cursor) is not int or not 0<=cursor<480:
        raise ValueError('Invalid cooling cursor')
    model,manifest,runtime=artifacts()
    entry=next((e for e in manifest['episodes'] if e['episode_id']==episode_id and e['split']=='test'),None)
    if entry is None: raise FileNotFoundError('Cooling episode not found')
    path=ROOT/'observations/test'/(episode_id+'.csv.gz')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sensor_sha256']:
        raise ValueError('Cooling observation hash mismatch')
    rows=[]
    with gzip.open(path,'rt',encoding='utf-8',newline='') as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=OBS_FIELDS: raise ValueError('Cooling observation schema mismatch')
        for i,row in enumerate(reader):
            if i>cursor: break
            clean={'recorded_at':row['recorded_at']}
            for field in OBS_FIELDS[1:]:
                try: value=float(row[field]); clean[field]=value if math.isfinite(value) else None
                except (ValueError,TypeError): clean[field]=None
            rows.append(clean)
    if len(rows)!=cursor+1 or cursor>=entry['samples']: raise ValueError('Cooling cursor out of range')
    return rows,model,entry,runtime


def replay(episode_id, cursor):
    rows,model,entry,runtime=prefix(episode_id,cursor)
    predictions=predict_prefix(model,rows)
    return {'episode_id':episode_id,'cursor':cursor,'samples':entry['samples'],
            'source':'synthetic_only','machine_id':'SIM-'+episode_id,
            'cutoff':rows[-1]['recorded_at'],'horizon_minutes':15,'alarm_threshold':model['alarm_threshold'],
            'event_temperature_c':100,'event_duration_seconds':180,'model_sha256':runtime['model_sha256'],
            'sensor_sha256':entry['sensor_sha256'],'prediction':predictions[-1],
            'history':[{'observation':row,'prediction':p} for row,p in zip(rows,predictions)][-61:],
            'real_trackunit_supported':False,'limitation':LIMITATION}


def prefix_dataset(episode_id,cursor):
    from app.local_datasets import LocalDataset
    from app.models import Machine,TelemetrySnapshot
    rows,_,_,runtime=prefix(episode_id,cursor)
    machine_id='SIM-'+episode_id
    return LocalDataset(name=f'冷却预警 {episode_id} · 第{cursor+1}分钟',
        provenance='synthetic',source_document='冷却热平衡模拟 v1；仅供演示；数据截止 '+rows[-1]['recorded_at'],
        replay_at=datetime.fromisoformat(rows[-1]['recorded_at']),
        cooling_reference={'episode_id':episode_id,'cursor':cursor,'model_sha256':runtime['model_sha256']},
        machine=Machine(machine_id=machine_id,serial_number=machine_id,model='SIM-EXC-90kW',
            machine_type='diesel_hydraulic_excavator',customer='模拟演示',location='独立虚拟设备',
            last_seen_at=rows[-1]['recorded_at']),
        telemetry=[TelemetrySnapshot(machine_id=machine_id,recorded_at=row['recorded_at'],
            operating_hours=row['operating_hours'],idle_hours=row['idle_hours'],fuel_remaining_percent=row['fuel_percent'],
            engine_status='unknown' if row['engine_rpm'] is None else 'running' if row['engine_rpm']>=500 else 'stopped') for row in rows])


def prepare(episode_id,cursor):
    from app.local_datasets import save_dataset
    dataset=prefix_dataset(episode_id,cursor)
    return {**save_dataset(dataset),'cooling':verified_context(dataset),
            'question':'解释这个模拟片段的冷却预警、温度变化和数据局限。不能将模型得分当作故障概率或据此指定更换零件。'}


def verified_context(dataset):
    reference=dataset.cooling_reference
    if reference is None: return None
    expected=prefix_dataset(reference.episode_id,reference.cursor)
    if expected.model_dump()!=dataset.model_dump(): raise ValueError('Cooling dataset/source/cutoff mismatch')
    result=replay(reference.episode_id,reference.cursor)
    return {'method':'cooling_warning_v1','source':'synthetic_only','machine_id':result['machine_id'],
            'episode_id':reference.episode_id,'cutoff':result['cutoff'],'model_sha256':result['model_sha256'],
            'horizon_minutes':15,'alarm_threshold':result['alarm_threshold'],'prediction':result['prediction'],
            'event_definition':{'temperature_c':100,'continuous_seconds':180,'meaning':'experimental thermal event, not component failure'},
            'latest_observations':[p['observation'] for p in result['history'][-11:]],'limitation':LIMITATION}


def evaluation():
    _,_,runtime=artifacts()
    result=json.loads((ROOT/'evaluation.json').read_text(encoding='utf-8'))
    if result['model_sha256']!=runtime['model_sha256']: raise ValueError('Evaluation model mismatch')
    # Aggregate post-hoc assessment only; no episode event times in normal runtime responses.
    return {**{k:result[k] for k in ('scope','split_counts','validation_selection','definitions')},
        'extended':extended_evaluation(runtime['model_sha256']),
        'test':{name:{k:v for k,v in metrics.items() if k!='per_episode'} for name,metrics in result['test'].items()}}


def extended_evaluation(model_sha256):
    if model_sha256!=EXTENDED_ORIGINAL_MODEL_SHA256:
        return {'status':'unavailable','reason':'扩展评估与当前模型不匹配。'}
    try:
        raw=(ROOT.parent/'cooling_alarm_calibration_v2/evaluation.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=EXTENDED_EVALUATION_SHA256:
            raise ValueError('Evaluation hash mismatch')
        result=json.loads(raw)
        keys=('episodes','events','detected_events','event_recall','median_lead_minutes',
              'false_alert_episodes','false_alert_episodes_per_eligible_hour','eligible_hours','false_alert_minutes')
        reports={}
        for name in ('original','candidate','temperature_95c'):
            metrics=result['reports'][name]
            reports[name]={'overall':{key:metrics['overall'][key] for key in keys},
                'groups':{group:{key:metrics['groups'][group][key] for key in keys} for group in ('nominal','shifted')}}
        return {'status':'available','source':'synthetic_only','evaluated_at':result['evaluated_at'],
            'evaluation_sha256':EXTENDED_EVALUATION_SHA256,'current_model_sha256':model_sha256,
            'candidate_adopted':False,'candidate_passed_protocol':result['deployable_under_protocol'],
            'reports':reports,'limitation':'扩大模拟测试仍有漏报和误报，候选报警参数未通过预设门槛。不能当作实机故障预测效果。'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'status':'unavailable','reason':'扩展评估文件缺失或未通过完整性校验，不能展示其指标。'}
