from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.request_data_mode import set_mode, reset_mode

from app.api import routes_ai, routes_analytics, routes_health, routes_machines, routes_reports, routes_sync
from app.database import init_database
from app.nl_query import answer_question
from app.scheduler import start_auto_sync, stop_auto_sync
from app.trackunit_sync import sync_fleet_snapshot
from app.api import routes_assistant, routes_drafts, routes_cases, routes_xgss, routes_fault_reference, routes_demo, routes_xgss_context
from app.api import routes_platform_asset, routes_can_replay, routes_xgss_research, routes_research_email
from app.api import routes_fault_events, routes_sensor_series


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


@app.middleware('http')
async def request_data_mode(request, call_next):
    mode = request.headers.get('x-jilian-data-mode')
    if mode not in (None, 'demo', 'live'):
        return JSONResponse({'detail':'Unknown data mode'}, status_code=400)
    token = set_mode(mode)
    try:
        return await call_next(request)
    finally:
        reset_mode(token)

app.mount("/assistant-ui", StaticFiles(directory=Path(__file__).parent / "assistant_ui", html=True), name="assistant-ui")

# Serve the side panel over the same origin as the workbench so a local check can drive
# both together. Only the files the panel itself loads are exposed: the manifest and the
# icons are deliberately left out, since publishing them would hand out the extension id
# and the icon set for no benefit to anyone running this locally.
_PANEL_FILES = {
    'panel.html': 'text/html; charset=utf-8',
    'panel.js': 'application/javascript; charset=utf-8',
    'panel.css': 'text/css; charset=utf-8',
    'context.js': 'application/javascript; charset=utf-8',
    'xgss-catalog.js': 'application/javascript; charset=utf-8',
    'xgss-research-runner.js': 'application/javascript; charset=utf-8',
    'research-bridge.js': 'application/javascript; charset=utf-8',
    'trackunit-sensor-page.js': 'application/javascript; charset=utf-8',
    'sensor-series-bridge.js': 'application/javascript; charset=utf-8',
    'assets/xcmg-logo.png': 'image/png',
}
_EXTENSION_DIR = Path(__file__).resolve().parents[1] / "extension"


@app.get("/panel-preview/{relative_path:path}")
def panel_preview(relative_path: str):
    """Read-only preview of the side panel for the local probes."""
    media_type = _PANEL_FILES.get(relative_path)
    if media_type is None:
        raise HTTPException(404, "Not part of the panel preview")
    path = _EXTENSION_DIR / relative_path
    if not path.is_file():
        raise HTTPException(404, "Panel file missing")
    return Response(path.read_bytes(), media_type=media_type,
                    headers={'Cache-Control': 'no-store'})

for router in (
    routes_sensor_series.router,
    routes_fault_events.router,
    routes_research_email.router,
    routes_xgss_research.router,
    routes_can_replay.router,
    routes_demo.router,
    routes_fault_reference.router,
    routes_xgss.router,
    routes_xgss_context.router,
    routes_platform_asset.router,
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
