"""
tradesteward_fetch.py
=====================
Pulls daily bot-trade P&L directly from TradeSteward's report endpoint and
aggregates it by strategy — the same numbers shown in the "Strategy Profits
and Open Premium" panel on the Historical Dashboards page.

This replaces the screenshot -> Claude-vision -> parse step entirely. The
endpoint returns structured JSON, so results are exact and free.

Endpoint (discovered from the page's XHR):
    GET https://www.tradesteward.com/ajax
        ?action=reports_botAjaxReport
        &date=YYYY-MM-DD
        &accountNum=all
        &_=<epoch_ms cache-buster>
    -> {"data": [ {per-bot-trade record}, ... ]}

Auth is a normal logged-in session, but TradeSteward's session cookie is
session-only (dropped when the browser process exits) and a remembered
device still triggers a passkey prompt on sign-in — so a session can't be
saved once and reused headlessly across separate runs. Instead each run
opens a real (headed) browser once at the start; you sign in there (passkey
or password), and that same session then carries the rest of the run.
Fully headless (headless=True) only works if a session already happens to be
live in that on-disk profile, which in practice it won't be. No credentials
are ever stored by this script.

Pure functions (parse_money, aggregate_by_strategy, aggregate_by_account_strategy)
have no network dependency and are unit-tested in validate_against_panel.py.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

ENDPOINT = "https://www.tradesteward.com/ajax"
DASHBOARD_URL = "https://www.tradesteward.com/trading/"  # logged-in dashboard (redirects to login if signed out)
PROFILE_DIR = Path.home() / ".tradesteward_profile"      # persisted browser session lives here


# --------------------------------------------------------------------------- #
# Pure parsing / aggregation  (no network — safe to unit test)
# --------------------------------------------------------------------------- #
def parse_money(s: str) -> float:
    """'-$1,410.00' -> -1410.0 ; '$2,690.00' -> 2690.0 ; '($20.00)' -> -20.0"""
    s = s.strip()
    negative = s.startswith("-") or s.startswith("(")
    for ch in "$,()-":
        s = s.replace(ch, "")
    s = s.strip()
    if not s:
        return 0.0
    value = float(s)
    return -value if negative else value


def extract_trades(payload: dict) -> list[dict]:
    """Flatten the endpoint payload into simple per-trade dicts."""
    trades = []
    for row in payload.get("data", []):
        trades.append(
            {
                "serial": row.get("botTradeSerial"),
                "strategy": (row.get("strategy") or "").strip(),
                "account": (row.get("accountName") or "").strip(),
                "bot": (row.get("botName") or "").strip(),
                "profit": parse_money(row.get("profitDollars", {}).get("value", "0")),
            }
        )
    return trades


def aggregate_by_strategy(trades: list[dict]) -> dict[str, float]:
    """{strategy: total_profit} — matches the dashboard's 'All Accounts' panel."""
    out: dict[str, float] = defaultdict(float)
    for t in trades:
        out[t["strategy"]] += t["profit"]
    return dict(out)


def aggregate_by_account_strategy(trades: list[dict]) -> dict[tuple[str, str], float]:
    """{(account, strategy): total_profit} — for splitting Main vs Second vs x023."""
    out: dict[tuple[str, str], float] = defaultdict(float)
    for t in trades:
        out[(t["account"], t["strategy"])] += t["profit"]
    return dict(out)


# --------------------------------------------------------------------------- #
# Network layer  (Playwright, persistent auth)
# --------------------------------------------------------------------------- #
def _build_url(day: date) -> str:
    return (
        f"{ENDPOINT}?action=reports_botAjaxReport"
        f"&date={day.isoformat()}"
        f"&accountNum=all"
        f"&_={int(time.time() * 1000)}"
    )


def _looks_authenticated(payload_text: str) -> bool:
    """Endpoint returns JSON with a 'data' key when logged in; HTML (a login
    page) when not."""
    try:
        return "data" in json.loads(payload_text)
    except (json.JSONDecodeError, TypeError):
        return False


class TradeStewardClient:
    """Context manager holding one authenticated browser session."""

    def __init__(self, headless: bool = False, profile_dir: Path = PROFILE_DIR):
        self.headless = headless
        self.profile_dir = profile_dir
        self._pw = None
        self._ctx = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        # Persistent context = a real profile on disk; cookies survive across runs.
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
        )
        return self

    def __exit__(self, *exc):
        if self._ctx:
            self._ctx.close()
        if self._pw:
            self._pw.stop()

    def ensure_logged_in(
        self,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
        on_waiting: Callable[[], None] | None = None,
    ):
        """Probe the endpoint; if not authenticated, open the login page and
        poll until the user signs in (handles MFA/passkey) or `timeout`
        elapses. Only meaningful with headless=False.

        No keypress is required: the auth probe is the real signal (a
        passkey ceremony completing is what we're actually waiting on), so
        we just poll it directly instead of waiting on a terminal input()
        that a non-terminal caller (e.g. a web backend) couldn't provide.
        """
        probe = self._ctx.request.get(_build_url(date.today()))
        if _looks_authenticated(probe.text()):
            return

        if self.headless:
            raise RuntimeError(
                "Not logged in and running headless. TradeSteward's session "
                "doesn't persist across runs, so headless mode can't sign in — "
                "re-run with headless=False (the default) instead."
            )

        page = self._ctx.new_page()
        page.goto(DASHBOARD_URL)
        if on_waiting:
            on_waiting()

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(poll_interval)
            probe = self._ctx.request.get(_build_url(date.today()))
            if _looks_authenticated(probe.text()):
                page.close()
                return
        page.close()
        raise TimeoutError(
            f"Not signed in after {timeout:.0f}s. The TradeSteward window is "
            "still open — finish signing in there and retry."
        )

    def fetch_day(self, day: date) -> list[dict]:
        resp = self._ctx.request.get(_build_url(day))
        text = resp.text()
        if not _looks_authenticated(text):
            raise RuntimeError(f"Auth lost while fetching {day}. Re-run with --login.")
        return extract_trades(json.loads(text))


# --------------------------------------------------------------------------- #
# High-level helpers
# --------------------------------------------------------------------------- #
def weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon-Fri
            yield d
        d += timedelta(days=1)


def _print_waiting():
    print(
        "\n>>> A TradeSteward sign-in window opened — log in there (passkey or "
        "password). Waiting for it to complete...\n"
    )


def fetch_range(start: date, end: date, headless: bool = False) -> dict[str, dict]:
    """{ 'YYYY-MM-DD': {strategy: total} } across a weekday range."""
    results: dict[str, dict] = {}
    with TradeStewardClient(headless=headless) as client:
        client.ensure_logged_in(on_waiting=_print_waiting)
        for day in weekdays(start, end):
            trades = client.fetch_day(day)
            if trades:  # skip holidays / empty days
                results[day.isoformat()] = aggregate_by_strategy(trades)
    return results


# --------------------------------------------------------------------------- #
# Integration hook — where this meets the existing app
# --------------------------------------------------------------------------- #
# aggregate_by_strategy() returns {tradesteward_label: total}. The existing app
# already owns the label->sheet mapping (the Mappings tab / label_to_sheet dict)
# and the SQLite write. So the wiring is literally:
#
#     from tradesteward_fetch import fetch_range          # or fetch a single day
#     import database
#     for day, strat_totals in fetch_range(start, end).items():
#         sheet_values, unmapped = database.map_to_sheets(strat_totals)
#         database.save_day(day, sheet_values)
#         if unmapped:
#             print(f"{day}: unmapped labels -> {unmapped}")   # surface, never drop
#
# i.e. this file drops straight into the parser.py slot; everything downstream
# (mapping, SQLite, xlsx export) is unchanged.


def main():
    ap = argparse.ArgumentParser(description="Fetch TradeSteward daily P&L by strategy.")
    ap.add_argument("--login", action="store_true", help="Headed run to sign in once.")
    ap.add_argument("--day", help="Single date YYYY-MM-DD.")
    ap.add_argument("--start", help="Backfill start YYYY-MM-DD.")
    ap.add_argument("--end", help="Backfill end YYYY-MM-DD (default: today).")
    ap.add_argument("--by-account", action="store_true", help="Split by account.")
    args = ap.parse_args()

    if args.login:
        with TradeStewardClient(headless=False) as client:
            client.ensure_logged_in(on_waiting=_print_waiting)
            print(">>> Signed in.\n")
        return

    if args.day:
        d = date.fromisoformat(args.day)
        with TradeStewardClient(headless=False) as client:
            client.ensure_logged_in(on_waiting=_print_waiting)
            trades = client.fetch_day(d)
        if args.by_account:
            agg = aggregate_by_account_strategy(trades)
            for (acct, strat), v in sorted(agg.items()):
                print(f"{acct:16} {strat:32} {v:>12,.2f}")
        else:
            for strat, v in sorted(aggregate_by_strategy(trades).items()):
                print(f"{strat:32} {v:>12,.2f}")
        return

    if args.start:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else date.today()
        results = fetch_range(start, end)
        print(json.dumps(results, indent=2))
        return

    ap.print_help()


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------- #
# Convenience: one-shot day fetch for callers that just want {strategy: total}
# (used by the Streamlit app and by ingest.py). Opens a browser session
# reusing the saved profile; headless=False by default since the site
# requires a fresh sign-in per process (see module docstring).
# --------------------------------------------------------------------------- #
def fetch_day_totals(
    day: date, headless: bool = False, on_waiting: Callable[[], None] | None = None
) -> dict[str, float]:
    with TradeStewardClient(headless=headless) as client:
        client.ensure_logged_in(on_waiting=on_waiting)
        return aggregate_by_strategy(client.fetch_day(day))
