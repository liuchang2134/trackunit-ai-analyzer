import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.core.config import settings


AutoSyncCallable = Callable[[], dict[str, Any]]

_task: asyncio.Task | None = None
_state: dict[str, Any] = {
    "enabled": False,
    "running": False,
    "interval_seconds": 300,
    "last_run_at": None,
    "next_run_at": None,
    "last_result": None,
    "error": None,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def auto_sync_status() -> dict[str, Any]:
    return dict(_state)


async def _loop(sync_func: AutoSyncCallable) -> None:
    interval = settings.trackunit_sync_interval_seconds
    run_on_start = settings.trackunit_auto_sync_run_on_start
    _state.update({
        "enabled": True,
        "interval_seconds": interval,
        "next_run_at": (_utc_now() if run_on_start else _utc_now() + timedelta(seconds=interval)).isoformat(),
    })

    while True:
        if not run_on_start:
            await asyncio.sleep(interval)
        run_on_start = False
        _state.update({"running": True, "error": None})
        try:
            result = await asyncio.to_thread(sync_func)
            _state.update({
                "last_run_at": _utc_now().isoformat(),
                "last_result": result,
            })
        except Exception as exc:
            _state.update({
                "last_run_at": _utc_now().isoformat(),
                "error": str(exc),
            })
        finally:
            _state.update({
                "running": False,
                "next_run_at": (_utc_now() + timedelta(seconds=interval)).isoformat(),
            })


def start_auto_sync(sync_func: AutoSyncCallable) -> None:
    global _task
    enabled = settings.trackunit_auto_sync_enabled
    interval = settings.trackunit_sync_interval_seconds
    _state.update({"enabled": enabled, "interval_seconds": interval})
    if enabled and _task is None:
        _task = asyncio.create_task(_loop(sync_func))


def stop_auto_sync() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
    _state.update({"running": False})
