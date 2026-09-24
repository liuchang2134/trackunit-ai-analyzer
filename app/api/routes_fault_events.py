"""Local reads and explicit bounded Trackunit fault refresh."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from app import trackunit_events as events

router = APIRouter(prefix='/assistant/fault-events', tags=['Fault events'])
HEADERS = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    machine_id: str = Field(min_length=1, max_length=200)
    dataset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    vin: str = Field(pattern=r'^[A-Z0-9]{8,32}$')


def _identity(machine_id, dataset_id, vin):
    try:
        return events.registered_machine(machine_id, dataset_id, vin)
    except (ValueError, KeyError, TypeError, OSError):
        raise HTTPException(422, '请选择已登记的实测设备，并核对设备及 VIN/PIN。', headers=HEADERS) from None


@router.get('')
def read(machine_id: str = Query(min_length=1, max_length=200),
         dataset_id: str | None = Query(default=None, pattern=r'^[a-f0-9]{64}$'),
         vin: str | None = Query(default=None, pattern=r'^[A-Z0-9]{8,32}$')):
    identity = _identity(machine_id, dataset_id, vin)
    try:
        return JSONResponse(events.read_state(identity), headers=HEADERS)
    except (ValueError, KeyError, TypeError, OSError):
        raise HTTPException(503, '本地故障记录无法读取或未通过校验。', headers=HEADERS) from None


@router.post('/refresh')
def refresh(body: RefreshRequest):
    identity = _identity(body.machine_id, body.dataset_id, body.vin)
    try:
        return JSONResponse(events.refresh(identity), headers=HEADERS)
    except (ValueError, KeyError, TypeError, OSError):
        raise HTTPException(503, '故障记录暂时无法读取或保存。', headers=HEADERS) from None


@router.post('/sync')
def sync(body: RefreshRequest):
    identity = _identity(body.machine_id, body.dataset_id, body.vin)
    try:
        return JSONResponse(events.refresh(identity, automatic=True), headers=HEADERS)
    except (ValueError, KeyError, TypeError, OSError):
        raise HTTPException(503, '自动故障读取状态无法核验，未继续自动读取。', headers=HEADERS) from None
