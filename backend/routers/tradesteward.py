"""TradeSteward fetch/backfill endpoints. Both are long-running (a real headed
browser window + a human login are involved), so each spawns a background
thread and returns a job_id immediately; the frontend polls GET /jobs/{id}."""
import threading
from datetime import date

from fastapi import APIRouter, HTTPException

import database
import ingest
import parser as ss_parser
import tradesteward_fetch as tsf
from backend import jobs
from backend.schemas import BackfillRequest, FetchDayRequest

router = APIRouter(tags=["tradesteward"])


def _on_waiting(job_id: str):
    jobs.update_job(job_id, status="awaiting_login")
    jobs.append_log(job_id, "Sign-in window opened on your desktop — waiting for login...")


def _run_fetch_day(job_id: str, day: date):
    try:
        jobs.update_job(job_id, status="running")
        strat_totals = tsf.fetch_day_totals(day, headless=False, on_waiting=lambda: _on_waiting(job_id))
        jobs.update_job(job_id, status="running")

        lines = [{"label": k, "value": v} for k, v in strat_totals.items()]
        label_to_sheet = database.get_label_to_sheet()
        sheet_values, unmapped = ss_parser.aggregate_to_sheets(lines, label_to_sheet)
        result = {
            "sheet_values": sheet_values,
            "unmapped": unmapped,
            "day_total": sum(sheet_values.values()) + sum(u["value"] for u in unmapped),
        }
        jobs.update_job(job_id, status="done", result=result)
    except Exception as e:
        jobs.update_job(job_id, status="error", error=str(e))
    finally:
        jobs.finish_job(job_id)


@router.post("/tradesteward/fetch-day")
def fetch_day(body: FetchDayRequest):
    try:
        job = jobs.create_job("fetch-day")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    threading.Thread(target=_run_fetch_day, args=(job.id, body.trade_date), daemon=True).start()
    return {"job_id": job.id}


def _run_backfill(job_id: str, start: date, end: date | None):
    def on_progress(summary: dict):
        job = jobs.get_job(job_id)
        prog = dict(job.progress) if job else {}
        prog["last_day"] = summary["day"]
        prog["days_done"] = prog.get("days_done", 0) + 1
        jobs.update_job(job_id, status="running", progress=prog)
        if summary.get("empty"):
            jobs.append_log(job_id, f"{summary['day']}  (empty/holiday)")
        else:
            flag = f"  new sheet(s): {', '.join(summary['new_sheets'])}" if summary["new_sheets"] else ""
            jobs.append_log(job_id, f"{summary['day']}  saved  day P&L ${summary['day_total']:,.2f}{flag}")

    try:
        jobs.update_job(job_id, status="running")
        result = ingest.ingest_range(
            start, end, headless=False, on_waiting=lambda: _on_waiting(job_id), on_progress=on_progress
        )
        jobs.update_job(job_id, status="done", result=result)
    except Exception as e:
        jobs.update_job(job_id, status="error", error=str(e))
    finally:
        jobs.finish_job(job_id)


@router.post("/tradesteward/backfill")
def backfill(body: BackfillRequest):
    try:
        job = jobs.create_job("backfill")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    threading.Thread(target=_run_backfill, args=(job.id, body.start, body.end), daemon=True).start()
    return {"job_id": job.id}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Best-effort: marks the job cancelled so the frontend stops polling/showing
    # it as active. The background thread (mid Playwright call) isn't forcibly
    # interrupted -- it'll finish or error on its own; the browser window can
    # just be closed manually if needed.
    jobs.update_job(job_id, status="cancelled")
    jobs.finish_job(job_id)
    return {"ok": True}
