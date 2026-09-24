"""Explicit same-origin email preview/status/send for one verified result."""
from urllib.parse import urlsplit
import sqlite3
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import JSONResponse
from pydantic import Field
from app import research_email as email
from app.api import routes_xgss_research as research
from app.api.routes_xgss_context import HEADERS

router=APIRouter(prefix='/assistant/xgss/research',tags=['Research preparation email'])


class SendRequest(research.Identity):
    preview_hash:str=Field(pattern=r'^[a-f0-9]{64}$')


def _checked(research_id,body):
    record=research.checked(research_id)
    if any(record[key]!=getattr(body,key) for key in ('machine_id','dataset_id','vin')):
        raise HTTPException(422,'排查结果与当前设备、VIN 或数据版本不一致。',headers=HEADERS)
    return record


def _respond(call):
    try:return JSONResponse(call(),headers=HEADERS)
    except email.EmailError as exc:
        raise HTTPException(exc.status_code,str(exc),headers=HEADERS) from None
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):
        raise HTTPException(503,'邮件预览或通知状态暂时不可用，未确认发送成功。',headers=HEADERS) from None


def _require_local_origin(request):
    origin=request.headers.get('origin','')
    expected=f'{request.url.scheme}://{request.url.netloc}'
    try:local=urlsplit(origin).hostname in ('localhost','127.0.0.1','::1')
    except ValueError:local=False
    if (not local or origin!=expected or
        request.headers.get('sec-fetch-site')=='cross-site' or
        request.headers.get('content-type','').split(';')[0].strip().lower()!='application/json'):
        raise HTTPException(403,'邮件发送只接受当前本机工作台的明确操作。',headers=HEADERS)


@router.post('/{research_id}/email-preview')
def preview(research_id:str,body:research.Identity):
    return _respond(lambda:email.preview(_checked(research_id,body)))


@router.post('/{research_id}/email-status')
def status(research_id:str,body:research.Identity):
    return _respond(lambda:email.status(_checked(research_id,body)))


@router.post('/{research_id}/email-send')
def send(research_id:str,body:SendRequest,request:Request):
    _require_local_origin(request)
    return _respond(lambda:email.send(lambda:_checked(research_id,body),body.preview_hash))
