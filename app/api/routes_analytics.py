from fastapi import APIRouter

from app.trend_analysis import get_fleet_trends


router = APIRouter()


@router.get("/analytics/trends")
def get_analytics_trends(days: int = 30):
    return get_fleet_trends(days)
