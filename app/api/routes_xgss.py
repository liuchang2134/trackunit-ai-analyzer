from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from app import xgss_handoff as xgss
from app import xgss_identity as identity
from app.local_datasets import load_dataset, save_dataset
from app.services.machine_service import find_machine
from app.data_store import get_data_source

router = APIRouter(prefix='/assistant/xgss', tags=['XGSS page handoff'])
HEADERS = {'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer'}


class OpenPage(BaseModel):
    machine_id: str = Field(min_length=1, max_length=200)
    dataset_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    vin: str = Field(pattern=r'^[A-Z0-9]{8,32}$')
    vin_confirmed: Literal[True]
    fault_code: str | None = Field(default=None, min_length=1, max_length=100)
    language: Literal['zh', 'en'] = 'zh'


class IdentityRequest(BaseModel):
    machine_id: str = Field(min_length=1, max_length=200)
    dataset_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    vin: str = Field(min_length=1, max_length=200)


class CorrectIdentity(BaseModel):
    machine_id: str = Field(min_length=1, max_length=200)
    dataset_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    current_vin: str = Field(min_length=1, max_length=200)
    new_vin: str = Field(pattern=r'^[A-Z0-9]{8,32}$')
    confirmed: Literal[True]

    @field_validator('new_vin', mode='before')
    @classmethod
    def normalize_new_vin(cls, value):
        return identity.normalized(value) if isinstance(value, str) else value


@router.get('/status')
def status():
    return JSONResponse(xgss.readiness(), headers=HEADERS)


def selected_machine(machine_id, dataset_id, vin):
    try:
        if dataset_id:
            data = load_dataset(dataset_id)
            machine, simulated = data.machine, data.provenance != 'user_supplied'
        else:
            data = None
            machine, simulated = find_machine(machine_id), get_data_source() != 'trackunit_cache'
        if machine is None or machine.machine_id != machine_id:
            raise LookupError()
    except (ValueError, OSError, LookupError):
        raise HTTPException(404, '找不到匹配的设备与数据版本。', headers=HEADERS) from None
    if simulated:
        raise HTTPException(422, '模拟设备不向 XGSS 生产环境发起请求。请选择对应的实测设备。', headers=HEADERS)
    if identity.normalized(machine.serial_number) != identity.normalized(vin):
        raise HTTPException(422, 'VIN/PIN 与所选设备的序列号不一致，请先核对设备资料。', headers=HEADERS)
    return machine, data


@router.post('/identity')
def identity_status(request: IdentityRequest):
    machine, _ = selected_machine(request.machine_id, request.dataset_id, request.vin)
    return JSONResponse(identity.status(machine, request.dataset_id), headers=HEADERS)


@router.post('/identity/correct')
def correct_identity(request: CorrectIdentity):
    machine, data = selected_machine(request.machine_id, request.dataset_id, request.current_vin)
    if identity.normalized(machine.serial_number) == request.new_vin and not identity.needs_verification(machine):
        raise HTTPException(422, '请填写核实后的整机 VIN/PIN，不能重复使用当前编号。', headers=HEADERS)
    try:
        # Only verify the explicitly confirmed candidate. No guessing, retry,
        # search over nearby serials, or copying sources from a different VIN.
        xgss.request_page(request.new_vin, language='zh')
    except xgss.XGSSUnavailable as error:
        raise HTTPException(503, str(error), headers=HEADERS) from None
    except xgss.XGSSUpstreamError as error:
        raise HTTPException(502, str(error), headers=HEADERS) from None
    except ValueError:
        raise HTTPException(422, '整机 VIN/PIN 格式无效。', headers=HEADERS) from None
    corrected = data.model_copy(deep=True)
    corrected.machine = machine.model_copy(update={'serial_number': request.new_vin})
    corrected.source_document = identity.source_document(data.source_document)
    try:
        saved = save_dataset(corrected)
        identity.save_binding(machine, request.dataset_id, request.new_vin, saved['dataset_id'])
    except (OSError, ValueError):
        raise HTTPException(503, '整机编号已通过 XGSS 校验，但本地保存未完成，请重试。', headers=HEADERS) from None
    # Cache refresh is optional: the verified binding is also applied to future
    # imports. Old datasets and research records remain immutable.
    from app.platform_asset_loader import correct_cached_identity
    try:
        correct_cached_identity(request.machine_id, request.dataset_id, saved)
    except (OSError, ValueError):
        pass
    return JSONResponse({**saved, 'status':'corrected',
                         'message':'已校正整机 VIN/PIN 并通过 XGSS 校验，请使用新的设备资料继续分析。'}, headers=HEADERS)


@router.post('/open')
def open_page(request: OpenPage):
    machine, _ = selected_machine(request.machine_id, request.dataset_id, request.vin)
    if identity.needs_verification(machine):
        detail = identity.status(machine, request.dataset_id)
        raise HTTPException(422, {**detail, 'code':'vin_required'}, headers=HEADERS)
    try:
        result = xgss.request_page(request.vin, request.fault_code, request.language)
        return JSONResponse({**result, 'machine_id':request.machine_id, 'dataset_id':request.dataset_id}, headers=HEADERS)
    except xgss.XGSSUnavailable as error:
        raise HTTPException(503, str(error), headers=HEADERS) from None
    except xgss.XGSSUpstreamError as error:
        raise HTTPException(502, str(error), headers=HEADERS) from None
    except ValueError:
        raise HTTPException(422, 'XGSS 查询参数无效，请核对 VIN 与故障码。', headers=HEADERS) from None
