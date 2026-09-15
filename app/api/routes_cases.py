from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from typing import Literal
from app import maintenance_cases as cases
from app.investigation_drafts import Source

router = APIRouter(prefix='/assistant/cases', tags=['Local maintenance cases'])
HEADERS = {'Cache-Control': 'no-store'}


def respond(action):
    try:
        result = action()
        return result if isinstance(result, Response) else JSONResponse(result, headers=HEADERS)
    except cases.CaseConflict:
        raise HTTPException(409, '任务已被更新，或该设备已有另一条进行中任务。当前输入已保留，请重新读取任务后核对。', headers=HEADERS) from None
    except cases.CaseMissing:
        raise HTTPException(404, '这条排查任务不存在或不可读取。', headers=HEADERS) from None
    except cases.CaseScopeError:
        raise HTTPException(404, '设备、数据版本或关联报告不匹配。请选择准确的设备与版本。', headers=HEADERS) from None
    except OSError:
        raise HTTPException(503, '本机排查任务无法读取或保存。请保留当前输入，检查本机存储后重试。', headers=HEADERS) from None


@router.get('')
def listing(state: Literal['active', 'archived', 'all'] = 'active',
            limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
            machine_id: str | None = Query(default=None, min_length=1, max_length=200), real_only: bool = False):
    return respond(lambda: cases.list_cases(state, limit, offset, machine_id, real_only))


@router.get('/current')
def current(machine_id: str = Query(min_length=1, max_length=200), source: Source = Query(),
            dataset_id: str | None = Query(default=None, pattern=r'^[0-9a-f]{64}$')):
    return respond(lambda: {'case': cases.current_case(machine_id, dataset_id, source), 'ai_used': False})


@router.post('')
def create(request: cases.CreateCase):
    return respond(lambda: cases.create_case(request))


@router.get('/{case_id}/export.md')
def export(case_id: str):
    def action():
        content, filename = cases.export_case(case_id)
        return Response(content, media_type='text/markdown; charset=utf-8', headers={**HEADERS,
            'Content-Disposition': f'attachment; filename="{filename}"', 'X-Content-Type-Options': 'nosniff'})
    return respond(action)


@router.get('/{case_id}')
def read(case_id: str):
    return respond(lambda: {'case': cases.read_case(case_id), 'ai_used': False})


@router.post('/{case_id}/events')
def update(case_id: str, request: cases.CaseEvent):
    return respond(lambda: cases.append_event(case_id, request))
