from fastapi import APIRouter

from app.data_store import cache_status, get_data_source
from app.database import get_database_status


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "phase": "live-ai-prototype", "data_source": get_data_source()}


@router.get("/data/source")
def get_current_data_source():
    return {"data_source": get_data_source()}


@router.get("/cache/status")
def get_cache_status():
    return cache_status()


@router.get("/database/status")
def get_db_status():
    return get_database_status()
