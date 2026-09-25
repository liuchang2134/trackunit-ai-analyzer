"""Contract tests for direct XGSS reads. All upstream traffic is mocked."""
import copy
import json
import time
import httpx
import pytest
from app import xgss_direct_api as api

VIN='XUGTESTVIN0000001'
SVG=b'<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="20mm" viewBox="0 0 10 20"><path d="M1 1L8 18" stroke="black"/></svg>'
ROOT={'id':10,'code':VIN,'name':'XC948','type':'0','leaf':False}
NODE={'id':20,'code':'252808033','name':'双变系统','leaf':True}
LIST={'id':30,'code':'PL_252808033','name':'双变系统'}
DETAIL={**LIST,'d2ids':['3944444.svg'],'parts':[
    {'code':'800365540','name':'变速箱总成','ballNum':'1','amount':'1','purchaseStatus':1},
    {'code':'252805194','name':'变速箱支架','ballNum':'2','amount':'1','purchaseStatus':2}]}

@pytest.fixture
def upstream(monkeypatch):
    calls=[];overrides={};state={'role':'0'}
    def route(request):
        path=request.url.path;calls.append((request.method,path,dict(request.url.params)))
        assert request.url.host=='xgss.xcmg.com'
        if path in overrides:
            value=overrides[path]
            if isinstance(value,Exception):raise value
            if isinstance(value,httpx.Response):return value
            data=value
        elif path.endswith('/login/init'):
            assert json.loads(request.content)=={'token':'entry-token','random':'random','userId':'user'}
            data={'token':'session-token','productDomains':[1000],'userType':{'code':state['role']}}
        else:
            assert request.headers['token']=='session-token'
            assert request.headers['productId']=='1000'
            if path.endswith('/root/'+VIN):data={'pin':VIN,'partRoots':[ROOT],'vinPermision':{'PER_PART_ATLAS_VIEW':'valid'}}
            elif '/children/' in path:
                assert request.url.params['code']==VIN
                assert request.url.params['nodeType']=='topPart'
                data=[NODE]
            elif '/partlist/list/' in path:data=[LIST]
            elif '/partlist/view/' in path:
                assert request.url.params['car']==VIN
                data=DETAIL
            elif '/image2d/' in path:return httpx.Response(200,content=SVG)
            else:raise AssertionError(path)
        return httpx.Response(200,json={'success':True,'data':copy.deepcopy(data)})
    client=httpx.Client(base_url=api.BASE,transport=httpx.MockTransport(route))
    original=api.CatalogClient
    monkeypatch.setattr(api,'CatalogClient',lambda vin,check_cancelled,progress:original(vin,check_cancelled,progress,client=client))
    monkeypatch.setattr(api.handoff,'request_page',lambda vin:{'url':api.BASE+'/#/CrmJump?vin='+vin+'&token=entry-token&random=random&userId=user'})
    return calls,overrides,state

def test_collect_binds_real_category_parts_and_raster_image_and_stops(upstream):
    result=api.collect_catalog(VIN,['变速箱','双变系统'])
    assert result['status']=='completed' and result['unmatched_terms']==[]
    assert result['requests']==6
    assert len(result['pages'])==1
    page=result['pages'][0]
    assert page['vin']==VIN and page['source']=='xgss_api_catalog'
    assert page['assembly_path']==['XC948','双变系统']
    assert [row['part_number'] for row in page['items']]==['800365540','252805194']
    assert page['illustrations'][0]['document_ref']=='3944444.svg'
    assert page['illustrations'][0]['data_url'].startswith('data:image/png;base64,')
    assert 'token' not in json.dumps(result)

def test_private_role_cannot_reveal_hidden_material_codes(upstream):
    upstream[2]['role']='9'
    result=api.collect_catalog(VIN,['双变系统'])
    assert [r['part_number'] for r in result['pages'][0]['items']]==['800365540']
    assert result['status']=='partial'

@pytest.mark.parametrize('vin',['OTHER1234',None])
def test_wrong_root_identity_stops_before_reading_parts(upstream,vin):
    upstream[1]['/api/rest/part/car/root/'+VIN]={'pin':vin,'partRoots':[ROOT]}
    with pytest.raises(api.DirectReadError,match='VIN') as error:api.collect_catalog(VIN,['双变系统'])
    assert error.value.kind=='direct_identity'
    assert len(upstream[0])==2

def test_wrong_authenticated_identity_stops_before_any_api(upstream,monkeypatch):
    monkeypatch.setattr(api.handoff,'request_page',lambda vin:{'url':api.BASE+'/#/CrmJump?vin=WRONG1234&token=t&random=r&userId=u'})
    with pytest.raises(api.DirectReadError) as error:api.collect_catalog(VIN,['双变系统'])
    assert error.value.kind=='direct_identity' and not upstream[0]

def test_wrong_detail_identity_never_downloads_drawing(upstream):
    upstream[1]['/api/rest/partlist/view/30/10']={**DETAIL,'code':'PL_DIFFERENT'}
    with pytest.raises(api.DirectReadError) as error:api.collect_catalog(VIN,['双变系统'])
    assert error.value.kind=='direct_schema'
    assert not any('/image2d/' in c[1] for c in upstream[0])

@pytest.mark.parametrize('root_payload',[
    {'pin':VIN,'partRoots':[None],'vinPermision':{'PER_PART_ATLAS_VIEW':'valid'}},
    {'pin':VIN,'partRoots':[ROOT],'vinPermision':None},
])
def test_malformed_root_is_typed_error(upstream,root_payload):
    upstream[1]['/api/rest/part/car/root/'+VIN]=root_payload
    with pytest.raises(api.DirectReadError):api.collect_catalog(VIN,['双变系统'])

def test_unavailable_image_leaves_explicit_partial_without_invented_picture(upstream):
    upstream[1]['/api/rest/partlist/view/30/10']={**DETAIL,'d2ids':[]}
    result=api.collect_catalog(VIN,['双变系统'])
    assert result['status']=='partial'
    assert result['pages'][0]['illustrations']==[]
    assert any('图纸' in issue for issue in result['unresolved'])

def test_multiple_drawing_sheets_are_not_arbitrarily_assigned_to_every_row(upstream):
    upstream[1]['/api/rest/partlist/view/30/10']={**DETAIL,'d2ids':['3944444.svg','3944445.svg']}
    result=api.collect_catalog(VIN,['双变系统'])
    assert result['status']=='completed'
    illustration=result['pages'][0]['illustrations'][0]
    assert illustration['document_ref'].startswith('sheets-')
    assert '共 2 页' in illustration['title']
    assert sum('/image2d/' in call[1] for call in upstream[0])==2

def test_requested_part_in_category_counts_as_found_without_scanning_other_systems(upstream):
    result=api.collect_catalog(VIN,['双变系统','变速箱总成'])
    assert result['status']=='completed' and result['requests']==6

def test_timeout_does_not_request_browser_fallback(upstream):
    upstream[1]['/api/rest/part/car/root/'+VIN]=httpx.ReadTimeout('private network details')
    with pytest.raises(api.DirectReadError) as error:api.collect_catalog(VIN,['双变系统'])
    assert error.value.kind=='direct_timeout' and 'private' not in str(error.value)

def test_redirect_is_not_followed(upstream):
    upstream[1]['/api/rest/part/car/root/'+VIN]=httpx.Response(302,headers={'location':'https://elsewhere.invalid/'})
    with pytest.raises(api.DirectReadError):api.collect_catalog(VIN,['双变系统'])
    assert len(upstream[0])==2

def test_cancel_before_authentication(upstream):
    def cancel():raise InterruptedError('cancelled')
    with pytest.raises(InterruptedError):api.collect_catalog(VIN,['双变系统'],check_cancelled=cancel)
    assert not upstream[0]

def test_budget_returns_existing_complete_page_as_partial(upstream,monkeypatch):
    monkeypatch.setattr(api,'MAX_REQUESTS',9)
    result=api.collect_catalog(VIN,['双变系统','不存在的分类'])
    assert len(result['pages'])==1 and result['status']=='partial'
    assert result['unmatched_terms']==['不存在的分类']
    assert len(upstream[0])<=9

@pytest.mark.parametrize('malicious',[
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><image href="file:///secret"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><use href="https://outside.invalid/x"/></svg>',
    b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///secret">]><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><text>&x;</text></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><style>@import "https://outside.invalid";</style></svg>',
])
def test_svg_external_resources_are_never_rendered(malicious):
    with pytest.raises(api.DirectReadError) as error:api.svg_png(malicious)
    assert error.value.kind=='direct_image'

def test_svg_mm_dimensions_and_standard_doctype_work():
    png=api.svg_png(b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">'+SVG)
    assert api.images.validate_png(png)==(800,1600)

def test_only_exact_read_routes_are_permitted():
    client=api.CatalogClient(VIN,lambda:None,lambda _:None)
    try:
        for method,path in [('POST','/api/rest/shopping/save'),('GET','https://other.invalid/api/rest/part/car/root/'+VIN)]:
            with pytest.raises(api.DirectReadError):client.request(method,path)
        assert client.requests==0
    finally:client.close()


def two_categories(upstream,*,unrelated=False):
    cooling={'id':21,'code':'252808034','name':'冷却系统','leaf':True}
    listing={'id':31,'code':'PL_252808034','name':'冷却系统'}
    children=[NODE,cooling]
    if unrelated:children.append({'id':22,'code':'252808035','name':'驾驶室装饰','leaf':False})
    upstream[1]['/api/rest/part/car/children/10/'+VIN]=children
    upstream[1]['/api/rest/partlist/list/21']=[listing]
    upstream[1]['/api/rest/partlist/view/31/10']={**listing,'d2ids':['3944445.svg'],
        'parts':[{'code':'800100001','name':'散热器','ballNum':'1','amount':'1','purchaseStatus':1}]}


def test_useful_category_stops_unrelated_bom_scan_with_many_unmatched_terms(upstream):
    unrelated={'id':22,'code':'252808035','name':'驾驶室装饰','leaf':False}
    upstream[1]['/api/rest/part/car/children/10/'+VIN]=[NODE,unrelated]
    terms=['双变系统','变速箱',*[f'尚无分类{i}' for i in range(9)]]
    result=api.collect_catalog(VIN,terms)
    assert len(result['pages'])==1 and result['status']=='partial'
    assert result['unmatched_terms']==terms[2:]
    assert result['requests']==6 and result['tree_reads']==1
    assert any('无匹配' in text for text in result['unresolved'])
    assert not any('/children/22/' in path for _,path,_ in upstream[0])


def test_matching_categories_continue_before_stopping_unrelated_scan(upstream):
    two_categories(upstream,unrelated=True)
    result=api.collect_catalog(VIN,['双变系统','冷却系统','水泵'])
    assert len(result['pages'])==2 and result['requests']==9
    assert result['matched_terms']==['双变系统','冷却系统']
    assert result['unmatched_terms']==['水泵'] and result['status']=='partial'
    assert not any('/children/22/' in path for _,path,_ in upstream[0])


def test_no_useful_page_keeps_bounded_search_through_unmatched_wrapper(upstream):
    node={'id':22,'code':'252808035','name':'动力安装模块','leaf':False}
    upstream[1]['/api/rest/part/car/children/10/'+VIN]=[node]
    upstream[1]['/api/rest/part/car/children/22/'+VIN]=[NODE]
    result=api.collect_catalog(VIN,['双变系统'])
    assert result['status']=='completed' and result['requests']==7
    assert result['pages'][0]['assembly_path']==['XC948','动力安装模块','双变系统']


@pytest.mark.parametrize('failure',[
    httpx.ReadTimeout('private details'),httpx.ConnectError('private details'),httpx.Response(503)])
def test_later_transport_failure_keeps_only_previously_verified_categories(upstream,failure):
    two_categories(upstream)
    upstream[1]['/api/rest/partlist/list/21']=failure
    result=api.collect_catalog(VIN,['双变系统','冷却系统'])
    assert result['status']=='partial' and len(result['pages'])==1
    assert result['pages'][0]['illustrations'][0]['document_ref']=='3944444.svg'
    assert result['matched_terms']==['双变系统'] and result['unmatched_terms']==['冷却系统']
    assert any('后续读取' in item for item in result['unresolved'])
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('failure,kind',[
    (httpx.Response(401),'direct_auth'),(httpx.Response(403),'direct_auth'),
    (httpx.Response(302,headers={'location':'https://outside.invalid/'}),'direct_unavailable'),
    (httpx.Response(200,content=b'not-json'),'direct_schema'),
    ([{'id':31,'code':'PL_DIFFERENT','name':'错配图册'}],'direct_schema')])
def test_later_auth_schema_or_redirect_error_never_becomes_partial_success(upstream,failure,kind):
    two_categories(upstream)
    upstream[1]['/api/rest/partlist/list/21']=failure
    with pytest.raises(api.DirectReadError) as error:
        api.collect_catalog(VIN,['双变系统','冷却系统'])
    assert error.value.kind==kind


def test_later_transport_failure_does_not_swallow_outer_cancel_or_deadline(upstream):
    two_categories(upstream)
    upstream[1]['/api/rest/partlist/list/21']=httpx.ReadTimeout('timeout after first page')
    class OuterDeadline(Exception):pass
    def check_cancelled():
        if any('/partlist/list/21' in path for _,path,_ in upstream[0]):
            raise OuterDeadline('outer request deadline/cancellation')
    with pytest.raises(OuterDeadline):
        api.collect_catalog(VIN,['双变系统','冷却系统'],check_cancelled=check_cancelled)


def test_own_query_deadline_is_not_reclassified_as_partial_transport_failure(upstream,monkeypatch):
    two_categories(upstream)
    def clock():
        return 100 if any('/image2d/' in path for _,path,_ in upstream[0]) else 0
    monkeypatch.setattr(api.time,'monotonic',clock)
    with pytest.raises(api.DirectReadError) as error:
        api.collect_catalog(VIN,['双变系统','冷却系统'])
    assert error.value.kind=='direct_timeout' and error.value.preserve_completed is False
