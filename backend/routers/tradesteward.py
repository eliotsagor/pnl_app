"""TradeSteward fetch/backfill endpoints. Both are long-running (a real headed
browser window + a human login are involved), so each spawns a background
thread and returns a job_id immediately; the frontend polls GET /jobs/{id}."""
import threading
from datetime import date

from fastapi import APIRouter, HTTPException

import database
import ingest
import parser as ss_parser
import quotes
import schwab_client
import tradesteward_fetch as tsf
from backend import jobs, snapshots
from backend.schemas import BackfillRequest, CompleteSchwabLoginRequest, FetchDayRequest, SaveSnapshotRequest

router = APIRouter(tags=["tradesteward"])


def _on_waiting(job_id: str):
    jobs.update_job(job_id, status="awaiting_login")
    jobs.append_log(
        job_id,
        "Sign-in window opened on your desktop — if a Windows Security "
        "passkey prompt appears, click Cancel on it; login then completes "
        "automatically.",
    )


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


def _run_fetch_positions(job_id: str):
    try:
        jobs.update_job(job_id, status="running")
        positions = tsf.fetch_open_positions(headless=False, on_waiting=lambda: _on_waiting(job_id))
        jobs.update_job(job_id, status="done", result={"positions": positions})
    except Exception as e:
        jobs.update_job(job_id, status="error", error=str(e))
    finally:
        jobs.finish_job(job_id)


@router.post("/tradesteward/positions")
def fetch_positions():
    try:
        job = jobs.create_job("fetch-positions")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    threading.Thread(target=_run_fetch_positions, args=(job.id,), daemon=True).start()
    return {"job_id": job.id}


def _run_fetch_risk(job_id: str):
    try:
        jobs.update_job(job_id, status="running")
        positions = tsf.fetch_open_positions(headless=False, on_waiting=lambda: _on_waiting(job_id))
        for pos in positions:
            name = (pos.get("bot_name") or "").upper()
            pos["is_bic"] = "BIC" in name
            pos["is_elmo"] = "PAIC" in name
            # Real $ given back from today's value if the stop triggers
            # (see position_give_back), not the static entry-based max_loss
            # -- exposed on the position itself so the frontend's client-side
            # strike re-aggregation (for the Elmo/BIC/Other and per-bot
            # filters) can split it across legs without duplicating this
            # scope-aware logic in TypeScript.
            give_back = tsf.position_give_back(pos)
            pos["at_risk"] = give_back if give_back is not None else abs(tsf.parse_money(pos.get("max_loss", "0") or "0"))
            # What's left to capture if this decays to worthless by expiry --
            # not max_profit-minus-captured, which reads 0 whenever
            # TradeSteward has no profit_target set (see
            # position_remaining_value). Also exposed for client-side
            # re-aggregation, same reasoning as at_risk above.
            remaining_value = tsf.position_remaining_value(pos)
            pos["remaining"] = remaining_value if remaining_value is not None else 0.0

        # Weight how much of a two-sided position's captured/remaining/at_risk
        # goes to each strike by each side's own live option value, instead
        # of a flat 50/50 -- TradeSteward only reports one combined $ figure
        # per position, but we do have each leg's own current price.
        try:
            chain = schwab_client.option_chain_lookup()
            side_weights = schwab_client.position_side_split_weights(positions, chain.get("contracts", {}))
            for pos in positions:
                w = side_weights.get(pos.get("serial"))
                if w is not None:
                    pos["side_split"] = w
        except Exception:
            side_weights = {}
        strikes = tsf.aggregate_short_strikes(positions, side_weights)
        try:
            quote = quotes.spx_quote()
        except Exception:
            quote = {}
        try:
            expected_move = schwab_client.spx_expected_move_remaining()
        except Exception:
            expected_move = {}
        try:
            stop_probs = schwab_client.stop_probabilities_by_strike(positions)
            for row in strikes:
                prob = stop_probs.get((row["strike"], row["type"]))
                if prob is not None:
                    row["stop_probability"] = prob
                    # Same model as the EV-of-holding table (position_expected_values),
                    # applied to this strike's own already-split remaining/at_risk
                    # rather than a whole position's: (1-p_stop) x what's left if it
                    # decays to worthless, minus p_stop x the real give-back to the
                    # stop. "not stopped" is realistic decay, not the full remaining
                    # ceiling, so this doesn't need a separate P(capture) estimate.
                    row["ev"] = (1 - prob) * row["remaining"] - prob * row["at_risk"]
        except Exception:
            pass  # stop-probability is best-effort; strikes still render without it
        try:
            greeks = schwab_client.net_greeks(positions)
        except Exception:
            greeks = {}
        try:
            position_ev = schwab_client.position_expected_values(positions)
            for pos in positions:
                ev = position_ev.get(pos.get("serial"))
                if ev is not None:
                    pos["stop_probability"] = ev["stop_probability"]
                    pos["stop_probability_by_side"] = ev["stop_probability_by_side"]
                    pos["ev"] = ev["ev"]
                    pos["delta"] = ev["delta"]
                    pos["gamma"] = ev["gamma"]
        except Exception:
            pass  # EV is best-effort; positions still render without it
        jobs.update_job(
            job_id,
            status="done",
            result={
                "strikes": strikes,
                "quote": quote,
                "expected_move": expected_move,
                "greeks": greeks,
                "positions": positions,
            },
        )
    except Exception as e:
        jobs.update_job(job_id, status="error", error=str(e))
    finally:
        jobs.finish_job(job_id)


@router.post("/tradesteward/risk")
def fetch_risk():
    try:
        job = jobs.create_job("fetch-risk")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    threading.Thread(target=_run_fetch_risk, args=(job.id,), daemon=True).start()
    return {"job_id": job.id}


@router.post("/tradesteward/risk/snapshots")
def save_risk_snapshot(body: SaveSnapshotRequest):
    job = jobs.get_job(body.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done" or job.result is None:
        raise HTTPException(status_code=409, detail="Job hasn't finished successfully yet")
    return snapshots.save_snapshot(job.result, body.label)


@router.get("/tradesteward/risk/snapshots")
def list_risk_snapshots():
    return snapshots.list_snapshots()


@router.get("/tradesteward/risk/snapshots/{snapshot_id}")
def get_risk_snapshot(snapshot_id: str):
    result = snapshots.load_snapshot(snapshot_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return result


@router.delete("/tradesteward/risk/snapshots/{snapshot_id}")
def delete_risk_snapshot(snapshot_id: str):
    if not snapshots.delete_snapshot(snapshot_id):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"ok": True}


@router.post("/schwab/login/begin")
def begin_schwab_login():
    """Step 1 of in-app Schwab re-auth: returns the authorization URL to
    open in a new tab, plus the state needed for step 2. No browser
    automation involved (unlike TradeSteward's flow) -- this just builds
    the URL; you complete the actual login/consent in your own browser tab
    and paste back the resulting redirect URL."""
    try:
        return schwab_client.begin_login_web()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/schwab/login/complete")
def complete_schwab_login(body: CompleteSchwabLoginRequest):
    """Step 2: exchanges the pasted redirect URL for a token. After this,
    the option-chain-backed figures (Stop%, EV, delta/gamma, expected
    move) on the Risk page start working again on the next fetch."""
    try:
        schwab_client.complete_login_web(body.received_url, body.state)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Login didn't complete: {e}")
    return {"ok": True}


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
