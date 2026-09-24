"""Synthetic local records and fake SMTP only; never use local credentials."""
import json
import smtplib
import sqlite3
from urllib.parse import parse_qs,urlsplit
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import research_email as email,xgss_research_ai as ai,xgss_research_store as store
from app.api import routes_research_email as routes

VIN='XUGTEST000000001'
DATASET='a'*64
ORIGIN='http://127.0.0.1:8890'
MAPPING='SPN 110 / FMI 15 (SA 0) 冷却液温度偏高：检查风扇（图册料号 800160318）的叶片与转动情况；仅确认叶片破损且核对适配后考虑更换。'


@pytest.fixture(autouse=True)
def isolation(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')
    monkeypatch.setattr(email,'STATE_DB',tmp_path/'email.sqlite3')
    monkeypatch.setattr(email,'IN_FLIGHT',set())
    for name in ('SMTP_HOST','SMTP_PORT','SMTP_SECURITY','SMTP_USERNAME','SMTP_PASSWORD','FROM','TO'):
        monkeypatch.delenv(email.PREFIX+name,raising=False)
    def forbidden(*a,**kw):raise AssertionError('No network or model call allowed')
    monkeypatch.setattr(ai,'generate_structured_with_deepseek',forbidden)
    monkeypatch.setattr(email.smtplib,'SMTP',forbidden)
    monkeypatch.setattr(email.smtplib,'SMTP_SSL',forbidden)


def configure(monkeypatch,recipients='service@example.test,parts@example.test'):
    values={'SMTP_HOST':'smtp.example.test','SMTP_USERNAME':'fixture-user','SMTP_PASSWORD':'fixture-password',
            'FROM':'sender@example.test','TO':recipients}
    for name,value in values.items():monkeypatch.setenv(email.PREFIX+name,value)


@pytest.fixture
def record():
    current=store.create('fixture-machine',DATASET,VIN)
    page=store.PageCapture(source='xgss_rendered_page',source_url='https://xgss.xcmg.com/',vin=VIN,
        title='冷却系统',assembly_path=['冷却系统'],items=[{'name':'风扇','part_number':'800160318','figure_ref':'4','quantity':'1'}],
        # Synthetic same-machine manual mapping supports a conditional candidate;
        # the temperature code and catalog entry do not prove fan damage.
        manual_sections=[{'title':'合成故障检查手册','text':MAPPING}],coverage='rendered_content_only')
    current=store.append(current['research_id'],page)
    source=store.evidence(current)['parts'][0]
    manual=store.evidence(current)['manuals'][0]
    current.update(model='XC948U',symptom='模拟 SPN 110 / FMI 15 持续作业温升，降低负荷后回落。',symptom_source='simulation',
        plan={'summary':'模拟排查'},analyzed_at='2026-09-22T12:00:00+00:00',analysis_revision=current['revision'],
        advice_quality_version=ai.grounding.VERSION,
        machine_context={'source':'trackunit_cache','sample_count':3,'last_sample_at':'2026-09-15T14:55:16+00:00',
            'metrics':{'operating_hours':{'value':419.73,'unit':'h','observed_at':'2026-09-15T14:55:16+00:00'}},
            'faults':[]},
        advice={'summary':'模拟温升需要检查冷却系统，风扇尚未确认损坏。',
            'parts':[{'source_id':source['source_id'],'reason':'同码合成手册要求检查风扇；尚未确认损坏',
                'replacement_condition':'现场检查叶片与转动情况，仅确认叶片破损且核对配置后考虑更换','part_number':'FAKE-999',
                'fault_relation':'direct','support':'manual_mapping','support_source_id':manual['source_id'],'support_quote':MAPPING}],
            'repair_steps':[{'instruction':'检查散热器外部清洁情况。','basis':'ai_inspection_suggestion','source_id':None,'source_quote':''}],
            'missing_evidence':['冷却系统实测温度']})
    store._write(current)
    return current


@pytest.fixture
def inspection_record(record):
    # A normalized cached inspection row must not become a preparation candidate
    # merely because it still carries a real catalog part number.
    part=record['advice']['parts'][0]
    part.update(support='catalog_only',support_source_id=None,support_quote='',reason='仅图册冷却分类相关，仍需核对实际故障点')
    normalized=ai.normalize_cached_advice(record)
    assert normalized['advice']['parts']==[]
    assert normalized['advice']['inspection_targets'][0]['part_number']=='800160318'
    store._write(normalized)
    return normalized


def load(record):return lambda:store.read(record['research_id'])


def identity(record):return {key:record[key] for key in ('machine_id','dataset_id','vin')}


@pytest.fixture
def client(record,monkeypatch):
    # Exercise the existing checked() source verifier without any live fleet data.
    monkeypatch.setattr(routes.research,'_verify_machine',lambda *a:None)
    app=FastAPI();app.include_router(routes.router)
    return TestClient(app,base_url=ORIGIN)


def test_preview_rebuilds_real_parts_retains_source_and_never_sends(record):
    result=email.preview(store.read(record['research_id']))
    assert result['status']=='preview' and result['notification_status']=='not_configured'
    assert result['configured'] is result['can_send'] is False
    assert result['body']==result['text']
    assert result['part_numbers']==['800160318']
    assert 'FAKE-999' not in json.dumps(result)
    for text in ('模拟','不代表','更换条件','尚未确认损坏','2026-09-15T14:55:16','图示位置 4','冷却系统'):
        assert text in result['body']
    assert not email.STATE_DB.exists()


def test_same_fault_manual_mapping_enters_mail_only_as_conditional_candidate(record):
    checked=ai.normalize_cached_advice(record)
    part=checked['advice']['parts'][0]
    assert part['evidence_level']=='conditional_candidate'
    assert part['status']=='candidate_requires_inspection'
    assert part['support_quote']==MAPPING
    assert part['support_source_id']==store.evidence(record)['manuals'][0]['source_id']
    draft=email.preview(checked)
    assert draft['part_numbers']==['800160318']
    for value in ('须先完成现场检查并确认适配','不构成确诊或采购下单','尚未确认损坏',
                  '仅确认叶片破损且核对配置后考虑更换'):
        assert value in draft['body']


def test_inspection_targets_never_enter_mail_part_numbers(record):
    page=store.PageCapture(source='xgss_rendered_page',source_url='https://xgss.xcmg.com/',vin=VIN,
        title='合成其他冷却部件',items=[{'name':'散热器','part_number':'TEST-INSPECT-002'}],
        manual_sections=[],coverage='rendered_content_only')
    updated=store.append(record['research_id'],page)
    radiator=store.evidence(updated)['parts'][-1]
    updated.update(advice=record['advice'],analysis_revision=updated['revision'])
    updated['advice']['parts'].append({'source_id':radiator['source_id'],'reason':'只有图册分类关联，待核对实际故障点',
        'replacement_condition':'检查冷却回路并核实散热器实际状况','fault_relation':'direct','support':'catalog_only'})
    checked=ai.normalize_cached_advice(updated)
    assert checked['advice']['inspection_targets'][0]['part_number']=='TEST-INSPECT-002'
    draft=email.preview(checked)
    assert draft['part_numbers']==['800160318']
    assert 'TEST-INSPECT-002' not in json.dumps(draft)


@pytest.mark.parametrize('route',['email-preview','email-status','email-send'])
def test_inspection_only_fault_is_rejected_by_all_mail_routes(client,inspection_record,monkeypatch,route):
    configure(monkeypatch)
    payload=identity(inspection_record)
    if route=='email-send':payload['preview_hash']='a'*64
    response=client.post(f"/assistant/xgss/research/{inspection_record['research_id']}/{route}",
        json=payload,headers={'Origin':ORIGIN})
    assert response.status_code==409
    assert '备件候选' in response.text
    assert not email.STATE_DB.exists()


@pytest.mark.parametrize('quality',[None,'fault-causality-0'])
@pytest.mark.parametrize('operation',['preview','status','send'])
def test_legacy_fault_advice_cannot_preview_or_send_email(record,monkeypatch,quality,operation):
    configure(monkeypatch)
    draft=email.preview(record)
    if quality is None:record.pop('advice_quality_version')
    else:record['advice_quality_version']=quality
    store._write(record)
    with pytest.raises(email.EmailError,match='重新分析') as error:
        if operation=='send':email.send(load(record),draft['preview_hash'])
        else:getattr(email,operation)(record)
    assert error.value.status_code==409
    assert not email.STATE_DB.exists()


def test_manual_mapping_for_another_fault_cannot_enter_preparation_mail(record):
    record['symptom']='模拟 SPN 110 / FMI 0 冷却液温升。'
    assert ai.normalize_cached_advice(record)['advice']['parts']==[]
    with pytest.raises(email.EmailError,match='备件候选') as error:email.preview(record)
    assert error.value.status_code==409


@pytest.mark.parametrize('source',['simulation','trackunit_page'])
@pytest.mark.parametrize('change',['stale','missing','unread_part','invented_prose'])
def test_invalid_or_stale_advice_cannot_be_previewed(record,change,source):
    record['symptom_source']=source
    if change=='stale':record['analysis_revision']-=1
    elif change=='missing':record.pop('advice')
    elif change=='unread_part':record['advice']['parts'][0]['source_id']='not-read'
    else:record['advice']['summary']='请更换料号 FAKE-999。'
    with pytest.raises(email.EmailError):email.preview(record)


def test_no_urls_credentials_or_unrelated_record_fields_in_preview(record):
    record['symptom']+=' https://xgss.xcmg.com/?token=PRIVATE_SIGNED password=PRIVATE_PASS'
    record['advice']['summary']+=' https://xgss.xcmg.com/?signature=PRIVATE_SIGNED'
    record['secret']='PRIVATE_SECRET'
    result=email.preview(record)
    serialized=json.dumps(result)
    for secret in ('PRIVATE_SIGNED','PRIVATE_PASS','PRIVATE_SECRET','https://xgss'):
        assert secret not in serialized


def test_manual_content_is_reconstructed_and_labelled(record):
    page=store.PageCapture(source='xgss_rendered_page',source_url='https://xgss.xcmg.com/',vin=VIN,
        title='维修手册',items=[],manual_sections=[{'title':'检查条件','text':'系统冷却后才可检查。禁止热机打开加注盖。'}],coverage='rendered_content_only')
    updated=store.append(record['research_id'],page)
    manual=store.evidence(updated)['manuals'][-1]
    updated.update(advice=record['advice'],analysis_revision=updated['revision'])
    updated['advice']['repair_steps']=[{'instruction':'错误的缓存指令','basis':'manual_excerpt','source_id':manual['source_id'],'source_quote':'系统冷却后才可检查。'}]
    result=email.preview(updated)
    assert '已读取维修原文' in result['body'] and '禁止热机打开加注盖。' in result['body']
    assert '错误的缓存指令' not in result['body']


def test_wrong_device_version_and_vin_are_rejected_by_route(client,record):
    url=f"/assistant/xgss/research/{record['research_id']}/email-preview"
    for field,value in [('machine_id','other'),('dataset_id','b'*64),('vin','XUGOTHER000000001')]:
        response=client.post(url,json={**identity(record),field:value})
        assert response.status_code==422
    good=client.post(url,json=identity(record))
    assert good.status_code==200 and good.headers['cache-control']=='no-store'


def test_sends_only_when_configured_and_preview_matches(record,monkeypatch):
    unconfigured=email.preview(record)
    assert email.send(load(record),unconfigured['preview_hash'])['status']=='not_configured'
    configure(monkeypatch)
    with pytest.raises(email.EmailError) as error:email.send(load(record),unconfigured['preview_hash'])
    assert error.value.status_code==409
    draft=email.preview(record)
    calls=[]
    monkeypatch.setattr(email,'_deliver',lambda config,body:calls.append(body) or 'sent')
    first=email.send(load(record),draft['preview_hash'])
    second=email.send(load(record),draft['preview_hash'])
    assert first['status']==second['status']=='sent' and len(calls)==1
    assert first['sent_at'] and first['can_send'] is False
    assert 'fixture-password' not in json.dumps(email.preview(record))


def test_reanalysis_with_same_source_revision_gets_new_delivery_identity(record,monkeypatch):
    configure(monkeypatch);deliveries=[]
    monkeypatch.setattr(email,'_deliver',lambda config,body:deliveries.append(body) or 'sent')
    first=email.preview(record)
    assert email.send(load(record),first['preview_hash'])['status']=='sent'
    updated=store.read(record['research_id'])
    updated.update(analyzed_at='2026-09-23T12:00:00+00:00')
    updated['advice']['summary']='模拟温升的新分析仍须检查风扇叶片与转动情况，尚未确认损坏。'
    store._write(updated)
    second=email.preview(updated)
    assert second['analysis_revision']==first['analysis_revision']
    assert second['preview_hash']!=first['preview_hash']
    assert second['notification_status']=='ready' and second['can_send'] is True
    assert email.send(load(updated),second['preview_hash'])['status']=='sent'
    assert email.send(load(updated),second['preview_hash'])['status']=='sent'
    assert len(deliveries)==2


def test_legacy_revision_only_delivery_key_does_not_block_current_policy(record,monkeypatch):
    configure(monkeypatch)
    config=email.configuration()
    legacy_key=email._digest({'research_id':record['research_id'],'revision':record['analysis_revision'],
        'destination':{'sender':config.sender,'recipients':config.recipients}})
    with email._database() as db:
        db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?,?)',
            (legacy_key,'old-preview','sent','previous-process','2026-09-21T00:00:00+00:00','2026-09-21T00:00:00+00:00'))
    draft=email.preview(record)
    assert draft['notification_status']=='ready' and draft['can_send'] is True


def test_new_source_revision_and_changed_recipient_configuration_require_new_preview(record,monkeypatch):
    configure(monkeypatch)
    draft=email.preview(record)
    configure(monkeypatch,'other@example.test')
    with pytest.raises(email.EmailError):email.send(load(record),draft['preview_hash'])
    fresh=email.preview(record)
    changed=store.read(record['research_id']);changed['revision']+=1;store._write(changed)
    with pytest.raises(email.EmailError) as error:email.send(load(record),fresh['preview_hash'])
    assert error.value.status_code==409


def test_concurrent_sends_submit_once(record,monkeypatch):
    configure(monkeypatch);draft=email.preview(record)
    entered,finish=Event(),Event();calls=[]
    def fake(config,body):
        calls.append(body);entered.set();assert finish.wait(5);return 'sent'
    monkeypatch.setattr(email,'_deliver',fake)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(email.send,load(record),draft['preview_hash'])
        assert entered.wait(5)
        second=pool.submit(email.send,load(record),draft['preview_hash']).result(5)
        assert second['status']=='sending' and second['can_send'] is False
        finish.set();assert first.result(5)['status']=='sent'
    assert len(calls)==1


def test_uncertain_and_interrupted_attempts_never_resend(record,monkeypatch):
    configure(monkeypatch);draft=email.preview(record);calls=[]
    monkeypatch.setattr(email,'_deliver',lambda *a:calls.append(1) or 'uncertain')
    assert email.send(load(record),draft['preview_hash'])['status']=='uncertain'
    assert email.send(load(record),draft['preview_hash'])['can_send'] is False
    assert len(calls)==1
    with email._database() as db:db.execute("UPDATE deliveries SET state='sending',owner='previous-process'")
    assert email.status(record)['status']=='uncertain'
    assert email.send(load(record),draft['preview_hash'])['status']=='uncertain'
    assert len(calls)==1


def test_failed_attempt_allows_explicit_retry(record,monkeypatch):
    configure(monkeypatch);draft=email.preview(record);outcomes=iter(['failed','sent'])
    monkeypatch.setattr(email,'_deliver',lambda *a:next(outcomes))
    assert email.send(load(record),draft['preview_hash'])['can_send'] is True
    assert email.send(load(record),draft['preview_hash'])['status']=='sent'


@pytest.mark.parametrize('phase,expected',[('login','failed'),('send_timeout','uncertain'),('refused','failed'),('partial','uncertain'),('ok','sent')])
def test_smtp_transport_tls_and_uncertain_outcomes(record,monkeypatch,phase,expected):
    configure(monkeypatch);events=[]
    class FakeSMTP:
        def __init__(self,*a,**kw):events.append('connect')
        def ehlo(self):events.append('ehlo')
        def starttls(self,**kw):events.append('tls')
        def login(self,*a):
            events.append('login')
            if phase=='login':raise smtplib.SMTPAuthenticationError(535,b'PRIVATE_CREDENTIAL')
        def send_message(self,message,**kwargs):
            events.append('send')
            assert kwargs['to_addrs']==['parts@example.test','service@example.test']
            assert 'fixture-password' not in message.as_string()
            if phase=='send_timeout':raise TimeoutError('PRIVATE_CREDENTIAL')
            if phase=='refused':raise smtplib.SMTPRecipientsRefused({})
            return {'service@example.test':(550,b'no')} if phase=='partial' else {}
        def quit(self):events.append('quit')
    monkeypatch.setattr(email.smtplib,'SMTP',FakeSMTP)
    result=email.send(load(record),email.preview(record)['preview_hash'])
    assert result['status']==expected
    assert events[:4]==['connect','ehlo','tls','ehlo']
    assert 'PRIVATE_CREDENTIAL' not in json.dumps(result)


@pytest.mark.parametrize('origin',[None,'null','https://attacker.example','http://localhost:8890','http://[invalid'])
def test_send_requires_same_local_origin(client,record,origin):
    draft=email.preview(record)
    headers={'Origin':origin} if origin else {}
    result=client.post(f"/assistant/xgss/research/{record['research_id']}/email-send",json={**identity(record),'preview_hash':draft['preview_hash']},headers=headers)
    assert result.status_code==403


def test_guarded_send_and_status_routes(client,record,monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(email,'_deliver',lambda *a:'sent')
    base=f"/assistant/xgss/research/{record['research_id']}"
    draft=client.post(base+'/email-preview',json=identity(record)).json()
    payload={**identity(record),'preview_hash':draft['preview_hash']}
    assert client.post(base+'/email-send',json={**payload,'recipients':['attacker@example.test']},headers={'Origin':ORIGIN}).status_code==422
    assert client.post(base+'/email-send',json=payload,headers={'Origin':ORIGIN,'Sec-Fetch-Site':'cross-site'}).status_code==403
    sent=client.post(base+'/email-send',json=payload,headers={'Origin':ORIGIN})
    assert sent.status_code==200 and sent.json()['status']=='sent'
    assert client.post(base+'/email-status',json=identity(record)).json()['status']=='sent'


def test_return_path_preserves_result_and_dataset(record):
    result=email.preview(record)
    link=urlsplit(result['return_path'])
    assert link.path=='/assistant-ui/'
    assert parse_qs(link.query)=={'research':[record['research_id']],'dataset':[DATASET]}
    assert link.fragment=='trackunit-asset='+record['machine_id']
    assert '外部收件人无法直接访问' in result['body']
    record['dataset_id']=None
    assert 'dataset' not in parse_qs(urlsplit(email.preview(record)['return_path']).query)


def test_database_errors_are_safe_and_never_claim_success(client,record,monkeypatch):
    def fail(*args):raise sqlite3.OperationalError('PRIVATE_STORAGE_DETAIL')
    monkeypatch.setattr(email,'_row',fail)
    response=client.post(f"/assistant/xgss/research/{record['research_id']}/email-status",json=identity(record))
    assert response.status_code==503
    assert 'PRIVATE_STORAGE_DETAIL' not in response.text


@pytest.fixture
def event_record(record):
    # Synthetic normalized event only. This is not a live-machine acceptance test.
    asset='00000000-0000-4000-8000-000000000001'
    source='00000000-0000-4000-8000-000000000002'
    event={'event_id':email.event_key(asset,source),'source_event_id':source,
           'machine_id':record['machine_id'],'trackunit_asset_id':asset,'vin':record['vin'],
           'code':'P0217','code_system':'j1939','spn':110,'fmi':15,'sa':0,
           'description':'Fixture cooling event','occurred_at':'2026-09-21T08:00:00+00:00',
           'event_time':'2026-09-21T08:05:00+00:00','cleared_at':None,
           'status':'OPEN','severity':'WARNING','source':'trackunit_asset_event_v3',
           'observed_at':'2026-09-21T09:00:00+00:00'}
    record.update(symptom_source='trackunit_event',symptom='后端冻结的故障事件背景',fault_event_id=event['event_id'],
                  fault_context={'trackunit_event':event,'operator_supplement':'操作员补充待检查','manuals':[]})
    record['advice']['summary']='冷却故障事件需要核查，尚未确认风扇损坏。'
    return record


def test_frozen_trackunit_event_is_primary_background(event_record):
    result=email.preview(event_record)
    assert result['subject'].startswith('[Trackunit 故障事件]') and 'P0217' in result['subject']
    for value in ('P0217','j1939','SPN 110 / FMI 15','OPEN','2026-09-21T08:00:00',
                  '解除时间：未记录','2026-09-21T09:00:00',event_record['fault_event_id'],
                  'Trackunit Asset Event v3','人工补充（非接口上报）：操作员补充待检查'):
        assert value in result['body']
    assert '未载入可用故障事件' not in result['body']
    assert '现象来源：人工补充现象' not in result['body']


@pytest.mark.parametrize('resolved_marker',['status','cleared_at'])
def test_resolved_event_cannot_prepare_parts_from_historical_manual_mapping(event_record,resolved_marker):
    event=event_record['fault_context']['trackunit_event']
    if resolved_marker=='status':event['status']='RESOLVED'
    else:event['cleared_at']='2026-09-21T08:10:00+00:00'
    checked=ai.normalize_cached_advice(event_record)
    assert checked['advice']['parts']==[]
    assert checked['advice']['inspection_targets']
    with pytest.raises(email.EmailError,match='备件候选') as error:email.preview(event_record)
    assert error.value.status_code==409


@pytest.mark.parametrize('change',['machine','vin','event_id','missing','wrong_source'])
def test_invalid_frozen_event_cannot_enter_mail(event_record,change):
    event=event_record['fault_context']['trackunit_event']
    if change=='machine':event['machine_id']='another-machine'
    elif change=='vin':event['vin']='XUGOTHER000000001'
    elif change=='event_id':event_record['fault_event_id']='a'*64
    elif change=='missing':event_record['fault_context'].pop('trackunit_event')
    else:event_record['symptom_source']='operator_report'
    with pytest.raises(email.EmailError):email.preview(event_record)


def test_user_question_does_not_become_actual_fault(record):
    record.update(symptom_source='user_question',symptom='SPN 110 / FMI 15 涉及的这个部件需要如何检查？')
    result=email.preview(record)
    assert '用户咨询问题' in result['subject']
    assert '不代表已发生故障或现场测量' in result['body']


def test_accepted_mail_with_failed_state_write_blocks_resend(record,monkeypatch):
    configure(monkeypatch);draft=email.preview(record);deliveries=[]
    original=email._database;opens=0
    def fail_second_open():
        nonlocal opens
        opens+=1
        if opens==2:raise sqlite3.OperationalError('PRIVATE_WRITE_ERROR')
        return original()
    monkeypatch.setattr(email,'_database',fail_second_open)
    monkeypatch.setattr(email,'_deliver',lambda *a:deliveries.append(1) or 'sent')
    with pytest.raises(email.EmailError) as failure:email.send(load(record),draft['preview_hash'])
    assert failure.value.status_code==503 and 'PRIVATE_WRITE_ERROR' not in str(failure.value)
    assert email.status(record)['status']=='uncertain'
    assert email.send(load(record),draft['preview_hash'])['can_send'] is False
    assert len(deliveries)==1


def test_ssl_transport_and_secret_free_configuration_repr(record,monkeypatch):
    configure(monkeypatch);monkeypatch.setenv(email.PREFIX+'SMTP_SECURITY','ssl');events=[]
    class FakeSSL:
        def __init__(self,host,port,timeout,context):
            assert host=='smtp.example.test' and port==465 and timeout==20
            assert context.check_hostname
            events.append('ssl')
        def login(self,*args):events.append('login')
        def send_message(self,*args,**kwargs):events.append('send');return {}
        def quit(self):events.append('quit')
    monkeypatch.setattr(email.smtplib,'SMTP_SSL',FakeSSL)
    assert 'fixture-password' not in repr(email.configuration())
    assert email.send(load(record),email.preview(record)['preview_hash'])['status']=='sent'
    assert events==['ssl','login','send','quit']


def test_mail_display_translates_known_labels_preserving_values_conditions_and_record(record):
    record['machine_context']['source']='imported_user_supplied'
    record['advice']['summary']='模拟排查：fault_coverage=unknown；累计工时 419.73 h，也不能补造温度、压力或维修周期。'
    record['advice']['repair_steps'][0]['instruction']='检查前须待系统冷却；禁止热机打开加注盖。'
    record['advice']['parts'][0]['replacement_condition']='仅在现场确认风扇损坏且核对同机适配后更换。'
    record['advice']['missing_evidence']=['machine_context 中 observed_at 对应记录超过 24 h；缺少冷却液实测温度。']
    before=json.dumps(record,ensure_ascii=False,sort_keys=True)
    body=email.preview(record)['body']
    for value in ('已载入Trackunit设备数据','故障记录覆盖范围未知','尚无温度、压力和维修周期等实测依据',
                  '模拟排查','419.73 h','24 h','800160318','禁止热机打开加注盖',
                  '仅在现场确认风扇损坏且核对同机适配后更换'):
        assert value in body
    for value in ('imported_user_supplied','fault_coverage=unknown','不能补造温度','machine_context','observed_at'):
        assert value not in body
    assert json.dumps(record,ensure_ascii=False,sort_keys=True)==before


def test_known_prose_cleanup_keeps_realtime_qualifier_and_unknown_prohibitions():
    value='不能补造温度、压力、维修周期或实时测量；禁止超过 2000 rpm；不能补造未知字段。'
    assert email._display_text(value)=='尚无温度、压力、维修周期或实时测量依据；禁止超过 2000 rpm；不能补造未知字段。'


def test_official_manual_and_operator_words_bypass_prose_translation(record):
    original='保留原文标签 fault_coverage=unknown；禁止热机打开加注盖。'
    page=store.PageCapture(source='xgss_rendered_page',source_url='https://xgss.xcmg.com/',vin=VIN,
        title='维修手册',items=[],manual_sections=[{'title':'原文条件','text':original}],coverage='rendered_content_only')
    updated=store.append(record['research_id'],page);manual=store.evidence(updated)['manuals'][-1]
    updated.update(advice=record['advice'],analysis_revision=updated['revision'],symptom='SPN 110 / FMI 15；人工保留描述 imported_user_supplied。')
    updated['advice']['repair_steps']=[{'instruction':'缓存文字','basis':'manual_excerpt','source_id':manual['source_id'],'source_quote':original}]
    body=email.preview(updated)['body']
    assert original in body and '人工保留描述 imported_user_supplied。' in body


@pytest.mark.parametrize('model',['Data not available','unknown','未提供','未知'])
def test_mail_unknown_model_heading_is_actionable_without_guessing_machine(record,model):
    record['model']=model
    preview=email.preview(record)
    assert '机型待确认' in preview['subject'] and '机型：机型待确认' in preview['body']
    assert 'Data not available' not in preview['subject']


@pytest.mark.parametrize('custom',[False,True])
def test_maintenance_mail_simplifies_only_the_exact_system_question(record,custom):
    question=('请检查空气滤芯，上次更换是在 300 h；service_history_status=unknown 是我的原话。'
              if custom else email.maintenance.default_question())
    record.update(analysis_mode='maintenance',symptom_source='user_question',symptom=question)
    record['advice']={'summary':'按累计工时 419.73 h 核对保养记录，周期尚未确认。',
        'parts':[],'repair_steps':[],
        'missing_evidence':['上次保养记录（service_history_status=unknown）；工时采样已超过 24 h。']}
    before=json.dumps(record,ensure_ascii=False,sort_keys=True)
    preview=email.preview(record)
    assert preview['subject'].startswith('[AI 工时保养]')
    assert '故障背景' not in preview['body'] and '不是到期通知' in preview['body']
    if custom:assert question in preview['body']
    else:
        assert question not in preview['body']
        assert '按机型与已载入工时筛选保养件和易损件。' in preview['body']
    assert '上次保养记录尚未核实' in preview['body'] and '24 h' in preview['body'] and '419.73 h' in preview['body']
    assert json.dumps(record,ensure_ascii=False,sort_keys=True)==before


def test_maintenance_label_cleanup_preserves_conditions_numbers_and_unknown_tags():
    assert email._model_label(None)=='机型待确认'
    assert email._model_label('XE80U')=='XE80U'
    text='`service_history_status=unknown`；仅确认堵塞后考虑更换；采样 419.73 h；custom_status=unknown。'
    assert email._display_text(text)=='上次保养记录尚未核实；仅确认堵塞后考虑更换；采样 419.73 h；custom_status=unknown。'



def test_page_visible_fault_preview_preserves_scope_and_real_parts(record):
    observation='Trackunit Events 页可见 SPN 110/FMI 15 (SA 0)；冷却液温度偏高。'
    record.update(symptom_source='trackunit_page',symptom=observation)
    before=json.dumps(record,ensure_ascii=False,sort_keys=True)
    draft=email.preview(record)
    assert draft['subject'].startswith('[Trackunit 页面可见故障]')
    assert draft['part_numbers']==['800160318']
    assert draft['notification_status']=='not_configured' and draft['can_send'] is False
    for value in (observation,'仅覆盖已读取的页面内容','尚未通过故障 API 核验完整事件、状态与历史',
                  '不代表实时测量','须先完成现场检查并确认适配','图示位置 4','更换条件'):
        assert value in draft['body']
    for value in ('Trackunit Asset Event v3','现象来源：人工补充现象','未载入可用故障事件'):
        assert value not in draft['body']
    assert json.dumps(record,ensure_ascii=False,sort_keys=True)==before
    assert not email.STATE_DB.exists()


def test_page_visible_fault_preview_route_keeps_device_binding(client,record):
    record.update(symptom_source='trackunit_page',symptom='页面可见 SPN 110 / FMI 15 冷却液温度偏高故障卡片。')
    store._write(record)
    url=f"/assistant/xgss/research/{record['research_id']}/email-preview"
    response=client.post(url,json=identity(record))
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['part_numbers']==['800160318']
    for field,value in [('machine_id','other'),('dataset_id','b'*64),('vin','XUGOTHER000000001')]:
        assert client.post(url,json={**identity(record),field:value}).status_code==422


def test_page_visible_fault_cannot_relabel_an_api_event(event_record):
    event_record['symptom_source']='trackunit_page'
    with pytest.raises(email.EmailError,match='故障事件与现象来源不一致'):
        email.preview(event_record)
