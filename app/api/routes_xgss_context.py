"""Read-only XGSS browser capture handoff into the local assistant."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from app import xgss_catalog_context as catalog
from app.local_datasets import load_dataset
from app.services.machine_service import find_machine
from app.data_store import get_data_source

router=APIRouter(prefix='/assistant/xgss',tags=['XGSS visible catalog context'])
HEADERS={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'}


class CaptureRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    machine_id: str=Field(min_length=1,max_length=200)
    dataset_id: str | None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    capture: catalog.CatalogCapture


def _verify_machine(machine_id,dataset_id,vin):
    try:
        if dataset_id:
            data=load_dataset(dataset_id)
            machine,real=data.machine,data.provenance=='user_supplied'
        else:
            machine,real=find_machine(machine_id),get_data_source()=='trackunit_cache'
        if machine is None or machine.machine_id!=machine_id: raise ValueError()
    except (ValueError,OSError,LookupError):
        raise HTTPException(404,'找不到匹配的设备与数据版本。',headers=HEADERS) from None
    if not real:
        raise HTTPException(422,'请选择实测设备后读取 XGSS 图册；模拟数据不关联真实备件。',headers=HEADERS)
    if not vin or machine.serial_number.strip().upper()!=vin:
        raise HTTPException(422,'图册显示的 VIN/PIN 与当前设备不一致，未导入任何条目。',headers=HEADERS)


@router.post('/catalog-context')
def save_capture(request: CaptureRequest):
    _verify_machine(request.machine_id,request.dataset_id,request.capture.vin)
    try:
        result=catalog.save_catalog_context(request.capture,dataset_id=request.dataset_id,machine_id=request.machine_id)
        return JSONResponse(result,headers=HEADERS)
    except ValueError as error:
        raise HTTPException(422,str(error),headers=HEADERS) from None
    except OSError:
        raise HTTPException(503,'本地图册记录暂时无法保存。',headers=HEADERS) from None


@router.get('/catalog-context')
def read_capture(machine_id: str=Query(min_length=1,max_length=200),
                 vin: str=Query(pattern=r'^[A-Z0-9]{8,32}$'),
                 dataset_id: str | None=Query(default=None,pattern=r'^[a-f0-9]{64}$')):
    _verify_machine(machine_id,dataset_id,vin)
    try:
        return JSONResponse(catalog.load_catalog_context(dataset_id,vin,machine_id),headers=HEADERS)
    except (OSError,ValueError,KeyError,TypeError):
        raise HTTPException(503,'本地图册记录暂时无法读取或校验未通过。',headers=HEADERS) from None
