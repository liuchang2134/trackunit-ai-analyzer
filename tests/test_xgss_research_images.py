"""Synthetic PNG fixtures only: no browser, remote fetch, or production model."""
import base64
import hashlib
from io import BytesIO
import json
import struct

import pytest
from PIL import Image
from pydantic import ValidationError
from app import xgss_research_store as store, xgss_research_images as images, xgss_research_ai as ai

VIN='XUGTEST000000001'


def png(color='red'):
    output=BytesIO()
    Image.new('RGB',(3,2),color).save(output,format='PNG')
    return output.getvalue()


def illustration(data=None,**changes):
    return {'data_url':images.PNG_PREFIX+base64.b64encode(data or png()).decode(),
            'title':'冷却系统图纸','document_ref':'3944450.svg',**changes}


def content(**changes):
    return {'source':'xgss_rendered_page','source_url':'https://xgss.xcmg.com/',
            'vin':VIN,'title':'测试冷却图册','assembly_path':['冷却系统'],
            'items':[{'name':'测试散热器','part_number':'TEST-001'}],
            'manual_sections':[],'coverage':'rendered_content_only',**changes}


@pytest.fixture
def record(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    return store.create('fixture-machine','a'*64,VIN)


def append(record,**changes):
    return store.append(record['research_id'],store.PageCapture.model_validate(content(**changes)))


def test_legacy_hash_and_part_sources_survive_picture_attachment_without_invalidating_advice(record):
    current=append(record)
    original=current['pages'][0]
    expected=hashlib.sha256(json.dumps(original['content'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert original['capture_id']==expected
    source_id=store.evidence(current)['parts'][0]['source_id']
    current.update(advice={'summary':'已有建议'},analysis_revision=current['revision'],analyzed_at='fixture-time')
    store._write(current)
    updated=append(record,illustrations=[illustration()])
    page=updated['pages'][0]
    assert len(updated['pages'])==1 and updated['revision']==current['revision']
    assert updated['advice']==current['advice'] and updated['analysis_revision']==current['analysis_revision']
    assert page['capture_id']==expected and page['captured_at']==original['captured_at']
    assert store.evidence(updated)['parts'][0]['source_id']==source_id
    assert 'illustrations' not in page['content']
    assert 'data_url' not in json.dumps(updated) and images.PNG_PREFIX not in json.dumps(updated)
    metadata=page['illustrations'][0]
    assert set(metadata)=={'image_id','title','document_ref','width','height','captured_at'}
    assert (metadata['width'],metadata['height'])==(3,2)
    assert store.read_image(store.read(record['research_id']),metadata['image_id'])==png()
    before=store._path(record['research_id']).read_bytes()
    assert append(record,illustrations=[illustration()])==updated
    assert store._path(record['research_id']).read_bytes()==before


def test_replacing_picture_preserves_text_revision_and_plain_recap_preserves_picture(record):
    current=append(record,illustrations=[illustration()])
    current.update(advice={'summary':'已有建议'},analysis_revision=current['revision'])
    store._write(current)
    changed=append(record,illustrations=[illustration(png('blue'),document_ref='3944451')])
    assert changed['revision']==current['revision'] and changed['advice']==current['advice']
    assert changed['pages'][0]['capture_id']==current['pages'][0]['capture_id']
    assert changed['pages'][0]['illustrations'][0]['image_id']!=current['pages'][0]['illustrations'][0]['image_id']
    assert append(record)==changed


@pytest.mark.parametrize('bad',[
    {'data_url':'https://xgss.xcmg.com/api/doc/image2d/3944450.svg'},
    {'data_url':'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4='},
    {'document_ref':'../3944450.svg'},
    {'document_ref':'3944450.svg?token=secret'},
    {'document_ref':'https://xgss.xcmg.com/3944450.svg'},
])
def test_image_transport_rejects_addresses_svg_and_non_basename_references(bad):
    with pytest.raises(ValidationError):
        store.PageCapture.model_validate(content(illustrations=[illustration(**bad)]))


def test_multiple_images_and_svg_disguised_as_png_cannot_change_existing_page(record):
    with pytest.raises(ValidationError):
        store.PageCapture.model_validate(content(illustrations=[illustration(),illustration()]))
    current=append(record)
    before=store._path(record['research_id']).read_bytes()
    with pytest.raises(images.ImageCaptureError):
        append(record,illustrations=[illustration(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')])
    assert store._path(record['research_id']).read_bytes()==before
    assert not (store.STORE/'images').exists()
    assert store.read(record['research_id'])==current


@pytest.mark.parametrize('width,height',[(4097,1),(3000,3000),(0,2)])
def test_image_dimension_bounds_are_checked_before_pixel_decode(record,width,height):
    data=bytearray(png());data[16:24]=struct.pack('>II',width,height)
    before=store._path(record['research_id']).read_bytes()
    with pytest.raises(images.ImageCaptureError,match='尺寸'):
        append(record,illustrations=[illustration(bytes(data))])
    assert store._path(record['research_id']).read_bytes()==before


def test_image_byte_and_research_budget_rejection_preserve_sources_and_advice(record,monkeypatch):
    current=append(record,illustrations=[illustration()])
    current.update(advice={'summary':'已有建议'},analysis_revision=current['revision'])
    store._write(current)
    before=store._path(record['research_id']).read_bytes()
    monkeypatch.setattr(images,'MAX_IMAGE_BYTES',len(png())-1)
    with pytest.raises(images.ImageCaptureError):append(record,title='另一页',illustrations=[illustration()])
    assert store._path(record['research_id']).read_bytes()==before
    monkeypatch.setattr(images,'MAX_IMAGE_BYTES',2*1024*1024)
    monkeypatch.setattr(images,'MAX_RESEARCH_IMAGE_BYTES',len(png()))
    with pytest.raises(images.ImageCaptureError,match='图片总量'):
        append(record,title='另一页',illustrations=[illustration(png('blue'))])
    assert store._path(record['research_id']).read_bytes()==before
    assert len(list((store.STORE/'images').glob('*.png')))==1


def test_wrong_vin_and_failed_metadata_write_leave_no_new_blob(record,monkeypatch):
    before=store._path(record['research_id']).read_bytes()
    with pytest.raises(ValueError,match='VIN'):
        append(record,vin='XUGOTHER000000001',illustrations=[illustration()])
    assert not (store.STORE/'images').exists()
    def unavailable(_record):raise OSError('fixture metadata write failure')
    monkeypatch.setattr(store,'_write',unavailable)
    with pytest.raises(OSError):append(record,illustrations=[illustration()])
    assert store._path(record['research_id']).read_bytes()==before
    assert list((store.STORE/'images').glob('*'))==[]


def test_image_route_checks_research_membership_identity_hash_and_private_headers(record,monkeypatch):
    from fastapi import FastAPI,HTTPException
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    current=append(record,illustrations=[illustration()]);metadata=current['pages'][0]['illustrations'][0]
    checks=[]
    def verify(machine,dataset,vin):checks.append((machine,dataset,vin))
    monkeypatch.setattr(routes,'_verify_machine',verify)
    app=FastAPI();app.include_router(routes.router);client=TestClient(app)
    url=f"/assistant/xgss/research/{record['research_id']}/images/{metadata['image_id']}"
    response=client.get(url)
    assert response.status_code==200 and response.content==png()
    assert response.headers['content-type']=='image/png'
    assert response.headers['cache-control']=='no-store' and response.headers['x-content-type-options']=='nosniff'
    assert checks[-1]==(record['machine_id'],record['dataset_id'],VIN)
    other=store.create('other-device','b'*64,VIN)
    assert client.get(f"/assistant/xgss/research/{other['research_id']}/images/{metadata['image_id']}").status_code==404
    images.path_for(store.STORE/'images',metadata['image_id']).write_bytes(b'broken')
    assert client.get(url).status_code==404
    assert store.read(record['research_id'])['pages'][0]['content']==current['pages'][0]['content']
    def wrong_version(*args):raise HTTPException(422,'fixture wrong version')
    monkeypatch.setattr(routes,'_verify_machine',wrong_version)
    assert client.get(url).status_code==422


def test_new_inline_image_response_and_ai_projection_contain_no_image_payload(record,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import routes_xgss_research as routes
    monkeypatch.setattr(routes,'_verify_machine',lambda *a:None)
    app=FastAPI();app.include_router(routes.router);client=TestClient(app)
    response=client.post(f"/assistant/xgss/research/{record['research_id']}/pages",json=content(illustrations=[illustration()]))
    assert response.status_code==200
    assert response.json()['pages'][0]['illustrations'][0]['document_ref']=='3944450.svg'
    assert 'data_url' not in response.text
    current=store.read(record['research_id'])
    current.update(plan={'summary':'模拟排查计划'},model='XC948U',symptom='模拟温升，需要排查。',symptom_source='simulation')
    store._write(current)
    sent=[]
    def model(messages,*args,**kwargs):
        sent.append(messages[1]['content'])
        return json.dumps({'summary':'模拟场景，需核查散热器。','parts':[],
            'repair_steps':[{'instruction':'核查现场现象。','basis':'ai_inspection_suggestion'}],'missing_evidence':[]},ensure_ascii=False)
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',model)
    analyzed=ai.analyze(record['research_id'])
    assert analyzed['pages'][0]['illustrations']==current['pages'][0]['illustrations']
    for forbidden in ('illustrations','data_url','image_id','3944450.svg','data:image','冷却系统图纸'):
        assert forbidden not in ''.join(sent)


def test_missing_optional_png_decoder_keeps_text_only_capture_available(record,monkeypatch):
    monkeypatch.setattr(images,'Image',None)
    assert append(record)['revision']==1
    with pytest.raises(images.ImageCaptureError,match='无法校验'):
        append(record,illustrations=[illustration()])
