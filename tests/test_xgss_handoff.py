import base64
import json
import httpx
import pytest
from fastapi.testclient import TestClient
pytest.importorskip('cryptography', reason='Install requirements-xgss.txt for optional XGSS tests')
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from app import xgss_handoff as xgss
from app.api import routes_xgss
from app.main import app
from scripts.prepare_parts_demo import build_demo

VIN='XUGTEST0000000001'


@pytest.fixture
def configured(monkeypatch):
    key=rsa.generate_private_key(public_exponent=65537,key_size=1024)
    config=dict(identity={'username':'LOCAL_TEST_ONLY','orderId':'TEST_CONTEXT'}, type=2,
                fault_code_field='testFaultField',fault_code_location='encrypted_payload')
    monkeypatch.setattr(xgss,'configuration',lambda:(config,key.public_key()))
    calls=[]
    def transport(request):
        calls.append(request)
        return httpx.Response(200,json={'success':True,'data':'https://xgss.xcmg.com/test-page?token=TEST_ONLY'})
    original=httpx.Client
    monkeypatch.setattr(xgss.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(transport),**kw))
    return config,key,calls


def plaintext(configured):
    _,key,calls=configured
    body=json.loads(calls[0].content)
    encoded=base64.b64decode(body['data'])
    return json.loads(b''.join(key.decrypt(encoded[i:i+128],padding.PKCS1v15()) for i in range(0,len(encoded),128))),body


def test_fault_handoff_uses_configured_field_and_preserves_returned_url(configured):
    result=xgss.request_page(VIN,'E4030')
    clear,body=plaintext(configured)
    assert clear['vin']==VIN and clear['testFaultField']=='E4030'
    assert clear['type']==2 and clear['terminal']=='t4' and clear['systemCode']=='iov'
    assert 'E4030' not in json.dumps(body)
    assert result['url']=='https://xgss.xcmg.com/test-page?token=TEST_ONLY'
    assert result['destination']=='manual_or_catalog'
    assert result['manual_match_verified'] is False and result['manual_content_loaded'] is False
    assert len(configured[2])==1


def test_catalog_without_fault_does_not_invent_empty_fault_field(configured):
    configured[0]['fault_code_field']=None
    result=xgss.request_page(VIN)
    clear,_=plaintext(configured)
    assert 'testFaultField' not in clear
    assert result['destination']=='catalog'


def test_missing_fault_contract_never_silently_downgrades_to_catalog(configured):
    configured[0]['fault_code_field']=None
    with pytest.raises(xgss.XGSSUnavailable):xgss.request_page(VIN,'E4030')
    assert not configured[2]


def test_outer_field_only_when_config_explicitly_confirms_location(configured):
    configured[0]['fault_code_location']='outer_body'
    xgss.request_page(VIN,'E4030')
    clear,body=plaintext(configured)
    assert body['testFaultField']=='E4030' and 'testFaultField' not in clear


@pytest.mark.parametrize('url', ['https://xgss.xcmg.com.evil.test/page','http://xgss.xcmg.com/page',
    'https://user:pass@xgss.xcmg.com/page','https://xgss.xcmg.com:444/page','javascript:alert(1)',
    'https://xgss.xcmg.com\\@evil.test','https://xgss.xcmg.com/\nsecret',None])
def test_untrusted_destination_rejected(url):
    assert not xgss.valid_destination(url)


@pytest.mark.parametrize('status,body', [(401,{'data':'secret upstream message'}),(302,{}),
    (200,{'success':False,'message':'secret account error'}),(200,{'success':True,'data':'https://evil.test'})])
def test_errors_are_not_manual_missing_or_returned_upstream_text(configured,monkeypatch,status,body):
    class ResponseClient:
        def __init__(self,**kwargs):assert kwargs['follow_redirects'] is False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,*args,**kwargs):return httpx.Response(status,json=body)
    monkeypatch.setattr(xgss.httpx,'Client',ResponseClient)
    with pytest.raises(xgss.XGSSUpstreamError) as error:xgss.request_page(VIN,'E4030')
    assert 'secret' not in str(error.value)


def test_readiness_does_not_expose_identity_or_call_network(configured):
    result=xgss.readiness()
    assert result['catalog_ready'] and result['fault_ready'] and not result['live_verified']
    assert 'LOCAL_TEST_ONLY' not in json.dumps(result)
    assert not configured[2]


def test_unconfigured_status_is_actionable_and_contains_no_url(monkeypatch,tmp_path):
    monkeypatch.delenv('XGSS_CONFIG_PATH',raising=False)
    monkeypatch.setattr(xgss,'CONFIG_PATH',tmp_path/'absent.json')
    result=TestClient(app).get('/assistant/xgss/status')
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    assert result.json()['catalog_ready'] is False and 'url' not in result.json()


def test_route_binds_vin_and_source_before_any_upstream_request(monkeypatch):
    data=build_demo()
    data.machine.serial_number=VIN
    monkeypatch.setattr(routes_xgss,'load_dataset',lambda _:data)
    calls=[]
    monkeypatch.setattr(xgss,'request_page',lambda *args:(calls.append(args) or {'url':'https://xgss.xcmg.com/test'}))
    request=dict(machine_id=data.machine.machine_id,dataset_id='a'*64,vin=VIN,vin_confirmed=True,fault_code='E4030')
    client=TestClient(app)
    assert client.post('/assistant/xgss/open',json=request).status_code==422
    data.provenance='user_supplied'
    assert client.post('/assistant/xgss/open',json={**request,'machine_id':'WRONG'}).status_code==404
    assert client.post('/assistant/xgss/open',json={**request,'vin':'XUGOTHER00000001'}).status_code==422
    assert client.post('/assistant/xgss/open',json={**request,'vin_confirmed':False}).status_code==422
    assert not calls
    result=client.post('/assistant/xgss/open',json=request)
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    assert result.headers['referrer-policy']=='no-referrer'
    assert calls==[(VIN,'E4030','zh')]


def test_config_requires_explicit_identity_query_mode_and_contract(monkeypatch,tmp_path):
    monkeypatch.delenv('XGSS_CONFIG_PATH',raising=False)
    path=tmp_path/'config.json';monkeypatch.setattr(xgss,'CONFIG_PATH',path)
    for value in ({}, {'query_mode_confirmed':False}, {'query_mode_confirmed':True,'identity':{'username':'test'}},
                  {'query_mode_confirmed':True,'identity':{'username':'test','orderId':'test'},'type':2,'fault_code_field':'vin'}):
        path.write_text(json.dumps(value))
        assert xgss.readiness()['catalog_ready'] is False
