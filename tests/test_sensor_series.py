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
    keys, parsed = series.parse_csv(csv_text(rows()).replace('CAN 50278', 'CAN 12345'))
    assert keys[0] == 'can_12345' and parsed[0]['can_12345'] == 70


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
    record['ai_analysis'] = {'analysis_version': series.ANALYSIS_VERSION, 'evidence_version': series.EVIDENCE_VERSION, 'summary': '尚未确认故障，按传感器趋势进行条件性部件排查。', 'hypotheses': [{
        'failure_mode': '冷却系统条件性关注', 'priority': 'routine', 'reason': '目前温度变化不足以确认故障，请结合相同负载继续核对。',
        'evidence_ids': ['range_coolant_c'], 'search_terms': ['散热器'], 'inspection': '核对散热器与风扇状态后再决定是否需要准备配件。'}]}
    series._write(series._path(report['series_id']), record)
    value = series.parts_handoff(report['series_id'], ASSET, dataset, 0)
    assert value['hypothesis'] == record['ai_analysis']['hypotheses'][0]
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
    old = {'analysis_version': series.ANALYSIS_VERSION, 'evidence_version': series.EVIDENCE_VERSION,
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


def export_text(headers, values, start=datetime(2026, 1, 2, 10, tzinfo=timezone.utc)):
    stream=io.StringIO(newline='')
    writer=csv.writer(stream)
    writer.writerow(['Date and time',*headers])
    for index,value in enumerate(values):
        writer.writerow([(start+timedelta(minutes=index*2)).isoformat(),*value])
    return stream.getvalue()


def batch(dataset,exports,**extra):
    return series.import_batch(ASSET,dataset,exports,series.SOURCE,ASSET,**extra)


def test_batch_merges_four_channel_exports_without_importing_previous_latest(dataset):
    old=imported(dataset)
    a={'csv_text':export_text(['Battery Voltage (CAN 90001)'],[[25+i/10] for i in range(12)]),
       'units':{'can_90001':'V'}}
    b={'csv_text':export_text(['DEF Tank Temperature (CAN 90002)'],[[20+i/10] for i in range(12)]),
       'units':{'can_90002':'°C'}}
    value=batch(dataset,[a,b])
    assert value['sample_count']==12 and len(value['channels'])==2
    assert {c['key'] for c in value['channels']}=={'can_90001','can_90002'}
    assert value['series_id']!=old['series_id']
    assert value['chart_points'][0]['can_90001']==25
    assert value['chart_points'][0]['can_90002']==20
    assert len(value['export_batches'])==2
    assert all(len(item['export_id'])==64 and item['origin']=='user_confirmed_export' for item in value['export_batches'])
    again=batch(dataset,[b,a,a])
    assert again['series_id']==value['series_id'] and again['batch_id']==value['batch_id']


def test_merge_preserves_sparse_sampling_without_fill_or_false_alignment(dataset):
    a={'csv_text':export_text(['Battery Voltage (CAN 90001)'],[[25],[26],[27]]),'units':{'can_90001':'V'}}
    b={'csv_text':export_text(['DEF Tank Temperature (CAN 90002)'],[[20],[21],[22]],
        start=datetime(2026,1,2,10,1,tzinfo=timezone.utc)),'units':{'can_90002':'°C'}}
    value=batch(dataset,[a,b])
    assert value['sample_count']==6
    assert value['chart_points'][0]['can_90002'] is None
    assert value['chart_points'][1]['can_90001'] is None
    assert value['quality']['missing_values']=={'can_90001':3,'can_90002':3}


def test_conflicting_duplicate_or_units_leave_latest_and_files_unchanged(dataset):
    prior=imported(dataset)
    before={p.name:p.read_bytes() for p in series.STORE.iterdir()}
    a={'csv_text':export_text(['Battery Voltage (CAN 90001)'],[[25],[26],[27]]),'units':{'can_90001':'V'}}
    b={**a,'csv_text':a['csv_text'].replace(',26',',24')}
    with pytest.raises(ValueError,match='冲突'):batch(dataset,[a,b])
    with pytest.raises(ValueError,match='冲突'):batch(dataset,[a,{**a,'units':{'can_90001':'mV'}}])
    assert series.latest(ASSET,dataset)['series_id']==prior['series_id']
    assert before=={p.name:p.read_bytes() for p in series.STORE.iterdir()}


def test_bad_batch_identity_window_and_last_csv_are_atomic(dataset):
    prior=imported(dataset)
    a={'csv_text':export_text(['Battery Voltage (CAN 90001)'],[[25],[26],[27]]),'units':{'can_90001':'V'}}
    with pytest.raises(ValueError,match='不一致'):
        batch(dataset,[{**a,'page_url':'https://new.manager.trackunit.com/assets/other/insights'}])
    with pytest.raises(ValueError,match='窗口'):
        batch(dataset,[a,{**a,'csv_text':a['csv_text'].replace('2026-01-02','2026-01-03')}])
    with pytest.raises(ValueError):batch(dataset,[a,{'csv_text':'broken'}])
    assert series.latest(ASSET,dataset)['series_id']==prior['series_id']


def test_large_packed_fault_message_is_exact_and_never_charted_or_analyzed(dataset):
    huge='18446744073709551615'
    text=export_text(['DM1 Fault Code (CAN 90003)','Battery Voltage (CAN 90001)'],[[huge,25],[huge,26],[huge,27]])
    value=batch(dataset,[{'csv_text':text,'units':{'can_90003':'-','can_90001':'V'}}])
    channel={c['key']:c for c in value['channels']}['can_90003']
    assert channel['latest']==huge and channel['kind']=='code' and channel['ai_eligible'] is False
    assert channel['min'] is None and channel['mean'] is None
    assert all(p['can_90003'] is None for p in value['chart_points'])
    raw=series._read(value['series_id'],ASSET,dataset)
    assert all(row['can_90003']==huge for row in raw['raw_rows'])
    assert not any('can_90003' in e['id'] for e in value['evidence'])


def test_unlabeled_unsafe_numeric_channel_preserved_as_code(dataset):
    text=export_text(['Manufacturer Data (CAN 90004)'],[['9007199254740993'],['1'],['2']])
    value=batch(dataset,[{'csv_text':text,'units':{'can_90004':'-'}}])
    channel=value['channels'][0]
    assert channel['kind']=='code' and channel['latest']=='2' and not value['ai_available']
    with pytest.raises(ValueError,match='单位'):series.analyze(value['series_id'],ASSET,dataset)


def test_state_and_counter_are_not_continuous_regression(dataset):
    text=export_text(['Red Stop Lamp (CAN 90005)','Total Work Hours of Engine (CAN 50251)'],[[i%2,100+i] for i in range(12)])
    value=batch(dataset,[{'csv_text':text,'units':{'can_90005':'-','can_50251':'h'},
                          'channel_metadata':{'can_90005':{'kind':'continuous'}}}])
    channels={c['key']:c for c in value['channels']}
    assert channels['can_90005']['kind']=='state' and channels['can_50251']['kind']=='counter'
    assert channels['can_90005']['mean'] is None
    assert not any(e['id'].startswith(('observed_','running_can_','range_can_')) for e in value['evidence'])
    assert any(e['id']=='context_can_90005' for e in value['evidence'])
    assert value['prediction']['continuation'] is None


def test_unknown_units_preserved_but_excluded_from_ai_while_confirmed_channels_work(dataset,monkeypatch):
    text=export_text(['Battery Voltage (CAN 90001)','Unknown Quantity (CAN 90006)'],[[25+i/10,999+i] for i in range(12)])
    value=batch(dataset,[{'csv_text':text,'channel_metadata':{'can_90001':{'unit':'V'}}}])
    assert value['unit_status']=='partially_confirmed' and value['ai_available']
    channels={c['key']:c for c in value['channels']}
    assert channels['can_90006']['unit']=='单位待核对' and not channels['can_90006']['ai_eligible']
    assert not any('can_90006' in e['id'] for e in value['evidence'])
    calls=[]
    def fake(messages,schema,timeout_seconds):
        calls.append(json.loads(messages[-1]['content']))
        return json.dumps({'summary':'电压在本次连续观察窗口内变化，可结合供电工况继续核对。','hypotheses':[{
            'failure_mode':'供电系统趋势关注','priority':'watch','reason':'电压连续观测存在方向性变化，需要结合作业负载核对，不能认定电池损坏。',
            'evidence_ids':['observed_can_90001_trend'],'search_terms':['蓄电池'],'inspection':'核对端子连接及同工况电压变化，再考虑备件准备。'}]},ensure_ascii=False)
    monkeypatch.setattr(series,'generate_structured_with_deepseek',fake)
    result=series.analyze(value['series_id'],ASSET,dataset)
    assert result['ai_analysis']['hypotheses'][0]['priority']=='watch'
    assert [channel['key'] for channel in calls[0]['channels']]==['can_90001']
    assert '999' not in json.dumps(calls[0])
    assert calls[0]['conditional_monitoring_only'] is False


def test_batch_route_metadata_and_bounded_channels(dataset):
    app=FastAPI();app.include_router(router);client=TestClient(app)
    headers=[f'Quantity {index} (CAN {91000+index})' for index in range(96)]
    text=export_text(headers,[[float(i)]*96 for i in range(3)])
    response=client.post('/assistant/sensor-series/import-batch',json={
        'machine_id':ASSET,'dataset_id':dataset,'source':series.SOURCE,'source_asset_id':ASSET,
        'exports':[{'csv_text':text,'channel_metadata':{'can_91000':{'unit':'g','kind':'continuous'}}}]})
    assert response.status_code==200,response.text
    assert len(response.json()['channels'])==96
    assert response.headers['cache-control']=='no-store'
    too_many=export_text(headers+['Extra (CAN 91999)'],[[1]*97]*3)
    with pytest.raises(ValueError,match='96'):batch(dataset,[{'csv_text':too_many}])


def test_batch_row_and_cell_limit_checked_before_write(dataset,monkeypatch):
    prior=imported(dataset)
    text=export_text(['Quantity (CAN 90001)'],[[1],[2],[3]])
    monkeypatch.setattr(series,'MAX_MERGED_ROWS',2)
    with pytest.raises(ValueError,match='50000'):batch(dataset,[{'csv_text':text}])
    assert series.latest(ASSET,dataset)['series_id']==prior['series_id']


def test_pointer_write_failure_preserves_previous_latest(dataset,monkeypatch):
    prior=imported(dataset)
    old_files=set(series.STORE.iterdir())
    original=series._write
    def fail_pointer(path,value):
        if path.name.startswith('latest-'):raise OSError('simulated full disk')
        return original(path,value)
    monkeypatch.setattr(series,'_write',fail_pointer)
    with pytest.raises(OSError):
        batch(dataset,[{'csv_text':export_text(['Battery Voltage (CAN 90001)'],[[25],[26],[27]])}])
    assert set(series.STORE.iterdir())==old_files
    assert series.latest(ASSET,dataset)['series_id']==prior['series_id']


def test_legacy_evidence_migration_and_four_key_identity_remain(dataset):
    value=imported(dataset)
    raw=series._read(value['series_id'],ASSET,dataset)
    raw.pop('channel_metadata');raw.pop('ai_available');raw['evidence_version']=2
    raw['ai_analysis']={'analysis_version':2,'summary':'旧版四通道分析','hypotheses':[]}
    series._write(series._path(value['series_id']),raw)
    migrated=series.latest(ASSET,dataset)
    assert migrated['evidence_version']==series.EVIDENCE_VERSION and migrated['ai_analysis'] is None
    assert {c['key'] for c in migrated['channels']}==set(UNITS)


def test_spn_fmi_oc_and_raw_fault_information_are_codes(dataset):
    text=export_text(['SPN (CAN 50295)','FMI (Fault Mode Identification) (CAN 50296)',
                     'OC (Fault Count) (CAN 50297)','Current/Historical Fault Information Announcement (CAN 50298)'],
                    [[0,0,0,'71745328524567070']]*3)
    value=batch(dataset,[{'csv_text':text,'units':{f'can_{id}':'-' for id in range(50295,50299)}}])
    assert all(channel['kind']=='code' and not channel['ai_eligible'] for channel in value['channels'])
    assert next(c for c in value['channels'] if c['key']=='can_50298')['latest']=='71745328524567070'
    assert not value['ai_available']


def test_legacy_unconfirmed_units_remain_unconfirmed_on_migration(dataset):
    value=series.import_series(ASSET,dataset,csv_text(rows()),series.SOURCE,ASSET)
    raw=series._read(value['series_id'],ASSET,dataset)
    raw.pop('channel_metadata');raw.pop('ai_available');raw['evidence_version']=2
    series._write(series._path(value['series_id']),raw)
    migrated=series.latest(ASSET,dataset)
    assert not migrated['ai_available']
    assert all(c['unit']=='单位待核对' and not c['ai_eligible'] for c in migrated['channels'])


@pytest.mark.parametrize(('label','kind'),[
    ('Gear Information','state'),('Display "NN"','state'),('Engine Make_Model_Serial','code'),
    ('Input1','state'),('Input 5','state'),('NCD Indicator (Yellow)','state'),
    ('Low Urea Level Alarm','state'),('DPF Regeneration Indicator Light','state'),
    ('High Regeneration Exhaust Temperature Alarm','state'),
    ('Information Data of Multi-Package Fault','code'),
    ('Torque Converter Input Shaft Speed','continuous'),('Torque Converter Output Shaft Speed','continuous'),
    ('Transmission Oil Temperature','continuous')])
def test_verified_advanced_signal_names_do_not_turn_codes_or_states_into_trends(label,kind):
    assert series._channel_kind(label)==kind


def test_identifier_and_gear_override_client_continuous_metadata(dataset):
    text=export_text(['Engine Make_Model_Serial (CAN 91001)','Gear Information (CAN 91002)',
                     'Display "NN" (CAN 91003)','Input1 (CAN 91004)',
                     'Transmission Oil Temperature (CAN 91005)'],[['XC948U',1,'NN',0,45+i] for i in range(12)])
    value=batch(dataset,[{'csv_text':text,'units':{f'can_{i}':'-' if i<91005 else '°C' for i in range(91001,91006)},
                        'channel_metadata':{f'can_{i}':{'kind':'continuous'} for i in range(91001,91006)}}])
    kinds={c['key']:c['kind'] for c in value['channels']}
    assert kinds=={'can_91001':'code','can_91002':'state','can_91003':'state','can_91004':'state','can_91005':'continuous'}
    trends=[e['id'] for e in value['evidence'] if e['id'].startswith('observed_')]
    assert trends==['observed_can_91005_trend']


def test_explicit_input_channels_and_engine_identifier_are_preserved(dataset):
    identifier='CMMNS*6B S5 D067       *22566122**************************************************************'
    text=export_text(['Transmission Oil Reservoir Temperature (CAN 50332)',
                     'Engine Make_Model_Serial (CAN 50580)','INPUT1 (INPUT1)','INPUT5 (INPUT5)'],
                    [[34+i,identifier,i%2,1] for i in range(12)])
    value=batch(dataset,[{'csv_text':text,'units':{'can_50332':'°C','can_50580':'-','input_1':'-','input_5':'-'}}])
    channels={c['key']:c for c in value['channels']}
    assert channels['can_50580']['latest']==identifier and not channels['can_50580']['ai_eligible']
    assert channels['input_1']['kind']=='state' and channels['input_5']['kind']=='state'
    assert any(e['id']=='observed_can_50332_trend' for e in value['evidence'])
    assert not any('can_50580' in e['id'] for e in value['evidence'])
    for bad in ('INPUT1 (INPUT2)','INPUT7 (INPUT7)','Other (INPUT1)'):
        with pytest.raises(ValueError,match='表头'):
            series.parse_csv(text.replace('INPUT1 (INPUT1)',bad))


def test_complementary_rows_and_multiple_dtc_frames_at_same_instant_are_preserved(dataset):
    start='2026-01-02T10:00:00+00:00'
    stream=io.StringIO(newline='');writer=csv.writer(stream)
    writer.writerow(['Date and time','Low Urea Level Alarm (CAN 50309)','DPF Regeneration Indicator Light (CAN 50310)',
                     'Active Diagnostic Trouble Codes (CAN 50578)'])
    for i in range(3):
        at=(datetime.fromisoformat(start)+timedelta(minutes=i)).isoformat()
        writer.writerow([at,'Lamp OFF','','04-FF-68-0A-03-01-FF-FF'])
        writer.writerow([at,'','OFF','03-FF-00-00-00-00-FF-FF'])
    value=batch(dataset,[{'csv_text':stream.getvalue()}])
    raw=series._read(value['series_id'],ASSET,dataset)
    assert value['sample_count']==3
    assert raw['raw_rows'][0]['can_50309']=='Lamp OFF' and raw['raw_rows'][0]['can_50310']=='OFF'
    assert raw['raw_rows'][0]['can_50578']==['04-FF-68-0A-03-01-FF-FF','03-FF-00-00-00-00-FF-FF']
    channel=next(c for c in value['channels'] if c['key']=='can_50578')
    assert channel['latest_values']==raw['raw_rows'][0]['can_50578'] and isinstance(channel['latest'],str)
    assert channel['ai_eligible'] is False


def test_explicit_input6_output1_accepted_but_unobserved_ports_rejected(dataset):
    text=export_text(['INPUT6 (INPUT6)','OUTPUT1 (OUTPUT1)'],[[0,1],[1,0],[0,0]])
    value=batch(dataset,[{'csv_text':text,'units':{'input_6':'-','output_1':'-'}}])
    assert {c['key']:c['kind'] for c in value['channels']}=={'input_6':'state','output_1':'state'}
    with pytest.raises(ValueError,match='表头'):series.parse_csv(text.replace('OUTPUT1 (OUTPUT1)','OUTPUT2 (OUTPUT2)'))



def test_asynchronous_inputs_do_not_fragment_existing_running_trends(dataset):
    base=imported(dataset)
    first={'csv_text':csv_text(rows()),'units':UNITS}
    async_signals={'csv_text':export_text(['INPUT1 (INPUT1)',HEADERS[1]],[[1,190]]*12,
                   start=datetime(2026,1,2,10,1,tzinfo=timezone.utc)),
                   'units':{'input_1':'-','coolant_c':'°C'}}
    combined=batch(dataset,[first,async_signals])
    select=lambda report:{item['id']:item for item in report['evidence']
        if item['id'].startswith('running_') or item['id']=='load_rpm_direction'}
    assert select(combined)==select(base)
    # The asynchronous high temperatures remain observed values but never
    # acquire an invented simultaneous RPM context.
    assert next(c for c in combined['channels'] if c['key']=='coolant_c')['max']==190
    assert select(combined)['running_cooling_trend']['sample_count']==12
    assert select(combined)['running_cooling_trend']['end_value']==rows()[-1][1]
    assert combined['sample_count']==24


@pytest.mark.parametrize('stopped',[False,True])
def test_rpm_specific_long_gap_and_explicit_stop_break_running_segments(dataset,stopped):
    data=rows(12)
    # A 12-minute missing RPM interval must not be filled by input samples.
    # With an explicit stop, the same separation is required even over 2 min.
    if stopped:
        data[6][4]=0
        for row in data[7:]:row[4]=1500
    else:
        data=data[:5]+rows(5,start=datetime(2026,1,2,10,20,tzinfo=timezone.utc))
    a={'csv_text':csv_text(data),'units':UNITS}
    b={'csv_text':export_text(['INPUT1 (INPUT1)'],[[1]]*30,
                    start=datetime(2026,1,2,10,1,tzinfo=timezone.utc)),'units':{'input_1':'-'}}
    combined=batch(dataset,[a,b])
    trends={item['id']:item for item in combined['evidence']}
    if stopped:
        # Last running piece spans only eight minutes; preceding piece remains
        # the latest sufficiently long one and ends before RPM=0.
        assert trends['running_cooling_trend']['end']==data[5][0]
    else:
        assert 'running_cooling_trend' not in trends
    assert not any(item.get('sample_count',0)>6 for item in combined['evidence'] if item['id'].startswith('running_'))


def test_cached_ai_requires_matching_evidence_version_and_recomputes_old_segmentation(dataset):
    value=imported(dataset)
    raw=series._read(value['series_id'],ASSET,dataset)
    output={'summary':'当前历史水温有连续变化，需要结合负载和转速继续关注。','hypotheses':[{
        'failure_mode':'冷却系统持续升温监测','priority':'routine',
        'reason':'同一运行分段水温逐步上升，需要结合实际负载进一步观察。',
        'evidence_ids':['running_cooling_trend'],'search_terms':['散热器'],
        'inspection':'在相近负载下继续记录水温，检查散热器外部状态。'}],
        'analysis_version':series.ANALYSIS_VERSION,'evidence_version':3}
    raw['evidence_version']=3;raw['ai_analysis']=output
    series._write(series._path(value['series_id']),raw)
    migrated=series.latest(ASSET,dataset)
    assert migrated['evidence_version']==4 and migrated['ai_analysis'] is None and migrated['ai_analysis_outdated']
    raw=series._read(value['series_id'],ASSET,dataset)
    raw['ai_analysis']['evidence_version']=4
    assert series._cached_analysis(raw) is not None
