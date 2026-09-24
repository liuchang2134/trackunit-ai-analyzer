"""Source-grounded mail previews and explicit SMTP delivery; never auto-send.

SMTP credentials are read only at request time from RESEARCH_EMAIL_* variables.
The delivery ledger contains hashes/status, never credentials, message bodies or URLs.
"""
from contextlib import contextmanager
from dataclasses import dataclass,field
from datetime import datetime,timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote,urlencode
import hashlib
import json
import os
import re
import smtplib
import sqlite3
import ssl
import threading
import uuid

from app import xgss_research_ai as ai,xgss_research_store as store
from app import maintenance_recommendations as maintenance
from app.trackunit_events import FaultEvent,event_key

STATE_DB=Path(__file__).resolve().parents[1]/'data/local/research-email.sqlite3'
LOCK=threading.RLock()
IN_FLIGHT=set()
PROCESS_ID=uuid.uuid4().hex
PREFIX='RESEARCH_EMAIL_'


class EmailError(ValueError):
    def __init__(self,message,status_code=422):
        super().__init__(message)
        self.status_code=status_code


@dataclass(frozen=True)
class Configuration:
    host:str
    port:int
    security:str
    username:str
    password:str=field(repr=False)
    sender:str
    recipients:tuple[str,...]


def _address(value):
    return bool(re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',value))


def configuration():
    """Missing or invalid settings never imply a usable sending channel."""
    values={key:os.getenv(PREFIX+key,'') for key in
            ('SMTP_HOST','SMTP_PORT','SMTP_SECURITY','SMTP_USERNAME','SMTP_PASSWORD','FROM','TO')}
    host=values['SMTP_HOST'].strip()
    security=values['SMTP_SECURITY'].strip().lower() or 'starttls'
    sender=values['FROM'].strip()
    recipients=tuple(sorted(set(x.strip() for x in values['TO'].split(',') if x.strip())))
    try:port=int(values['SMTP_PORT'] or ('465' if security=='ssl' else '587'))
    except ValueError:return None
    if (not re.fullmatch(r'[A-Za-z0-9.-]+',host) or not 1<=port<=65535 or
        security not in ('starttls','ssl') or not values['SMTP_USERNAME'] or not values['SMTP_PASSWORD'] or
        not _address(sender) or not 1<=len(recipients)<=20 or not all(_address(x) for x in recipients)):
        return None
    if any('\r' in value or '\n' in value for value in values.values()):return None
    return Configuration(host,port,security,values['SMTP_USERNAME'],values['SMTP_PASSWORD'],sender,recipients)


def _digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _text(value,default='未记录'):
    if value is None or value=='':return default
    text=str(value)
    text=re.sub(r'(?i)(?:https?://|https?%3a%2f%2f)[^\s<>]+','[页面地址已省略]',text)
    text=re.sub(r'(?i)\b[\w-]*(?:token|password|passwd|secret|api[_-]?key|authorization|cookie|signature|session[_-]?id)\s*[:=]\s*[^\s,;]+','[认证信息已省略]',text)
    text=re.sub(r'(?i)\bBearer\s+[^\s,;]+','[认证信息已省略]',text)
    return ' '.join(text.split()) or default


def _display_text(value):
    """Translate known internal labels in presentation only, never source quotes."""
    text=_text(value)
    text=re.sub(r'`?fault_coverage\s*=\s*unknown`?','故障记录覆盖范围未知',text)
    text=re.sub(r'`?service_history_status\s*=\s*unknown`?','上次保养记录尚未核实',text)
    labels={'imported_user_supplied':'已载入Trackunit设备数据','trackunit_cache':'Trackunit 本地缓存数据',
            'fault_coverage':'故障记录覆盖范围','machine_context':'设备数据快照','quantity':'图示用量',
            'observed_at':'采样时间','age_hours':'采样距今小时数','stale_after_24h':'历史采样标记',
            'source_id':'资料引用','manual_excerpt':'手册原文','ai_inspection_suggestion':'AI 检查建议'}
    text=re.sub(r'(?<![A-Za-z0-9_])('+ '|'.join(labels) +r')(?![A-Za-z0-9_])',lambda match:labels[match.group()],text)
    # Exact known model-rule echoes only. Keep numbers, conditions and unrelated
    # prohibitions; official excerpts and user-supplied observations bypass this.
    text=re.sub(r'(?:也)?不能补造温度、压力、维修周期或实时测量','尚无温度、压力、维修周期或实时测量依据',text)
    text=re.sub(r'(?:也)?不能补造温度、压力(?:和|或)维修周期','尚无温度、压力和维修周期等实测依据',text)
    return text


def _model_label(value):
    text=_text(value,'')
    return ('机型待确认' if text.casefold() in ('','data not available','unknown','未提供','未知','型号未知','机型未提供')
            else text)


def _source(row):
    path=' / '.join(_text(x) for x in row.get('assembly_path',[]))
    result=_text(row.get('page_title'))+((' / '+path) if path else '')
    if row.get('pdf_pages'):result+=' / 页码 '+_text(row['pdf_pages'])
    return result+'；资料时间：'+_text(row.get('captured_at'))


def _event(record):
    raw=(record.get('fault_context') or {}).get('trackunit_event')
    if record.get('symptom_source')!='trackunit_event':
        if raw or record.get('fault_event_id'):
            raise EmailError('故障事件与现象来源不一致，不能生成邮件。')
        return None
    event=FaultEvent.model_validate(raw).model_dump()
    if (event['machine_id']!=record['machine_id'] or event['vin']!=record['vin'] or
        event['event_id']!=record.get('fault_event_id') or
        event['event_id']!=event_key(str(uuid.UUID(event['trackunit_asset_id'])),str(uuid.UUID(event['source_event_id'])))):
        raise EmailError('故障事件与当前设备或本次结果不一致。')
    return event


def _body(record,sources):
    advice=record['advice']
    maintenance_mode=record.get('analysis_mode')=='maintenance'
    event=_event(record)
    source=record.get('symptom_source')
    labels={'simulation':'模拟现象','operator_report':'人工补充现象',
            'user_question':'用户咨询问题','trackunit_event':'Trackunit 故障事件',
            'trackunit_page':'Trackunit 页面可见故障'}
    if source not in labels:
        raise EmailError('现象来源不完整，不能生成备件准备邮件。')
    label=labels[source]
    if maintenance_mode:label='AI 工时保养'
    event_code=(_text(event.get('code'),'') or f"SPN {_text(event.get('spn'))} / FMI {_text(event.get('fmi'))}") if event else ''
    subject=f"[{label}] {_model_label(record.get('model'))} {event_code+' ' if event_code else ''}备件准备建议 · 结果版本 {record['analysis_revision']}"
    lines=['设备与结果',f"机型：{_model_label(record.get('model'))}",f"VIN/PIN：{_text(record['vin'])}",
           f"设备编号：{_text(record['machine_id'])}",f"排查编号：{record['research_id']}",
           f"结果版本：{record['analysis_revision']}；分析时间：{_text(record.get('analyzed_at'))}",
           '', '保养依据' if maintenance_mode else '故障背景',f"任务来源：{label}" if maintenance_mode else f"现象来源：{label}"]
    if event:
        lines += [f"事件编号：{event['event_id']}；原始事件编号：{event['source_event_id']}",
                  f"故障码：{_text(event.get('code'))}；编码体系：{_text(event['code_system'])}",
                  f"SPN {_text(event.get('spn'))} / FMI {_text(event.get('fmi'))}；SA {_text(event.get('sa'))}",
                  f"发生时间：{_text(event['occurred_at'])}；解除时间：{_text(event.get('cleared_at'))}",
                  f"事件时间：{_text(event['event_time'])}；事件状态：{event['status']}；等级：{_text(event.get('severity'))}",
                  f"事件描述：{_text(event.get('description'))}",
                  f"出处：Trackunit Asset Event v3；采集时间：{_text(event['observed_at'])}；状态对应所读取的事件记录。"]
        supplement=(record.get('fault_context') or {}).get('operator_supplement')
        if supplement:lines.append('人工补充（非接口上报）：'+_text(supplement))
    else:
        question=record.get('symptom')
        if maintenance_mode and isinstance(question,str) and question.strip()==maintenance.default_question():
            lines.append('按机型与已载入工时筛选保养件和易损件。')
        else:lines.append(_text(question))
        if source=='trackunit_page':
            lines.append('出处：Trackunit Events 页可见故障卡片；仅覆盖已读取的页面内容，尚未通过故障 API 核验完整事件、状态与历史，不代表实时测量。')
        if source=='simulation':lines.append('此现象为模拟输入，不代表该设备已发生实际故障。')
        if source=='user_question':lines.append('以上为保养咨询，不代表已发生故障或已达到更换期限。' if maintenance_mode else '以上为用户咨询问题，不代表已发生故障或现场测量。')
    context=record.get('machine_context') or {}
    faults=context.get('faults') or []
    if not event and not maintenance_mode:
        if faults:
            lines.append('已载入同机故障记录（状态对应记录时间）：')
            for fault in faults:
                lines.append(f"- 故障码 {_text(fault.get('fault_code'))}；SPN {_text(fault.get('spn'))} / FMI {_text(fault.get('fmi'))}；发生时间 {_text(fault.get('occurred_at'))}；状态 {_text(fault.get('status'))}")
        elif source!='trackunit_page':
            lines.append('未载入可用故障事件；不据此判断设备无故障。')
    for key in ('manual_fault','engineering_fault'):
        fault=record.get(key)
        if fault:
            origin='明确标注的测试事件' if fault.get('source')=='test' else '人工补充故障码'
            lines.append(f"{origin}：{_text(fault.get('code'))}；适用配置：{_text(fault.get('configuration') or fault.get('version'))}。不代表 Trackunit 已上传此故障。")
    lines+=['','采样依据',f"数据来源：{_display_text(context.get('source'))}；最近记录：{_text(context.get('last_sample_at'))}",
            f"有效采样：{_text(context.get('sample_count'))} 条；仅为已载入快照。"]
    for key,label in (('operating_hours','累计工时'),('idle_hours','累计怠速'),('fuel_remaining_percent','燃油余量')):
        metric=(context.get('metrics') or {}).get(key) or {}
        if metric.get('value') is not None:
            lines.append(f"- {label}：{_text(metric['value'])} {_text(metric.get('unit'),'')}；采样时间：{_text(metric.get('observed_at'))}")
    if maintenance_mode:
        lines+=['上次保养记录和适用周期尚未核实；当前为 AI 检查与备件准备建议，不是到期通知。']
    lines+=['','AI 保养与易损件建议' if maintenance_mode else '可能原因与维修方向',_display_text(advice['summary'])]
    manual_by_id={row['source_id']:row for row in sources['manuals']}
    for index,step in enumerate(advice['repair_steps'],1):
        official=step['basis']=='manual_excerpt'
        lines.append(f"{index}. {'已读取维修原文' if official else 'AI 检查建议'}：{_text(step['instruction']) if official else _display_text(step['instruction'])}")
        if official:lines.append('   出处：'+_source(manual_by_id[step['source_id']]))
    if not sources['manuals']:
        lines.append('本次没有维修手册正文；以上为 AI 检查方向，具体拆装步骤与参数须核对适用手册。')
    lines+=['','条件性备件准备清单','以下条目须先完成现场检查并确认适配，不构成确诊或采购下单；图册用量不是采购数量。']
    real_parts={row['source_id']:row for row in sources['parts']}
    numbers=[]
    for index,part in enumerate(advice['parts'],1):
        source=real_parts.get(part['source_id'])
        if not source or source['part_number']!=part.get('part_number'):
            raise EmailError('备件料号未通过实际资料校验。')
        numbers.append(source['part_number'])
        lines.append(f"{index}. {_text(source['name'])}；料号 {source['part_number']}；图示位置 {_text(source.get('figure_ref'))}")
        if maintenance_mode:lines.append('   类别：'+{'maintenance':'保养件','wear':'易损件'}[part['part_role']])
        lines.append('   准备理由：'+_display_text(part['reason']))
        lines.append('   更换条件：'+_display_text(part['replacement_condition']))
        lines.append('   出处：'+_source(source))
    if not numbers:lines.append('当前无经实际图册核验的备件候选；未生成订购料号。')
    if advice.get('missing_evidence'):
        lines+=['','待补充证据']+['- '+_display_text(item) for item in advice['missing_evidence']]
    query={'research':record['research_id']}
    if record.get('dataset_id'):query['dataset']=record['dataset_id']
    path='/assistant-ui/?'+urlencode(query)+'#trackunit-asset='+quote(record['machine_id'],safe='')
    # This is an actual local route, not a fabricated external or authenticated URL.
    lines+=['','返回本次结果（本机路径）：'+path,
            '需在运行本地服务的电脑打开此路径；外部收件人无法直接访问本机工作台。',
            '核对以上排查编号与结果版本后继续处理。']
    return subject,'\n'.join(lines),numbers,path


def _prepare(record,config):
    if not record.get('advice'):
        raise EmailError('尚无有效 AI 结果，不能生成备件准备邮件。',409)
    if (type(record.get('revision')) is not int or type(record.get('analysis_revision')) is not int or
        record.get('analysis_revision')!=record['revision']):
        raise EmailError('资料已更新，当前 AI 结果已过期；请完成本次分析后重新预览。',409)
    try:
        checked=ai.normalize_cached_advice(record)
        if not checked.get('advice'):
            raise EmailError('备件建议需要重新分析后再生成邮件。',409)
        if checked.get('analysis_mode')!='maintenance' and not checked['advice'].get('parts'):
            raise EmailError('当前没有已通过故障关联依据校验的备件候选，不能生成备件准备邮件。',409)
        sources=ai.research_evidence(checked)
        subject,body,numbers,path=_body(checked,sources)
    except EmailError:raise
    except (ValueError,KeyError,TypeError,AttributeError):
        raise EmailError('当前结果未通过来源校验，无法生成邮件。') from None
    destination={'sender':config.sender,'recipients':config.recipients} if config else None
    draft={'subject':subject,'body':body,'research_id':record['research_id'],
           'analysis_revision':record['analysis_revision'],'analyzed_at':_text(record.get('analyzed_at')),
           'part_numbers':numbers,'return_path':path}
    draft['preview_hash']=_digest({**draft,'destination':destination})
    # A new analysis can change the qualified candidates without changing the
    # captured-source revision. Only the identical preview shares send state.
    draft['_delivery_key']=_digest({'preview_hash':draft['preview_hash']})
    return draft


@contextmanager
def _database():
    STATE_DB.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(STATE_DB,timeout=10)
    db.row_factory=sqlite3.Row
    try:
        db.execute('CREATE TABLE IF NOT EXISTS deliveries (delivery_key TEXT PRIMARY KEY, preview_hash TEXT NOT NULL, state TEXT NOT NULL, owner TEXT NOT NULL, updated_at TEXT NOT NULL, sent_at TEXT)')
        yield db
        db.commit()
    finally:db.close()


def _row(key):
    if not STATE_DB.exists():return None
    with _database() as db:
        row=db.execute('SELECT * FROM deliveries WHERE delivery_key=?',(key,)).fetchone()
        return dict(row) if row else None


def _state(draft,config,row=None):
    state=row['state'] if row else ('ready' if config else 'not_configured')
    if state=='sending' and (row['owner']!=PROCESS_ID or draft['_delivery_key'] not in IN_FLIGHT):state='uncertain'
    messages={'not_configured':'发件账户或收件人尚未完整配置；邮件未发送。',
              'ready':'预览已就绪；点击发送后才会发送邮件。',
              'sending':'正在提交邮件，请勿重复发送。',
              'sent':'SMTP 服务器已接受邮件；该结果版本不会重复发送。',
              'failed':'邮件未被服务器接受，可核查配置后重试。',
              'uncertain':'发送结果未确认，请先核查发件箱或服务商记录；已禁止自动和重复发送。'}
    return {'status':state,'configured':config is not None,'can_send':config is not None and state in ('ready','failed'),
            'preview_hash':draft['preview_hash'],'message':messages[state],
            'recipients':list(config.recipients) if config else [],'sent_at':row.get('sent_at') if row else None}


def preview(record):
    config=configuration()
    draft=_prepare(record,config)
    state=_state(draft,config,_row(draft['_delivery_key']))
    return {**{key:value for key,value in draft.items() if not key.startswith('_')},**state,
            'status':'preview','notification_status':state['status'],'text':draft['body']}


def status(record):
    config=configuration()
    draft=_prepare(record,config)
    return _state(draft,config,_row(draft['_delivery_key']))


def _deliver(config,draft):
    message=EmailMessage()
    message['Subject']=draft['subject']
    message['From']=config.sender
    message['To']=', '.join(config.recipients)
    message['Date']=format_datetime(datetime.now(timezone.utc))
    message['Message-ID']=f"<{draft['_delivery_key']}@jilian.local>"
    message.set_content(draft['body'])
    client=None
    submission_started=False
    try:
        tls=ssl.create_default_context()
        if config.security=='ssl':client=smtplib.SMTP_SSL(config.host,config.port,timeout=20,context=tls)
        else:
            client=smtplib.SMTP(config.host,config.port,timeout=20)
            client.ehlo();client.starttls(context=tls);client.ehlo()
        client.login(config.username,config.password)
        submission_started=True
        refused=client.send_message(message,from_addr=config.sender,to_addrs=list(config.recipients))
        return 'uncertain' if refused else 'sent'
    except (smtplib.SMTPRecipientsRefused,smtplib.SMTPSenderRefused,smtplib.SMTPDataError):return 'failed'
    except Exception:
        # No server exception text may reveal credentials, addresses or URLs.
        return 'uncertain' if submission_started else 'failed'
    finally:
        if client is not None:
            try:client.quit()
            except Exception:pass


def send(load_record,preview_hash):
    """Called only by the guarded explicit-send route; load_record rechecks identity."""
    with LOCK,store.LOCK:
        config=configuration()
        draft=_prepare(load_record(),config)
        if preview_hash!=draft['preview_hash']:
            raise EmailError('邮件内容、资料或收件配置已变化，请重新预览后发送。',409)
        if config is None:return _state(draft,config)
        key=draft['_delivery_key']
        with _database() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT * FROM deliveries WHERE delivery_key=?',(key,)).fetchone()
            row=dict(existing) if existing else None
            if row and row['state'] in ('sent','sending','uncertain'):
                return _state(draft,config,row)
            now=datetime.now(timezone.utc).isoformat()
            db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?,NULL) ON CONFLICT(delivery_key) DO UPDATE SET preview_hash=excluded.preview_hash,state=excluded.state,owner=excluded.owner,updated_at=excluded.updated_at,sent_at=NULL',
                       (key,draft['preview_hash'],'sending',PROCESS_ID,now))
        IN_FLIGHT.add(key)
    try:
        outcome=_deliver(config,draft)
        now=datetime.now(timezone.utc).isoformat()
        with LOCK,_database() as db:
            db.execute('UPDATE deliveries SET state=?,updated_at=?,sent_at=? WHERE delivery_key=?',
                       (outcome,now,now if outcome=='sent' else None,key))
    except Exception:
        # If the ledger write fails after SMTP accepted data, do not allow retry.
        raise EmailError('发送结果暂时无法保存，请先核查服务商记录，勿重复发送。',503) from None
    finally:
        with LOCK:IN_FLIGHT.discard(key)
    return _state(draft,config,_row(key))
