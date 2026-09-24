"""Read-only local CAN replay. No real telemetry is sent externally."""
import asyncio
import json
import threading
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from app.can_replay import recorded_replay, synthetic_replay
from app.can_demo_ai import SyntheticAnalysisRequest, analyze_synthetic
from app.deepseek_client import DeepSeekError, InvestigationCancelled, cancellation_scope, reset_cancellation_scope

router = APIRouter(prefix='/assistant/can-replay', tags=['CAN replay'])


@router.get('')
def replay(scenario: Literal['recorded', 'synthetic'] = 'recorded'):
    try:
        data = recorded_replay() if scenario == 'recorded' else synthetic_replay()
    except FileNotFoundError:
        raise HTTPException(404, '实车回放尚未导入，可先使用模拟工况。') from None
    return JSONResponse(data, headers={'Cache-Control': 'no-store'})


@router.post('/synthetic-analysis')
async def synthetic_analysis(payload: SyntheticAnalysisRequest, request: Request):
    # Only scenario + integer cursor are accepted; extra fields are forbidden.
    # No real capture, user telemetry, VIN or workbook content enters this path.
    cancelled = threading.Event()

    def worker():
        token = cancellation_scope(cancelled.is_set)
        try:
            return analyze_synthetic(payload)
        finally:
            reset_cancellation_scope(token)

    def event(value):
        return 'data: ' + json.dumps(value, ensure_ascii=False) + '\n\n'

    async def stream():
        task = None
        try:
            yield event({'type': 'progress', 'stage': 'model_decision', 'message': 'DeepSeek 正在分析模拟工况…'})
            task = asyncio.create_task(asyncio.to_thread(worker))
            while not task.done():
                if await request.is_disconnected():
                    cancelled.set()
                    return
                await asyncio.wait({task}, timeout=1)
                if not task.done():
                    yield ': heartbeat\n\n'
            result = await task
            if not cancelled.is_set():
                yield event({'type': 'result', 'report': result})
        except InvestigationCancelled:
            yield event({'type': 'cancelled', 'message': '分析已停止。'})
        except DeepSeekError as exc:
            yield event({'type': 'error', 'message': str(exc), 'kind': exc.kind})
        except (ValueError, TypeError):
            yield event({'type': 'error', 'message': 'AI 回答未通过证据或格式校验，请重试。'})
        finally:
            cancelled.set()
            if task is not None and not task.done():
                # Consume a late exception after client cancellation.
                task.add_done_callback(lambda done: None if done.cancelled() else done.exception())

    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-store'})
