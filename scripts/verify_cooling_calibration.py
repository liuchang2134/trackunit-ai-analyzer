"""Independent arithmetic and artifact checks over saved per-minute experiment evidence."""
import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'data/cooling_alarm_calibration_v2'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    evaluation = read(DATA/'evaluation.json')
    selection = read(DATA/'selection.json')
    protocol = read(DATA/'protocol.json')
    assert digest(DATA/'selection.json') == evaluation['selection_sha256']
    assert digest(DATA/'protocol.json') == selection['protocol_sha256']
    assert digest(DATA/'candidate-model.json') == evaluation['candidate_sha256'] == selection['candidate_sha256']
    for path, expected in protocol['source_hashes'].items():
        assert digest(ROOT/path) == expected
    for name in ('model', 'manifest'):
        assert digest(ROOT/'data/cooling_warning_v1'/f'{name}.json') == protocol[f'v1_{name}_sha256']
    assert selection['frozen_at'] < evaluation['evaluated_at']
    seen_seeds = {read(p)['seed'] for p in (ROOT/'data/cooling_warning_v1/evaluator_only').glob('*/*/event.json')}
    for split, count in [('validation',48), ('test',96)]:
        entries = read(DATA/f'{split}-manifest.json')['episodes']
        assert len(entries) == count
        groups = defaultdict(int)
        for e in entries:
            assert e['seed'] not in seen_seeds
            seen_seeds.add(e['seed'])
            groups[e['profile']] += 1
            private = DATA/'evaluator_only'/split/e['episode_id']
            assert digest(DATA/'observations'/split/(e['episode_id']+'.csv.gz')) == e['sensor_sha256']
            assert digest(private/'event.json') == e['event_sha256']
            assert digest(private/'thermal_truth.csv.gz') == e['truth_sha256']
            # Independently derive the first 180 seconds at or above 100C.
            event_s, sustained = None, 0
            with gzip.open(private/'thermal_truth.csv.gz', 'rt', encoding='utf-8') as stream:
                for row in csv.DictReader(stream):
                    sustained = sustained + 5 if float(row['true_coolant_c']) >= 100 else 0
                    if sustained >= 180:
                        event_s = int(row['elapsed_s'])
                        break
            meta = read(private/'event.json')
            assert meta['event_s'] == event_s
            assert meta['event_index'] == (math.ceil(event_s/60)-1 if event_s else None)
        assert dict(groups) == dict(nominal=count//2, shifted=count//2)
    assert digest(DATA/'validation-manifest.json') == selection['validation_sha256']
    assert digest(DATA/'test-manifest.json') == evaluation['test_manifest_sha256']
    opportunity, totals = {}, {}
    for name, expected_hash in evaluation['audit_hashes'].items():
        path = DATA/'audit'/name
        assert digest(path) == expected_hash
        by_episode = defaultdict(list)
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for row in csv.DictReader(stream):
                by_episode[row['episode_id']].append(row)
        assert len(by_episode) == 96
        details = []
        for eid, rows in by_episode.items():
            assert [int(r['sample_index']) for r in rows] == list(range(480))
            valid = [r for r in rows if r['eligible'] == '1']
            positives = [r for r in valid if r['label'] == '1']
            found = [r for r in positives if r['alarm'] == '1']
            event = int(rows[0]['event_index']) if rows[0]['event_index'] else None
            for r in rows:
                assert int(r['label']) == int(event is not None and 0 < event-int(r['sample_index']) <= 15)
            false_indexes = {int(r['sample_index']) for r in valid if r['label']=='0' and r['alarm']=='1'}
            details.append(dict(group=rows[0]['group'], event=event,
                lead=event-min(int(r['sample_index']) for r in found) if found else None,
                false=sum(i-1 not in false_indexes for i in false_indexes), minutes=len(valid),
                counts={k:sum((r['label'],r['alarm'])==pair for r in valid)
                        for k,pair in dict(tp=('1','1'),fp=('0','1'),tn=('0','0'),fn=('1','0')).items()}))
            if name == 'original.csv.gz' and event is not None and not found:
                opportunity[eid] = dict(group=rows[0]['group'], eligible_positive_minutes=len(positives),
                    max_score_in_eligible_event_window=max((float(r['score']) for r in positives if r['score']),default=None))
        expected = evaluation['reports'][name[:-7]]
        for group in ('overall','nominal','shifted'):
            items = details if group == 'overall' else [r for r in details if r['group'] == group]
            actual = expected['overall'] if group == 'overall' else expected['groups'][group]
            counts = {k:sum(r['counts'][k] for r in items) for k in ('tp','fp','tn','fn')}
            leads = [r['lead'] for r in items if r['lead'] is not None]
            assert counts == actual['window_counts']
            assert sum(r['event'] is not None for r in items) == actual['events']
            assert len(leads) == actual['detected_events']
            assert (median(leads) if leads else None) == actual['median_lead_minutes']
            assert sum(r['false'] for r in items) == actual['false_alert_episodes']
            assert sum(r['minutes'] for r in items)/60 == actual['eligible_hours']
            assert counts['fp'] == actual['false_alert_minutes']
            assert actual['false_alert_episodes']/actual['eligible_hours'] == actual['false_alert_episodes_per_eligible_hour']
        totals[name[:-7]] = expected['overall']
    result = dict(status='verified', evaluation_sha256=digest(DATA/'evaluation.json'),
                  checked_new_episodes=144, checked_test_minutes_per_policy=46080,
                  missed_events_with_prediction_opportunity=opportunity, totals=totals)
    out = ROOT/'docs/evaluation/2026-09-14-cooling-calibration-independent.json'
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)


if __name__ == '__main__':
    main()
