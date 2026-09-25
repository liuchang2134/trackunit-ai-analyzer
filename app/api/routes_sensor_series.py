"""Import and assess current-device Trackunit sensor exports; no remote reads."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from app import sensor_series as series
from app.deepseek_client import DeepSeekError

router = APIRouter(prefix='/assistant/sensor-series', tags=['Continuous sensor evidence'])
HEADERS = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}


class Identity(BaseModel):
    model_config = ConfigDict(extra='forbid')
    machine_id: str = Field(min_length=1, max_length=200)
    dataset_id: str = Field(pattern=r'^[a-f0-9]{64}$')


class ChannelMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str | None = Field(default=None, min_length=1, max_length=180)
    unit: str | None = Field(default=None, min_length=1, max_length=24)
    kind: Literal['continuous', 'state', 'code', 'counter'] | None = None


class ExportInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    csv_text: str = Field(min_length=1, max_length=series.MAX_BYTES)
    units: dict[str, str] | None = Field(default=None, max_length=series.MAX_CHANNELS)
    channel_metadata: dict[str, ChannelMetadata] | None = Field(default=None, max_length=series.MAX_CHANNELS)
    captured_at: str | None = Field(default=None, max_length=50)
    page_url: str | None = Field(default=None, max_length=500)


class SourceIdentity(Identity):
    source: Literal['trackunit_advanced_sensors_export']
    source_asset_id: str = Field(min_length=1, max_length=200)
    origin: Literal['user_confirmed_export', 'browser_export_capture'] = 'user_confirmed_export'
    captured_at: str | None = Field(default=None, max_length=50)
    page_url: str | None = Field(default=None, max_length=500)


class ImportRequest(SourceIdentity, ExportInput):
    pass


class BatchImportRequest(SourceIdentity):
    exports: list[ExportInput] = Field(min_length=1, max_length=series.MAX_EXPORTS)


class PartsHandoffRequest(Identity):
    hypothesis_index: int = Field(ge=0, le=3, strict=True)


def _result(call, missing=False):
    try:
        return JSONResponse(call(), headers=HEADERS)
    except ValueError as error:
        raise HTTPException(404 if missing else 422, str(error)[:300], headers=HEADERS) from None
    except DeepSeekError:
        raise HTTPException(503, 'XCMG AI 暂时无法完成趋势分析；已导入的曲线与统计仍可查看。', headers=HEADERS) from None
    except OSError:
        raise HTTPException(503, '连续传感器资料暂时无法读取或保存。', headers=HEADERS) from None


@router.post('/import')
def import_csv(body: ImportRequest):
    return _result(lambda: series.import_series(**body.model_dump(exclude_none=True)))


@router.post('/import-batch')
def import_batch(body: BatchImportRequest):
    return _result(lambda: series.import_batch(**body.model_dump(exclude_none=True)))


@router.get('/latest')
def latest(machine_id: str = Query(min_length=1, max_length=200),
           dataset_id: str = Query(pattern=r'^[a-f0-9]{64}$')):
    return _result(lambda: series.latest(machine_id, dataset_id), missing=True)


@router.post('/{series_id}/analyze')
def analyze(series_id: str, body: Identity):
    return _result(lambda: series.analyze(series_id, body.machine_id, body.dataset_id))


@router.post('/{series_id}/parts-handoff')
def parts_handoff(series_id: str, body: PartsHandoffRequest):
    return _result(lambda: series.parts_handoff(series_id, body.machine_id, body.dataset_id, body.hypothesis_index))
