"""Real CSV format, asset binding, segmented evidence, and constrained AI tests."""
import csv
import io
import json
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import local_datasets, sensor_series as series
from app.local_datasets import LocalDataset, save_dataset
from app.models import Machine, TelemetrySnapshot
from app.api.routes_sensor_series import router

ASSET = '00000000-0000-0000-0000-000000009992'
HEADERS = ['Date and time', 'Engine Coolant Temperature (Water Temperature) (CAN 50278)',
           'Engine Oil Pressure (CAN 50281)', 'Load Percentage at Current Speed  (CAN 50283)',
           'Engine Speed (CAN 50286)']
UNITS = {'coolant_c': '°C', 'oil_pressure_kpa': 'kPa', 'engine_load_percent': '%', 'engine_rpm': 'rpm'}


def csv_text(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(HEADERS)
    writer.writerows(rows)
    return stream.getvalue()


def rows(count=12, start=datetime(2026, 1, 2, 10, tzinfo=timezone.utc)):
    return [[(start + timedelta(minutes=i * 2)).isoformat(), 70 + i * .3, 350, 45, 1500] for i in range(count)]


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(local_datasets, 'DATASETS', tmp_path / 'datasets')
    monkeypatch.setattr(series, 'STORE', tmp_path / 'series')
    machine = Machine(machine_id=ASSET, model='TEST-LOADER', serial_number='TEST-SERIES-PIN',
        machine_type='Wheel loader', customer='Test', location='Test site', last_seen_at='2026-01-02T10:00:00Z')
    data = LocalDataset(name='Trackunit series test', source_document='Trackunit AEMP snapshot',
        provenance='user_supplied', machine=machine,
        telemetry=[TelemetrySnapshot(machine_id=ASSET, recorded_at='2026-01-02T10:00:00Z', operating_hours=10)])
    return save_dataset(data)['dataset_id']


def imported(dataset, data=None, **extra):
    return series.import_series(ASSET, dataset, csv_text(data or rows()), series.SOURCE, ASSET, units=UNITS, **extra)


def test_export_dates_respect_explicit_offsets():
    assert series._parse_time('9/17/26, 5:00:05 AM EDT').isoformat() == '2026-09-17T09:00:05+00:00'
    assert series._parse_time('1/2/26, 5:00:05 AM EST').isoformat() == '2026-01-02T10:00:05+00:00'
    with pytest.raises(ValueError, match='时区'):
        series.parse_csv(csv_text([['2026-01-02 10:00:00', 70, 350, 45, 1500]] * 3))


def test_gap_segments_and_stopped_oil_are_preserved(dataset):
    data = rows()
    data += [['2026-01-04T10:00:00+00:00', 70, 0, 0, 0],
             ['2026-01-04T10:02:00+00:00', 69, 0, 0, 0],
             ['2026-01-04T10:04:00+00:00', 68, 0, 0, 0]]
    report = imported(dataset, data)
    assert report['sample_count'] == 15
    assert report['quality']['gap_count'] == 1
    assert len(report['segments']) == 2
    assert report['chart_points'][12]['break_before'] is True
    ev = {item['id']: item for item in report['evidence']}
    assert ev['oil_running_context']['running_zero_count'] == 0
    assert ev['oil_running_context']['stopped_zero_count'] == 3
    assert ev['running_cooling_trend']['end'] == data[11][0]
    assert report['prediction']['failure_time'] is None
    assert report['prediction']['continuation']['horizon_minutes'] == 15
    assert 'raw_rows' not in report and 'vin' not in report


def test_current_snapshot_refresh_keeps_same_vin_history(dataset):
    first = imported(dataset)
    data = local_datasets.load_dataset(dataset)
    data.name = 'Refreshed Trackunit snapshot'
    data.telemetry[0].operating_hours = 11
    newer = save_dataset(data)['dataset_id']
    again = series.latest(ASSET, newer)
    assert again['series_id'] == first['series_id']
    assert again['dataset_id'] == newer and again['import_dataset_id'] == dataset
    data.machine.serial_number = 'ANOTHER-VIN'
    wrong = save_dataset(data)['dataset_id']
    with pytest.raises(ValueError):
        series.latest(ASSET, wrong)
    with pytest.raises(ValueError):
        series._read(first['series_id'], ASSET, wrong)


def test_missing_channel_interval_is_not_bridged(dataset):
    data = rows()
    for row in data[3:9]:
        row[1] = ''
    report = imported(dataset, data)
    assert report['quality']['gap_count'] == 0
    assert report['quality']['missing_values']['coolant_c'] == 6
    assert 'running_cooling_trend' not in [item['id'] for item in report['evidence']]
    assert report['prediction']['continuation'] is None


def test_bad_identity_origin_columns_and_values_are_rejected(dataset):
    with pytest.raises(ValueError, match='不一致'):
        series.import_series(ASSET, dataset, csv_text(rows()), series.SOURCE, 'other-machine')
    with pytest.raises(ValueError, match='来源设备页面'):
        imported(dataset, origin='browser_export_capture')
    with pytest.raises(ValueError, match='不一致'):
        imported(dataset, page_url='https://new.manager.trackunit.com/assets/another/insights')
    bad = rows()
    bad[2][1] = 'nan'
    with pytest.raises(ValueError, match='范围'):
        imported(dataset, bad)
    bad = rows()
    bad.append([bad[0][0], 140, 350, 45, 1500])
    with pytest.raises(ValueError, match='冲突'):
        imported(dataset, bad)
    with pytest.raises(ValueError, match='不支持'):
        series.parse_csv(csv_text(rows()).replace('CAN 50278', 'CAN 12345'))


def test_units_need_confirmation_and_plot_is_bounded(dataset):
    unconfirmed = series.import_series(ASSET, dataset, csv_text(rows()), series.SOURCE, ASSET)
    assert unconfirmed['unit_status'] == 'requires_confirmation'
    with pytest.raises(ValueError, match='单位'):
        series.analyze(unconfirmed['series_id'], ASSET, dataset)
    data = rows(3000)
    for row in data:
        row[1] = 80
    report = imported(dataset, data)
    assert len(report['chart_points']) <= 1500
    assert report['chart_points'][-1]['timestamp'] == data[-1][0]


def test_ai_uses_continuous_evidence_and_no_identity(dataset, monkeypatch):
    report = imported(dataset)
    calls = []
    def fake(messages, schema, timeout_seconds):
        calls.append(messages)
        return json.dumps({'summary': '历史运行水温随时间逐步上升，仍需结合暖机和负载区分正常变化与冷却风险。',
            'hypotheses': [{'failure_mode': '冷却散热能力变化的条件性关注', 'priority': 'watch',
                'reason': '同一运行分段水温逐步上升，仅支持继续观察，不能确认散热器损坏。',
                'evidence_ids': ['running_cooling_trend'], 'search_terms': ['散热器', '风扇'],
                'inspection': '核对风扇与散热器清洁状态，再比较相同负载的温度变化。'}]}, ensure_ascii=False)
    monkeypatch.setattr(series, 'generate_structured_with_deepseek', fake)
    result = series.analyze(report['series_id'], ASSET, dataset)
    assert result['ai_analysis']['hypotheses'][0]['search_terms'] == ['散热器', '风扇']
    prompt = str(calls)
    assert 'running_cooling_trend' in prompt and 'rate_per_minute' in prompt
    assert ASSET not in prompt and 'TEST-SERIES-PIN' not in prompt and dataset not in prompt
    series.analyze(report['series_id'], ASSET, dataset)
    assert len(calls) == 1


def test_ai_rejects_invented_evidence_and_part_numbers(dataset):
    report = imported(dataset)
    output = {'summary': '样本尚不足以判定故障，以下仅为条件性排查方向。', 'hypotheses': [{
        'failure_mode': '冷却系统待检查', 'priority': 'routine', 'reason': '根据已有温度变化，建议进一步核对冷却系统状态。',
        'evidence_ids': ['nonexistent'], 'search_terms': ['散热器'], 'inspection': '先核对风扇和散热器，再结合连续负载判断。'}]}
    with pytest.raises(ValueError, match='证据'):
        series._validate_analysis(json.dumps(output), report)
    output['hypotheses'][0]['evidence_ids'] = ['range_coolant_c']
    output['hypotheses'][0]['search_terms'] = ['散热器12345678']
    with pytest.raises(ValueError, match='料号'):
        series._validate_analysis(json.dumps(output), report)


def test_routes_return_no_store_and_source_binding(dataset):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.post('/assistant/sensor-series/import', json={'machine_id': ASSET, 'dataset_id': dataset,
        'source': series.SOURCE, 'source_asset_id': ASSET, 'csv_text': csv_text(rows()), 'units': UNITS})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['origin'] == 'user_confirmed_export'
    response = client.get('/assistant/sensor-series/latest', params={'machine_id': ASSET, 'dataset_id': dataset})
    assert response.status_code == 200


def test_handoff_uses_saved_hypothesis_and_same_vin(dataset, monkeypatch):
    report = imported(dataset)
    record = series._read(report['series_id'], ASSET, dataset)
    record['ai_analysis'] = {'analysis_version': series.ANALYSIS_VERSION, 'summary': '尚未确认故障，按传感器趋势进行条件性部件排查。', 'hypotheses': [{
        'failure_mode': '冷却系统条件性关注', 'priority': 'routine', 'reason': '目前温度变化不足以确认故障，请结合相同负载继续核对。',
        'evidence_ids': ['range_coolant_c'], 'search_terms': ['散热器'], 'inspection': '核对散热器与风扇状态后再决定是否需要准备配件。'}]}
    series._write(series._path(report['series_id']), record)
    value = series.parts_handoff(report['series_id'], ASSET, dataset, 0)
    assert value['symptom_source'] == 'user_question'
    assert value['evidence_ids'] == ['range_coolant_c']
    assert '不是已上报故障码' in value['symptom']
    assert 'range_coolant_c' in value['symptom']
    with pytest.raises(ValueError):
        series.parts_handoff(report['series_id'], 'another', dataset, 0)
    with pytest.raises(ValueError):
        series.parts_handoff(report['series_id'], ASSET, dataset, 1)


def test_explicit_endpoint_direction_and_normal_window_wording(dataset):
    data = rows()
    for i, row in enumerate(data):
        row[1], row[3], row[4] = 80, 62 - i, 1800 - i * 10
    report = imported(dataset, data)
    assert series._condition_only(report)
    evidence = {item['id']: item for item in report['evidence']}
    assert evidence['running_engine_rpm_trend']['endpoint_direction'] == 'down'
    assert evidence['load_rpm_direction']['endpoint_relation'] == 'same'
    output = {'summary': '此历史窗口负载与转速均下降，油压稳定，未见持续恶化，建议继续按同工况监测。', 'hypotheses': [{
        'failure_mode': '润滑系统同工况油压核对', 'priority': 'routine',
        'reason': '负载与转速均下降，油压仍稳定，当前证据仅支持同工况连续观察。',
        'evidence_ids': ['running_engine_rpm_trend', 'running_engine_load_percent_trend'],
        'search_terms': ['机油滤清器'], 'inspection': '下次作业对照同转速、负载和温度的油压，再决定是否需要备件。'}]}
    series._validate_analysis(json.dumps(output), report)
    output['hypotheses'][0]['reason'] = '负载62到51，转速1800到1690，变化方向不一致且拟合R²较低。'
    with pytest.raises(ValueError, match='同向'):
        series._validate_analysis(json.dumps(output), report)
    output['hypotheses'][0]['reason'] = '负载与转速均下降，油压稳定，当前证据仅支持同工况连续观察。'
    output['hypotheses'][0]['priority'] = 'watch'
    with pytest.raises(ValueError, match='routine'):
        series._validate_analysis(json.dumps(output), report)
    output['hypotheses'][0]['priority'] = 'routine'
    output['hypotheses'][0]['failure_mode'] = '机油压力传感器异常关注'
    with pytest.raises(ValueError, match='传感器异常'):
        series._validate_analysis(json.dumps(output), report)


def test_old_analysis_cache_is_hidden_and_refreshed_without_rebinding(dataset, monkeypatch):
    report = imported(dataset)
    record = series._read(report['series_id'], ASSET, dataset)
    record['evidence_version'] = 1
    record['ai_analysis'] = {'summary': 'Old result', 'hypotheses': [], 'generated_at': '2026-01-02T12:00:00Z'}
    captured_at = record['captured_at']
    series._write(series._path(record['series_id']), record)
    pending = series.latest(ASSET, dataset)
    assert pending['ai_analysis'] is None and pending['ai_analysis_outdated'] is True
    assert pending['evidence_version'] == series.EVIDENCE_VERSION
    assert any(item.get('endpoint_direction') for item in pending['evidence'])
    def fake(messages, schema, timeout_seconds):
        return json.dumps({'summary': '历史水温在同一运行窗口上升，结合负载进行条件性关注与资料核对。', 'hypotheses': [{
            'failure_mode': '冷却系统持续升温监测', 'priority': 'routine',
            'reason': '同一运行分段水温逐步上升，需要结合实际负载进一步观察。',
            'evidence_ids': ['running_cooling_trend'], 'search_terms': ['散热器'],
            'inspection': '在相近负载下继续记录水温，检查散热器外部状态。'}]}, ensure_ascii=False)
    monkeypatch.setattr(series, 'generate_structured_with_deepseek', fake)
    result = series.analyze(report['series_id'], ASSET, dataset)
    assert result['ai_analysis']['analysis_version'] == series.ANALYSIS_VERSION
    assert result['captured_at'] == captured_at and result['import_dataset_id'] == dataset
    assert result['source'] == series.SOURCE and result['series_id'] == report['series_id']
    assert 'analysis_history' not in result


def test_analysis_is_concise_and_does_not_repeat_internal_rules(dataset):
    report = imported(dataset)
    output = {'summary': '历史水温有变化，需要结合负载继续观察；不输出概率和日期。', 'hypotheses': [{
        'failure_mode': '冷却系统持续升温监测', 'priority': 'routine',
        'reason': '同一运行分段水温逐步上升，需要结合实际负载进一步观察。',
        'evidence_ids': ['running_cooling_trend'], 'search_terms': ['散热器'],
        'inspection': '在相近负载下继续记录水温，检查散热器外部状态。'}]}
    with pytest.raises(ValueError, match='生成约束'):
        series._validate_analysis(json.dumps(output), report)
    output['summary'] = '观察' * 151
    with pytest.raises(ValueError):
        series._validate_analysis(json.dumps(output), report)


def test_parts_terms_match_xgss_collection_contract(dataset):
    report = imported(dataset)
    output = {'summary': '历史工况存在温度变化，可对照同转速和负载继续监测。', 'hypotheses': [{
        'failure_mode': '冷却系统持续升温监测', 'priority': 'routine',
        'reason': '同一运行分段水温逐步上升，需要结合实际负载进一步观察。',
        'evidence_ids': ['running_cooling_trend'], 'search_terms': [' 散热器 ', '风扇、散热器', '', '水泵; 风扇'],
        'inspection': '在相近负载下继续记录水温，检查散热器外部状态。'}]}
    checked = series._validate_analysis(json.dumps(output), report)
    assert checked['hypotheses'][0]['search_terms'] == ['散热器', '风扇', '水泵']
    for terms in (['泵'], ['器' * 41], ['部件' + chr(65 + i) for i in range(13)]):
        output['hypotheses'][0]['search_terms'] = terms
        with pytest.raises(ValueError):
            series._validate_analysis(json.dumps(output), report)
    output['hypotheses'][0]['search_terms'] = ['部件' + chr(65 + i) for i in range(12)] * 2
    checked = series._validate_analysis(json.dumps(output), report)
    assert len(checked['hypotheses'][0]['search_terms']) == 12


def test_invalid_terms_in_current_version_cache_can_be_regenerated(dataset, monkeypatch):
    report = imported(dataset)
    record = series._read(report['series_id'], ASSET, dataset)
    old = {'analysis_version': series.ANALYSIS_VERSION,
        'summary': '历史水温存在变化，需要同工况观察并核对冷却部件资料。', 'hypotheses': [{
        'failure_mode': '冷却系统持续升温监测', 'priority': 'routine',
        'reason': '同一运行分段水温逐步上升，需要结合实际负载进一步观察。',
        'evidence_ids': ['running_cooling_trend'], 'search_terms': ['泵'],
        'inspection': '在相近负载下继续记录水温，检查冷却部件外部状态。'}]}
    record['ai_analysis'] = old
    series._write(series._path(report['series_id']), record)
    pending = series.latest(ASSET, dataset)
    assert pending['ai_analysis'] is None and pending['ai_analysis_outdated']
    calls = []
    def fake(messages, schema, timeout_seconds):
        calls.append(1)
        output = {key: old[key] for key in ('summary', 'hypotheses')}
        output['hypotheses'][0]['search_terms'] = ['水泵', '水泵']
        return json.dumps(output, ensure_ascii=False)
    monkeypatch.setattr(series, 'generate_structured_with_deepseek', fake)
    result = series.analyze(report['series_id'], ASSET, dataset)
    assert result['ai_analysis']['hypotheses'][0]['search_terms'] == ['水泵']
    assert result['ai_analysis']['analysis_version'] == old['analysis_version']
    handoff = series.parts_handoff(report['series_id'], ASSET, dataset, 0)
    assert handoff['search_terms'] == ['水泵']
    series.analyze(report['series_id'], ASSET, dataset)
    assert len(calls) == 1
