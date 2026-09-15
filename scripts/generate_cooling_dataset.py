"""Independent synthetic thermal experiment; numerical values are assumptions, not OEM calibration."""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.generate_diagnostic_dataset import simulate, DT
from app.cooling_warning import CHANNELS

TARGET = ROOT/'data/cooling_warning_v1'
SCENARIOS = ('healthy', 'hot_ambient', 'gradual_loss', 'severe_loss', 'partial_loss', 'recovery')
OBS_FIELDS = ['recorded_at', *CHANNELS, 'operating_hours', 'idle_hours', 'fuel_percent']
STEPS = 5760


def episode(seed, scenario, profile='nominal'):
    if profile not in ('nominal', 'shifted'):
        raise ValueError('Unknown thermal simulation profile')
    base = simulate(seed, 'healthy', steps=STEPS)
    rng = random.Random(seed+8135)
    ambient = rng.uniform(35, 42) if scenario == 'hot_ambient' else rng.uniform(12, 38)
    capacity = rng.uniform(300, 500)  # kJ/K, effective lumped engine + coolant mass
    conductance = rng.uniform(.85, 1.10)  # multiplicative virtual-machine variation
    heat_factor = rng.uniform(.42, .58)
    onset = rng.uniform(60, 150)*60
    ramp = rng.uniform(60, 150)*60
    floor = {'healthy':1., 'hot_ambient':1., 'gradual_loss':.28,
             'severe_loss':.12, 'partial_loss':.60, 'recovery':.22}[scenario]
    recovery_at = onset+ramp*rng.uniform(.55, 1.10)
    # Independent nuisance parameters; nominal keeps its original random stream.
    thermostat_start, thermostat_span, fan_start, fan_span = 72, 15, 78, 17
    sensor_bias = sensor_drift = 0.
    coolant_noise = .20
    if profile == 'shifted':
        capacity = rng.uniform(260, 560)
        conductance = rng.uniform(.75, 1.20)
        heat_factor = rng.uniform(.38, .62)
        thermostat_start, thermostat_span = rng.uniform(70, 76), rng.uniform(13, 19)
        fan_start, fan_span = rng.uniform(75, 81), rng.uniform(14, 20)
        sensor_bias, sensor_drift = rng.uniform(-.6, .6), rng.uniform(-.5, .5)
        coolant_noise = .35
    temperature = ambient
    sustained = 0; event_s = None; observations = []; truth = []; largest_step = 0
    hours = base['physical'][0]['operating_hours']-DT/3600
    idle = base['physical'][0]['idle_hours']-DT/3600
    fuel = base['physical'][0]['fuel_l']+base['physical'][0]['fuel_lph']*DT/3600
    start_fuel = fuel; burned = 0.
    for i, physical in enumerate(base['physical']):
        elapsed = (i+1)*DT
        # Accelerated deterioration is a test scenario, not a wear-life law.
        progress = max(0., min(1., (elapsed-onset)/ramp))
        effectiveness = 1-(1-floor)*progress
        if scenario == 'recovery' and elapsed >= recovery_at:
            effectiveness += (1-effectiveness)*min(1., (elapsed-recovery_at)/900)
        on = bool(physical['engine_on']) and event_s is None
        shaft = physical['shaft_kw'] if on else 0.
        rpm = physical['engine_rpm'] if on else 0.
        pressure = physical['hydraulic_pressure_bar'] if on else 0.
        flow = physical['hydraulic_flow_lpm'] if on else 0.
        thermostat = max(0., min(1., (temperature-thermostat_start)/thermostat_span))
        fan = (.35+.65*max(0., min(1., (temperature-fan_start)/fan_span)))*(.7+.3*rpm/2100) if on else 0
        ua = (.045+.90*thermostat*fan*effectiveness)*conductance
        heat = (8+heat_factor*shaft) if on else 0.
        before = temperature
        temperature += DT*(heat-ua*(temperature-ambient))/capacity
        largest_step = max(largest_step, abs(temperature-before))
        assert ambient <= temperature < 125, (seed, elapsed, temperature)
        # Energy balance is checked before rounding, independently from the saved rows.
        assert abs(capacity*(temperature-before)-DT*(heat-ua*(before-ambient))) < 1e-8
        sustained = sustained+DT if temperature >= 100 else 0
        if sustained >= 180 and event_s is None: event_s = elapsed
        burn = (1.6+shaft*.245/.835)*DT/3600 if on else 0.
        fuel -= burn; burned += burn
        hours += DT/3600 if on else 0
        idle += DT/3600 if on and physical['work_state'] in ('warmup', 'idle') else 0
        truth.append({'elapsed_s': elapsed, 'true_coolant_c': temperature,
                      'cooling_effectiveness': effectiveness, 'shaft_kw':shaft, 'heat_kw':heat,
                      'ua_kw_per_k':ua, 'engine_on':on, 'work_state':physical['work_state'] if on else 'off'})
        if elapsed % 60 == 0:
            observations.append(dict(recorded_at=physical['timestamp'],
                coolant_c=round(temperature+sensor_bias+sensor_drift*elapsed/(STEPS*DT)+rng.gauss(0,coolant_noise),2), ambient_c=round(ambient+rng.gauss(0,.10),2),
                engine_rpm=round(max(0.,rpm+rng.gauss(0,15)),1),
                hydraulic_pressure_bar=round(max(0.,pressure+rng.gauss(0,max(1,pressure*.04))),2),
                hydraulic_flow_lpm=round(max(0.,flow+rng.gauss(0,max(.5,flow*.04))),2),
                operating_hours=round(hours,6), idle_hours=round(idle,6), fuel_percent=round(fuel/250*100,6)))
    assert abs(start_fuel-fuel-burned) < 1e-8
    metadata = dict(seed=seed, scenario=scenario, event_s=event_s,
        event_index=math.ceil(event_s/60)-1 if event_s else None, ambient_c=ambient,
        capacity_kj_per_k=capacity, conductance_factor=conductance, shaft_heat_fraction=heat_factor,
        onset_s=onset, ramp_s=ramp, effectiveness_floor=floor, recovery_at_s=recovery_at,
        largest_5s_temperature_step_c=largest_step, fuel_conservation_error_l=abs(start_fuel-fuel-burned))
    if profile == 'shifted':
        metadata.update(profile=profile, thermostat_start_c=thermostat_start, thermostat_span_c=thermostat_span,
                        fan_start_c=fan_start, fan_span_c=fan_span, sensor_bias_c=sensor_bias,
                        sensor_drift_per_episode_c=sensor_drift, coolant_noise_sigma_c=coolant_noise)
    return observations, truth, metadata


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Fixed gzip header gives reproducible bytes.
    import io
    with path.open('wb') as out, gzip.GzipFile(filename='', fileobj=out, mode='wb', mtime=0) as gz:
        with io.TextIOWrapper(gz, encoding='utf-8', newline='') as text:
            writer=csv.DictWriter(text, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    manifest = {'version':'cooling_warning_v1', 'source':'synthetic_only', 'sample_interval_seconds':60,
        'event_definition':{'temperature_c':100, 'continuous_seconds':180, 'prediction_horizon_minutes':15,
                            'meaning':'Experimental sustained-temperature event; not an OEM fault or damage label'},
        'episodes':[], 'physical_invariants':'Thermal energy balance, temperature bound and fuel conservation asserted for every episode.'}
    for split, count, offset in [('train',72,0),('validation',24,1000),('test',24,2000)]:
        events=0
        for j in range(count):
            seed=2026091400+offset+j
            eid='CW-'+hashlib.sha256(str(seed).encode()).hexdigest()[:12]
            observations, truth, meta=episode(seed, SCENARIOS[j%len(SCENARIOS)])
            path=TARGET/'observations'/split/(eid+'.csv.gz')
            write_csv(path, OBS_FIELDS, observations)
            private=TARGET/'evaluator_only'/split/eid; private.mkdir(parents=True,exist_ok=True)
            write_csv(private/'thermal_truth.csv.gz',list(truth[0]),truth)
            (private/'event.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
            manifest['episodes'].append({'episode_id':eid, 'split':split, 'samples':len(observations),
                'sensor_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            events += meta['event_index'] is not None
        print(split, count, 'episodes;',events,'events',flush=True)
    (TARGET/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__ == '__main__': main()
