from app import xgss_direct_api as api
from app.xgss_catalog_search import term_matches, route_score
from test_xgss_direct_api import upstream, VIN, ROOT


def test_catalog_navigation_handles_real_export_names_without_inventing_matches():
    assert term_matches('润滑油泵（铲运）', '机油泵')
    assert term_matches('水泵及驱动组件', '冷却液泵')
    assert term_matches('PE9754 后处理', 'Aftertreatment')
    assert not term_matches('集中润滑系统', '润滑系统')
    assert not term_matches('后处理组件', '尿素泵')
    assert route_score('后处理组件', ['尿素泵']) == 2
    assert route_score('发动机系统', ['机油压力传感器']) == 1
    assert route_score('集中润滑系统', ['机油压力传感器']) == 0
    assert not term_matches('变速箱壳', '变速箱油滤清器')
    for term in ('Transmission Oil Pressure', '变速箱油压传感器', '液压油压力传感器'):
        assert route_score('润滑油泵（铲运）', [term]) == 0
        assert route_score('机油滤清器', [term]) == 0
    assert route_score('液压系统', ['液压油压力传感器']) == 2
    assert route_score('双变系统', ['Transmission Oil Pressure']) == 2
    assert route_score('变速箱总成(国产)', ['变矩器']) == 1
    assert route_score('发动机-双变连接', ['变矩器']) == 0


def branch(upstream, *, system, parts):
    engine={'id':21,'code':'engine','name':'发动机系统','leaf':False}
    upstream[1]['/api/rest/part/car/children/10/'+VIN]=[engine]
    upstream[1]['/api/rest/part/car/children/21/'+VIN]=[system]
    listing={'id':31,'code':'PL_'+system['code'],'name':system['name']}
    upstream[1]['/api/rest/partlist/list/'+str(system['id'])]=[listing]
    upstream[1]['/api/rest/partlist/view/31/10']={**listing,'d2ids':['3944444.svg'],'parts':parts}


def test_urea_parts_are_found_inside_aftertreatment_bom(upstream):
    branch(upstream,system={'id':22,'code':'after','name':'后处理组件','leaf':True},parts=[
        {'name':'尿素箱','code':'TEST-UREA1','ballNum':3,'purchaseStatus':1}])
    result=api.collect_catalog(VIN,['DEF tank'])
    assert result['status']=='completed'
    assert result['pages'][0]['items'][0]['part_number']=='TEST-UREA1'
    assert result['matched_terms']==['DEF tank']
    assert result['requests']==7


def test_engine_oil_search_traverses_engine_not_chassis_greasing(upstream):
    branch(upstream,system={'id':22,'code':'oil','name':'润滑油泵（铲运）','leaf':True},parts=[
        {'name':'润滑油泵','code':'TEST-OIL1','ballNum':1,'purchaseStatus':1}])
    upstream[1]['/api/rest/part/car/children/10/'+VIN].insert(0,
        {'id':23,'code':'grease','name':'集中润滑系统','leaf':True})
    result=api.collect_catalog(VIN,['机油泵'])
    assert result['status']=='completed'
    assert result['pages'][0]['items'][0]['part_number']=='TEST-OIL1'
    assert not any('/partlist/list/23' in path for _,path,_ in upstream[0])


def test_route_alone_does_not_report_requested_component_as_found(upstream):
    branch(upstream,system={'id':22,'code':'after','name':'后处理组件','leaf':True},parts=[
        {'name':'安装支架','code':'TEST-BRACKET1','ballNum':3,'purchaseStatus':1}])
    result=api.collect_catalog(VIN,['尿素泵'])
    assert result['status']=='partial'
    assert result['matched_terms']==[] and result['unmatched_terms']==['尿素泵']


def test_torque_converter_search_keeps_expanding_gearbox_after_system_page(upstream):
    branch(upstream,system={'id':22,'code':'gearbox','name':'变速箱总成(国产)','leaf':False},parts=[
        {'name':'变速箱总成','code':'TEST-BOX1','ballNum':1,'purchaseStatus':1}])
    upstream[1]['/api/rest/part/car/children/10/'+VIN][0]['name']='双变系统'
    upstream[1]['/api/rest/partlist/list/21']=[{'id':35,'code':'PL_engine','name':'双变系统'}]
    upstream[1]['/api/rest/partlist/view/35/10']={'id':35,'code':'PL_engine','name':'双变系统','d2ids':[],
        'parts':[{'name':'变速箱总成','code':'TEST-BOX1','ballNum':1,'purchaseStatus':1}]}
    node={'id':24,'code':'converter','name':'变矩器','leaf':True}
    upstream[1]['/api/rest/part/car/children/22/'+VIN]=[node]
    upstream[1]['/api/rest/partlist/list/24']=[{'id':36,'code':'PL_converter','name':'变矩器'}]
    upstream[1]['/api/rest/partlist/view/36/10']={'id':36,'code':'PL_converter','name':'变矩器','d2ids':['3944444.svg'],
        'parts':[{'name':'变矩器','code':'TEST-TORQUE1','ballNum':1,'purchaseStatus':1}]}
    result=api.collect_catalog(VIN,['变矩器'])
    assert '变矩器' in result['matched_terms']
    assert any(p['items'][0]['part_number']=='TEST-TORQUE1' for p in result['pages'])
