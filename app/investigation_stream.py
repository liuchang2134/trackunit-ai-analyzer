"""Streamed investigation: real progress events, a real cancel, and a validated report.

One POST returns the live event stream for one investigation, so the run never
depends on server-side state shared between requests. That matters because the
server may handle the next request in a different worker process; anything kept
only in memory would be invisible there, and a stream that cannot be resumed is
exactly the case a user hits when a read appears to "not associate".

Events describe work that has actually happened (a device read completed, a model
decision started), never a timer, so the progress a user sees cannot be
fabricated.

Cancellation is cooperative and real. The reader closing the response — pressing
stop, navigating away, switching device — cancels the investigation, and the
worker observes the cancel before every further model call and discards an
in-flight answer. What is *not* claimed: an HTTP request already sent to the
provider finishes there, because the client reads each response fully. Cancel
therefore stops the investigation and all subsequent calls, and says so instead
of pretending the upstream request was aborted mid-body.

Only a fully received and validated report is emitted as a result. Partial model
output is never rendered as a diagnosis.
"""
from __future__ import annotations

import json
import queue
import threading
import traceback

from app.deepseek_client import InvestigationCancelled, cancellation_scope, reset_cancellation_scope
from app.gemini_client import GeminiError
from app.local_assistant import InvestigationRequest, investigation_scope, reset_investigation_scope
from app.ollama_client import OllamaError

_QUEUE_MAX = 200


class _Investigation:
    """One in-flight investigation and the queue its events are delivered through."""

    def __init__(self, request: InvestigationRequest):
        self.request = request
        self.events: queue.Queue = queue.Queue(maxsize=_QUEUE_MAX)
        self._cancel = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()

    def emit(self, event: dict) -> None:
        """Deliver one event, dropping it rather than blocking when nobody reads."""
        try:
            self.events.put_nowait(event)
        except queue.Full:
            pass

    def start(self) -> None:
        threading.Thread(target=self._run, name='jilian-investigation', daemon=True).start()

    def _run(self) -> None:
        from app.local_assistant import investigate
        # Scopes are installed inside the worker thread: contextvars set on the
        # starting thread would not be visible to work done here.
        cancel_token = cancellation_scope(lambda: self.cancelled)
        observer_token = investigation_scope(self)
        try:
            report = investigate(self.request)
        except InvestigationCancelled:
            self.emit({'type': 'cancelled', 'message': '已停止本次分析；不会再发起新的模型请求。'})
        except Exception as error:  # noqa: BLE001 - every provider failure is reported to the caller
            # The traceback stays server-side; the client gets a sanitised reason.
            traceback.print_exc()
            self.emit(_error_event(error))
        else:
            self.emit({'type': 'result', 'report': report})
        finally:
            reset_investigation_scope(observer_token)
            reset_cancellation_scope(cancel_token)
            self.emit({'type': 'end'})


def _error_event(error: Exception) -> dict:
    if isinstance(error, (GeminiError, OllamaError)) or hasattr(error, 'kind'):
        return {'type': 'error', 'message': str(error), 'kind': getattr(error, 'kind', 'analysis_incomplete')}
    return {'type': 'error', 'message': f'分析未完成：{error}', 'kind': 'analysis_incomplete'}


def _sse(event: dict) -> str:
    return 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'


def stream_investigation(request: InvestigationRequest):
    """Run one investigation and yield its SSE frames as they happen.

    Closing this generator — the reader disconnected, or stopped on purpose —
    cancels the investigation, so no worker keeps making model calls for a
    report nobody is waiting for.
    """
    investigation = _Investigation(request)
    investigation.start()
    try:
        while True:
            try:
                event = investigation.events.get(timeout=1.0)
            except queue.Empty:
                # A heartbeat keeps the connection observable without inventing progress.
                yield ': waiting\n\n'
                continue
            yield _sse(event)
            if event['type'] == 'end':
                return
    finally:
        investigation.cancel()
