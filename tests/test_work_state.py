from app.work_state import CHANNELS,FEATURES,FeatureWindow,predict_features


def row(at='2026-06-29T08:00:00Z',rpm=1000):
    return dict(zip(CHANNELS,[rpm,20,5,0]),recorded_at=at)


def test_features_ignore_labels_and_other_hidden_fields():
    observation=row()
    enriched={**observation,'work_state':'dig','scenario':'failure','shaft_kw':999,'episode_id':'test'}
    assert FeatureWindow().add(enriched)==FeatureWindow().add(observation)
    assert len(FeatureWindow().add(observation))==len(FEATURES)


def test_causal_window_uses_only_current_and_past_samples():
    window=FeatureWindow()
    first=window.add(row())
    second=window.add(row('2026-06-29T08:00:05Z',1300))
    assert first[0]==1000 and first[4]==1000 and first[8]==0
    assert second[0]==1300 and second[4]==1150 and second[8]==300
    window.add(row('2026-06-29T08:00:10Z',1700))
    assert first[4]==1000 and second[4]==1150
    after_gap=window.add(row('2026-06-29T08:01:00Z',1100))
    assert after_gap[4]==1100 and after_gap[8]==0


def test_missing_invalid_or_unordered_samples_abstain_and_clear_history():
    for invalid in [dict(row(),engine_rpm=None),dict(row(),speed_kmh=float('nan')),
        dict(row(),engine_rpm=True),dict(row(),hydraulic_flow_lpm=-1),dict(row(),recorded_at='2026-06-29T08:00:00')]:
        window=FeatureWindow();window.add(row())
        assert window.add(invalid) is None
        assert not window.rows
    window=FeatureWindow();window.add(row())
    assert window.add(row()) is None
    assert predict_features({},None)['state']=='unknown'
