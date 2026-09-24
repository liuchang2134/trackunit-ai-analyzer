"""Validated, allowlisted continuation of a completed local investigation.

The history hash is the authority; browser-supplied hypotheses and model summaries
are never used as operator observations. No credentials or source URLs are projected.
"""
import json
from app.investigation_history import read_investigation
from app.local_assistant import ManualFault, manual_fault_evidence
from app.manual_knowledge import EngineeringFault, ManualRecord, retrieve_manuals, engineering_fault_evidence
from app import trackunit_events


def _copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def manual_projection(raw):
    item=ManualRecord.model_validate(raw).model_dump()
    keys=('reference_id','title','model','configuration','version','pdf_pages','section','text')
    return {**{key:item[key] for key in keys},'source_id':item['reference_id'],
            'applicability':raw.get('applicability','model_reference_only'),
            'page_title':'本地手册 · '+item['title'],'captured_at':'本地资料，非 XGSS 采集',
            'assembly_path':[item['section']],'capture_id':None,'source_kind':'applicable_local_manual'}


def validate_fault_context(machine_model,manual_fault=None,engineering_fault=None):
    if manual_fault and engineering_fault:
        raise ValueError('一次排查不能同时使用 TV12U 协议和 XE55U 工程故障。')
    manual=ManualFault.model_validate(manual_fault) if manual_fault else None
    engineering=EngineeringFault.model_validate(engineering_fault) if engineering_fault else None
    context={'manual_fault':None,'engineering_fault':None,'manuals':[]}
    code=None
    if manual:
        evidence=manual_fault_evidence(manual,machine_model)
        fields=('method','code','observation_source','applicability','reference_id','model','version','limitations')
        context['manual_fault']={key:evidence[key] for key in fields if key in evidence}
        definition_fields=('code','description','display_prompt','display_rule_raw','display_text_raw',
                           'reminder_description','reminder_mode','can_id','byte_index','bit_index','source_sheet','source_row')
        context['manual_fault']['definition']={key:evidence['definition'][key] for key in definition_fields if key in evidence['definition']}
        code=manual.code
    if engineering:
        retrieval=retrieve_manuals(engineering,machine_model)
        context['engineering_fault']=engineering_fault_evidence(engineering,retrieval)
        context['manuals']=[manual_projection(item) for item in retrieval['records']]
        if engineering.configuration!='unknown' and retrieval['status']=='matched':
            code=engineering.code
    return {'manual_fault':manual.model_dump() if manual else None,
            'engineering_fault':engineering.model_dump() if engineering else None,
            'fault_context':context,'catalog_fault_code':code}


def load_handoff(source_report_id,machine_id,dataset_id,machine_model):
    saved=read_investigation(source_report_id)
    request,report=saved.get('request'),saved.get('report')
    if not isinstance(request,dict) or not isinstance(report,dict) or report.get('status')!='completed':
        raise ValueError('仅能继续已完成且可校验的分析报告。')
    if any(item.get('machine_id')!=machine_id or (item.get('dataset_id') or None)!=(dataset_id or None)
           for item in (request,report)):
        raise ValueError('原分析报告与当前设备或数据版本不一致。')
    question=request.get('question')
    if not isinstance(question,str) or not question.strip() or len(question)>3000:
        raise ValueError('原分析报告缺少可继续使用的原始问题。')
    faults=validate_fault_context(machine_model,request.get('manual_fault'),request.get('engineering_fault'))
    engineering=faults['engineering_fault']
    # Revalidate applicability against current model/configuration, but preserve
    # the original report's quoted version instead of silently replacing its text.
    manuals={}
    if engineering:
        for raw in report.get('manual_references',[]):
            item=ManualRecord.model_validate(raw)
            if (item.model!=machine_model.strip().upper() or engineering['code'] not in item.fault_codes or
                (engineering['configuration']!='unknown' and item.configuration!=engineering['configuration'])):
                raise ValueError('原报告手册与当前故障或已选配置不一致。')
            if report.get('evidence',{}).get(item.reference_id)!=raw:
                raise ValueError('原报告手册引用与保存的证据不一致。')
            projected=manual_projection(raw)
            projected['applicability']=faults['fault_context']['engineering_fault']['applicability']
            projected['page_title']='原分析引用手册 · '+item.title
            projected['captured_at']=report.get('generated_at') or '原报告未记录时间'
            projected['source_kind']='source_report_manual'
            manuals[item.reference_id]=projected
    hypotheses=[]
    for row in report.get('component_hypotheses',[])[:6]:
        if not isinstance(row,dict):
            continue
        refs=row.get('reference_ids',[])
        if not refs or not all(ref in manuals for ref in refs):
            continue
        checks=[]
        for check in row.get('checks',[])[:3]:
            if not isinstance(check,dict):
                continue
            check_refs=check.get('evidence_ids',[])
            quote=check.get('source_quote')
            if not isinstance(quote,str) or not quote.strip():
                continue
            ref=next((ref for ref in check_refs if ref in refs and ' '.join(quote.split()) in ' '.join(manuals[ref]['text'].split())),None)
            if ref:
                checks.append({'text':str(check.get('text',''))[:350],'reference_id':ref,'source_quote':quote})
        if checks:
            hypotheses.append({'component':str(row.get('component',''))[:120],
                'rationale':str(row.get('rationale',''))[:750],'reference_ids':list(refs),
                'search_terms':[term for term in row.get('search_terms',[])[:8] if isinstance(term,str) and 0<len(term)<=100],
                'checks':checks})
    valid_refs=set(manuals)
    if faults['manual_fault']:valid_refs.add('operator:manual-fault')
    if engineering:valid_refs.add('operator:engineering-fault')
    prior_directions=[]
    for candidate in report.get('parts_candidates',[])[:6]:
        name=candidate.get('name') if isinstance(candidate,dict) else None
        if isinstance(name,str) and name.strip() and name not in [item['component'] for item in prior_directions]:
            prior_directions.append({'component':name[:120],'search_terms':[name[:100]],'provenance':'prior_ai_inference'})
    prior_analysis={'summary':str(report.get('summary',''))[:1500],'provenance':'prior_ai_inference',
        'citations':[ref for ref in report.get('citations',[]) if isinstance(ref,str) and ref in report.get('evidence',{})],
        'citation_scope':'source_report_only_not_current_catalog','directions':prior_directions}
    context={'source_report_id':source_report_id,'prior_analysis':prior_analysis,'component_hypotheses':hypotheses,
             'citations':[ref for ref in report.get('citations',[]) if ref in valid_refs],
             'manuals':list(manuals.values())}
    # The frozen report's manual version owns a continued investigation.
    if engineering:faults['fault_context']['manuals']=list(manuals.values())
    return _copy({'symptom':question,'symptom_source':'simulation' if engineering and engineering['source']=='test' else 'user_question',
                  'source_report_id':source_report_id,'handoff_context':context,**faults})


def plan_context(body,machine_model):
    if getattr(body,'fault_event_id',None):
        if body.source_report_id or body.manual_fault or body.engineering_fault or body.symptom_source!='trackunit_event':
            raise ValueError('真实故障事件不能混入旧报告、测试故障或其他来源。')
        event=trackunit_events.load_event(body.fault_event_id,body.machine_id,body.dataset_id,body.vin)
        code=event['code'] or f"SPN {event['spn']} / FMI {event['fmi']}"
        symptom=f"Trackunit 已保存故障事件：{code}；发生时间 {event['occurred_at']}；记录状态 {event['status']}。"
        if event['description']:
            symptom+='事件描述：'+event['description'][:800]
        # Supplementary user text is not promoted into the provider's event body.
        context={'trackunit_event':event,'operator_supplement':body.symptom.strip(),
                 'manual_fault':None,'engineering_fault':None,'manuals':[]}
        # E4030 is the documented XGSS example. Other OEM codes and J1939 tuples
        # retain their raw form for AI; use the generic same-VIN catalog for them.
        catalog_code='E4030' if event['code']=='E4030' and event['code_system']=='oem_unspecified' and machine_model.upper()=='XE55U' else None
        return {'fault_event_id':event['event_id'],'symptom':symptom,'symptom_source':'trackunit_event',
                'source_report_id':None,'handoff_context':None,'manual_fault':None,'engineering_fault':None,
                'fault_context':context,'catalog_fault_code':catalog_code}
    if body.symptom_source=='trackunit_event':
        raise ValueError('真实故障来源必须关联已保存的同机事件。')
    if body.source_report_id:
        handoff=load_handoff(body.source_report_id,body.machine_id,body.dataset_id,machine_model)
        if body.symptom!=handoff['symptom'].strip() or body.symptom_source!=handoff['symptom_source']:
            raise ValueError('原问题或来源已更改，请作为新的资料排查开始。')
        for name in ('manual_fault','engineering_fault'):
            provided=getattr(body,name)
            if provided is not None and provided.model_dump()!=handoff[name]:
                raise ValueError('原报告的故障上下文已更改，请开始新的资料排查。')
        return handoff
    faults=validate_fault_context(machine_model,body.manual_fault,body.engineering_fault)
    if faults['engineering_fault'] and faults['engineering_fault']['source']=='test' and body.symptom_source!='simulation':
        raise ValueError('测试故障码必须保留模拟来源。')
    return {'source_report_id':None,'handoff_context':None,**faults}


def evidence(record,captured):
    """Add exact inherited manual sources, never inherited parts or part numbers."""
    result=_copy(captured)
    known={item['source_id'] for item in result['manuals']}
    for item in (record.get('fault_context') or {}).get('manuals',[]):
        if item['source_id'] not in known:
            result['manuals'].append(_copy(item));known.add(item['source_id'])
    if len(result['manuals'])>len(captured['manuals']):result['coverage']='captured_pages_and_applicable_manuals'
    return result
