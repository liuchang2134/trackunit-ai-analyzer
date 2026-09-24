"""Pure projection tests; no external services or local datasets are loaded."""
from datetime import datetime,timezone
import json

import pytest

from app.models import FaultCode,TelemetrySnapshot
from app.xgss_machine_context import build_context

NOW=datetime(2026,9,22,12,tzinfo=timezone.utc)
MACHINE='private-machine-id'


def sample(at,**values):
    return TelemetrySnapshot(machine_id=MACHINE,recorded_at=at,**values)


def fault(at,**values):
    return FaultCode(machine_id=MACHINE,fault_code='E4030',description='Private free text',
        severity='medium',status='open',occurred_at=at,**values)


def test_each_metric_uses_its_own_latest_valid_observation_time():
    telemetry=[
        sample('2026-09-20T10:00:00Z',operating_hours=123.5),
        sample('2026-09-21T12:00:00Z',idle_hours=20),
        sample('2026-09-22T11:00:00Z',fuel_remaining_percent=40),
        sample('2026-09-22T11:59:00Z',latitude=12,longitude=34),
    ]
    result=build_context(MACHINE,telemetry,[],now=NOW)
    assert result['sample_count']==4
    assert result['as_of']=='2026-09-22T12:00:00+00:00'
    assert result['last_sample_at']=='2026-09-22T11:59:00+00:00'
    assert result['metrics']['operating_hours']=={'value':123.5,'unit':'h',
        'observed_at':'2026-09-20T10:00:00+00:00','age_hours':50,'stale_after_24h':True}
    assert result['metrics']['idle_hours']['age_hours']==24
    assert result['metrics']['idle_hours']['stale_after_24h'] is False
    assert result['metrics']['fuel_remaining_percent']['age_hours']==1
    assert result['metrics']['fuel_remaining_percent']['value']==40


def test_invalid_future_other_device_and_conflicting_rows_are_excluded():
    telemetry=[
        sample('2026-09-22T09:00:00Z',operating_hours=10,idle_hours=0,fuel_remaining_percent=100),
        sample('2026-09-22T10:00:00Z',operating_hours=-1,idle_hours=float('nan'),fuel_remaining_percent=101),
        sample('2026-09-22T10:30:00Z',operating_hours=float('inf'),idle_hours=-1,fuel_remaining_percent=-2),
        sample('2026-09-22T11:00:00Z',operating_hours=11),
        sample('2026-09-22T11:00:00Z',operating_hours=12),
        sample('2026-09-23T00:00:00Z',operating_hours=20),
        sample('2026-09-22T11:30:00',operating_hours=21),
        sample('not a timestamp',operating_hours=22),
        TelemetrySnapshot(machine_id='other-machine',recorded_at='2026-09-22T11:45:00Z',operating_hours=999),
    ]
    result=build_context(MACHINE,telemetry,[],now=NOW)
    assert {field:row['value'] for field,row in result['metrics'].items()}=={
        'operating_hours':10,'idle_hours':0,'fuel_remaining_percent':100}
    assert result['excluded_samples']=={'conflicting_timestamp':2,'invalid_or_future_timestamp':3,'other_machine':1,'duplicate':0}


def test_projection_never_includes_identity_position_raw_payload_or_description():
    telemetry=[sample('2026-09-22T10:00:00Z',operating_hours=10,trackunit_asset_id='SECRET-ASSET',
        equipment_id='SECRET-EQUIPMENT',latitude=12.345,longitude=67.891,
        raw_payload={'vin':'SECRET-VIN','source_document':'SECRET-DOC'})]
    faults=[fault('2026-09-22T10:30:00Z',trackunit_asset_id='SECRET-ASSET',equipment_id='SECRET-EQUIPMENT',
        spn=123,fmi=4,raw_payload={'vin':'SECRET-VIN','secret':'SECRET-TOKEN'})]
    result=build_context(MACHINE,telemetry,faults,now=NOW)
    wire=json.dumps(result,ensure_ascii=False,allow_nan=False)
    for private in (MACHINE,'SECRET-','Private free text','machine_id','trackunit_asset_id','equipment_id',
                    'latitude','longitude','raw_payload','source_document','vin'):
        assert private not in wire
    assert set(result['faults'][0])=={'fault_code','spn','fmi','severity','status','occurred_at'}
    assert result['faults'][0]['spn']==123 and result['faults'][0]['fmi']==4


def test_fault_projection_keeps_latest_eight_same_machine_valid_records():
    faults=[fault(f'2026-09-22T{hour:02d}:00:00Z') for hour in range(12)]
    faults.extend([fault('invalid'),fault('2026-09-23T00:00:00Z'),fault('2026-09-22T11:30:00')])
    faults.append(FaultCode(machine_id='another-machine',fault_code='OTHER',description='',severity='high',
        status='resolved',occurred_at='2026-09-22T11:59:00Z'))
    result=build_context(MACHINE,[],faults,now=NOW)
    assert len(result['faults'])==8
    assert result['faults'][0]['occurred_at']=='2026-09-22T04:00:00+00:00'
    assert result['faults'][-1]['occurred_at']=='2026-09-22T11:00:00+00:00'
    assert result['fault_records_loaded_total']==15
    assert result['fault_coverage']=='unknown'
    assert 'OTHER' not in json.dumps(result)


def test_missing_metrics_remain_unknown_and_naive_reference_time_is_rejected():
    result=build_context(MACHINE,[],[],now=NOW)
    assert result['sample_count']==0 and result['fault_records_loaded_total']==0
    assert result['last_sample_at'] is None
    assert result['faults']==[] and result['fault_coverage']=='unknown'
    for metric in result['metrics'].values():
        assert metric['value'] is None and metric['observed_at'] is None
        assert metric['age_hours'] is None and metric['stale_after_24h'] is None
    with pytest.raises(ValueError,match='timezone'):
        build_context(MACHINE,[],[],now=NOW.replace(tzinfo=None))
