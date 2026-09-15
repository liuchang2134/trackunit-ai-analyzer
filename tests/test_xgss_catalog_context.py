"""All catalog items below are test fixtures, never production spare part evidence."""
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app import xgss_catalog_context as catalog
from app.api import routes_xgss_context as routes
from scripts.prepare_parts_demo import build_demo

VIN='XUGTEST0000000001'
DATASET='a'*64


@pytest.fixture
def sample(monkeypatch,tmp_path):
    monkeypatch.setattr(catalog,'STORE',tmp_path/'catalog')
    return catalog.CatalogCapture(schema_version=1,source='xgss_visible_dom',source_url='https://xgss.xcmg.com/',
        vin=VIN,model='XE55U',configuration='XE55U.00III',assembly_path=['电气系统（测试分类）'],
        items=[dict(name='测试保险丝',part_number='TEST-001',figure_ref='1',quantity='2')],
        capture_status='visible_rows',visible_rows=1,coverage='visible_rows_only',warnings=[])


def test_snapshot_rows_have_stable_source_references_and_private_storage(sample):
    first=catalog.save_catalog_context(sample,dataset_id=DATASET,machine_id='machine-test')
    again=catalog.save_catalog_context(sample,dataset_id=DATASET,machine_id='machine-test')
    assert first==again
    assert first['items'][0]['source_id']==f"xgss:{first['capture_id']}:1"
    assert catalog.load_catalog_context(DATASET,VIN,'machine-test')==first
    assert catalog.load_catalog_context('b'*64,VIN,'machine-test')['status']=='not_captured'
    assert catalog.load_catalog_context(DATASET,'XUGOTHER000000001','machine-test')['status']=='not_captured'
    with pytest.raises(ValueError):catalog.load_catalog_context(DATASET,VIN,'wrong-machine')


def test_fleet_capture_and_no_dataset_demo_are_separate(sample):
    result=catalog.save_catalog_context(sample,machine_id='machine-test')
    assert catalog.load_catalog_context(None,VIN,'machine-test')==result
    assert catalog.load_catalog_context(None,VIN)['status']=='not_captured'
    assert catalog.load_catalog_context(None,None)['items']==[]
    assert catalog.load_catalog_context(None,VIN,'other-machine')['status']=='not_captured'


def test_unreadable_capture_does_not_replace_previous_rows(sample):
    first=catalog.save_catalog_context(sample,dataset_id=DATASET,machine_id='machine-test')
    unreadable=sample.model_copy(update={'capture_status':'no_visible_rows','items':[],'visible_rows':0})
    with pytest.raises(ValueError):catalog.save_catalog_context(unreadable,dataset_id=DATASET,machine_id='machine-test')
    assert catalog.load_catalog_context(DATASET,VIN)==first


def test_session_urls_and_unknown_fields_never_enter_capture(sample):
    for change in ({'source_url':'https://xgss.xcmg.com/catalog?token=TEST'}, {'cookie':'TEST'}, {'visible_rows':2}):
        with pytest.raises(ValidationError):catalog.CatalogCapture.model_validate({**sample.model_dump(),**change})


def test_modified_source_rows_and_source_ids_fail_validation(sample):
    first=catalog.save_catalog_context(sample,dataset_id=DATASET,machine_id='machine-test')
    path=catalog.STORE/f"{first['capture_id']}.json"
    changed=json.loads(path.read_text(encoding='utf-8'));changed['items'][0]['part_number']='TEST-999'
    path.write_text(json.dumps(changed),encoding='utf-8')
    with pytest.raises(ValueError):catalog.load_catalog_context(DATASET,VIN)


def test_route_rejects_mixed_vins_versions_and_synthetic_data(sample,monkeypatch):
    data=build_demo();data.machine.serial_number=VIN
    monkeypatch.setattr(routes,'load_dataset',lambda _:data)
    app=FastAPI();app.include_router(routes.router);client=TestClient(app)
    body={'machine_id':data.machine.machine_id,'dataset_id':DATASET,'capture':sample.model_dump()}
    assert client.post('/assistant/xgss/catalog-context',json=body).status_code==422
    data.provenance='user_supplied'
    assert client.post('/assistant/xgss/catalog-context',json={**body,'machine_id':'wrong'}).status_code==404
    assert client.post('/assistant/xgss/catalog-context',json={**body,'capture':{**body['capture'],'vin':'XUGOTHER000000001'}}).status_code==422
    assert not catalog.STORE.exists()
    saved=client.post('/assistant/xgss/catalog-context',json=body)
    assert saved.status_code==200 and saved.headers['cache-control']=='no-store'
    params={'machine_id':data.machine.machine_id,'dataset_id':DATASET,'vin':VIN}
    read=client.get('/assistant/xgss/catalog-context',params=params)
    assert read.status_code==200 and read.json()==saved.json()
    assert client.get('/assistant/xgss/catalog-context',params={**params,'vin':'XUGOTHER000000001'}).status_code==422
