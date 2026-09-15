from datetime import datetime, timedelta, timezone
import pytest
from app.cooling_warning import CoolingWindow, FEATURES, predict_prefix


def rows(count=20, temperature=85):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [dict(recorded_at=(base + timedelta(minutes=i)).isoformat(), coolant_c=temperature+i*.1,
                 ambient_c=25, engine_rpm=1700, hydraulic_pressure_bar=180,
                 hydraulic_flow_lpm=100, operating_hours=200+i/60, idle_hours=20,
                 fuel_percent=80-i*.02) for i in range(count)]


def constant_model():
    return dict(format='cooling_forest_v1', feature_names=FEATURES, classes=[0, 1],
                provenance='synthetic_only', alarm_threshold=.6, horizon_minutes=15,
                trees=[dict(left=[-1], right=[-1], feature=[-2], threshold=[-2], values=[[.1, .9]])])


def test_requires_ten_minutes_and_uses_only_past():
    window = CoolingWindow()
    data = rows()
    assert all(window.add(row) is None for row in data[:10])
    features = window.add(data[10])
    assert len(features) == len(FEATURES)
    assert features[FEATURES.index('coolant_delta10')] == pytest.approx(1)
    expected = predict_prefix(constant_model(), data[:15])
    data[15]['coolant_c'] = 120
    assert predict_prefix(constant_model(), data[:15]) == expected
    assert expected[-1]['status'] == 'warning'


@pytest.mark.parametrize('bad', [None, 'nan', float('inf'), True, -50, 200])
def test_bad_temperature_clears_window(bad):
    window = CoolingWindow()
    data = rows()
    for row in data[:12]: window.add(row)
    data[12]['coolant_c'] = bad
    assert window.add(data[12]) is None
    assert window.add(data[13]) is None


def test_gap_and_duplicate_clear_history():
    window = CoolingWindow()
    data = rows(30)
    for row in data[:12]: window.add(row)
    assert window.add(data[14]) is None
    assert window.add(data[14]) is None
    assert window.add(data[15]) is None


def test_stopped_high_and_warming_are_not_forecasts():
    data = rows()
    result = predict_prefix(constant_model(), data)
    assert result[0]['status'] == 'unknown'
    assert result[10]['status'] == 'watch'
    data[-1]['engine_rpm'] = 0
    assert predict_prefix(constant_model(), data)[-1]['status'] == 'stopped'
    data[-1]['engine_rpm'] = 1800
    data[-1]['coolant_c'] = 101
    assert predict_prefix(constant_model(), data)[-1]['status'] == 'current_high'


def test_model_contract_is_not_silently_accepted():
    model = constant_model()
    model['feature_names'] = ['future_event']
    with pytest.raises(ValueError): predict_prefix(model, rows())
