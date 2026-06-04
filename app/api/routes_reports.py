from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.report_exporter import build_fleet_excel_report, build_fleet_pdf_report


router = APIRouter()


@router.get("/reports/fleet/excel")
def download_fleet_excel_report(days: int = 30):
    path = build_fleet_excel_report(days)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/reports/fleet/pdf")
def download_fleet_pdf_report(days: int = 30):
    path = build_fleet_pdf_report(days)
    return FileResponse(path, filename=path.name, media_type="application/pdf")
