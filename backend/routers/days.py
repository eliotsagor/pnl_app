from datetime import date

from fastapi import APIRouter, File, HTTPException, UploadFile

import database
import parser as ss_parser
from backend.schemas import AddToStrategyRequest, SaveDayRequest

router = APIRouter(tags=["days"])


@router.get("/strategies")
def strategies():
    return database.get_strategies()


@router.get("/day/{iso_date}")
def get_day(iso_date: date):
    data = database.get_day(iso_date)
    return {sheet: info["value"] for sheet, info in data.items()}


@router.post("/day/{iso_date}")
def save_day(iso_date: date, body: SaveDayRequest):
    database.save_day(iso_date, body.sheet_values)
    return {"ok": True}


@router.delete("/day/{iso_date}")
def delete_day(iso_date: date):
    database.save_day(iso_date, {})
    return {"ok": True}


@router.post("/day/{iso_date}/add-to-strategy")
def add_to_strategy(iso_date: date, body: AddToStrategyRequest):
    try:
        new_total = database.add_to_day(iso_date, body.sheet_name, body.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    day_total = sum(v["value"] for v in database.get_day(iso_date).values())
    return {"sheet_name": body.sheet_name, "new_total": new_total, "day_total": day_total}


@router.post("/screenshot/parse")
async def parse_screenshot(file: UploadFile = File(...)):
    image_bytes = await file.read()
    media_type = file.content_type or "image/png"
    try:
        parsed = ss_parser.parse_screenshot(image_bytes, media_type)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse failed: {e}")

    label_to_sheet = database.get_label_to_sheet()
    sheet_values, unmapped = ss_parser.aggregate_to_sheets(parsed["lines"], label_to_sheet)
    computed_total = sum(sheet_values.values()) + sum(u["value"] for u in unmapped)
    return {
        "lines": parsed["lines"],
        "total": parsed.get("total"),
        "sheet_values": sheet_values,
        "unmapped": unmapped,
        "computed_total": computed_total,
    }
