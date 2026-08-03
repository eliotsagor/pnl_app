"""
ingest.py
=========
Glue between tradesteward_fetch (the endpoint fetcher) and the existing
database / mapping layer. Fetches a day (or range) of bot-trade P&L from
TradeSteward, routes each strategy label to its sheet using the SAME
label->sheet mapping the screenshot flow uses, and writes it to SQLite.

Unmapped labels are never dropped — they're collected and reported so you can
add the mapping once and re-run.

Usage:
    python tradesteward_fetch.py --login          # one-time interactive sign-in
    python ingest.py --day 2026-07-30             # ingest a single day
    python ingest.py --backfill 2026-04-07 2026-08-01
    python ingest.py --apply-suggested-mappings   # add the 3 endpoint labels below
    python ingest.py --backfill 2026-04-07        # end defaults to today
"""

from __future__ import annotations

import argparse
from datetime import date
from typing import Callable

import database
import parser as ss_parser          # reuse aggregate_to_sheets verbatim
import tradesteward_fetch as tsf


# Endpoint-vocabulary labels that aren't in the historical screenshot mapping.
# These are *suggestions* — best-guess routing for labels seen in the live
# endpoint. Apply with --apply-suggested-mappings, or edit in the Mappings tab.
# (LCV = long call vertical, LPV = long put vertical -> Verticals;
#  the endpoint says "Thursday RIC" where the old screenshots said "RIC Wed Thur".)
SUGGESTED_MAPPINGS = {
    "LCV 50/50":        "Verticals",
    "LCV":               "Verticals",
    "Bear - LPV 50/50": "Verticals",
    "Thursday RIC":     "Wed Thu RIC",
}


def _totals_to_lines(strat_totals: dict[str, float]) -> list[dict]:
    """Adapt {label: total} into the [{'label','value'}] shape aggregate_to_sheets wants."""
    return [{"label": k, "value": v} for k, v in strat_totals.items()]


def _auto_map(unmapped: list[dict], sheet_values: dict) -> list[str]:
    """Create a same-named sheet + mapping for each unmapped label, folding its
    value into sheet_values. Returns the list of newly created sheet names.

    New sheets aren't in template.xlsx yet, so Export silently skips them
    until a matching tab (and, for BIC/Total rollups, an exporter.py entry)
    is added — but nothing is lost from the database.
    """
    new_sheets = []
    for u in unmapped:
        label = u["label"]
        database.add_strategy(label)
        database.add_mapping(label, label)
        sheet_values[label] = sheet_values.get(label, 0) + u["value"]
        new_sheets.append(label)
    return new_sheets


def ingest_day(
    day: date, headless: bool = False, on_waiting: Callable[[], None] | None = None
) -> tuple[dict, list]:
    """Fetch one day, map to sheets (auto-creating a sheet for any never-seen
    label), save. Returns (sheet_values, new_sheets)."""
    strat_totals = tsf.fetch_day_totals(day, headless=headless, on_waiting=on_waiting)
    label_to_sheet = database.get_label_to_sheet()
    sheet_values, unmapped = ss_parser.aggregate_to_sheets(
        _totals_to_lines(strat_totals), label_to_sheet
    )
    new_sheets = _auto_map(unmapped, sheet_values)
    if sheet_values:
        database.save_day(day, sheet_values)
    return sheet_values, new_sheets


def ingest_range(
    start: date,
    end: date | None = None,
    headless: bool = False,
    on_waiting: Callable[[], None] | None = None,
    on_progress: Callable[[dict], None] | None = None,
):
    """Backfill a weekday range. Fetches all days in ONE browser session,
    saves each, and returns a consolidated report of unmapped labels.

    TradeSteward's auth session is per-process (no durable session cookie),
    so headless=False (the default) opens a visible browser once for login —
    complete the passkey/password prompt there — and the same session then
    carries through the whole range unattended.

    `on_progress`, if given, is called once per weekday with the same
    summary dict the print() line below builds from — callers that want
    live progress (e.g. a web backend polling job status) get it without
    scraping stdout.
    """
    end = end or date.today()
    database.init_db()
    database.seed_if_empty()
    label_to_sheet = database.get_label_to_sheet()

    saved_days = 0
    empty_days = 0
    new_sheets_summary: list[str] = []  # labels auto-created as new sheets during this run

    with tsf.TradeStewardClient(headless=headless) as client:
        client.ensure_logged_in(on_waiting=on_waiting)
        for day in tsf.weekdays(start, end):
            trades = client.fetch_day(day)
            if not trades:
                empty_days += 1
                if on_progress:
                    on_progress({"day": str(day), "day_total": 0.0, "new_sheets": [], "saved": False, "empty": True})
                continue
            strat_totals = tsf.aggregate_by_strategy(trades)
            sheet_values, unmapped = ss_parser.aggregate_to_sheets(
                _totals_to_lines(strat_totals), label_to_sheet
            )
            newly_created = _auto_map(unmapped, sheet_values)
            for label in newly_created:
                label_to_sheet[label] = label  # so later days in this range use it directly
                if label not in new_sheets_summary:
                    new_sheets_summary.append(label)
            if sheet_values:
                database.save_day(day, sheet_values)
                saved_days += 1
            day_total = sum(sheet_values.values())
            flag = f"  ✨ new sheet(s): {', '.join(newly_created)}" if newly_created else ""
            print(f"  {day}  saved  day P&L ${day_total:>12,.2f}{flag}")
            if on_progress:
                on_progress({
                    "day": str(day), "day_total": day_total,
                    "new_sheets": newly_created, "saved": bool(sheet_values), "empty": False,
                })

    print(f"\nDone. {saved_days} days saved, {empty_days} empty/holiday days skipped.")
    if new_sheets_summary:
        print("\nNEW SHEETS AUTO-CREATED (no mapping existed for these labels before this run):")
        for label in new_sheets_summary:
            print(f"  {label}")
        print(
            "\nThese are saved in the database now, but Export will skip them until you "
            "add a matching tab to template.xlsx (and, for BIC/Total rollups, list them "
            "in exporter.py's bic_sheets/total_components)."
        )
    else:
        print("No new labels encountered — all mapped cleanly. ✅")

    return {
        "saved_days": saved_days,
        "empty_days": empty_days,
        "new_sheets": new_sheets_summary,
    }


def apply_suggested_mappings():
    database.init_db()
    database.seed_if_empty()
    existing = database.get_label_to_sheet()
    for label, sheet in SUGGESTED_MAPPINGS.items():
        was = existing.get(label)
        database.add_mapping(label, sheet)
        note = "(unchanged)" if was == sheet else (f"(was: {was})" if was else "(new)")
        print(f"  {label:20} -> {sheet:14} {note}")
    print("Applied. Review/adjust any of these in the Mappings tab.")


def main():
    ap = argparse.ArgumentParser(description="Ingest TradeSteward P&L into the workbook db.")
    ap.add_argument("--day", help="Ingest a single date YYYY-MM-DD.")
    ap.add_argument("--backfill", nargs="+", metavar=("START", "END"),
                    help="Backfill START [END]; END defaults to today.")
    ap.add_argument("--apply-suggested-mappings", action="store_true",
                    help="Add the 3 endpoint-vocabulary label mappings.")
    args = ap.parse_args()

    if args.apply_suggested_mappings:
        apply_suggested_mappings()
        return

    if args.day:
        sheet_values, new_sheets = ingest_day(date.fromisoformat(args.day), on_waiting=tsf._print_waiting)
        for sheet, v in sorted(sheet_values.items()):
            print(f"  {sheet:18} {v:>12,.2f}")
        if new_sheets:
            print("New sheet(s) auto-created (add a matching tab to template.xlsx):")
            for label in new_sheets:
                print(f"  {label}")
        return

    if args.backfill:
        start = date.fromisoformat(args.backfill[0])
        end = date.fromisoformat(args.backfill[1]) if len(args.backfill) > 1 else None
        ingest_range(start, end, on_waiting=tsf._print_waiting)
        return

    ap.print_help()


if __name__ == "__main__":
    main()
