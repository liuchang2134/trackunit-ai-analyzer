from datetime import timedelta
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import fault_context, parts_catalog
from app.models import FaultCode
from scripts.prepare_parts_demo import build_demo


@pytest.fixture
def context_data(monkeypatch, tmp_path):
    data=build_demo()
    monkeypatch.setattr(fault_context,'load_dataset',lambda _:data)
    monkeypatch.setattr(parts_catalog,'CATALOG_PATH',tmp_path/'parts.json')
    monkeypatch.setattr(httpx,'post',lambda *a,**k:pytest.fail('Local source lookup must not call AI or XGSS'))
    monkeypatch.setattr(httpx,'get',lambda *a,**k:pytest.fail('Local source lookup must not synchronize'))
    return data


def part(data,number='DEMO-MATCH',**updates):
    return parts_catalog.CatalogPart(**dict(dict(part_number=number,name='演示传感器',component='sensor',
        models=[data.machine.model],fault_codes=['ENG-BOOST-102-3'],checks=['检查依据原文 <script>示例</script>'],
        source_document='人工演示目录',source_page='p.2',revision='demo-v1',provenance='demo'),**updates))


def fetch(data,code='ENG-BOOST-102-3',**extra):
    return TestClient(app).get('/assistant/fault-context',params={
        'machine_id':data.machine.machine_id,'fault_code':code,'dataset_id':'a'*64,**extra})


def test_lookup_preserves_source_and_exact_fault_model_serial_filters(context_data):
    data=context_data
    parts_catalog.import_catalog(parts_catalog.CatalogImport(parts=[part(data),
        part(data,'DEMO-OTHER-CODE',fault_codes=['OTHER']),part(data,'DEMO-OTHER-MODEL',models=['OTHER']),
        part(data,'DEMO-OTHER-SERIAL',applicability='serial_list',serial_numbers=['OTHER'])]))
    response=fetch(data)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    value=response.json()
    assert value['source']=='imported_synthetic' and value['as_of']==data.replay_at.isoformat()
    assert value['ai_used'] is False and value['upstream_sync_performed'] is False
    assert [p['part_number'] for p in value['parts_candidates']]==['DEMO-MATCH']
    assert value['parts_candidates'][0]['checks']==['检查依据原文 <script>示例</script>']
    assert value['parts_candidates'][0]['serial_verified'] is False
    assert value['manual']['status']=='not_integrated' and 'url' not in value['manual']


def test_lookup_rejects_missing_and_wrong_device_or_dataset(context_data):
    data=context_data
    assert fetch(data,'UNKNOWN').status_code==404
    assert fetch(data,machine_id='OTHER').status_code==404


def test_fault_lookup_excludes_other_machine_future_and_invalid_time(context_data):
    data=context_data
    base=data.faults[0]
    data.faults.extend([
        base.model_copy(update={'machine_id':'OTHER'}),
        base.model_copy(update={'occurred_at':(data.replay_at+timedelta(hours=1)).isoformat()}),
        base.model_copy(update={'occurred_at':'not-a-date'})])
    value=fetch(data).json()
    assert value['record_facts']['valid_loaded_records']==2
    assert value['record_facts']['excluded_records']=={'other_machine':1,'after_cutoff':1,'invalid_timestamp':1}


def test_future_only_code_cannot_be_used_to_search_catalog(context_data):
    data=context_data
    data.faults=[data.faults[0].model_copy(update={'occurred_at':(data.replay_at+timedelta(hours=1)).isoformat()})]
    assert fetch(data).status_code==404


def test_real_source_never_returns_demo_parts(context_data):
    data=context_data
    parts_catalog.import_catalog(parts_catalog.CatalogImport(parts=[part(data)]))
    data.provenance='user_supplied'
    data.replay_at=None
    value=fetch(data).json()
    assert value['source']=='imported_user_supplied' and not value['parts_candidates']
    assert value['search_diagnostics']['reason_code']=='no_eligible_catalog'


@pytest.mark.parametrize('conflict',[False,True])
def test_latest_record_status_is_historical_or_conflicting_not_machine_health(context_data,conflict):
    data=context_data
    latest=max(data.faults,key=lambda f:f.occurred_at).model_copy(update={'status':'resolved'})
    data.faults=[latest]
    if conflict:
        data.faults.append(latest.model_copy(update={'status':'open'}))
    value=fetch(data).json()
    assert value['latest_record_status']==('conflicting' if conflict else 'resolved')
    assert value['record_facts']['groups'][0]['independent_failure_count'] is None


def test_corrupted_catalog_is_a_service_error_not_empty_match(context_data):
    parts_catalog.CATALOG_PATH.write_text('broken',encoding='utf-8')
    response=fetch(context_data)
    assert response.status_code==503
    assert '目录' in response.json()['detail']
