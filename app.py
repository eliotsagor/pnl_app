"""Streamlit UI for daily P&L tracking."""
import calendar as _calendar
from datetime import date, datetime
from pathlib import Path
import io
import os
import sys

import streamlit as st

import database
import parser as ss_parser
import exporter
import tradesteward_fetch as tsf
import ingest

APP_DIR = Path(__file__).parent
TEMPLATE_PATH = APP_DIR / "template.xlsx"

st.set_page_config(page_title="Daily P&L Tracker", layout="wide")

# ---------- Material-inspired theme polish ----------
# Palette: dark surface #1a1a19 on page plane #0d0d0d, accent blue #3987e5,
# status good #0ca30c / critical #d03b3b (validated dark-mode contrast pair).
st.markdown(
    """
    <style>
    html, body, [class*="css"] {
        font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    h1, h2, h3, h4 {
        font-weight: 500;
        letter-spacing: -0.01em;
    }

    /* Buttons: rounded, elevated, smooth hover */
    div[data-testid="stButton"] button,
    div[data-testid="stDownloadButton"] button,
    div[data-testid="stFormSubmitButton"] button {
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.10);
        box-shadow: 0 1px 3px rgba(0,0,0,0.35), 0 1px 2px rgba(0,0,0,0.24);
        transition: box-shadow 0.15s ease, transform 0.15s ease;
    }
    div[data-testid="stButton"] button:hover,
    div[data-testid="stDownloadButton"] button:hover,
    div[data-testid="stFormSubmitButton"] button:hover {
        box-shadow: 0 2px 6px rgba(0,0,0,0.45), 0 1px 3px rgba(0,0,0,0.3);
        transform: translateY(-1px);
    }

    /* Metrics as elevated cards */
    div[data-testid="stMetric"] {
        background: #1a1a19;
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.35), 0 1px 2px rgba(0,0,0,0.24);
    }

    /* Expanders */
    div[data-testid="stExpander"] {
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 12px;
        overflow: hidden;
    }

    /* Tabs: bolder active indicator */
    button[data-baseweb="tab"] {
        font-weight: 500;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #3987e5;
    }
    div[data-baseweb="tab-highlight"] {
        background-color: #3987e5;
        height: 3px;
        border-radius: 3px 3px 0 0;
    }

    /* Hide Streamlit's own chrome (Deploy button, kebab menu, footer) so the
       app doesn't visibly announce itself as a generic Streamlit app. */
    header[data-testid="stHeader"] { display: none; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }

    /* Top nav bar (segmented control) */
    div[data-testid="stSegmentedControl"] {
        background: #1a1a19;
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 12px;
        padding: 4px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }
    div[data-testid="stSegmentedControl"] label {
        border-radius: 9px !important;
        font-weight: 500;
    }

    /* Alert boxes: rounded with a left accent bar */
    div[data-testid="stAlert"] {
        border-radius: 10px;
        border-left-width: 4px;
        border-left-style: solid;
    }

    /* Forms as subtle cards */
    div[data-testid="stForm"] {
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 12px;
        padding: 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(":material/monitoring: Daily P&L Tracker")

# Initialise database on first run
database.init_db()
database.seed_if_empty()


# ---------- Top navigation ----------
_PAGES = {
    "Enter Day": ":material/edit_calendar:",
    "Custom Trades (FOMC etc.)": ":material/calculate:",
    "Calendar": ":material/calendar_month:",
    "Year View": ":material/table_chart:",
    "Mappings": ":material/route:",
    "Export": ":material/file_download:",
}
_page_options = list(_PAGES.keys())
# A calendar day-cell click is a real link (?day=...) -> full page reload ->
# fresh session, which would otherwise reset navigation to the first page.
_default_page = "Calendar" if st.query_params.get("day") else "Enter Day"
page = st.segmented_control(
    "Page",
    _page_options,
    format_func=lambda p: f"{_PAGES[p]} {p}",
    default=_default_page,
    label_visibility="collapsed",
)
if page is None:  # segmented_control allows deselect; keep the last page instead
    page = _default_page
st.write("")


# ---------- Helper: render the per-strategy editing form ----------
def render_day_editor(trade_date, sheet_values, unmapped=None, key_prefix="edit"):
    """Render an editable form for one day's values. Returns the dict of values on submit."""
    strategies = database.get_strategies()
    label_to_sheet = database.get_label_to_sheet()

    st.subheader(f"Values for {trade_date}")

    if unmapped:
        st.warning(f"{len(unmapped)} unmapped label(s). Add them in the Mappings tab.")
        for u in unmapped:
            st.text(f"  • {u['label']} = {u['value']}")

    edited = {}
    cols = st.columns(2)
    for i, s in enumerate(strategies):
        if s["sheet_name"] == "All BICs":
            continue  # All BICs is computed
        col = cols[i % 2]
        current = sheet_values.get(s["sheet_name"], 0.0)
        val = col.number_input(
            s["sheet_name"],
            value=float(current) if current else 0.0,
            step=1.0,
            format="%.2f",
            key=f"{key_prefix}_{s['id']}",
        )
        if val != 0.0:
            edited[s["sheet_name"]] = val

    # Live total preview
    if edited:
        # All BICs subtotal
        bic_sheets = {"BIC $6 $4", "BIC $4", "BIC $3", "BIC 1 DTE", "BIC Standard", "BIC Re-Entry"}
        all_bics = sum(v for sheet, v in edited.items() if sheet in bic_sheets)
        non_bic = sum(v for sheet, v in edited.items() if sheet not in bic_sheets)
        total = all_bics + non_bic
        st.metric("Live Total", f"${total:,.2f}", help=f"All BICs subtotal: ${all_bics:,.2f}")

    return edited


# ============================================================
# PAGE: Enter Day (screenshot upload + manual entry)
# ============================================================
if page == "Enter Day":
    col1, col2 = st.columns([1, 2])
    with col1:
        trade_date = st.date_input("Trade date", value=date.today())
    with col2:
        existing = database.get_day(trade_date)
        if existing:
            st.info(f"This date already has {len(existing)} entries. Saving will overwrite.")

    tab_fetch, tab_upload, tab_manual = st.tabs(
        [
            ":material/link: Fetch from TradeSteward",
            ":material/photo_camera: Upload Screenshot",
            ":material/edit: Manual Entry",
        ]
    )

    # ---------- Direct fetch from TradeSteward endpoint ----------
    with tab_fetch:
        st.caption(
            "Pulls the day's per-strategy P&L straight from TradeSteward — no "
            "screenshot, exact numbers. TradeSteward requires a fresh sign-in "
            "(passkey or password) each run, so this opens a browser window — "
            "log in there, then it continues automatically."
        )

        if st.button("Fetch this day", type="primary", icon=":material/link:", key="fetch_ts"):
            with st.spinner(f"Fetching {trade_date} from TradeSteward..."):
                try:
                    strat_totals = tsf.fetch_day_totals(trade_date)
                    lines = [{"label": k, "value": v} for k, v in strat_totals.items()]
                    label_to_sheet = database.get_label_to_sheet()
                    sheet_values, unmapped = ss_parser.aggregate_to_sheets(lines, label_to_sheet)
                    st.session_state["fetched"] = {
                        "sheet_values": sheet_values,
                        "unmapped": unmapped,
                        "day_total": sum(sheet_values.values()) + sum(u["value"] for u in unmapped),
                    }
                    st.session_state["fetched_date"] = trade_date
                    st.success(f"Fetched {len(strat_totals)} strategies")
                except Exception as e:
                    st.error(f"Fetch failed: {e}")
                    if "logged in" in str(e).lower() or "auth" in str(e).lower():
                        st.info("Run this once in a terminal, then retry:")
                        st.code("python tradesteward_fetch.py --login", language="bash")

        if "fetched" in st.session_state and st.session_state.get("fetched_date") == trade_date:
            f = st.session_state["fetched"]
            st.divider()
            st.metric("Day total (bot trades)", f"${f['day_total']:,.2f}")
            edited = render_day_editor(
                trade_date, f["sheet_values"], f["unmapped"], key_prefix="fetched"
            )
            if st.button("Save to Database", type="primary", icon=":material/save:", key="save_fetched"):
                database.save_day(trade_date, edited)
                st.success(f"Saved {trade_date}")
                del st.session_state["fetched"]
                st.rerun()

        st.divider()
        with st.expander("Backfill a date range", icon=":material/event_repeat:"):
            st.caption("Fetches every weekday in the range in one session and saves each day.")
            bc1, bc2 = st.columns(2)
            bf_start = bc1.date_input("From", value=date(2026, 4, 7), key="bf_start")
            bf_end = bc2.date_input("To", value=date.today(), key="bf_end")
            if st.button("Run backfill", key="run_backfill"):
                with st.spinner(f"Backfilling {bf_start} → {bf_end}..."):
                    try:
                        summary = ingest.ingest_range(bf_start, bf_end)
                        st.success(
                            f"Saved {summary['saved_days']} days, "
                            f"skipped {summary['empty_days']} empty/holiday days."
                        )
                        if summary["new_sheets"]:
                            st.warning(
                                "New sheet(s) auto-created for never-seen labels — add a matching "
                                "tab to template.xlsx before exporting these:"
                            )
                            for label in summary["new_sheets"]:
                                st.text(f"  • {label}")
                        else:
                            st.success("No new labels encountered — all mapped cleanly.")
                    except Exception as e:
                        st.error(f"Backfill failed: {e}")
                        if "logged in" in str(e).lower() or "auth" in str(e).lower():
                            st.code("python tradesteward_fetch.py --login", language="bash")

    # ---------- Screenshot upload ----------
    with tab_upload:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.info(
                "ANTHROPIC_API_KEY isn't set — required to parse screenshots. "
                "Set it in your shell before launching:",
                icon=":material/key:",
            )
            st.code("export ANTHROPIC_API_KEY=sk-ant-...", language="bash")

        uploaded = st.file_uploader(
            "TradeSteward screenshot",
            type=["png", "jpg", "jpeg"],
            key="screenshot_upload",
        )

        if uploaded is not None:
            st.image(uploaded, width=400)
            if st.button("Parse with Claude", type="primary", icon=":material/auto_awesome:"):
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    st.error("ANTHROPIC_API_KEY not set — see the notice above.")
                else:
                    with st.spinner("Parsing screenshot..."):
                        try:
                            media_type = f"image/{uploaded.type.split('/')[-1]}"
                            if media_type == "image/jpg":
                                media_type = "image/jpeg"
                            parsed = ss_parser.parse_screenshot(uploaded.getvalue(), media_type)
                            st.session_state["parsed"] = parsed
                            st.session_state["parsed_date"] = trade_date
                            st.success(f"Parsed {len(parsed['lines'])} lines")
                        except Exception as e:
                            st.error(f"Parse failed: {e}")

        # Show parsed results if available
        if "parsed" in st.session_state and st.session_state.get("parsed_date") == trade_date:
            parsed = st.session_state["parsed"]
            st.divider()

            st.write("**Parsed lines from screenshot:**")
            for entry in parsed["lines"]:
                color = "green" if entry["value"] > 0 else ("red" if entry["value"] < 0 else "gray")
                label_esc = entry["label"].replace("$", "\\$")
                st.markdown(f"&nbsp;&nbsp;:{color}[●] {label_esc}: \\${entry['value']:,.2f}")

            if parsed.get("total") is not None:
                st.write(f"**Headline total in screenshot:** ${parsed['total']:,.2f}")

            label_to_sheet = database.get_label_to_sheet()
            sheet_values, unmapped = ss_parser.aggregate_to_sheets(parsed["lines"], label_to_sheet)

            # Sanity check
            computed = sum(sheet_values.values()) + sum(u["value"] for u in unmapped)
            if parsed.get("total") is not None:
                if abs(computed - parsed["total"]) < 0.01:
                    st.success(f"Computed total ${computed:,.2f} matches screenshot")
                else:
                    st.warning(f"Computed \\${computed:,.2f} ≠ screenshot \\${parsed['total']:,.2f}")

            st.divider()
            edited = render_day_editor(trade_date, sheet_values, unmapped, key_prefix="parsed")

            if st.button("Save to Database", type="primary", icon=":material/save:", key="save_parsed"):
                database.save_day(trade_date, edited)
                st.success(f"Saved {trade_date}")
                del st.session_state["parsed"]
                st.rerun()

    # ---------- Manual entry ----------
    with tab_manual:
        edited = render_day_editor(trade_date, existing and {k: v["value"] for k, v in existing.items()} or {}, key_prefix="manual")
        if st.button("Save to Database", type="primary", icon=":material/save:", key="save_manual"):
            database.save_day(trade_date, edited)
            st.success(f"Saved {trade_date}")
            st.rerun()


# ============================================================
# PAGE: Custom Trades (for FOMC-style days)
# ============================================================
elif page == "Custom Trades (FOMC etc.)":
    st.header("Custom Trade P&L Calculator")
    st.caption("For days with manual trade-log calculations (e.g. FOMC custom diagonals).")

    trade_date = st.date_input("Trade date", value=date.today(), key="custom_date")

    target_strategy = st.selectbox(
        "Add P&L to which strategy sheet?",
        [s["sheet_name"] for s in database.get_strategies() if s["sheet_name"] != "All BICs"],
        index=[s["sheet_name"] for s in database.get_strategies() if s["sheet_name"] != "All BICs"].index("FOMC Meeting"),
    )

    st.divider()
    st.markdown("**Add each trade leg:**")
    st.caption("Enter quantity (positive for long, negative for short), price per spread unit (in dollars), and whether it's a DEBIT or CREDIT to your account.")

    if "custom_trades" not in st.session_state:
        st.session_state["custom_trades"] = []

    with st.form("add_trade", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])
        time_str = c1.text_input("Time", placeholder="14:30:31")
        units = c2.number_input("Spread units", value=1.0, step=1.0)
        price = c3.number_input("Price per unit", value=0.0, step=0.01, format="%.2f")
        action = c4.selectbox("Cash flow", ["DEBIT (out)", "CREDIT (in)"])
        multiplier = c5.number_input("Mult", value=100, step=1, help="100 for SPX")
        if st.form_submit_button("Add", icon=":material/add:"):
            sign = -1 if action.startswith("DEBIT") else 1
            cash = sign * units * price * multiplier
            st.session_state["custom_trades"].append({
                "time": time_str, "units": units, "price": price,
                "action": action, "cash": cash, "mult": multiplier,
            })

    if st.session_state["custom_trades"]:
        st.divider()
        st.write("**Trade ledger:**")
        total = 0
        for i, t in enumerate(st.session_state["custom_trades"]):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.text(f"{t['time']} | {t['units']:>4.0f}u × ${t['price']:.2f} × {t['mult']} {t['action']}")
            c2.text(f"${t['cash']:+,.2f}")
            if c3.button("", icon=":material/delete:", key=f"del_{i}"):
                st.session_state["custom_trades"].pop(i)
                st.rerun()
            total += t["cash"]
        st.metric("Net P&L", f"${total:,.2f}")

        c1, c2 = st.columns(2)
        if c1.button(f"Save ${total:,.2f} to {target_strategy} on {trade_date}", type="primary", icon=":material/save:"):
            # Add to whatever's already there
            existing = database.get_day(trade_date)
            current = existing.get(target_strategy, {}).get("value", 0.0)
            new_total = current + total
            # Merge - keep all existing values, update target
            sheet_values = {k: v["value"] for k, v in existing.items()}
            sheet_values[target_strategy] = new_total
            database.save_day(trade_date, sheet_values)
            target_esc = target_strategy.replace("$", "\\$")
            st.success(f"Added \\${total:,.2f} to {target_esc} on {trade_date} (new total there: \\${new_total:,.2f})")
            st.session_state["custom_trades"] = []
            st.rerun()
        if c2.button("Clear all", icon=":material/delete_sweep:"):
            st.session_state["custom_trades"] = []
            st.rerun()


# ============================================================
# PAGE: Calendar
# ============================================================
elif page == "Calendar":
    years = database.get_years_with_data()
    if not years:
        st.info("No data yet. Enter some days first.")
    else:
        # A click on a calendar day cell is a real link (?day=YYYY-MM-DD), which
        # does a full page reload -> new Streamlit session. Use it to restore
        # both the month cursor and the picked day across that reload.
        qp_day = st.query_params.get("day")
        qp_date = None
        if qp_day:
            try:
                qp_date = date.fromisoformat(qp_day)
            except ValueError:
                qp_date = None

        # Initialise calendar cursor in session state
        if "cal_year" not in st.session_state or "cal_month" not in st.session_state:
            if qp_date:
                st.session_state["cal_year"] = qp_date.year
                st.session_state["cal_month"] = qp_date.month
            else:
                latest = database.get_dates_with_data()[-1]
                if isinstance(latest, str):
                    latest = date.fromisoformat(latest)
                st.session_state["cal_year"] = latest.year
                st.session_state["cal_month"] = latest.month

        # Header + month nav
        nav_l, nav_title, nav_r = st.columns([1, 6, 1])
        if nav_l.button("‹", use_container_width=True, key="cal_prev"):
            y, m = st.session_state["cal_year"], st.session_state["cal_month"]
            m -= 1
            if m == 0:
                m = 12
                y -= 1
            st.session_state["cal_year"], st.session_state["cal_month"] = y, m
            st.rerun()
        if nav_r.button("›", use_container_width=True, key="cal_next"):
            y, m = st.session_state["cal_year"], st.session_state["cal_month"]
            m += 1
            if m == 13:
                m = 1
                y += 1
            st.session_state["cal_year"], st.session_state["cal_month"] = y, m
            st.rerun()
        y = st.session_state["cal_year"]
        m = st.session_state["cal_month"]
        nav_title.markdown(
            f"<h3 style='text-align:center;margin:0'>{_calendar.month_name[m]} {y}</h3>",
            unsafe_allow_html=True,
        )

        totals = database.get_month_totals(y, m)
        month_sum = sum(totals.values())
        win_days = sum(1 for v in totals.values() if v > 0)
        loss_days = sum(1 for v in totals.values() if v < 0)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Net P&L", f"${month_sum:,.2f}")
        k2.metric("Trading days", f"{len(totals)}")
        k3.metric("Green / Red", f"{win_days} / {loss_days}")
        best = max(totals.values(), default=0)
        worst = min(totals.values(), default=0)
        k4.metric("Best / Worst", f"${best:,.0f} / ${worst:,.0f}")

        st.markdown(
            """
            <style>
            .pnl-cal { width: 100%; border-collapse: separate; border-spacing: 6px; }
            .pnl-cal th { color: #898781; font-weight: 600; font-size: 0.8rem; text-align: center; padding: 4px; }
            .pnl-cal td { vertical-align: top; padding: 0; height: 90px; width: 14.28%;
                          background: #1a1a19; border-radius: 10px; border: 1px solid rgba(255,255,255,0.10);
                          box-shadow: 0 1px 3px rgba(0,0,0,0.3); transition: transform 0.12s ease, box-shadow 0.12s ease; }
            .pnl-cal td.empty { background: transparent; border: none; box-shadow: none; }
            .pnl-cal td.muted { background: #141413; padding: 10px; }
            .pnl-cal td.win { background: rgba(12,163,12,0.12); border-color: rgba(12,163,12,0.35); }
            .pnl-cal td.loss { background: rgba(208,59,59,0.12); border-color: rgba(208,59,59,0.35); }
            .pnl-cal td.win:hover, .pnl-cal td.loss:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 10px rgba(0,0,0,0.4);
            }
            .pnl-cal .cal-link { display: block; height: 90px; padding: 10px; color: inherit;
                                  text-decoration: none; cursor: pointer; }
            .pnl-cal .daynum { color: #898781; font-size: 0.85rem; }
            .pnl-cal .pnl { font-size: 1.05rem; font-weight: 700; margin-top: 6px; font-variant-numeric: tabular-nums; }
            .pnl-cal .pnl.win { color: #0ca30c; }
            .pnl-cal .pnl.loss { color: #d03b3b; }
            </style>
            """,
            unsafe_allow_html=True,
        )

        weeks = _calendar.Calendar(firstweekday=6).monthdayscalendar(y, m)
        html = ['<table class="pnl-cal"><thead><tr>']
        for h in ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]:
            html.append(f"<th>{h}</th>")
        html.append("</tr></thead><tbody>")
        for week in weeks:
            html.append("<tr>")
            for d in week:
                if d == 0:
                    html.append('<td class="empty"></td>')
                    continue
                v = totals.get(d)
                if v is None:
                    html.append(f'<td class="muted"><div class="daynum">{d}</div></td>')
                else:
                    cls = "win" if v > 0 else ("loss" if v < 0 else "")
                    pnl_cls = "win" if v > 0 else ("loss" if v < 0 else "")
                    sign = "" if v < 0 else ""
                    day_iso = date(y, m, d).isoformat()
                    html.append(
                        f'<td class="{cls}"><a class="cal-link" href="?day={day_iso}" target="_self">'
                        f'<div class="daynum">{d}</div>'
                        f'<div class="pnl {pnl_cls}">{sign}${v:,.0f}</div></a></td>'
                    )
            html.append("</tr>")
        html.append("</tbody></table>")
        st.markdown("".join(html), unsafe_allow_html=True)

        st.divider()
        # Day detail — defaults to whichever day was clicked in the calendar above
        month_dates_with_data = sorted(totals.keys())
        if month_dates_with_data:
            default_index = 0
            if qp_date and qp_date.year == y and qp_date.month == m and qp_date.day in month_dates_with_data:
                default_index = month_dates_with_data.index(qp_date.day)
            picked_day = st.selectbox(
                "Inspect a day",
                month_dates_with_data,
                index=default_index,
                format_func=lambda dn: f"{y}-{m:02d}-{dn:02d}  (${totals[dn]:,.2f})",
            )
            picked = date(y, m, picked_day)
            data = database.get_day(picked)
            if data:
                bic_sheets = {"BIC $6 $4", "BIC $4", "BIC $3", "BIC 1 DTE", "BIC Standard", "BIC Re-Entry"}
                total = 0.0
                for sheet, info in sorted(data.items()):
                    v = info["value"]
                    total += v
                    color = "green" if v > 0 else "red"
                    sheet_esc = sheet.replace("$", "\\$")
                    st.markdown(f"&nbsp;&nbsp;:{color}[●] {sheet_esc}: \\${v:,.2f}")
                st.metric("Day Total", f"${total:,.2f}")
                if st.button("Delete this day", icon=":material/delete:"):
                    database.save_day(picked, {})
                    st.success(f"Deleted {picked}")
                    st.rerun()


# ============================================================
# PAGE: Year View
# ============================================================
elif page == "Year View":
    years = database.get_years_with_data()
    if not years:
        st.info("No data yet. Enter some days first.")
    else:
        year = st.selectbox("Year", years[::-1], index=0)
        matrix, order = database.get_year_matrix(year)

        # Sort strategies by their display_order
        sheets = sorted(matrix.keys(), key=lambda s: order[s])

        months = list(range(1, 13))
        month_labels = [_calendar.month_abbr[m] for m in months]

        # Build rows: strategy, Jan..Dec, YTD
        rows = []
        col_totals = {m: 0.0 for m in months}
        for sheet in sheets:
            row = {"Strategy": sheet}
            ytd = 0.0
            for m in months:
                v = matrix[sheet].get(m, 0.0)
                row[month_labels[m - 1]] = v
                ytd += v
                col_totals[m] += v
            row["YTD"] = ytd
            rows.append(row)
        # Totals row
        total_row = {"Strategy": "TOTAL"}
        grand = 0.0
        for m in months:
            total_row[month_labels[m - 1]] = col_totals[m]
            grand += col_totals[m]
        total_row["YTD"] = grand
        rows.append(total_row)

        # Render as HTML for color + bold totals
        st.markdown(
            """
            <style>
            .pnl-year { width:100%; border-collapse: collapse; font-size: 0.9rem;
                        border: 1px solid rgba(255,255,255,0.10); border-radius: 12px; overflow: hidden; }
            .pnl-year th, .pnl-year td { padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.08);
                                          text-align: right; font-variant-numeric: tabular-nums; }
            .pnl-year th { color: #898781; font-weight: 600; background: #1a1a19; position: sticky; top: 0; }
            .pnl-year th.strat, .pnl-year td.strat { text-align: left; font-weight: 600; font-variant-numeric: normal; }
            .pnl-year tr.total td { font-weight: 700; border-top: 2px solid rgba(255,255,255,0.20); background: #1a1a19; }
            .pnl-year td.win { color: #0ca30c; }
            .pnl-year td.loss { color: #d03b3b; }
            .pnl-year td.zero { color: #555; }
            </style>
            """,
            unsafe_allow_html=True,
        )

        def fmt_cell(v):
            if v == 0:
                return '<td class="zero">—</td>'
            cls = "win" if v > 0 else "loss"
            return f'<td class="{cls}">${v:,.0f}</td>'

        html = ['<table class="pnl-year"><thead><tr><th class="strat">Strategy</th>']
        for lbl in month_labels:
            html.append(f"<th>{lbl}</th>")
        html.append("<th>YTD</th></tr></thead><tbody>")
        for row in rows:
            is_total = row["Strategy"] == "TOTAL"
            tr_cls = ' class="total"' if is_total else ""
            html.append(f"<tr{tr_cls}><td class=\"strat\">{row['Strategy']}</td>")
            for lbl in month_labels:
                html.append(fmt_cell(row[lbl]))
            html.append(fmt_cell(row["YTD"]))
            html.append("</tr>")
        html.append("</tbody></table>")
        st.markdown("".join(html), unsafe_allow_html=True)


# ============================================================
# PAGE: Mappings
# ============================================================
elif page == "Mappings":
    st.header("Screenshot Label → Sheet Mappings")
    st.caption("When the parser sees a label on the left, it puts the value on the sheet on the right. Multiple labels can map to one sheet (e.g. BIC 1:1 \\$2 and BIC \\$3 1:1 both → BIC \\$3) and the values get summed.")

    mappings = database.get_mappings()
    for m in mappings:
        st.text(f"  '{m['screenshot_label']}'  →  {m['sheet_name']}")

    st.divider()
    st.subheader("Add a new mapping")
    with st.form("add_mapping", clear_on_submit=True):
        label = st.text_input("Screenshot label (exact text as shown)")
        sheet = st.selectbox("Target sheet", [s["sheet_name"] for s in database.get_strategies()])
        if st.form_submit_button("Add mapping"):
            if label:
                database.add_mapping(label, sheet)
                st.success(f"Added: '{label}' → {sheet}")
                st.rerun()


# ============================================================
# PAGE: Export
# ============================================================
elif page == "Export":
    st.header("Export to Excel")
    st.caption("Generates an .xlsx file matching the original layout. Uses the template file as a base so all conditional formatting (red/green) is preserved.")

    if not TEMPLATE_PATH.exists():
        st.error(f"Template not found at {TEMPLATE_PATH}. Place the empty template workbook there.")
    else:
        if st.button("Generate Excel file", type="primary", icon=":material/table_view:"):
            out_path = APP_DIR / f"PnL_Export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            exporter.export_to_xlsx(TEMPLATE_PATH, out_path)
            with open(out_path, "rb") as f:
                st.download_button(
                    "Download .xlsx",
                    f.read(),
                    file_name=out_path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    icon=":material/download:",
                )
            st.success(f"Generated {out_path.name}")

    st.divider()
    n = len(database.get_dates_with_data())
    st.caption(f"Database contains {n} days of data.")
