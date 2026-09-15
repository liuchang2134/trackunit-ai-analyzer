from fastapi import APIRouter, HTTPException, Query
from app.local_assistant import InvestigationRequest, investigate
from app.ollama_client import OllamaError
from app.gemini_client import GeminiError
from app.deepseek_client import DeepSeekError
from app.parts_catalog import CatalogImport, import_catalog, load_catalog
from pydantic import BaseModel, ConfigDict, Field
from app.inspection_feedback import InspectionFeedback
from app.observation_export import Metric, Window

router = APIRouter(prefix="/assistant", tags=["Local assistant"])


def cooling_response(callback):
    from fastapi.responses import JSONResponse
    try: return JSONResponse(callback(), headers={'Cache-Control':'no-store'})
    except FileNotFoundError:
        raise HTTPException(404,'冷却预警演示资料尚未生成，或片段不存在。') from None
    except (ValueError,KeyError,TypeError):
        raise HTTPException(422,'冷却预警资料、模型或回放时点校验失败。') from None
    except OSError:
        raise HTTPException(503,'本地冷却演示资料暂时无法读取。') from None


@router.get('/cooling/episodes')
def cooling_episodes():
    from app.cooling_demo import list_episodes
    return cooling_response(list_episodes)


@router.get('/cooling/replay')
def cooling_replay(episode_id: str=Query(pattern=r'^CW-[0-9a-f]{12}$'),cursor: int=Query(ge=0,le=479)):
    from app.cooling_demo import replay
    return cooling_response(lambda: replay(episode_id,cursor))


@router.get('/cooling/evaluation')
def cooling_evaluation():
    from app.cooling_demo import evaluation
    return cooling_response(evaluation)


@router.get('/cooling/context')
def cooling_dataset_context(dataset_id: str=Query(pattern=r'^[0-9a-f]{64}$')):
    from app.cooling_demo import verified_context
    from app.local_datasets import load_dataset
    return cooling_response(lambda:verified_context(load_dataset(dataset_id)))


class CoolingPrepareRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    episode_id: str=Field(pattern=r'^CW-[0-9a-f]{12}$')
    cursor: int=Field(ge=0,le=479,strict=True)


@router.post('/cooling/prepare')
def cooling_prepare(request: CoolingPrepareRequest):
    from app.cooling_demo import prepare
    return cooling_response(lambda:prepare(request.episode_id,request.cursor))


@router.get('/fault-context')
def selected_fault_context(machine_id: str = Query(min_length=1, max_length=200),
                           fault_code: str = Query(min_length=1, max_length=200),
                           dataset_id: str | None = Query(default=None, pattern=r'^[0-9a-f]{64}$')):
    from fastapi.responses import JSONResponse
    from app.fault_context import get_fault_context
    try:
        return JSONResponse(get_fault_context(machine_id, fault_code, dataset_id), headers={'Cache-Control': 'no-store'})
    except LookupError:
        raise HTTPException(404, '当前设备或数据版本没有这条有效故障记录，请重新选择。') from None
    except (OSError, ValueError):
        raise HTTPException(503, '故障资料或本地备件目录无法读取，请检查数据文件。') from None


@router.get('/device-overview')
def selected_device_overview(machine_id: str = Query(min_length=1,max_length=200),
                             dataset_id: str | None = Query(default=None,pattern=r'^[0-9a-f]{64}$')):
    from app.device_overview import device_overview
    try:
        return device_overview(machine_id,dataset_id)
    except ValueError:
        raise HTTPException(404,'当前设备或数据版本不可用，请重新选择。') from None
    except OSError:
        raise HTTPException(503,'设备资料暂时无法读取，请稍后重试。') from None


@router.get('/device-index')
def local_device_index():
    from fastapi.responses import JSONResponse
    from app.device_index import device_index
    try:
        return JSONResponse(device_index(), headers={'Cache-Control': 'no-store'})
    except OSError:
        raise HTTPException(503, '设备列表暂时无法读取，请重试。') from None


@router.get('/device-overview.csv')
def download_device_observations(machine_id: str = Query(min_length=1, max_length=200),
                                 dataset_id: str | None = Query(default=None, pattern=r'^[0-9a-f]{64}$'),
                                 metric: Metric = 'operating_hours', window: Window = 'all',
                                 expected_revision: str | None = Query(default=None, pattern=r'^[0-9a-f]{64}$')):
    from fastapi.responses import Response
    from app.observation_export import export_observations, ChangedObservations
    try:
        content, filename = export_observations(machine_id, dataset_id, metric, window, expected_revision)
    except ChangedObservations:
        raise HTTPException(409, '设备数据已更新，请回到助手重新选择设备，载入最新图表后再导出。',
                            headers={'Cache-Control': 'no-store'}) from None
    except ValueError:
        raise HTTPException(404, '当前设备或数据版本不可用，请重新选择。') from None
    except OSError:
        raise HTTPException(503, '设备资料暂时无法读取，请稍后重试。') from None
    return Response(content, media_type='text/csv; charset=utf-8', headers={
        'Cache-Control': 'no-store', 'Content-Disposition': f'attachment; filename="{filename}"',
        'X-Content-Type-Options': 'nosniff'})


@router.get('/work-state/episodes')
def work_state_episodes():
    from app.work_state_demo import list_episodes
    return list_episodes()


@router.get('/work-state/replay')
def work_state_replay(episode_id: str=Query(pattern=r'^EP-[0-9a-f]{12}$'),
                      start: int=Query(default=0,ge=0,le=5759),count: int=Query(default=360,ge=1,le=720)):
    from app.work_state_demo import replay_episode
    try:
        return replay_episode(episode_id,start,count)
    except FileNotFoundError:
        raise HTTPException(404,'模拟工况或模型尚未生成，请运行工况训练脚本。') from None
    except (ValueError,KeyError,TypeError):
        raise HTTPException(422,'模拟输入或模型校验失败，未返回识别结果。') from None
    except OSError:
        raise HTTPException(503,'本地工况资料暂时无法读取。') from None


class HistorySyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    days: int = Field(default=7, ge=1, le=14, strict=True)


@router.get("/history-sources")
def history_sources():
    from app.history_sync import registered_sources
    return registered_sources()


@router.post("/sync-history")
def sync_history(request: HistorySyncRequest):
    from app.history_sync import sync_registered_source
    try:
        return sync_registered_source(request.source_id, request.days)
    except ValueError as exc:
        if "15 minutes" in str(exc) or "already running" in str(exc):
            raise HTTPException(429, "此设备正在同步或距上次请求不足15分钟，请稍后再试。") from None
        raise HTTPException(422, "设备资料或响应格式不符合要求，未完成同步。") from None
    except OSError:
        raise HTTPException(503, "本地同步资料或存储不可用。") from None


@router.get("/integration-status")
def last_integration_status():
    from app.integration_status import integration_status
    return integration_status()


@router.post("/investigate")
def run_investigation(request: InvestigationRequest):
    from app.ai_request_status import capture_context, record_outcome
    from app.local_assistant import ManualFaultError
    from app.fault_reference import ReferenceUnavailable
    context = capture_context()
    try:
        report = investigate(request)
    except ReferenceUnavailable as exc:
        raise HTTPException(503, str(exc), headers={'Cache-Control': 'no-store'}) from None
    except ManualFaultError as exc:
        raise HTTPException(422, str(exc), headers={'Cache-Control': 'no-store'}) from None
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    except (GeminiError, DeepSeekError) as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': str(exc), 'provider_error': exc.provider_error or {'kind': exc.kind},
                             'ai_status': record_outcome(context, 'failed', error=exc)}, status_code=503,
                            headers={'Cache-Control': 'no-store'})
    except OllamaError as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': str(exc), 'ai_status': record_outcome(context, 'failed', error=exc)},
                            status_code=503, headers={'Cache-Control':'no-store'})
    from app.investigation_history import save_investigation
    try:
        saved = save_investigation(report, request.model_dump())
        return {**report, "record_id": saved["record_id"], "history_saved": True,
                'ai_status': record_outcome(context, 'report_saved')}
    except OSError:
        return {**report, "history_saved": False, 'ai_status': record_outcome(context, 'report_unsaved')}


@router.get('/ai-status')
def latest_ai_request_status():
    from fastapi.responses import JSONResponse
    from app.ai_request_status import request_status
    return JSONResponse(request_status(), headers={'Cache-Control':'no-store'})


@router.get('/runtime')
def runtime_configuration():
    from app.local_assistant import assistant_runtime
    return assistant_runtime()


@router.get("/history")
def investigation_history(machine_id: str | None = Query(default=None, max_length=200),
                          dataset_id: str | None = Query(default=None, max_length=100),
                          source: str | None = Query(default=None, max_length=100)):
    from app.investigation_history import list_investigations
    return list_investigations(machine_id=machine_id, dataset_id=dataset_id, source=source)


@router.get("/history/{record_id}")
def investigation_record(record_id: str):
    from app.investigation_history import read_investigation
    try:
        return read_investigation(record_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None


@router.get("/catalog")
def catalog_status():
    catalog = load_catalog()
    return {"total": len(catalog.parts), "demo": sum(p.provenance == "demo" for p in catalog.parts)}


@router.get('/history/{record_id}/feedback')
def report_feedback(record_id: str):
    from app.inspection_feedback import list_feedback
    try:return list_feedback(record_id)
    except (ValueError,OSError):raise HTTPException(422,'诊断记录或检查反馈无法校验。') from None


@router.post('/history/{record_id}/feedback')
def add_report_feedback(record_id: str,payload: InspectionFeedback):
    from app.inspection_feedback import save_feedback
    try:return save_feedback(record_id,payload)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    except OSError:raise HTTPException(503,'检查反馈保存失败。') from None


@router.post("/catalog/import")
def upload_catalog(payload: CatalogImport):
    try:
        return import_catalog(payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


from app.local_datasets import LocalDataset, CsvDatasetRequest, save_dataset, list_datasets, parse_csv


@router.get("/datasets")
def datasets():
    return list_datasets()


@router.post("/datasets/import")
def upload_dataset(payload: LocalDataset):
    return save_dataset(payload)


@router.post("/datasets/import-csv")
def upload_csv(payload: CsvDatasetRequest):
    try:
        return save_dataset(parse_csv(payload))
    except ValueError:
        raise HTTPException(422, "Invalid CSV: check headers, timestamp timezone, numeric ranges and machine metadata") from None
