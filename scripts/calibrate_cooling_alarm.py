"""Frozen, episode-isolated alarm-policy experiment. Never overwrites v1 artifacts."""
import argparse
import csv
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.cooling_warning import CoolingWindow, HORIZON, predict_prefix
from scripts.generate_cooling_dataset import episode, write_csv, OBS_FIELDS, SCENARIOS

V1 = ROOT / 'data/cooling_warning_v1'
TARGET = ROOT / 'data/cooling_alarm_calibration_v2'
PLAN = ROOT / 'docs/superpowers/plans/2026-09-14-cooling-alarm-calibration.md'
THRESHOLDS = (.4, .5, .6, .7, .8, .9, .95)
CONFIRMATIONS = (2, 3, 4)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # An experiment phase is deliberately not an overwrite operation.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def prepare(eid, rows, meta, group, model):
    predictions = predict_prefix(model, rows)
    scores = [p['score'] for p in predictions]
    window = CoolingWindow()
    eligible = []
    event = meta['event_index']
    for i, row in enumerate(rows):
        features = window.add(row)
        valid = (features is not None and float(row['coolant_c']) < 100
                 and i + HORIZON < len(rows) and (event is None or i < event))
        eligible.append(valid)
    return dict(episode_id=eid, rows=rows, event=event, group=group, scores=scores,
                eligible=eligible, scenario=meta['scenario'])


def original_validation(model):
    result = []
    for path in sorted((V1 / 'observations/validation').glob('*.csv.gz')):
        eid = path.name[:-7]
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            rows = list(csv.DictReader(stream))
        meta = read(V1 / 'evaluator_only/validation' / eid / 'event.json')
        result.append(prepare(eid, rows, meta, 'original_validation', model))
    return result


def generate(split, model):
    count, offset = (48, 10000) if split == 'validation' else (96, 20000)
    previous_seeds = {read(p)['seed'] for p in (V1 / 'evaluator_only').glob('*/*/event.json')}
    result, manifest = [], []
    for j in range(count):
        seed = 2026091400 + offset + j
        assert seed not in previous_seeds
        profile = 'nominal' if j < count // 2 else 'shifted'
        eid = 'CA-' + hashlib.sha256(str(seed).encode()).hexdigest()[:12]
        rows, truth, meta = episode(seed, SCENARIOS[j % 6], profile)
        sensor_path = TARGET / 'observations' / split / (eid + '.csv.gz')
        private = TARGET / 'evaluator_only' / split / eid
        if sensor_path.exists() or private.exists():
            raise FileExistsError('Experiment episode already exists; do not overwrite it')
        write_csv(sensor_path, OBS_FIELDS, rows)
        write_csv(private / 'thermal_truth.csv.gz', list(truth[0]), truth)
        save(private / 'event.json', meta)
        manifest.append(dict(episode_id=eid, seed=seed, profile=profile, samples=len(rows),
                             sensor_sha256=sha(sensor_path), event_sha256=sha(private / 'event.json'),
                             truth_sha256=sha(private / 'thermal_truth.csv.gz')))
        # All policies see the rounded serialized observations, not latent truth.
        with gzip.open(sensor_path, 'rt', encoding='utf-8') as stream:
            saved_rows = list(csv.DictReader(stream))
        result.append(prepare(eid, saved_rows, meta, profile, model))
        if (j + 1) % 12 == 0:
            print(split, j + 1, '/', count, flush=True)
    save(TARGET / (split + '-manifest.json'), dict(source='synthetic_only', episodes=manifest))
    return result


def flags_for(item, threshold, confirmation):
    run, flags = 0, []
    for score in item['scores']:
        run = run + 1 if score is not None and score >= threshold else 0
        flags.append(run >= confirmation)
    return flags


def baseline_flags(item):
    window = CoolingWindow()
    run, flags = 0, []
    for row in item['rows']:
        valid = window.add(row) is not None and 95 <= float(row['coolant_c']) < 100
        run = run + 1 if valid else 0
        flags.append(run >= 2)
    return flags


def measure(items, threshold=None, confirmation=2, evidence_path=None):
    details, audit = [], []
    for item in items:
        flags = baseline_flags(item) if threshold is None else flags_for(item, threshold, confirmation)
        counts = dict(tp=0, fp=0, tn=0, fn=0)
        false_segments, previous_false, leads = 0, False, []
        for i, (flag, valid) in enumerate(zip(flags, item['eligible'])):
            label = int(item['event'] is not None and 0 < item['event'] - i <= HORIZON)
            false = bool(valid and flag and not label)
            false_segments += int(false and not previous_false)
            previous_false = false
            if valid:
                counts['tp' if flag and label else 'fp' if flag else 'fn' if label else 'tn'] += 1
                if flag and label:
                    leads.append(item['event'] - i)
            if evidence_path is not None:
                audit.append(dict(episode_id=item['episode_id'], group=item['group'], sample_index=i,
                                  event_index=item['event'], eligible=int(valid), label=label,
                                  alarm=int(flag), score=item['scores'][i]))
        details.append(dict(episode_id=item['episode_id'], group=item['group'], scenario=item['scenario'],
                            event_index=item['event'], lead_minutes=max(leads) if leads else None,
                            false_alert_episodes=false_segments, eligible_minutes=sum(item['eligible']),
                            window_counts=counts))

    def aggregate(rows):
        counts = {k: sum(r['window_counts'][k] for r in rows) for k in ('tp', 'fp', 'tn', 'fn')}
        events = sum(r['event_index'] is not None for r in rows)
        leads = [r['lead_minutes'] for r in rows if r['lead_minutes'] is not None]
        hours = sum(r['eligible_minutes'] for r in rows) / 60
        false = sum(r['false_alert_episodes'] for r in rows)
        return dict(episodes=len(rows), events=events, detected_events=len(leads),
                    event_recall=len(leads)/events if events else None,
                    median_lead_minutes=statistics.median(leads) if leads else None,
                    lead_minutes_detected=leads, false_alert_episodes=false, eligible_hours=hours,
                    false_alert_episodes_per_eligible_hour=false/hours if hours else None,
                    false_alert_minutes=counts['fp'], window_counts=counts)

    result = dict(overall=aggregate(details),
                  groups={g: aggregate([r for r in details if r['group'] == g])
                          for g in sorted({r['group'] for r in details})}, per_episode=details)
    if evidence_path is not None:
        write_csv(evidence_path, list(audit[0]), audit)
    return result


def selection_ok(report):
    return all(r['event_recall'] == 1 and (r['median_lead_minutes'] or 0) >= 10
               and r['false_alert_episodes_per_eligible_hour'] <= .1 for r in report['groups'].values())


def rank(trial):
    report = trial['metrics']
    return (max(r['false_alert_episodes_per_eligible_hour'] for r in report['groups'].values()),
            report['overall']['false_alert_minutes'],
            -min(r['median_lead_minutes'] or 0 for r in report['groups'].values()),
            -trial['threshold'], -trial['confirmation'])


def deployment_checks(candidate, original, baseline):
    checks = {}
    for group, r in candidate['groups'].items():
        old, base = original['groups'][group], baseline['groups'][group]
        checks[group] = dict(
            recall_at_least_90_percent=(r['event_recall'] or 0) >= .9,
            no_additional_missed_events=r['detected_events'] >= old['detected_events'],
            median_lead_at_least_10_minutes=(r['median_lead_minutes'] or 0) >= 10,
            median_lead_at_least_temperature_baseline=(r['median_lead_minutes'] or 0) >= (base['median_lead_minutes'] or 0),
            false_episode_budget_met=r['false_alert_episodes_per_eligible_hour'] <= .1,
            false_episodes_reduced_at_least_25_percent=r['false_alert_episodes_per_eligible_hour'] <= .75 * old['false_alert_episodes_per_eligible_hour'],
            no_more_false_minutes=r['false_alert_minutes'] <= old['false_alert_minutes'])
    return checks


def calibrate():
    TARGET.mkdir(parents=True, exist_ok=True)
    protocol = dict(created_at=datetime.now(timezone.utc).isoformat(), plan_sha256=sha(PLAN),
                    plan_text=PLAN.read_text(encoding='utf-8'), thresholds=THRESHOLDS, confirmations=CONFIRMATIONS,
                    v1_model_sha256=sha(V1 / 'model.json'), v1_manifest_sha256=sha(V1 / 'manifest.json'),
                    source_hashes={str(p.relative_to(ROOT)): sha(p) for p in
                        (Path(__file__), ROOT/'scripts/generate_cooling_dataset.py', ROOT/'app/cooling_warning.py')})
    save(TARGET / 'protocol.json', protocol)
    model = read(V1 / 'model.json')
    items = original_validation(model) + generate('validation', model)
    trials = []
    for threshold in THRESHOLDS:
        for confirmation in CONFIRMATIONS:
            metrics = measure(items, threshold, confirmation)
            metrics.pop('per_episode')
            trials.append(dict(threshold=threshold, confirmation=confirmation, eligible=selection_ok(metrics), metrics=metrics))
    acceptable = [t for t in trials if t['eligible']]
    # Fallback is explicitly experimental, never a release candidate.
    selected = min(acceptable, key=rank) if acceptable else min(trials, key=lambda t: (
        -min(r['event_recall'] or 0 for r in t['metrics']['groups'].values()),
        max(0, 10-min(r['median_lead_minutes'] or 0 for r in t['metrics']['groups'].values())), *rank(t)))
    model['alarm_threshold'] = selected['threshold']
    model['alarm_consecutive_minutes'] = selected['confirmation']
    save(TARGET / 'candidate-model.json', model)
    save(TARGET / 'selection.json', dict(frozen_at=datetime.now(timezone.utc).isoformat(),
        candidate_sha256=sha(TARGET/'candidate-model.json'), validation_sha256=sha(TARGET/'validation-manifest.json'),
        protocol_sha256=sha(TARGET/'protocol.json'), passed_validation=bool(acceptable), selected=selected, trials=trials))
    print(json.dumps(dict(passed_validation=bool(acceptable), threshold=selected['threshold'],
        confirmation=selected['confirmation'], groups=selected['metrics']['groups']), indent=2), flush=True)


def evaluate():
    selection, protocol = read(TARGET/'selection.json'), read(TARGET/'protocol.json')
    assert sha(TARGET/'candidate-model.json') == selection['candidate_sha256']
    assert sha(TARGET/'protocol.json') == selection['protocol_sha256']
    assert sha(V1/'model.json') == protocol['v1_model_sha256']
    assert sha(V1/'manifest.json') == protocol['v1_manifest_sha256']
    assert all(sha(ROOT/path) == digest for path, digest in protocol['source_hashes'].items())
    candidate, original = read(TARGET/'candidate-model.json'), read(V1/'model.json')
    items = generate('test', original)
    # Runtime parity over every test minute, including excluded and post-event rows.
    for item in items:
        expected = flags_for(item, candidate['alarm_threshold'], candidate['alarm_consecutive_minutes'])
        actual = [p['status'] == 'warning' for p in predict_prefix(candidate, item['rows'])]
        assert expected == actual
    reports = {}
    for name, threshold, confirmation in [('original', original['alarm_threshold'], 2),
            ('candidate', candidate['alarm_threshold'], candidate['alarm_consecutive_minutes']), ('temperature_95c', None, 2)]:
        reports[name] = measure(items, threshold, confirmation, TARGET/'audit'/f'{name}.csv.gz')
    checks = deployment_checks(reports['candidate'], reports['original'], reports['temperature_95c'])
    accepted = selection['passed_validation'] and all(all(v.values()) for v in checks.values())
    save(TARGET/'evaluation.json', dict(evaluated_at=datetime.now(timezone.utc).isoformat(),
        source='synthetic_only', candidate_sha256=selection['candidate_sha256'],
        selection_sha256=sha(TARGET/'selection.json'), test_manifest_sha256=sha(TARGET/'test-manifest.json'),
        audit_hashes={p.name: sha(p) for p in (TARGET/'audit').glob('*.csv.gz')},
        deployable_under_protocol=accepted, checks=checks, reports=reports))
    print(json.dumps(dict(deployable=accepted, checks=checks,
        metrics={k:v['groups'] for k,v in reports.items()}), indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['calibrate', 'evaluate'])
    args = parser.parse_args()
    calibrate() if args.phase == 'calibrate' else evaluate()
