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
opens a real (headed) browser once at the start; you sign in there, and
that same session then carries the rest of the run. Fully headless
(headless=True) only works if a session already happens to be live in that
on-disk profile, which in practice it won't be.

Run `python tradesteward_fetch.py --set-credentials` once to store your
email/password in Windows Credential Manager (via `keyring` -- never written
to disk in plaintext). After that, ensure_logged_in() auto-fills and submits
the login form itself instead of waiting on you to type it in; Chrome's
native passkey/WebAuthn popup that the email field otherwise triggers is
dismissed automatically before typing. If TradeSteward demands a passkey/MFA
step anyway (e.g. a new/unrecognized browser profile), it falls back to the
normal manual flow on the same window.

Pure functions (parse_money, aggregate_by_strategy, aggregate_by_account_strategy)
have no network dependency and are unit-tested in validate_against_panel.py.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

MONTH_ABBR = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
_OPEN_TIME_RE = re.compile(r"^\w+ (\w+) (\d+) ")
_LEG_RE = re.compile(r"^(-?\d+)\s+\S+\s+.*?(\d+(?:\.\d+)?)([CP])$")
_DOLLAR_STOP_RE = re.compile(r"^\$([\d.,]+)\s+Loss$", re.I)
_PCT_STOP_RE = re.compile(r"^([\d.]+)%\s+Loss$", re.I)
_POINTS_STOP_RE = re.compile(r"^([\d.]+)\s+Points?\s+ITM$", re.I)
_STOP_AT_RE = re.compile(r"Stop at \$([\d.,]+)", re.I)
_OPEN_CREDIT_RE = re.compile(r"Open:.*?\$([\d.,]+)\s+Credit", re.I | re.S)

ENDPOINT = "https://www.tradesteward.com/ajax"
DASHBOARD_URL = "https://www.tradesteward.com/trading/"  # logged-in dashboard (redirects to login if signed out)
PROFILE_DIR = Path.home() / ".tradesteward_profile"      # persisted browser session lives here

# Credential storage: Windows Credential Manager via `keyring`, never plaintext
# on disk. The email is stored as a keyring "username" alongside the service
# name so `--set-credentials` only has to be run once per machine.
KEYRING_SERVICE = "tradesteward_fetch"
KEYRING_EMAIL_KEY = "__email__"


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


def parse_open_month_day(format_time: str) -> tuple[int, int] | None:
    """'Mon May 18 9:31:27a' -> (5, 18). Returns None if unparseable."""
    m = _OPEN_TIME_RE.match(format_time or "")
    if not m:
        return None
    month = MONTH_ABBR.get(m.group(1))
    if month is None:
        return None
    return (month, int(m.group(2)))


def extract_trades(payload: dict) -> list[dict]:
    """Flatten the endpoint payload into simple per-trade dicts.

    The endpoint returns every trade still open as of the requested date,
    not just trades opened that day — a trade held overnight shows up on
    every day it remains open. `open_month_day` carries the trade's actual
    open date so callers can filter to "opened this day" and avoid counting
    the same trade's P&L on multiple days.
    """
    trades = []
    for row in payload.get("data", []):
        trades.append(
            {
                "serial": row.get("botTradeSerial"),
                "strategy": (row.get("strategy") or "").strip(),
                "account": (row.get("accountName") or "").strip(),
                "bot": (row.get("botName") or "").strip(),
                "profit": parse_money(row.get("profitDollars", {}).get("value", "0")),
                "open_month_day": parse_open_month_day((row.get("openTime") or {}).get("formatTime", "")),
            }
        )
    return trades


def extract_positions(payload: dict) -> list[dict]:
    """Flatten the endpoint payload (fetched with openOnly=1) into simple
    per-position dicts matching the dashboard's 'Current Bot Positions'
    panel: still-open trades with live stop/profit targets and running P&L.
    """
    positions = []
    for row in payload.get("data", []):
        legs = [p.get("symbol", "").replace("&nbsp;", "").strip() for p in row.get("positions", [])]
        stop = row.get("stopSetting", {})
        profit = row.get("profitSetting", {})
        dollars = row.get("profitDollars", {})
        pct_info = row.get("profitPercent", {})
        positions.append(
            {
                "serial": row.get("botTradeSerial"),
                "strategy": (row.get("strategy") or "").strip(),
                "bot_name": (row.get("botName") or "").strip(),
                "account": (row.get("accountName") or "").strip(),
                "symbol": (row.get("symbol") or "").strip(),
                "open_time": (row.get("openTime") or {}).get("formatTime", ""),
                "days_in_trade": (row.get("openTime") or {}).get("daysInTrade"),
                "legs": legs,
                "stop_target": stop.get("target", ""),
                "profit_target": profit.get("target", ""),
                "open_price": row.get("openPrice", ""),
                "profit_pct": pct_info.get("value", ""),
                "profit_pct_style": pct_info.get("style", ""),
                "profit_dollars": dollars.get("value", ""),
                "profit_dollars_style": dollars.get("style", ""),
                "max_profit": dollars.get("maxProfit", ""),
                "max_loss": dollars.get("maxLoss", ""),
                "stop_closest_strike": stop.get("closestStrike", ""),
            }
        )
    return positions


def parse_leg(leg: str) -> dict | None:
    """'-1 SPX Aug 18 2026 7695P' -> {'qty': -1, 'strike': 7695.0, 'type': 'P'}.
    None if the string doesn't match the expected '<signed qty> <symbol> ... <strike><C|P>' shape."""
    m = _LEG_RE.match(leg.strip())
    if not m:
        return None
    return {"qty": int(m.group(1)), "strike": float(m.group(2)), "type": m.group(3)}


def resolve_stop_barrier(position: dict, leg: dict) -> dict | None:
    """Turn a position's stop_target into a concrete barrier for one of its
    short legs, in whichever unit that stop type is naturally defined:

    - "$X Loss"    -> {'kind': 'option_price', 'price': entry + X}. Uses
      TradeSteward's own computed trigger price from stop_closest_strike
      ("...; Stop at $Y") directly when available (authoritative, no
      re-derivation), falling back to entry_credit + X if that field is
      ever missing.
    - "X% Loss"    -> {'kind': 'option_price', 'price': entry * (1 + X/100)}.
      Derived (TradeSteward doesn't expose a fixed $ target for this type,
      only a live "% Loss so far" reading) -- there's nothing for us to
      cross-check this against except that live reading, which is a
      snapshot of current distance, not a stored target.
    - "N Points ITM" -> {'kind': 'spot_price', 'price': strike -+ N}. This
      stop type's trigger already *is* a fixed SPX level (how far the
      strike is breached), so no option pricing is involved at all.
    - "None" / unrecognized -> None (no stop set, or a format we don't
      parse yet).

    entry credit comes from open_price ("Open: $X Credit..."); a position
    missing that (shouldn't happen for a short leg) also returns None.
    """
    target = (position.get("stop_target") or "").strip()
    if not target or target.lower() == "none":
        return None

    m = _DOLLAR_STOP_RE.match(target)
    if m:
        amount = float(m.group(1).replace(",", ""))
        closest = position.get("stop_closest_strike", "") or ""
        stop_at = _STOP_AT_RE.search(closest)
        if stop_at:
            return {"kind": "option_price", "price": float(stop_at.group(1).replace(",", ""))}
        entry = _OPEN_CREDIT_RE.search(position.get("open_price", "") or "")
        if not entry:
            return None
        return {"kind": "option_price", "price": float(entry.group(1).replace(",", "")) + amount}

    m = _PCT_STOP_RE.match(target)
    if m:
        pct = float(m.group(1))
        entry = _OPEN_CREDIT_RE.search(position.get("open_price", "") or "")
        if not entry:
            return None
        entry_credit = float(entry.group(1).replace(",", ""))
        return {"kind": "option_price", "price": entry_credit * (1 + pct / 100)}

    m = _POINTS_STOP_RE.match(target)
    if m:
        points = float(m.group(1))
        # A short call is breached (ITM) above its strike; a short put below.
        sign = 1 if leg["type"] == "C" else -1
        return {"kind": "spot_price", "price": leg["strike"] + sign * points}

    return None


def short_strikes_by_side(position: dict) -> dict[str, list[dict]]:
    """Split a position's short (qty < 0) legs into {'C': [...], 'P': [...]}."""
    out: dict[str, list[dict]] = {"C": [], "P": []}
    for leg_str in position.get("legs", []):
        leg = parse_leg(leg_str)
        if leg and leg["qty"] < 0:
            out[leg["type"]].append(leg)
    return out


def aggregate_short_strikes(positions: list[dict]) -> list[dict]:
    """Group every open position's short legs by strike, splitting each
    position's captured-so-far $ (current running P&L), remaining-to-capture
    $ (max profit ceiling minus what's already captured), and at-risk $
    (max loss) between its call side and put side.

    A position's running P&L (profit_dollars) climbs from 0 toward its
    max_profit ceiling as the trade decays favorably -- "captured so far" is
    that running value (floored at 0; a position currently underwater hasn't
    captured anything yet), and "remaining" is max_profit minus that, which
    naturally exceeds max_profit while the position is underwater (there's
    more than the full ceiling left to go until breakeven, then capture).

    - A one-sided position (short legs on only one side -- e.g. a vertical)
      puts its full captured/remaining/at-risk on that side.
    - A two-sided position (short legs on both call and put side -- e.g. an
      iron condor) splits 50/50 between the two sides, since TradeSteward
      only reports these figures per whole position, not per leg.

    Within a side, a position's $ is further split across its legs there in
    proportion to each leg's short quantity (matters for e.g. an unbalanced
    1x2 spread).

    Returns strike rows sorted (puts first, then calls, each ascending by
    strike), each with combined qty and summed $ from every position sharing
    that strike.
    """
    rows: dict[tuple[str, float], dict] = {}
    for pos in positions:
        sides = short_strikes_by_side(pos)
        has_call = bool(sides["C"])
        has_put = bool(sides["P"])
        share = 0.5 if (has_call and has_put) else 1.0

        max_profit = abs(parse_money(pos.get("max_profit", "0") or "0"))
        at_risk = abs(parse_money(pos.get("max_loss", "0") or "0"))
        captured = max(parse_money(pos.get("profit_dollars", "0") or "0"), 0.0)
        remaining = max_profit - captured

        bot_name_upper = (pos.get("bot_name") or "").upper()
        is_bic = "BIC" in bot_name_upper
        is_elmo = "PAIC" in bot_name_upper

        for side, legs in sides.items():
            if not legs:
                continue
            side_qty = sum(-leg["qty"] for leg in legs)  # short qty as positive contracts
            for leg in legs:
                key = (side, leg["strike"])
                row = rows.setdefault(
                    key,
                    {
                        "type": side,
                        "strike": leg["strike"],
                        "qty": 0,
                        "captured": 0.0,
                        "remaining": 0.0,
                        "at_risk": 0.0,
                        "positions": 0,
                        "is_bic": False,
                        "is_elmo": False,
                    },
                )
                leg_qty = -leg["qty"]
                row["qty"] += leg_qty
                if side_qty:
                    frac = share * (leg_qty / side_qty)
                    row["captured"] += captured * frac
                    row["remaining"] += remaining * frac
                    row["at_risk"] += at_risk * frac
                row["positions"] += 1
                row["is_bic"] = row["is_bic"] or is_bic
                row["is_elmo"] = row["is_elmo"] or is_elmo

    return sorted(rows.values(), key=lambda r: (r["type"] == "C", r["strike"]))


def trades_opened_on(trades: list[dict], day: date) -> list[dict]:
    """Filter to trades whose openTime falls on `day` — matches TradeSteward's
    'opened today' panel and avoids double-counting overnight holdovers."""
    target = (day.month, day.day)
    return [t for t in trades if t["open_month_day"] == target]


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


def _build_positions_url() -> str:
    """Current Bot Positions panel: same action as the daily report, but
    openOnly=1 in place of a date -- returns still-open trades with live
    stop/profit targets and running P&L instead of one settled day."""
    return f"{ENDPOINT}?action=reports_botAjaxReport&openOnly=1&accountNum=all&_={int(time.time() * 1000)}"


def _looks_authenticated(payload_text: str) -> bool:
    """Endpoint returns JSON with a 'data' key when logged in; HTML (a login
    page) when not."""
    try:
        return "data" in json.loads(payload_text)
    except (json.JSONDecodeError, TypeError):
        return False


def _load_saved_credentials() -> tuple[str, str] | None:
    """(email, password) from Windows Credential Manager, if previously
    stored via --set-credentials. Never touches disk in plaintext."""
    import keyring

    email = keyring.get_password(KEYRING_SERVICE, KEYRING_EMAIL_KEY)
    if not email:
        return None
    password = keyring.get_password(KEYRING_SERVICE, email)
    if not password:
        return None
    return email, password


def save_credentials(email: str, password: str) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, KEYRING_EMAIL_KEY, email)
    keyring.set_password(KEYRING_SERVICE, email, password)


def clear_saved_credentials() -> None:
    import keyring

    email = keyring.get_password(KEYRING_SERVICE, KEYRING_EMAIL_KEY)
    if email:
        try:
            keyring.delete_password(KEYRING_SERVICE, email)
        except keyring.errors.PasswordDeleteError:
            pass
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_EMAIL_KEY)
        except keyring.errors.PasswordDeleteError:
            pass


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

        # Reuse the blank page launch_persistent_context already created
        # rather than opening a second one -- a persistent context needs at
        # least one open page to stay alive, so a second page here would
        # leave the original blank window behind with nothing left to close
        # it once login succeeds.
        page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

        creds = _load_saved_credentials()
        if creds:
            email, password = creds
            if on_waiting:
                on_waiting()
            if self._try_autofill_login(page, email, password, timeout=timeout):
                probe = self._ctx.request.get(_build_url(date.today()))
                if _looks_authenticated(probe.text()):
                    page.goto("about:blank")
                    self._minimize(page)
                    return
            # Auto-fill didn't get us logged in (e.g. TradeSteward is forcing
            # a passkey/MFA step this time) -- fall through to manual login
            # on the same page instead of failing outright.
        else:
            page.goto(DASHBOARD_URL)
            if on_waiting:
                on_waiting()

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(poll_interval)
            probe = self._ctx.request.get(_build_url(date.today()))
            if _looks_authenticated(probe.text()):
                page.goto("about:blank")
                self._minimize(page)
                return
        page.close()
        raise TimeoutError(
            f"Not signed in after {timeout:.0f}s. The TradeSteward window is "
            "still open — finish signing in there and retry."
        )

    def _minimize(self, page) -> None:
        """Minimize the (now-blank, no-longer-needed) sign-in window via CDP.
        The page/context must stay open -- closing the last page in a
        persistent context ends the whole browser process -- so this just
        gets it out of the way instead."""
        try:
            cdp = self._ctx.new_cdp_session(page)
            window_id = cdp.send("Browser.getWindowForTarget")["windowId"]
            cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": "minimized"}})
        except Exception:
            pass

    def _try_autofill_login(self, page, email: str, password: str, timeout: float = 300.0) -> bool:
        """Fill and submit the login form with saved credentials. Returns
        True if the form was submitted (caller still re-probes auth after --
        TradeSteward may reject the password or demand MFA).

        On a profile with a remembered device, the page shows a "Welcome
        back, <email>" state with the email field hidden entirely (email
        comes from a cookie, not the form) and only the password field
        eventually shown -- so #emailInput is skipped there. On a fresh
        profile the full email+password form shows instead.

        Either way, TradeSteward also triggers a native Windows Security
        ("Choose a passkey") dialog on page load. That dialog lives outside
        the page/browser entirely -- Playwright can't see or dismiss it, and
        it blocks the password field until a human clicks Cancel.
        wait_for_selector(state="visible") covers that: it just sits there
        until the field becomes interactable, which happens as soon as the
        dialog is cancelled.
        """
        login_url = "https://www.tradesteward.com/useracct/login"
        timeout_ms = timeout * 1000
        try:
            page.goto(login_url, wait_until="domcontentloaded")
            is_cookie_login = page.is_visible("#cookieLogin")
            if not is_cookie_login:
                page.fill("#emailInput", email, timeout=timeout_ms)
            page.wait_for_selector("#passwordInput", state="visible", timeout=timeout_ms)
            # Typing can get its keystrokes partially eaten -- observed
            # losing characters mid-type, most likely to Chrome's own "Save
            # password?" popup or similar UI stealing focus right as the
            # passkey dialog is dismissed. Verify the full value stuck and
            # retry (clearing first) rather than submitting a truncated
            # password, which TradeSteward rejects with no visible error.
            for _ in range(5):
                page.fill("#passwordInput", "")
                page.type("#passwordInput", password, delay=60)
                if page.input_value("#passwordInput") == password:
                    break
                page.wait_for_timeout(400)
            if page.input_value("#passwordInput") != password:
                return False
            if page.is_visible("#rememberUser") and not page.is_checked("#rememberUser"):
                page.check("#rememberUser")
            page.click("input[type=submit]", timeout=timeout_ms)
            page.wait_for_load_state("domcontentloaded")
            return True
        except Exception:
            return False

    def fetch_day(self, day: date) -> list[dict]:
        """Trades opened on `day` only — the endpoint also includes trades
        opened on prior days that are still open, which would otherwise get
        counted again on every day they remain open."""
        resp = self._ctx.request.get(_build_url(day))
        text = resp.text()
        if not _looks_authenticated(text):
            raise RuntimeError(f"Auth lost while fetching {day}. Re-run with --login.")
        return trades_opened_on(extract_trades(json.loads(text)), day)

    def fetch_positions(self) -> list[dict]:
        """All currently-open bot positions, matching the dashboard's
        'Current Bot Positions' panel."""
        resp = self._ctx.request.get(_build_positions_url())
        text = resp.text()
        if not _looks_authenticated(text):
            raise RuntimeError("Auth lost while fetching open positions. Re-run with --login.")
        return extract_positions(json.loads(text))


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
    ap.add_argument(
        "--set-credentials",
        action="store_true",
        help="Store TradeSteward email/password in Windows Credential Manager "
        "so future logins auto-fill instead of requiring manual entry. "
        "Prompts for email and password (hidden input); never written to disk in plaintext.",
    )
    ap.add_argument("--clear-credentials", action="store_true", help="Remove saved credentials.")
    args = ap.parse_args()

    if args.set_credentials:
        import getpass

        email = input("TradeSteward email: ").strip()
        password = getpass.getpass("TradeSteward password: ")
        save_credentials(email, password)
        print(f">>> Saved credentials for {email} to Windows Credential Manager.")
        return

    if args.clear_credentials:
        clear_saved_credentials()
        print(">>> Cleared saved credentials.")
        return

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
# Shared long-lived client: TradeSteward re-challenges (passkey/password) on
# every new browser process, so a fresh TradeStewardClient per call means a
# fresh login prompt every time. Callers that make repeated single-day
# fetches within one backend process (the "Fetch this day" button) should
# reuse one client instead of logging in every time.
#
# Playwright's sync API binds its internal greenlet/event-loop machinery to
# the OS thread that created it, so the browser object can only ever be
# touched from that one thread — handing it to a different thread raises
# "cannot switch to a different thread (which happens to have exited)".
# The backend spawns a fresh thread per fetch-day request (see
# backend/routers/tradesteward.py), so a naively shared client breaks on the
# second request. Instead, the client lives on a single dedicated worker
# thread via a one-slot ThreadPoolExecutor, and every caller submits its work
# to that executor rather than touching the client directly — regardless of
# which thread the caller itself is running on.
# --------------------------------------------------------------------------- #
_worker = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="tradesteward-session")
_shared_client: TradeStewardClient | None = None


def _get_or_create_client(headless: bool) -> TradeStewardClient:
    global _shared_client
    if _shared_client is None:
        client = TradeStewardClient(headless=headless)
        client.__enter__()
        _shared_client = client
    return _shared_client


def _is_closed_context_error(exc: Exception) -> bool:
    msg = str(exc)
    return "has been closed" in msg or "disposed" in msg


def _fetch_day_totals_on_worker(
    day: date, headless: bool, on_waiting: Callable[[], None] | None
) -> dict[str, float]:
    global _shared_client
    client = _get_or_create_client(headless)
    try:
        client.ensure_logged_in(on_waiting=on_waiting)
        return aggregate_by_strategy(client.fetch_day(day))
    except Exception as e:
        if _is_closed_context_error(e):
            # The sign-in window (or its whole persistent context) was closed
            # manually instead of completing login -- the shared client is
            # dead. Tear it down properly (stops the underlying
            # sync_playwright() driver/dispatcher) rather than just dropping
            # the reference -- leaving the old driver running on this worker
            # thread makes the *next* sync_playwright().start() call fail
            # with "Sync API inside asyncio loop", since its dispatcher
            # thread/event loop is still alive underneath.
            try:
                client.__exit__(None, None, None)
            except Exception:
                pass
            _shared_client = None
            raise RuntimeError(
                "The TradeSteward sign-in window was closed before login "
                "completed. Please retry -- a new sign-in window will open."
            ) from e
        raise


def _fetch_positions_on_worker(
    headless: bool, on_waiting: Callable[[], None] | None
) -> list[dict]:
    global _shared_client
    client = _get_or_create_client(headless)
    try:
        client.ensure_logged_in(on_waiting=on_waiting)
        return client.fetch_positions()
    except Exception as e:
        if _is_closed_context_error(e):
            try:
                client.__exit__(None, None, None)
            except Exception:
                pass
            _shared_client = None
            raise RuntimeError(
                "The TradeSteward sign-in window was closed before login "
                "completed. Please retry -- a new sign-in window will open."
            ) from e
        raise


def close_shared_client():
    """Close the shared browser session, if one is open. Call on backend
    shutdown; a new fetch afterwards will open a fresh one (and re-prompt)."""
    def _close():
        global _shared_client
        if _shared_client is not None:
            _shared_client.__exit__(None, None, None)
            _shared_client = None

    _worker.submit(_close).result()


# --------------------------------------------------------------------------- #
# Convenience: one-shot day fetch for callers that just want {strategy: total}
# (used by the Streamlit app and by ingest.py). Runs on the dedicated
# long-lived session worker thread so repeated calls — even from different
# calling threads — reuse one browser session and only prompt for login once.
# See the "Shared long-lived client" section above.
# --------------------------------------------------------------------------- #
def fetch_day_totals(
    day: date, headless: bool = False, on_waiting: Callable[[], None] | None = None
) -> dict[str, float]:
    return _worker.submit(_fetch_day_totals_on_worker, day, headless, on_waiting).result()


def fetch_open_positions(
    headless: bool = False, on_waiting: Callable[[], None] | None = None
) -> list[dict]:
    """All currently-open bot positions (live P&L, stop/profit targets),
    reusing the shared session worker -- see 'Shared long-lived client' above."""
    return _worker.submit(_fetch_positions_on_worker, headless, on_waiting).result()
