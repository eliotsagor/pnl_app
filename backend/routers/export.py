import io
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import database
import exporter

router = APIRouter(tags=["export"])

APP_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATE_PATH = APP_DIR / "template.xlsx"


@router.post("/export")
def export_xlsx():
    buf = io.BytesIO()
    exporter.export_to_xlsx(TEMPLATE_PATH, buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=PnL_Export.xlsx"},
    )


@router.get("/stats")
def stats():
    return {"days_with_data": len(database.get_dates_with_data())}
