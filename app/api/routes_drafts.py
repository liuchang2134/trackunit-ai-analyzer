from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from app.investigation_drafts import DraftSaveRequest, DraftConflict, DraftScopeError, Source, read_draft, save_draft

router=APIRouter(prefix='/assistant',tags=['Local investigation drafts'])


def response(action):
    try:
        return JSONResponse(action(),headers={'Cache-Control':'no-store'})
    except DraftConflict:
        raise HTTPException(409,'另一页面已更新此草稿。请重新读取并恢复已存版本，再编辑保存。',headers={'Cache-Control':'no-store'}) from None
    except DraftScopeError:
        raise HTTPException(404,'草稿的设备、数据来源、故障码适用机型或关联报告不匹配，请重新选择对应设备。',headers={'Cache-Control':'no-store'}) from None
    except OSError:
        raise HTTPException(503,'本机草稿无法读取或保存。当前输入仍在页面中，请勿关闭；检查本机存储后重试。',headers={'Cache-Control':'no-store'}) from None


@router.get('/draft')
def get_draft(machine_id: str=Query(min_length=1,max_length=200),
              source: Source=Query(), dataset_id: str | None=Query(default=None,pattern=r'^[0-9a-f]{64}$')):
    return response(lambda:read_draft(machine_id,dataset_id,source))


@router.put('/draft')
def put_draft(request: DraftSaveRequest):
    return response(lambda:save_draft(request))
