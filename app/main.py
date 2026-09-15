from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_ai, routes_analytics, routes_health, routes_machines, routes_reports, routes_sync
from app.database import init_database
from app.nl_query import answer_question
from app.scheduler import start_auto_sync, stop_auto_sync
from app.trackunit_sync import sync_fleet_snapshot
from app.api import routes_assistant, routes_drafts, routes_cases, routes_xgss, routes_fault_reference, routes_demo


app = FastAPI(
    title="Trackunit AI Analyzer",
    description="Trackunit telematics data analysis and fleet intelligence API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assistant-ui", StaticFiles(directory=Path(__file__).parent / "assistant_ui", html=True), name="assistant-ui")

for router in (
    routes_demo.router,
    routes_fault_reference.router,
    routes_xgss.router,
    routes_cases.router,
    routes_drafts.router,
    routes_assistant.router,
    routes_health.router,
    routes_sync.router,
    routes_analytics.router,
    routes_reports.router,
    routes_machines.router,
    routes_ai.router,
):
    app.include_router(router)


@app.on_event("startup")
async def start_optional_auto_sync() -> None:
    init_database()
    start_auto_sync(sync_fleet_snapshot)


@app.on_event("shutdown")
async def stop_optional_auto_sync() -> None:
    stop_auto_sync()
