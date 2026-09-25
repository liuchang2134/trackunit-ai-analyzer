"""Explicit direct-read retries are local-only and preserve verified evidence."""
import base64
from io import BytesIO

from PIL import Image
from pydantic import ValidationError
import pytest

from app import xgss_research_store as store, xgss_direct_collection as direct

VIN='XUGTEST000000001'


def page(title, *, picture=False):
    payload={'source':'xgss_api_catalog','source_url':'https://xgss.xcmg.com/',
             'vin':VIN,'title':title,'assembly_path':['整机',title],
             'items':[{'name':'测试阀总成','part_number':'TEST-001'}],
             'manual_sections':[],'coverage':'api_selected_categories'}
    if picture:
        output=BytesIO();Image.new('RGB',(3,2),'red').save(output,format='PNG')
        payload['illustrations']=[{'data_url':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode(),
                                   'title':'测试原图','document_ref':'fixture.svg'}]
    return store.PageCapture.model_validate(payload)


def response(pages, *, partial=False):
    return {'pages':pages,'status':'partial' if partial else 'completed',
            'unmatched_terms':[],'unresolved':['图示尚未取得'] if partial else []}


@pytest.fixture
def record(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    record=store.create('fixture-machine','a'*64,VIN)
    record['plan']={'summary':'补图测试'};store._write(record)
    return record


def collect(record, **changes):
    return direct.collect(record['research_id'],direct.CollectRequest(
        expected_revision=record['revision'],terms=['双变系统'],**changes))


@pytest.mark.parametrize('value',['true','false','1','0',1,0,None,[],{}])
def test_force_refresh_rejects_non_boolean(value):
    with pytest.raises(ValidationError):
        direct.CollectRequest(expected_revision=0,terms=['双变系统'],force_refresh=value)


def test_force_refresh_defaults_false_and_accepts_only_real_booleans():
    assert direct.CollectRequest(expected_revision=0,terms=['双变系统']).force_refresh is False
    for value in (True,False):
        assert direct.CollectRequest(expected_revision=0,terms=['双变系统'],force_refresh=value).force_refresh is value


def test_fresh_partial_force_refresh_recovers_picture_preserving_saved_image_and_advice(record,monkeypatch):
    # Fill the catalogue budget: retries must reuse their own page capacity.
    for index in range(6):record=store.append(record['research_id'],page(f'已有分类{index}'))
    calls=[]
    def reader(*args,**kwargs):
        calls.append(kwargs)
        if len(calls)==1:
            return response([page('双变一',picture=True),page('双变二')],partial=True)
        # The already verified image is absent in this response and must survive.
        return response([page('双变一'),page('双变二',picture=True)])
    monkeypatch.setattr(direct,'_read_catalog',reader)
    partial=collect(record)
    assert len(partial['pages'])==8 and partial['direct_collection']['status']=='partial'
    partial.update(advice={'summary':'已核对的建议'},analysis_revision=partial['revision'])
    store._write(partial)
    image_id=partial['pages'][6]['illustrations'][0]['image_id']
    original_image=store.read_image(partial,image_id)
    old_ids=[item['capture_id'] for item in partial['pages']]
    cached=collect(partial)
    assert cached['direct_collection']['cached'] is True and len(calls)==1
    refreshed=collect(partial,force_refresh=True)
    assert len(calls)==2 and calls[1]['max_pages']==2 and calls[1]['max_parts']==394
    assert refreshed['direct_collection']['cached'] is False
    assert refreshed['direct_collection']['status']=='completed'
    assert refreshed['pages'][6]['illustrations']==partial['pages'][6]['illustrations']
    assert store.read_image(refreshed,image_id)==original_image
    assert refreshed['pages'][7]['illustrations']
    assert [item['capture_id'] for item in refreshed['pages']]==old_ids
    assert refreshed['revision']==partial['revision']
    assert refreshed['advice']==partial['advice']
    assert refreshed['analysis_revision']==partial['analysis_revision']


def test_force_refresh_skips_completed_cache_too(record,monkeypatch):
    calls=[]
    monkeypatch.setattr(direct,'_read_catalog',lambda *args,**kwargs:(calls.append(1),response([page('双变系统')]))[1])
    saved=collect(record)
    assert collect(saved,force_refresh=False)['direct_collection']['cached'] is True
    assert collect(saved,force_refresh=True)['direct_collection']['cached'] is False
    assert len(calls)==2


@pytest.mark.parametrize('change',['revision','active'])
def test_force_refresh_cannot_bypass_request_guards(record,monkeypatch,change):
    monkeypatch.setattr(direct,'_read_catalog',lambda *args,**kwargs:response([page('双变系统')],partial=True))
    saved=collect(record)
    if change=='revision':
        stale=dict(saved);stale['revision']=0
    else:
        other=store.create(saved['machine_id'],saved['dataset_id'],saved['vin'])
        other['plan']={'summary':'另一排查'};store._write(other)
        store.activate(other['research_id'],None);stale=saved
    def unexpected(*args,**kwargs):raise AssertionError('Rejected retry must not query XGSS')
    monkeypatch.setattr(direct,'_read_catalog',unexpected)
    before=store._path(saved['research_id']).read_bytes()
    with pytest.raises(direct.DirectCollectionError) as error:collect(stale,force_refresh=True)
    assert error.value.kind==('direct_revision_changed' if change=='revision' else 'direct_active_changed')
    assert store._path(saved['research_id']).read_bytes()==before
