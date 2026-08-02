# Daily P&L Tracker

A local Streamlit app that replaces the per-day Excel-editing workflow with:
- Screenshot upload → Claude vision parses TradeSteward output → preview/edit → save
- SQLite database as the source of truth
- One-click export back to the same `.xlsx` layout (formulas + conditional formatting preserved)
- Custom trade calculator for FOMC-style days

## Files

```
pnl_app/
├── app.py             # Streamlit UI (run this)
├── database.py        # SQLite schema + CRUD
├── parser.py          # Claude vision screenshot parser
├── exporter.py        # Rebuild .xlsx from database
├── seed_april.py      # One-time seed with April 2026 data
├── template.xlsx      # Empty version of your master spreadsheet (you supply)
├── pnl.db             # Auto-created on first run
└── requirements.txt
```

## Setup

```bash
cd pnl_app
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Put your empty template here (the original .xlsx with no values filled in)
cp ~/Downloads/2026-_Daily_PnL_By_Strategy.xlsx ./template.xlsx

# Set your API key (get from https://console.anthropic.com/)
export ANTHROPIC_API_KEY=sk-ant-...

# One-time: seed the April data we already entered
python seed_april.py

# Run the app
streamlit run app.py
```

The app opens in your browser at http://localhost:8501.

## Daily workflow

1. **Enter Day** tab → pick today's date → drag in screenshot → click "Parse with Claude"
2. Review the parsed values; edit any that look wrong
3. Click "Save to Database"
4. For FOMC-style days with custom trades, use the **Custom Trades** tab to compute the P&L, then save it to the FOMC Meeting sheet
5. Whenever you want a fresh Excel file, go to **Export** → "Generate Excel file"

## Adding new strategies

If TradeSteward starts showing a new strategy label:
1. Go to the **Mappings** tab
2. Type the exact label (e.g. "New BIC Variant")
3. Pick the target sheet from the dropdown
4. From then on, the parser will route it automatically

If you need a brand new sheet (not yet in the workbook), edit `database.py` → `SEED_STRATEGIES` and add the sheet name, then add a matching sheet to `template.xlsx`.

## Cost

Each screenshot import calls Claude vision once. Currently ~2¢ per parse depending on model and image size.

## Backups

`pnl.db` is a single SQLite file. Copy it anywhere to back up. The database is the source of truth — the .xlsx is just a rendered view of it.
