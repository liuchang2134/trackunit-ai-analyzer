"""Same-VIN local evidence and user-authorized DeepSeek service analysis."""
import asyncio
import json
import threading
import logging
from typing import Literal
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import JSONResponse,StreamingResponse,Response
from pydantic import BaseModel,ConfigDict,Field,ValidationError,model_validator
from app import xgss_research_store as store
from app import xgss_research_images as images
from app.api.routes_xgss_context import _verify_machine,HEADERS
from app import xgss_research_ai as ai
from app import xgss_research_handoff as handoff_context
from app import xgss_auto_fault as auto_fault
from app.local_datasets import load_dataset
from app.services.machine_service import find_machine,find_telemetry,find_faults
from app.xgss_machine_context import build_context
from app.deepseek_client import DeepSeekError,InvestigationCancelled,cancellation_scope,reset_cancellation_scope

router=APIRouter(prefix='/assistant/xgss/research',tags=['XGSS research evidence'])


class Identity(BaseModel):
    model_config=ConfigDict(extra='forbid')
    machine_id:str=Field(min_length=1,max_length=200)
    dataset_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    vin:str=Field(pattern=r'^[A-Z0-9]{8,32}$')


class PlanRequest(Identity,ai.Symptom):
    automatic:bool=False
    analysis_mode:Literal['fault','maintenance']='fault'
    symptom:str=Field(default='',max_length=3000)
    fault_event_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    source_report_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    manual_fault:handoff_context.ManualFault|None=None
    engineering_fault:handoff_context.EngineeringFault|None=None

    @model_validator(mode='before')
    @classmethod
    def maintenance_question(cls,value):
        if isinstance(value,dict) and value.get('analysis_mode')=='maintenance' and value.get('symptom_source')=='user_question':
            symptom=value.get('symptom','')
            if isinstance(symptom,str) and not symptom.strip():
                return {**value,'symptom':ai.maintenance.default_question()}
        return value


class HandoffRequest(Identity):
    source_report_id:str=Field(pattern=r'^[a-f0-9]{64}$')


class ActivateRequest(Identity):
    expected_research_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')


@router.post('/handoff')
def handoff(body:HandoffRequest):
    _verify_machine(body.machine_id,body.dataset_id,body.vin)
    dataset=load_dataset(body.dataset_id) if body.dataset_id else None
    machine=dataset.machine if dataset else find_machine(body.machine_id)
    try:
        return JSONResponse(handoff_context.load_handoff(body.source_report_id,body.machine_id,body.dataset_id,machine.model),headers=HEADERS)
    except (ValueError,KeyError,TypeError):
        raise HTTPException(422,'原分析不能接续，请核对设备、数据版本和故障适用范围。',headers=HEADERS) from None


def model_stream(request,call,message):
    cancelled=threading.Event()
    def worker():
        token=cancellation_scope(cancelled.is_set)
        try:return call()
        finally:reset_cancellation_scope(token)
    def event(value):return 'data: '+json.dumps(value,ensure_ascii=False)+'\n\n'
    async def stream():
        task=None
        try:
            yield event({'type':'progress','message':message})
            task=asyncio.create_task(asyncio.to_thread(worker))
            while not task.done():
                if await request.is_disconnected():cancelled.set();return
                await asyncio.wait({task},timeout=1)
                if not task.done():yield ': heartbeat\n\n'
            record=await task
            if not cancelled.is_set():yield event({'type':'result','record':{**record,'evidence':ai.research_evidence(record)}})
        except InvestigationCancelled:
            yield event({'type':'cancelled','message':'分析已停止。'})
        except auto_fault.AutoFaultError as exc:
            yield event({'type':'error','message':str(exc),'kind':exc.kind})
        except DeepSeekError as exc:
            yield event({'type':'error','message':str(exc),'kind':exc.kind})
        except ValidationError as exc:
            # Log schema paths/types only, never provider text or source contents.
            issues=[{'loc':e['loc'],'type':e['type']} for e in exc.errors()]
            logging.getLogger(__name__).warning('XGSS AI schema validation: %s',issues)
            yield event({'type':'error','message':'AI 返回的结构不完整，未保存建议；请重新生成。','kind':'schema_validation'})
        except ai.ModelOutputValidationError as exc:
            logging.getLogger(__name__).warning('XGSS AI evidence validation: %s',exc.kind)
            yield event({'type':'error','message':str(exc),'kind':exc.kind})
        except store.EvidenceLimitError as exc:
            yield event({'type':'error','message':str(exc),'kind':'evidence_limit'})
        except (ValueError,TypeError,KeyError) as exc:
            messages={
                '分析过程中资料已更新，请重新分析。':('资料已更新，请重新分析当前资料。','evidence_changed'),
                '本次资料已在分析，请等待完成。':('当前资料正在分析，请等待完成。','analysis_busy'),
                '请先生成检索计划并读取同 VIN 资料。':('尚未读取该设备的图册资料，请先读取资料。','evidence_missing'),
            }
            error_message,kind=messages.get(str(exc),('当前资料无法完成分析，已保留原始资料，请重新读取后再分析。','evidence_validation'))
            logging.getLogger(__name__).warning('XGSS AI validation failure: %s (%s)',kind,type(exc).__name__)
            yield event({'type':'error','message':error_message,'kind':kind})
        except OSError:
            yield event({'type':'error','message':'排查记录暂时无法保存。'})
        finally:
            cancelled.set()
            if task is not None and not task.done():task.add_done_callback(lambda done:None if done.cancelled() else done.exception())
    return StreamingResponse(stream(),media_type='text/event-stream',headers=HEADERS)


@router.post('/plan')
async def plan(body:PlanRequest,request:Request):
    _verify_machine(body.machine_id,body.dataset_id,body.vin)
    dataset=load_dataset(body.dataset_id) if body.dataset_id else None
    machine=dataset.machine if dataset else find_machine(body.machine_id)
    context=loaded_context(body,dataset)
    def fault_plan(continuation):
        symptom=ai.Symptom(symptom=continuation.get('symptom',body.symptom),
            symptom_source=continuation.get('symptom_source',body.symptom_source))
        return ai.plan(body.machine_id,body.dataset_id,body.vin,machine.model,symptom,
            machine_context=context,fault_event_id=continuation.get('fault_event_id'),
            **{key:continuation[key] for key in ('source_report_id','manual_fault','engineering_fault','handoff_context','fault_context','catalog_fault_code')})
    if body.automatic:
        def automatic_plan():
            record=auto_fault.plan(body,lambda:fault_plan(handoff_context.plan_context(body,machine.model)))
            try:
                return ai.normalize_cached_advice(record)
            except (ValueError,TypeError,KeyError):
                raise auto_fault.AutoFaultError('auto_fault_cached_advice_invalid',
                    '已保存的建议未通过来源校验，未自动重试；请核对资料后手动分析。') from None
        return model_stream(request,automatic_plan,
            'AI 正在核验新故障并自动规划部件排查与资料检索…')
    if body.analysis_mode=='maintenance':
        if body.symptom_source!='user_question' or any((body.fault_event_id,body.source_report_id,body.manual_fault,body.engineering_fault)):
            raise HTTPException(422,'保养推荐请使用独立的工时与资料，不关联故障事件或旧排查。',headers=HEADERS)
        symptom=ai.Symptom(symptom=body.symptom.strip() or ai.maintenance.default_question(),symptom_source='user_question')
        return model_stream(request,lambda:ai.plan(body.machine_id,body.dataset_id,body.vin,machine.model,symptom,
            machine_context=context,analysis_mode='maintenance',machine_type=getattr(machine,'machine_type','')),'AI 正在结合机型与工时查找保养件和易损件…')
    try:
        continuation=handoff_context.plan_context(body,machine.model)
    except (ValueError,KeyError,TypeError):
        raise HTTPException(422,'故障或原分析上下文未通过核验；请核对机型、配置、原问题及来源。',headers=HEADERS) from None
    return model_stream(request,lambda:fault_plan(continuation),
        'XCMG AI 正在结合设备证据规划部件排查与资料检索…')


def loaded_context(body,dataset=None):
    """Derive the authorized projection on the server, never from client fields."""
    if body.dataset_id:
        dataset=dataset or load_dataset(body.dataset_id)
        context=build_context(body.machine_id,dataset.telemetry,dataset.faults)
        context['source']='imported_user_supplied'
    else:
        context=build_context(body.machine_id,find_telemetry(body.machine_id),find_faults(body.machine_id))
        context['source']='trackunit_cache'
    return context


@router.post('/machine-context')
def machine_context(body:Identity):
    """Local display only. This endpoint does not call or feed a cloud model."""
    _verify_machine(body.machine_id,body.dataset_id,body.vin)
    context=loaded_context(body)
    return JSONResponse({'context':context,'destination':'local_only'},headers=HEADERS)


@router.post('/latest')
def latest(body:Identity):
    _verify_machine(body.machine_id,body.dataset_id,body.vin)
    record=store.latest(body.machine_id,body.dataset_id,body.vin)
    if record is None:
        raise HTTPException(404,'当前设备和数据版本没有可恢复的资料排查。',headers=HEADERS)
    return result(record)


@router.post('/active')
def active(body:Identity):
    _verify_machine(body.machine_id,body.dataset_id,body.vin)
    try:
        record=store.active(body.machine_id,body.dataset_id,body.vin)
    except (ValueError,OSError):
        raise HTTPException(503,'活动排查暂时无法读取或校验失败。',headers=HEADERS) from None
    if record is None:
        raise HTTPException(404,'当前设备和数据版本没有正在进行的资料排查。',headers=HEADERS)
    return result(record)


@router.post('/{research_id}/activate')
def activate(research_id:str,body:ActivateRequest):
    record=checked(research_id)
    if (record['machine_id']!=body.machine_id or record['dataset_id']!=body.dataset_id or record['vin']!=body.vin):
        raise HTTPException(422,'排查记录与当前设备、VIN 或数据版本不一致。',headers=HEADERS)
    try:
        return result(store.activate(research_id,body.expected_research_id))
    except store.ActiveResearchConflict:
        raise HTTPException(409,'其他工作区已切换活动排查，请读取当前排查后继续。',headers=HEADERS) from None
    except ValueError:
        raise HTTPException(422,'排查计划无效，未切换当前活动排查。',headers=HEADERS) from None
    except OSError:
        raise HTTPException(503,'活动排查暂时无法更新。',headers=HEADERS) from None


@router.post('/{research_id}/analyze')
async def analyze(research_id:str,request:Request):
    checked(research_id)
    return model_stream(request,lambda:ai.analyze(research_id),'XCMG AI 正在结合图册和维修资料生成建议…')


def checked(research_id):
    try:
        record=store.read(research_id)
    except (ValueError,OSError,KeyError,TypeError):
        raise HTTPException(404,'资料不存在或校验失败。',headers=HEADERS) from None
    _verify_machine(record['machine_id'],record['dataset_id'],record['vin'])
    return record


def result(record):
    try:
        record=ai.normalize_cached_advice(record)
    except (ValueError,TypeError,KeyError):
        record={k:v for k,v in record.items() if k not in ('advice','analysis_revision','analyzed_at')}
        record['advice_error']='历史建议未通过来源校验，已隐藏；原始资料仍保留。请重新生成排查计划。'
    return JSONResponse({**record,'evidence':ai.research_evidence(record)},headers=HEADERS)


@router.post('')
def create(body:Identity):
    _verify_machine(body.machine_id,body.dataset_id,body.vin)
    try:
        return result(store.create(body.machine_id,body.dataset_id,body.vin))
    except OSError:
        raise HTTPException(503,'资料收集暂时无法保存。',headers=HEADERS) from None


@router.get('/{research_id}')
def read(research_id:str):
    return result(checked(research_id))


@router.post('/{research_id}/pages')
def append(research_id:str,body:store.PageCapture):
    checked(research_id)
    try:
        return result(store.append(research_id,body))
    except store.EvidenceLimitError as exc:
        raise HTTPException(422,'本页未导入，已有资料与建议保持不变。'+str(exc),headers=HEADERS) from None
    except images.ImageCaptureError as exc:
        raise HTTPException(422,str(exc),headers=HEADERS) from None
    except ValueError:
        raise HTTPException(422,'页面设备不一致、资料超限或校验失败，未导入。',headers=HEADERS) from None
    except OSError:
        raise HTTPException(503,'资料收集暂时无法保存。',headers=HEADERS) from None



@router.get('/{research_id}/images/{image_id}')
def read_image(research_id:str,image_id:str):
    record=checked(research_id)
    try:
        data=store.read_image(record,image_id)
    except (ValueError,OSError,KeyError,TypeError):
        raise HTTPException(404,'图册图片不存在或校验失败。',headers=HEADERS) from None
    return Response(data,media_type='image/png',headers={**HEADERS,'X-Content-Type-Options':'nosniff',
                    'Content-Security-Policy':"default-src 'none'; sandbox"})
