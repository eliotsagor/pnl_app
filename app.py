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

APP_DIR = Path(__file__).parent
TEMPLATE_PATH = APP_DIR / "template.xlsx"

st.set_page_config(page_title="Daily P&L Tracker", layout="wide")
st.title("📊 Daily P&L Tracker")

# Initialise database on first run
database.init_db()
database.seed_if_empty()


# ---------- Sidebar: navigation and config ----------
with st.sidebar:
    st.header("Navigation")
    page = st.radio(
        "Page",
        ["Enter Day", "Custom Trades (FOMC etc.)", "Calendar", "Year View", "Mappings", "Export"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("**API Key**")
    api_key_status = "✅ Set" if os.environ.get("ANTHROPIC_API_KEY") else "❌ Not set"
    st.caption(f"ANTHROPIC_API_KEY: {api_key_status}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.caption("Set it in your shell before launching:")
        st.code("export ANTHROPIC_API_KEY=sk-ant-...", language="bash")


# ---------- Helper: render the per-strategy editing form ----------
def render_day_editor(trade_date, sheet_values, unmapped=None, key_prefix="edit"):
    """Render an editable form for one day's values. Returns the dict of values on submit."""
    strategies = database.get_strategies()
    label_to_sheet = database.get_label_to_sheet()

    st.subheader(f"Values for {trade_date}")

    if unmapped:
        st.warning(f"⚠️ {len(unmapped)} unmapped label(s). Add them in the Mappings tab.")
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
            st.info(f"📝 This date already has {len(existing)} entries. Saving will overwrite.")

    tab_upload, tab_manual = st.tabs(["📸 Upload Screenshot", "✏️ Manual Entry"])

    # ---------- Screenshot upload ----------
    with tab_upload:
        uploaded = st.file_uploader(
            "TradeSteward screenshot",
            type=["png", "jpg", "jpeg"],
            key="screenshot_upload",
        )

        if uploaded is not None:
            st.image(uploaded, width=400)
            if st.button("🤖 Parse with Claude", type="primary"):
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    st.error("ANTHROPIC_API_KEY not set. See sidebar for instructions.")
                else:
                    with st.spinner("Parsing screenshot..."):
                        try:
                            media_type = f"image/{uploaded.type.split('/')[-1]}"
                            if media_type == "image/jpg":
                                media_type = "image/jpeg"
                            parsed = ss_parser.parse_screenshot(uploaded.getvalue(), media_type)
                            st.session_state["parsed"] = parsed
                            st.session_state["parsed_date"] = trade_date
                            st.success(f"✅ Parsed {len(parsed['lines'])} lines")
                        except Exception as e:
                            st.error(f"Parse failed: {e}")

        # Show parsed results if available
        if "parsed" in st.session_state and st.session_state.get("parsed_date") == trade_date:
            parsed = st.session_state["parsed"]
            st.divider()

            st.write("**Parsed lines from screenshot:**")
            for entry in parsed["lines"]:
                color = "🟢" if entry["value"] > 0 else ("🔴" if entry["value"] < 0 else "⚪")
                st.text(f"  {color} {entry['label']}: ${entry['value']:,.2f}")

            if parsed.get("total") is not None:
                st.write(f"**Headline total in screenshot:** ${parsed['total']:,.2f}")

            label_to_sheet = database.get_label_to_sheet()
            sheet_values, unmapped = ss_parser.aggregate_to_sheets(parsed["lines"], label_to_sheet)

            # Sanity check
            computed = sum(sheet_values.values()) + sum(u["value"] for u in unmapped)
            if parsed.get("total") is not None:
                if abs(computed - parsed["total"]) < 0.01:
                    st.success(f"✅ Computed total ${computed:,.2f} matches screenshot")
                else:
                    st.warning(f"⚠️ Computed ${computed:,.2f} ≠ screenshot ${parsed['total']:,.2f}")

            st.divider()
            edited = render_day_editor(trade_date, sheet_values, unmapped, key_prefix="parsed")

            if st.button("💾 Save to Database", type="primary", key="save_parsed"):
                database.save_day(trade_date, edited)
                st.success(f"Saved {trade_date}")
                del st.session_state["parsed"]
                st.rerun()

    # ---------- Manual entry ----------
    with tab_manual:
        edited = render_day_editor(trade_date, existing and {k: v["value"] for k, v in existing.items()} or {}, key_prefix="manual")
        if st.button("💾 Save to Database", type="primary", key="save_manual"):
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
        if st.form_submit_button("➕ Add"):
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
            if c3.button("🗑", key=f"del_{i}"):
                st.session_state["custom_trades"].pop(i)
                st.rerun()
            total += t["cash"]
        st.metric("Net P&L", f"${total:,.2f}")

        c1, c2 = st.columns(2)
        if c1.button(f"💾 Save ${total:,.2f} to {target_strategy} on {trade_date}", type="primary"):
            # Add to whatever's already there
            existing = database.get_day(trade_date)
            current = existing.get(target_strategy, {}).get("value", 0.0)
            new_total = current + total
            # Merge - keep all existing values, update target
            sheet_values = {k: v["value"] for k, v in existing.items()}
            sheet_values[target_strategy] = new_total
            database.save_day(trade_date, sheet_values)
            st.success(f"Added ${total:,.2f} to {target_strategy} on {trade_date} (new total there: ${new_total:,.2f})")
            st.session_state["custom_trades"] = []
            st.rerun()
        if c2.button("🗑 Clear all"):
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
        # Initialise calendar cursor in session state
        if "cal_year" not in st.session_state or "cal_month" not in st.session_state:
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
            .pnl-cal th { color: #888; font-weight: 600; font-size: 0.8rem; text-align: center; padding: 4px; }
            .pnl-cal td { vertical-align: top; padding: 10px; height: 90px; width: 14.28%;
                          background: #1a1f2b; border-radius: 6px; border: 1px solid #2a2f3b; }
            .pnl-cal td.empty { background: transparent; border: none; }
            .pnl-cal td.muted { background: #161a23; }
            .pnl-cal td.win { background: #1d3a26; border-color: #2d5a3a; }
            .pnl-cal td.loss { background: #3a1d1d; border-color: #5a2d2d; }
            .pnl-cal .daynum { color: #aaa; font-size: 0.85rem; }
            .pnl-cal .pnl { font-size: 1.05rem; font-weight: 700; margin-top: 6px; }
            .pnl-cal .pnl.win { color: #4ade80; }
            .pnl-cal .pnl.loss { color: #f87171; }
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
                    html.append(
                        f'<td class="{cls}"><div class="daynum">{d}</div>'
                        f'<div class="pnl {pnl_cls}">{sign}${v:,.0f}</div></td>'
                    )
            html.append("</tr>")
        html.append("</tbody></table>")
        st.markdown("".join(html), unsafe_allow_html=True)

        st.divider()
        # Day detail picker (clicking calendar cells in pure HTML isn't trivial)
        month_dates_with_data = sorted(totals.keys())
        if month_dates_with_data:
            picked_day = st.selectbox(
                "Inspect a day",
                month_dates_with_data,
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
                    color = "🟢" if v > 0 else "🔴"
                    st.text(f"  {color} {sheet}: ${v:,.2f}")
                st.metric("Day Total", f"${total:,.2f}")
                if st.button("🗑 Delete this day"):
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
            .pnl-year { width:100%; border-collapse: collapse; font-size: 0.9rem; }
            .pnl-year th, .pnl-year td { padding: 8px 10px; border-bottom: 1px solid #2a2f3b; text-align: right; }
            .pnl-year th { color: #888; font-weight: 600; background: #161a23; position: sticky; top: 0; }
            .pnl-year th.strat, .pnl-year td.strat { text-align: left; font-weight: 600; }
            .pnl-year tr.total td { font-weight: 700; border-top: 2px solid #444; background: #161a23; }
            .pnl-year td.win { color: #4ade80; }
            .pnl-year td.loss { color: #f87171; }
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
    st.caption("When the parser sees a label on the left, it puts the value on the sheet on the right. Multiple labels can map to one sheet (e.g. BIC 1:1 $2 and BIC $3 1:1 both → BIC $3) and the values get summed.")

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
        if st.button("📤 Generate Excel file", type="primary"):
            out_path = APP_DIR / f"PnL_Export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            exporter.export_to_xlsx(TEMPLATE_PATH, out_path)
            with open(out_path, "rb") as f:
                st.download_button(
                    "⬇️ Download .xlsx",
                    f.read(),
                    file_name=out_path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            st.success(f"Generated {out_path.name}")

    st.divider()
    n = len(database.get_dates_with_data())
    st.caption(f"Database contains {n} days of data.")
