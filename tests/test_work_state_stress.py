import random
from collections import Counter
from scripts.stress_work_state import stress_row,score,summary


def observation(pressure=100):
    return {'recorded_at':'2026-01-01T00:00:00Z','engine_rpm':1800,'hydraulic_pressure_bar':pressure,'hydraulic_flow_lpm':100,'speed_kmh':0}


def test_pressure_freeze_holds_past_observation_and_releases():
    original=observation(150)
    altered,active,held=stress_row(original,120,'pressure_freeze',random.Random(1),None)
    assert active and held==150
    changed,active,held=stress_row(observation(200),121,'pressure_freeze',random.Random(1),held)
    assert changed['hydraulic_pressure_bar']==150 and active
    released,active,held=stress_row(observation(210),360,'pressure_freeze',random.Random(1),held)
    assert released['hydraulic_pressure_bar']==210 and not active
    assert original['hydraulic_pressure_bar']==150


def test_missing_measurement_not_replaced_with_zero():
    changed,affected,_=stress_row(observation(),5,'missing_pressure_20pct',random.Random(1),None)
    assert affected and changed['hydraulic_pressure_bar'] is None


def test_unknown_and_high_score_errors_use_explicit_denominators():
    counts=Counter()
    score(counts,{'state':'unknown','candidate_state':'dig','score':.5},'dig')
    score(counts,{'state':'dig','candidate_state':'dig','score':.95},'swing')
    score(counts,{'state':'idle','candidate_state':'idle','score':.99},'idle')
    result=summary(counts)
    assert result['coverage']==2/3
    assert result['accepted_accuracy']==.5
    assert result['high_score_error_fraction']==.5
