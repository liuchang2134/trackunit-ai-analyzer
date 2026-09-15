"""Offline, explicitly scoped fault-code reference endpoints."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app import fault_reference as reference

router = APIRouter(prefix='/assistant/fault-reference', tags=['Fault reference'])
HEADERS = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}


@router.get('/status')
def status():
    return JSONResponse(reference.reference_status(), headers=HEADERS)


@router.get('')
def query_reference(
    model: str = Query(min_length=1, max_length=32),
    version: str = Query(min_length=1, max_length=32),
    code: str | None = Query(default=None, min_length=1, max_length=16),
    q: str | None = Query(default=None, max_length=120),
):
    if code is not None and q is not None:
        raise HTTPException(422, '请使用故障码精确查询或关键词搜索中的一种。', headers=HEADERS)
    try:
        catalog = reference.load_reference()
        if code is not None:
            item = reference.lookup_fault(catalog, model=model, version=version, code=code)
            if item is None:
                raise HTTPException(404, '此协议版本未收录该故障码，不自动套用其他代码。', headers=HEADERS)
            items = [item]
        else:
            items = reference.search_faults(catalog, model=model, version=version, q=q or '')
        return JSONResponse({**catalog, 'items': items, 'total': len(items)}, headers=HEADERS)
    except reference.ReferenceUnavailable as error:
        raise HTTPException(503, str(error), headers=HEADERS) from None
    except ValueError as error:
        raise HTTPException(422, str(error), headers=HEADERS) from None
