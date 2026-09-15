import csv
import gzip
import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from app import work_state_demo as demo
from app.work_state import FEATURES,CHANNELS
from app.main import app


@pytest.fixture
def artifacts(tmp_path,monkeypatch):
    monkeypatch.setattr(demo,'ROOT',tmp_path)
    model={'format':'numeric_random_forest_v1','feature_names':FEATURES,'classes':['idle','dig'],
        'provenance':'synthetic_only','abstain_below':.65,
        'trees':[{'left':[-1],'right':[-1],'feature':[-2],'threshold':[-2],'values':[[.9,.1]]}]}
    raw=json.dumps(model).encode();(tmp_path/'model.json').write_bytes(raw)
    (tmp_path/'evaluation.json').write_text(json.dumps({'model_sha256':hashlib.sha256(raw).hexdigest()}))
    directory=tmp_path/'observations/test';directory.mkdir(parents=True)
    path=directory/'EP-0123456789ab.csv.gz'
    with gzip.open(path,'wt',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['recorded_at',*CHANNELS]);writer.writeheader()
        for seconds in [5,10,15,20]:writer.writerow(dict(zip(CHANNELS,[1000,20,5,0]),recorded_at=f'2026-06-29T08:00:{seconds:02}Z'))
    return tmp_path


def test_only_sensor_inputs_and_requested_window_are_returned(artifacts):
    result=demo.replay_episode('EP-0123456789ab',start=1,count=2)
    assert [r['sample_index'] for r in result['samples']]==[1,2]
    assert all(r['state']=='idle' for r in result['samples'])
    assert set(result['samples'][0]['sensors'])==set(CHANNELS)
    assert result['source']=='synthetic_held_out_sensors'
    assert result['real_trackunit_supported'] is False


def test_model_hash_tampering_is_rejected(artifacts):
    with (artifacts/'model.json').open('a') as stream:stream.write(' ')
    with pytest.raises(ValueError,match='hash'):demo.replay_episode('EP-0123456789ab')


def test_route_rejects_path_traversal_and_unbounded_windows(artifacts):
    client=TestClient(app)
    assert client.get('/assistant/work-state/replay',params={'episode_id':'../../secret'}).status_code==422
    assert client.get('/assistant/work-state/replay',params={'episode_id':'EP-0123456789ab','count':721}).status_code==422
    assert client.get('/assistant/work-state/replay',params={'episode_id':'EP-0123456789ab','start':-1}).status_code==422
    assert client.get('/assistant/work-state/replay',params={'episode_id':'EP-0123456789ab','start':4}).status_code==422
    assert client.get('/assistant/work-state/replay',params={'episode_id':'EP-ffffffffffff'}).status_code==404
    assert client.get('/assistant/work-state/replay',params={'episode_id':'EP-0123456789ab'}).status_code==200


def test_extra_label_column_cannot_enter_replay(artifacts):
    path=artifacts/'observations/test/EP-0123456789ab.csv.gz'
    with gzip.open(path,'wt') as stream:stream.write('recorded_at,work_state\n2026-01-01T00:00:00Z,dig\n')
    with pytest.raises(ValueError,match='schema'):demo.replay_episode('EP-0123456789ab')


def test_nonfinite_sensor_file_returns_validation_error(artifacts):
    path=artifacts/'observations/test/EP-0123456789ab.csv.gz'
    with gzip.open(path,'wt',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['recorded_at',*CHANNELS]);writer.writeheader()
        writer.writerow(dict(zip(CHANNELS,['nan',20,5,0]),recorded_at='2026-06-29T08:00:05Z'))
    client=TestClient(app)
    response=client.get('/assistant/work-state/replay',params={'episode_id':'EP-0123456789ab'})
    assert response.status_code==422
