# Daily P&L Tracker

A local app that replaces the per-day Excel-editing workflow with:
- **Direct fetch from TradeSteward** — pulls the day's per-strategy P&L straight
  from the reporting endpoint (no screenshot, exact numbers, free)
- Screenshot upload → Claude vision parses TradeSteward output → preview/edit → save
  (kept as a fallback)
- SQLite database as the source of truth
- One-click export back to the same `.xlsx` layout (formulas + conditional formatting preserved)
- Custom trade calculator for FOMC-style days

The UI is a **FastAPI + React (Vite/MUI)** app (`backend/` + `frontend/`). An
older Streamlit UI (`app.py`) still works and shares the same `pnl.db`, kept
as a fallback during the transition — see "Legacy Streamlit UI" below.

## Files

```
pnl_app/
├── backend/                # FastAPI app
│   ├── main.py             #   app setup, serves frontend/dist in daily-use mode
│   ├── jobs.py              #   background job registry (TradeSteward fetch/backfill)
│   └── routers/             #   one module per resource (days, calendar, mappings, export, tradesteward)
├── frontend/                # Vite + React + TypeScript + MUI
│   └── src/{api,pages,components,hooks,utils}/
├── scripts/
│   ├── dev.ps1              # dev mode: backend --reload + Vite dev server (2 windows)
│   └── start.ps1            # daily-use mode: one process, builds frontend if needed
├── database.py              # SQLite schema + CRUD (imported by both UIs, unchanged)
├── tradesteward_fetch.py    # Fetch P&L from the TradeSteward endpoint (Playwright)
├── ingest.py                # fetch -> map to sheets -> save (single day or backfill)
├── parser.py                # Claude vision screenshot parser (fallback)
├── exporter.py               # Rebuild .xlsx from database
├── app.py                    # Legacy Streamlit UI (fallback, see below)
├── template.xlsx             # Empty version of your master spreadsheet (you supply)
├── pnl.db                    # Auto-created on first run
└── requirements.txt
```

## Setup

```powershell
cd pnl_app
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium      # first install only

cd frontend
npm install
cd ..

# Put your empty template here (the original .xlsx with no values filled in)
copy $env:USERPROFILE\Downloads\2026-_Daily_PnL_By_Strategy.xlsx .\template.xlsx

# Set your API key if you'll use the screenshot-upload fallback (get one from https://console.anthropic.com/)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

## Running it

**Day to day:**

```powershell
.\scripts\start.ps1
```

Builds the frontend once (skips the build if `frontend\dist` already exists —
delete it, or re-run `npm run build` in `frontend/`, after pulling frontend
changes) and runs a single server at **http://localhost:8000**, opening it in
your browser automatically.

**While developing** (auto-reloading backend + Vite hot-reload):

```powershell
.\scripts\dev.ps1
```

Opens two windows — backend on :8000, frontend dev server on :5173 (proxies
`/api/*` to :8000). Use **http://localhost:5173** while this is running.

## Fetching straight from TradeSteward

The fetcher reads the same numbers shown in the dashboard's "Strategy Profits"
panel directly from TradeSteward's report endpoint, so there's no screenshot
step and the values are exact.

**Auth note:** TradeSteward's session cookie is per-process (it doesn't
survive after the browser closes), and a remembered device still triggers a
passkey prompt on each new sign-in — so a true one-time headless login isn't
possible. Instead, every fetch or backfill opens a real (headed) browser
window once at the start; sign in there (passkey or password), and the same
session then carries through the rest of that run unattended — so a backfill
across months still only needs one login click, not one per day. In the app,
this shows as a live status panel ("sign-in window opened, waiting...") that
updates automatically once you're logged in — no need to switch back to a
terminal.

**One-off endpoint sanity check** from the command line (opens a browser to
sign in, prints strategy totals for a day):

```powershell
.\.venv\Scripts\python.exe tradesteward_fetch.py --day 2026-07-30
```

**Catch up the database** from the command line (weekdays only, one browser
session — sign in when the window opens, then it runs unattended):

```powershell
.\.venv\Scripts\python.exe ingest.py --apply-suggested-mappings   # add the LCV / LPV / Thursday RIC labels
.\.venv\Scripts\python.exe ingest.py --backfill 2026-04-07
```

Any strategy label the endpoint emits that isn't in the mapping gets a **new
sheet auto-created for it** (never dropped) — you'll still need to add a
matching tab to `template.xlsx` (and, for BIC-family/rollup strategies, list
it in `exporter.py`'s `bic_sheets`/`total_components`) before it shows up in
an export. `save_day` overwrites, so re-running a backfill is always safe.

From the app: **Enter Day → Fetch from TradeSteward** fetches a single day for
review/save, and its **Backfill a date range** panel runs the same catch-up —
both show live progress instead of blocking with no feedback.

## Schwab API setup (Risk dashboard expected-move overlay)

The Risk dashboard's expected-move overlay needs a real SPX 0DTE ATM straddle
price, which comes from the Schwab Trader API via `schwab_client.py`. This is
optional — the rest of the app works without it — but if you want that
overlay, each person running the app needs **their own** Schwab developer app
(the key/secret are tied to your Schwab account, not shareable):

1. Register a developer app at https://developer.schwab.com (needs a Schwab
   brokerage account). Set its callback/redirect URL to exactly
   `https://127.0.0.1:8080`. Wait for the app status to show "Ready For Use"
   (can take a day or so after creation).
2. Store the app key/secret locally (prompts for both, hidden input, saved to
   Windows Credential Manager — never written to disk in plaintext):
   ```powershell
   .\.venv\Scripts\python.exe schwab_client.py --set-credentials
   ```
3. Do the one-time OAuth browser consent (opens a browser to Schwab's login
   page, then redirects to `https://127.0.0.1:8080`; expect a self-signed-cert
   warning there — proceed past it):
   ```powershell
   .\.venv\Scripts\python.exe schwab_client.py --login
   ```
   If that fails to catch the redirect automatically (e.g. the cert warning
   has no bypass option), use the copy-paste fallback instead:
   ```powershell
   .\.venv\Scripts\python.exe schwab_client.py --login-manual
   ```
4. The resulting token is cached at `~/.schwab_token.json` and refreshes
   itself silently after that — no need to repeat step 3 day to day.

To remove saved credentials: `python schwab_client.py --clear-credentials`.

## Daily workflow

1. **Enter Day → Fetch from TradeSteward** → pick the date → "Fetch this day"
2. Review the values; edit any that look wrong
3. Click "Save to Database"
4. For FOMC-style days with custom trades, use the **Custom Trades** page to compute the P&L, then save it to the target sheet
5. Whenever you want a fresh Excel file, go to **Export** → "Generate Excel file"

(The Upload Screenshot tab still works as a fallback if the endpoint is ever unavailable — needs `ANTHROPIC_API_KEY` set.)

## Adding new strategies

If TradeSteward starts showing a new strategy label:
1. Go to the **Mappings** page
2. Type the exact label (e.g. "New BIC Variant")
3. Pick the target sheet from the dropdown
4. From then on, fetches will route it automatically

If you need a brand new sheet (not yet in the workbook), edit `database.py` → `SEED_STRATEGIES` and add the sheet name, then add a matching sheet to `template.xlsx`. (Fetch/backfill already auto-create the database side of this for never-seen labels — see above — you just need to add the `template.xlsx` tab yourself.)

## Cost

Each screenshot import calls Claude vision once. Currently ~2¢ per parse depending on model and image size. TradeSteward fetches are free.

## Backups

`pnl.db` is a single SQLite file. Copy it anywhere to back up. The database is the source of truth — the .xlsx is just a rendered view of it.

## Legacy Streamlit UI

`app.py` is the original Streamlit UI, kept as a fallback while the React
app gets real-world use. It reads/writes the exact same `pnl.db` via the
same `database.py`, so both UIs can be used interchangeably, even on the
same day — nothing needs to be migrated between them.

```powershell
streamlit run app.py
```

Opens at http://localhost:8501. Plan is to retire this once the React app
has been the daily driver for a while — see the code comments in `app.py`
if you're picking this up again after that.
