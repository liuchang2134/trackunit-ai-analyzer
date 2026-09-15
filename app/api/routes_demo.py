from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from app.demo_case import DemoUnavailable, load_demo, render_demo_report

router = APIRouter(prefix='/assistant', tags=['Offline demonstration'])


@router.get('/demo-case')
def demo_case():
    try:
        return JSONResponse(load_demo(), headers={'Cache-Control': 'no-store'})
    except DemoUnavailable as error:
        raise HTTPException(503, str(error), headers={'Cache-Control': 'no-store'}) from None


@router.get('/demo-case/report.md')
def demo_report():
    try:
        return Response(render_demo_report(load_demo()), media_type='text/markdown', headers={
            'Content-Disposition': 'attachment; filename="tv12u-h10101-simulated-case.md"',
            'Cache-Control': 'no-store',
        })
    except DemoUnavailable as error:
        raise HTTPException(503, str(error), headers={'Cache-Control': 'no-store'}) from None
