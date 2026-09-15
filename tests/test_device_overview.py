from datetime import datetime, timezone, timedelta
from scripts.prepare_parts_demo import build_demo
from app.device_overview import build_overview
from app.models import TelemetrySnapshot
from app import device_overview as module


def test_overview_excludes_wrong_machine_future_and_conflicting_times_and_keeps_gaps():
    data=build_demo(); now=data.replay_at
    samples=[TelemetrySnapshot(machine_id=data.machine.machine_id,recorded_at=(now-timedelta(hours=2)).isoformat(),operating_hours=10),
             TelemetrySnapshot(machine_id=data.machine.machine_id,recorded_at=(now-timedelta(hours=1)).isoformat(),operating_hours=11),
             TelemetrySnapshot(machine_id='OTHER',recorded_at=now.isoformat(),operating_hours=999),
             TelemetrySnapshot(machine_id=data.machine.machine_id,recorded_at=(now+timedelta(hours=1)).isoformat(),operating_hours=1000)]
    result=build_overview(data.machine,samples,[],source='imported_synthetic',cutoff=now)
    assert len(result['series'])==2 and result['trend']['operating_hours_delta']==1
    assert result['series'][0]['idle_hours'] is None
    assert result['trend']['idle_share'] is None
    assert result['excluded_samples']['other_machine']==1
    samples.append(samples[0].model_copy(update={'operating_hours':99}))
    result=build_overview(data.machine,samples,[],source='mock',cutoff=now)
    assert len(result['series'])==1 and result['trend']['operating_hours_delta'] is None


def test_plot_sampling_keeps_endpoints_but_statistics_use_full_window():
    data=build_demo(); now=data.replay_at
    samples=[TelemetrySnapshot(machine_id=data.machine.machine_id,
        recorded_at=(now-timedelta(hours=100-i)).isoformat(),operating_hours=100+i,idle_hours=10+i/2) for i in range(101)]
    result=build_overview(data.machine,samples,[],source='mock',cutoff=now,max_points=8)
    assert len(result['series'])==8 and result['sampled_for_display']
    assert result['series'][0]['operating_hours']==100 and result['series'][-1]['operating_hours']==200
    assert result['trend']['valid_intervals']==100 and result['trend']['idle_share']==0.5
    assert result['ai_used'] is False and result['upstream_sync_performed'] is False


def test_dataset_overview_uses_replay_cutoff_and_rejects_device_mismatch(monkeypatch):
    import pytest
    data=build_demo()
    monkeypatch.setattr(module,'load_dataset',lambda key:data)
    result=module.device_overview(data.machine.machine_id,'example')
    assert result['as_of']==data.replay_at.isoformat()
    assert result['faults']['valid_loaded_records']==2
    with pytest.raises(ValueError,match='mismatch'):module.device_overview('OTHER','example')


def test_real_dataset_without_replay_cutoff_is_served_without_ai(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import gemini_client
    import pytest
    data=build_demo().model_copy(update={'provenance':'user_supplied','replay_at':None})
    monkeypatch.setattr(module,'load_dataset',lambda key:data)
    monkeypatch.setattr(gemini_client.httpx,'post',lambda *a,**k:pytest.fail('Overview must not call AI'))
    response=TestClient(app).get('/assistant/device-overview',params={'machine_id':data.machine.machine_id,'dataset_id':'a'*64})
    assert response.status_code==200
    value=response.json()
    assert value['source']=='imported_user_supplied' and value['ai_used'] is False
    assert value['trend']['operating_hours_delta'] is not None
    assert abs((datetime.now(timezone.utc)-datetime.fromisoformat(value['as_of'])).total_seconds())<5
