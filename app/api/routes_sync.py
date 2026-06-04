from fastapi import APIRouter
from pydantic import BaseModel

from app.data_store import load_sync_logs
from app.scheduler import auto_sync_status
from app.trackunit_sync import sync_faults, sync_fleet_snapshot, sync_time_series


router = APIRouter()


class DateRangeRequest(BaseModel):
    start_date: str
    end_date: str


@router.get("/sync/auto/status")
def get_auto_sync_status():
    return auto_sync_status()


@router.post("/sync/trackunit/fleet")
def sync_trackunit_fleet():
    return sync_fleet_snapshot()


@router.post("/sync/trackunit/timeseries")
def sync_trackunit_timeseries(request: DateRangeRequest):
    return sync_time_series(request.start_date, request.end_date)


@router.post("/sync/trackunit/faults")
def sync_trackunit_faults(request: DateRangeRequest):
    return sync_faults(request.start_date, request.end_date)


@router.get("/sync/logs")
def get_sync_logs():
    return load_sync_logs()
