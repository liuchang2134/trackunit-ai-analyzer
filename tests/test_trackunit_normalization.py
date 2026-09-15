from app.normalizer import normalize_trackunit_machine,normalize_trackunit_telemetry_series,normalize_trackunit_fault
from app.live_data_service import _normalize_telemetry


def test_metadata_and_zero_values_survive():
    raw={'Metadata':{'AssetId':'asset-1','MachineId':'machine-legacy'},
         'EquipmentHeader':{'EquipmentID':'equipment-1','PIN':'pin-1','Model':'EX'},
         'Location':{'Latitude':0,'Longitude':0,'datetime':'2026-01-01T00:00:00Z'},
         'CumulativeOperatingHours':{'Hour':0,'datetime':'2026-01-01T00:00:00Z'},
         'CumulativeIdleHours':{'Hour':0,'datetime':'2026-01-01T00:00:00Z'},
         'FuelRemaining':{'Percent':0,'datetime':'2026-01-01T00:00:00Z'},
         'EngineStatus':{'Running':False,'datetime':'2026-01-01T00:00:00Z'},
         'operating_hours':999,'latitude':99}
    machine=normalize_trackunit_machine(raw);rows=normalize_trackunit_telemetry_series(raw)
    assert machine.machine_id=='asset-1' and machine.serial_number=='pin-1'
    assert machine.latitude==0 and machine.longitude==0
    assert len(rows)==1 and rows[0].operating_hours==0 and rows[0].idle_hours==0
    assert rows[0].fuel_remaining_percent==0 and rows[0].engine_status=='stopped'
    assert rows[0].machine_id==machine.machine_id
    assert normalize_trackunit_fault({'assetId':'A','SPN':0,'FMI':0,'spn':9,'fmi':9}).fmi==0


def test_independent_times_are_not_falsely_aligned():
    raw={'metadata':{'assetId':'asset-1'},
         'Location':{'Latitude':1,'Longitude':2,'datetime':'2026-01-01T03:00:00Z'},
         'CumulativeOperatingHours':{'Hour':100,'datetime':'2026-01-01T01:00:00Z'},
         'CumulativeIdleHours':{'Hour':50,'datetime':'2026-01-01T02:00:00Z'},
         'FuelRemaining':{'Percent':20,'datetime':'2026-01-01T09:00:00+08:00'}}
    rows=_normalize_telemetry({'equipment':[raw]})
    assert len(rows)==3
    assert rows[0].operating_hours==100 and rows[0].fuel_remaining_percent==20
    assert rows[0].idle_hours is None and rows[0].latitude is None
    assert rows[1].idle_hours==50 and rows[1].operating_hours is None
    assert rows[2].latitude==1 and rows[2].operating_hours is None
    assert rows[0].recorded_at=='2026-01-01T01:00:00+00:00'


def test_missing_channel_time_never_borrows_location_or_update_time():
    raw={'id':'A','location':'工地名称','name':'display-only',
         'updatedAt':'2026-01-02T00:00:00Z','createdAt':'2026-01-01T00:00:00Z',
         'Location':{'Latitude':0,'datetime':'2026-01-01T03:00:00Z'},
         'CumulativeOperatingHours':{'Hour':100},'CumulativeIdleHours':{'Hour':None},'idle_hours':999}
    rows=normalize_trackunit_telemetry_series(raw)
    assert rows[0].recorded_at=='Data not available' and rows[0].operating_hours==100
    assert all(r.idle_hours is None for r in rows)
    assert rows[1].operating_hours is None
    machine=normalize_trackunit_machine(raw)
    assert machine.location=='工地名称' and machine.serial_number=='Data not available'
    assert normalize_trackunit_machine({'id':'A','updatedAt':raw['updatedAt']}).last_seen_at=='Data not available'


def test_lowercase_location_object_and_flat_zero():
    machine=normalize_trackunit_machine({'id':'A','location':{'latitude':0,'longitude':0},'city':'City'})
    assert machine.latitude==0 and machine.location=='City'
    row=normalize_trackunit_telemetry_series({'id':'A','operating_hours':0,'recordedAt':'2026-01-01T00:00:00Z'})[0]
    assert row.operating_hours==0 and row.recorded_at=='2026-01-01T00:00:00+00:00'


def test_recent_counter_is_seen_even_when_location_is_old():
    machine=normalize_trackunit_machine({'id':'A',
        'Location':{'datetime':'2026-01-01T00:00:00Z'},
        'CumulativeOperatingHours':{'Hour':100,'datetime':'2026-01-03T00:00:00Z'},
        'updatedAt':'2026-01-10T00:00:00Z'})
    assert machine.last_seen_at=='2026-01-03T00:00:00+00:00'
