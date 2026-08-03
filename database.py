"""SQLite database for daily P&L tracking."""
import sqlite3
from datetime import date
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "pnl.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables and seed strategies + mappings."""
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_name TEXT NOT NULL UNIQUE,
            display_order INTEGER NOT NULL DEFAULT 0,
            include_in_total INTEGER NOT NULL DEFAULT 1,
            include_in_all_bics INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            screenshot_label TEXT NOT NULL UNIQUE,
            strategy_id INTEGER NOT NULL,
            FOREIGN KEY (strategy_id) REFERENCES strategies(id)
        );

        CREATE TABLE IF NOT EXISTS daily_pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date DATE NOT NULL,
            strategy_id INTEGER NOT NULL,
            value REAL NOT NULL,
            note TEXT,
            UNIQUE(trade_date, strategy_id),
            FOREIGN KEY (strategy_id) REFERENCES strategies(id)
        );

        CREATE INDEX IF NOT EXISTS idx_pnl_date ON daily_pnl(trade_date);
        CREATE INDEX IF NOT EXISTS idx_pnl_strategy ON daily_pnl(strategy_id);
        """)


# Strategy seed data: (sheet_name, display_order, include_in_total, include_in_all_bics)
SEED_STRATEGIES = [
    ("BIC $6 $4",       10, 0, 1),
    ("BIC Standard",    20, 0, 1),
    ("BIC $4",          30, 0, 1),
    ("BIC $3",          40, 0, 1),
    ("BIC 1 DTE",       50, 0, 1),
    ("BIC Re-Entry",    55, 0, 1),
    ("All BICs",        60, 1, 0),
    ("Price Action IC", 70, 1, 0),
    ("Verticals",       80, 1, 0),
    ("Auto JSP",        90, 1, 0),
    ("Wed Thu RIC",    100, 1, 0),
    ("Lottery",        110, 1, 0),
    ("MOC IC",         120, 1, 0),
    ("WUGA",           130, 1, 0),
    ("MT BF",          140, 1, 0),
    ("Umbrella",       150, 1, 0),
    ("PM Umbrella",    160, 1, 0),
    ("Vol Crush",      170, 1, 0),
    ("Lunch Vol C Umb",180, 1, 0),
    ("LDOM",           190, 1, 0),
    ("FOMC Meeting",   200, 1, 0),
]

# Screenshot label -> strategy sheet name
# For combined entries (e.g. "BIC 1:1 $2" and "BIC $3 1:1" both go to BIC $3),
# we just map each label to its destination sheet; the UI sums them.
SEED_MAPPINGS = {
    "MOC no stop":                  "MOC IC",
    "Price Action Iron Condor Lite":"Price Action IC",
    "BIC 1:1 $2":                   "BIC $3",
    "BIC $3 1:1":                   "BIC $3",
    "BIC $4 1:1":                   "BIC $4",
    "BIC 1:1 Standard Times":       "BIC Standard",
    "All Day $6 put $4 call":       "BIC $6 $4",
    "BIC 1 DTE":                    "BIC 1 DTE",
    "BIC Re-Entry":                 "BIC Re-Entry",
    "JSP":                          "Verticals",
    "Short Call Vertical":          "Verticals",
    # Endpoint-vocabulary labels (from tradesteward_fetch). Adjust if wrong.
    "LCV 50/50":                    "Verticals",
    "LCV":                          "Verticals",
    "Bear - LPV 50/50":             "Verticals",
    "Thursday RIC":                 "Wed Thu RIC",
    "WUGA":                         "WUGA",
    "MT Friday Theta Junkie":       "MT BF",
    "Umbrella Delta":               "Umbrella",
    "Umbrella Friday":              "Umbrella",
    "PM Iron Condors":              "PM Umbrella",
    "Lunch Vol Crush Umbrella":     "Lunch Vol C Umb",
    "RIC Wed Thur":                 "Wed Thu RIC",
    "FOMC IC":                      "FOMC Meeting",
}


def seed_if_empty():
    """Seed strategies and mappings if tables are empty."""
    with get_db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]
        if n == 0:
            conn.executemany(
                "INSERT INTO strategies (sheet_name, display_order, include_in_total, include_in_all_bics) VALUES (?, ?, ?, ?)",
                SEED_STRATEGIES,
            )
        n = conn.execute("SELECT COUNT(*) FROM mappings").fetchone()[0]
        if n == 0:
            for label, sheet in SEED_MAPPINGS.items():
                sid = conn.execute("SELECT id FROM strategies WHERE sheet_name = ?", (sheet,)).fetchone()[0]
                conn.execute("INSERT INTO mappings (screenshot_label, strategy_id) VALUES (?, ?)", (label, sid))


def get_strategies():
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM strategies ORDER BY display_order"
        )]


def get_mappings():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT m.screenshot_label, s.sheet_name, s.id AS strategy_id
            FROM mappings m JOIN strategies s ON m.strategy_id = s.id
            ORDER BY m.screenshot_label
        """)]


def get_label_to_sheet():
    """Return dict mapping screenshot_label -> sheet_name."""
    return {m["screenshot_label"]: m["sheet_name"] for m in get_mappings()}


def save_day(trade_date: date, sheet_values: dict, notes: dict = None):
    """Save P&L values for a date. sheet_values is {sheet_name: value}."""
    notes = notes or {}
    with get_db() as conn:
        # Delete any existing entries for this date so we overwrite
        conn.execute("DELETE FROM daily_pnl WHERE trade_date = ?", (trade_date,))
        for sheet, value in sheet_values.items():
            if value is None:
                continue
            sid = conn.execute("SELECT id FROM strategies WHERE sheet_name = ?", (sheet,)).fetchone()
            if not sid:
                continue
            conn.execute(
                "INSERT INTO daily_pnl (trade_date, strategy_id, value, note) VALUES (?, ?, ?, ?)",
                (trade_date, sid[0], value, notes.get(sheet)),
            )


def get_day(trade_date: date):
    """Return {sheet_name: value} for a given date."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT s.sheet_name, p.value, p.note
            FROM daily_pnl p JOIN strategies s ON p.strategy_id = s.id
            WHERE p.trade_date = ?
        """, (trade_date,)).fetchall()
    return {r["sheet_name"]: {"value": r["value"], "note": r["note"]} for r in rows}


def get_all_pnl():
    """Return all P&L data as a list of (date, sheet_name, value) tuples."""
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT p.trade_date, s.sheet_name, p.value
            FROM daily_pnl p JOIN strategies s ON p.strategy_id = s.id
            ORDER BY p.trade_date, s.display_order
        """)]


def get_dates_with_data():
    with get_db() as conn:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT trade_date FROM daily_pnl ORDER BY trade_date"
        )]


def get_month_totals(year: int, month: int):
    """Return {day(int): day_total(float)} for every day in (year, month) that has data."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT trade_date, SUM(value) AS total
            FROM daily_pnl
            WHERE strftime('%Y', trade_date) = ?
              AND strftime('%m', trade_date) = ?
            GROUP BY trade_date
        """, (str(year), f"{month:02d}")).fetchall()
    out = {}
    for r in rows:
        d = r["trade_date"]
        if isinstance(d, str):
            d = date.fromisoformat(d)
        out[d.day] = float(r["total"])
    return out


def get_year_matrix(year: int):
    """Return {sheet_name: {month(int): monthly_sum(float)}} for the given year.

    Only includes strategies that have at least one entry in that year.
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT s.sheet_name, s.display_order,
                   CAST(strftime('%m', p.trade_date) AS INTEGER) AS month,
                   SUM(p.value) AS total
            FROM daily_pnl p JOIN strategies s ON p.strategy_id = s.id
            WHERE strftime('%Y', p.trade_date) = ?
            GROUP BY s.id, month
            ORDER BY s.display_order, month
        """, (str(year),)).fetchall()
    matrix = {}
    order = {}
    for r in rows:
        matrix.setdefault(r["sheet_name"], {})[int(r["month"])] = float(r["total"])
        order[r["sheet_name"]] = r["display_order"]
    return matrix, order


def get_years_with_data():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT CAST(strftime('%Y', trade_date) AS INTEGER) AS y "
            "FROM daily_pnl ORDER BY y"
        ).fetchall()
    return [r["y"] for r in rows]


def add_strategy(sheet_name: str, include_in_total: int = 1, include_in_all_bics: int = 0) -> int:
    """Create a new strategy sheet if it doesn't already exist. Returns its id."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM strategies WHERE sheet_name = ?", (sheet_name,)).fetchone()
        if row:
            return row[0]
        max_order = conn.execute("SELECT COALESCE(MAX(display_order), 0) FROM strategies").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO strategies (sheet_name, display_order, include_in_total, include_in_all_bics) VALUES (?, ?, ?, ?)",
            (sheet_name, max_order + 10, include_in_total, include_in_all_bics),
        )
        return cur.lastrowid


def add_to_day(trade_date: date, sheet_name: str, amount: float) -> float:
    """Add `amount` to whatever's already saved for sheet_name on trade_date
    (0 if none), atomically within one connection. Returns the new total."""
    with get_db() as conn:
        sid = conn.execute("SELECT id FROM strategies WHERE sheet_name = ?", (sheet_name,)).fetchone()
        if not sid:
            raise ValueError(f"Unknown sheet: {sheet_name}")
        row = conn.execute(
            "SELECT value FROM daily_pnl WHERE trade_date = ? AND strategy_id = ?",
            (trade_date, sid[0]),
        ).fetchone()
        new_total = (row[0] if row else 0.0) + amount
        conn.execute("DELETE FROM daily_pnl WHERE trade_date = ? AND strategy_id = ?", (trade_date, sid[0]))
        conn.execute(
            "INSERT INTO daily_pnl (trade_date, strategy_id, value, note) VALUES (?, ?, ?, NULL)",
            (trade_date, sid[0], new_total),
        )
        return new_total


def add_mapping(label: str, sheet_name: str):
    with get_db() as conn:
        sid = conn.execute("SELECT id FROM strategies WHERE sheet_name = ?", (sheet_name,)).fetchone()
        if not sid:
            raise ValueError(f"Unknown sheet: {sheet_name}")
        conn.execute(
            "INSERT OR REPLACE INTO mappings (screenshot_label, strategy_id) VALUES (?, ?)",
            (label, sid[0]),
        )


def reset_db():
    """Wipe and reinitialise. Useful in dev."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    seed_if_empty()


if __name__ == "__main__":
    init_db()
    seed_if_empty()
    print(f"DB ready at {DB_PATH}")
    print(f"Strategies: {len(get_strategies())}")
    print(f"Mappings: {len(get_mappings())}")
