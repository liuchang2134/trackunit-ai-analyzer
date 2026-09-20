from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from app.demo_case import DemoUnavailable, load_demo, render_demo_report
from app.demo_replay import ReplayUnavailable, build_replay, list_replays

router = APIRouter(prefix='/assistant', tags=['Offline demonstration'])


@router.get('/demo-case')
def demo_case():
    try:
        return JSONResponse(load_demo(), headers={'Cache-Control': 'no-store'})
    except DemoUnavailable as error:
        raise HTTPException(503, str(error), headers={'Cache-Control': 'no-store'}) from None


@router.get('/demo-case/replays')
def demo_replays():
    """Saved real AI runs available to replay; offline and read-only."""
    return JSONResponse(list_replays(), headers={'Cache-Control': 'no-store'})


@router.get('/demo-case/replay/{record_id}')
def demo_replay(record_id: str):
    """One saved real AI investigation, presented as a replay rather than a live run."""
    try:
        return JSONResponse(build_replay(record_id), headers={'Cache-Control': 'no-store'})
    except ReplayUnavailable as error:
        raise HTTPException(404, str(error), headers={'Cache-Control': 'no-store'}) from None


@router.get('/demo-case/replay/{record_id}/report.md')
def demo_replay_report(record_id: str):
    """The same replay as a portable Markdown evidence pack."""
    from app.demo_replay import render_replay_report
    try:
        content, filename = render_replay_report(build_replay(record_id))
    except ReplayUnavailable as error:
        raise HTTPException(404, str(error), headers={'Cache-Control': 'no-store'}) from None
    # The filename is generated from a validated record id, never from user text.
    safe = ''.join(ch for ch in filename if ch.isalnum() or ch in '-_.')
    return Response(content, media_type='text/markdown; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="{safe}"',
        'Cache-Control': 'no-store',
    })


@router.get('/demo-case/report.md')
def demo_report():
    try:
        return Response(render_demo_report(load_demo()), media_type='text/markdown', headers={
            'Content-Disposition': 'attachment; filename="tv12u-h10101-simulated-case.md"',
            'Cache-Control': 'no-store',
        })
    except DemoUnavailable as error:
        raise HTTPException(503, str(error), headers={'Cache-Control': 'no-store'}) from None
