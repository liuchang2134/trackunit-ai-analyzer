import csv
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from app import cooling_demo as demo, local_datasets as store
from app.cooling_warning import FEATURES
from app.main import app

EID='CW-0123456789ab'


@pytest.fixture
def artifacts(tmp_path,monkeypatch):
    monkeypatch.setattr(demo,'ROOT',tmp_path)
    monkeypatch.setattr(store,'DATASETS',tmp_path/'datasets')
    model=dict(format='cooling_forest_v1',feature_names=FEATURES,classes=[0,1],
        provenance='synthetic_only',horizon_minutes=15,alarm_threshold=.6,
        trees=[dict(left=[-1],right=[-1],feature=[-2],threshold=[-2],values=[[.1,.9]])])
    path=tmp_path/'observations/test'/(EID+'.csv.gz'); path.parent.mkdir(parents=True)
    base=datetime(2026,1,1,tzinfo=timezone.utc)
    with gzip.open(path,'wt',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=demo.OBS_FIELDS);writer.writeheader()
        for i in range(30): writer.writerow(dict(recorded_at=(base+timedelta(minutes=i)).isoformat(),
            coolant_c=85+i*.1,ambient_c=25,engine_rpm=1700,hydraulic_pressure_bar=180,
            hydraulic_flow_lpm=100,operating_hours=200+i/60,idle_hours=20,fuel_percent=80-i*.02))
    manifest={'source':'synthetic_only','sample_interval_seconds':60,'episodes':[dict(episode_id=EID,split='test',samples=30,
        sensor_sha256=hashlib.sha256(path.read_bytes()).hexdigest())]}
    for name,data in [('model',model),('manifest',manifest)]:
        (tmp_path/(name+'.json')).write_text(json.dumps(data),encoding='utf-8')
    (tmp_path/'runtime.json').write_text(json.dumps({name+'_sha256':hashlib.sha256((tmp_path/(name+'.json')).read_bytes()).hexdigest()
                                                  for name in ('model','manifest')}))
    return tmp_path


def test_replay_does_not_need_or_expose_evaluator_truth(artifacts):
    result=demo.replay(EID,14)
    assert result['prediction']['status']=='warning'
    assert len(result['history'])==15
    assert all(p['observation']['recorded_at']<=result['cutoff'] for p in result['history'])
    assert not (artifacts/'evaluator_only').exists()
    assert all(term not in json.dumps(result) for term in ('event_index','cooling_effectiveness','scenario'))


def test_handoff_is_idempotent_and_exact_source_prefix(artifacts):
    prepared=demo.prepare(EID,14)
    assert demo.prepare(EID,14)['dataset_id']==prepared['dataset_id']
    dataset=store.load_dataset(prepared['dataset_id'])
    assert len(dataset.telemetry)==15 and not dataset.faults
    assert dataset.machine.machine_id=='SIM-'+EID
    assert dataset.replay_at.isoformat()==prepared['cooling']['cutoff']
    assert demo.prepare(EID,15)['dataset_id']!=prepared['dataset_id']


@pytest.mark.parametrize('mutation',['machine','temperature_time','model','telemetry','real'])
def test_handoff_tampering_is_rejected_before_ai(artifacts,monkeypatch,mutation):
    from app import local_assistant as agent
    dataset=demo.prefix_dataset(EID,14)
    if mutation=='machine': dataset.machine.serial_number='REAL-SERIAL'
    if mutation=='temperature_time': dataset.cooling_reference.cursor=13
    if mutation=='model': dataset.cooling_reference.model_sha256='0'*64
    if mutation=='telemetry': dataset.telemetry[-1].operating_hours+=1
    if mutation=='real': dataset.provenance='user_supplied'
    monkeypatch.setattr(agent,'load_dataset',lambda _:dataset)
    monkeypatch.setattr(agent,'model_step',lambda *args,**kw:pytest.fail('Must not call AI'))
    with pytest.raises(ValueError,match='mismatch'):
        agent.investigate(agent.InvestigationRequest(machine_id=dataset.machine.machine_id,
            dataset_id='0'*64,question='解释模拟预警',task='overview'))


def test_cloud_receives_verified_prediction_and_must_cite_it(artifacts,monkeypatch):
    from app import local_assistant as agent
    prepared=demo.prepare(EID,14); calls=[]
    monkeypatch.setenv('AI_PROVIDER','gemini')
    def step(messages,allowed,timeout_seconds):
        calls.append(messages)
        initial=json.loads(next(m['content'] for m in messages if m['role']=='user'))
        assert initial['cooling_prediction']['cutoff']==prepared['cooling']['cutoff']
        assert len(initial['cooling_prediction']['latest_observations'])==11
        ids=['tool:1:snapshot']+(['prediction:cooling'] if len(calls)>1 else [])
        return agent.Decision(action='finish',summary='模拟温度预警需要核对传感器记录；模型得分不代表真实故障概率。',
                              evidence_ids=ids,next_check_ids=['check:cooling-source'])
    monkeypatch.setattr(agent,'model_step',step)
    result=agent.investigate(agent.InvestigationRequest(machine_id='SIM-'+EID,dataset_id=prepared['dataset_id'],
        question=prepared['question'],task='overview'))
    assert len(calls)==2 and 'prediction:cooling' in result['citations']
    assert result['evidence']['prediction:cooling']['prediction']['score']==pytest.approx(.9)
    assert any(f['fact_id']=='cooling-warning' and '0.900' in f['text'] for f in result['data_facts'])
    assert not result['parts_candidates']


def test_bounds_headers_and_model_integrity(artifacts):
    client=TestClient(app)
    for params in [dict(episode_id='../secret',cursor=0),dict(episode_id=EID,cursor=-1),dict(episode_id=EID,cursor=480)]:
        assert client.get('/assistant/cooling/replay',params=params).status_code==422
    response=client.get('/assistant/cooling/replay',params={'episode_id':EID,'cursor':14})
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert client.get('/assistant/cooling/replay',params={'episode_id':EID,'cursor':30}).status_code==422
    assert client.post('/assistant/cooling/prepare',json={'episode_id':EID,'cursor':True}).status_code==422
    with (artifacts/'model.json').open('a') as stream: stream.write(' ')
    assert client.get('/assistant/cooling/replay',params={'episode_id':EID,'cursor':14}).status_code==422


def test_generated_physical_dataset_is_reproducible_and_event_separated():
    from scripts.generate_cooling_dataset import episode
    first,truth,meta=episode(2026091421,'severe_loss')
    second,_,meta2=episode(2026091421,'severe_loss')
    assert first==second and meta==meta2
    assert len(first)==480 and len(truth)==5760
    assert meta['fuel_conservation_error_l']<1e-8
    assert all('work_state' not in row for row in first)


def test_extended_evaluation_matches_frozen_model_and_exposes_only_aggregates():
    result=TestClient(app).get('/assistant/cooling/evaluation')
    assert result.status_code==200
    extended=result.json()['extended']
    assert extended['status']=='available'
    assert extended['source']=='synthetic_only'
    assert extended['candidate_adopted'] is False
    assert extended['candidate_passed_protocol'] is False
    assert extended['current_model_sha256']==demo.artifacts()[2]['model_sha256']
    allowed={'episodes','events','detected_events','event_recall','median_lead_minutes',
             'false_alert_episodes','false_alert_episodes_per_eligible_hour','eligible_hours','false_alert_minutes'}
    for report in extended['reports'].values():
        assert set(report)=={'overall','groups'}
        assert set(report['groups'])=={'nominal','shifted'}
        for metrics in [report['overall'],*report['groups'].values()]:
            assert set(metrics)==allowed
        assert report['overall']['episodes']==96
        assert report['overall']['events']==sum(g['events'] for g in report['groups'].values())
    text=json.dumps(extended)
    assert not any(term in text for term in ('per_episode','event_index','cooling_effectiveness','CA-'))


@pytest.mark.parametrize('file_state',['missing','tampered'])
def test_extended_evaluation_unavailable_does_not_invent_zero_error_rates(tmp_path,monkeypatch,file_state):
    monkeypatch.setattr(demo,'ROOT',tmp_path/'cooling_warning_v1')
    if file_state=='tampered':
        target=tmp_path/'cooling_alarm_calibration_v2/evaluation.json'
        target.parent.mkdir()
        target.write_text('{"deployable_under_protocol": true}',encoding='utf-8')
    result=demo.extended_evaluation(demo.EXTENDED_ORIGINAL_MODEL_SHA256)
    assert result['status']=='unavailable'
    assert 'reports' not in result and 'candidate_passed_protocol' not in result


def test_extended_evaluation_never_reused_for_a_different_model():
    result=demo.extended_evaluation('0'*64)
    assert result['status']=='unavailable' and '不匹配' in result['reason']
    assert 'reports' not in result
