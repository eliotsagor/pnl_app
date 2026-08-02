"""Seed the database with the April 2026 data we entered manually."""
from datetime import date
import database


# Each entry: date -> {sheet_name: value}
APRIL_DATA = {
    date(2026, 4, 7): {
        "MOC IC": -2930,
        "Price Action IC": -11935,
        "BIC $3": -12480,        # BIC 1:1 $2 (-1455) + BIC $3 1:1 (-11025)
        "BIC $4": -20400,
        "Verticals": 3253,        # JSP (3920) + Short Call Vertical (-667)
        "BIC Standard": -15500,
        "BIC $6 $4": -7045,
        "Umbrella": 1020,
    },
    date(2026, 4, 8): {
        "MOC IC": -1445,
        "Price Action IC": -1355,
        "BIC $3": -1418,          # BIC 1:1 $2 (-1323) + BIC $3 1:1 (-95)
        "BIC $4": -230,
        "BIC Standard": 1295,
        "BIC $6 $4": -175,
        "Lunch Vol C Umb": 835,
    },
    date(2026, 4, 9): {
        "BIC $3": 2560,           # 1150 + 1410
        "Verticals": 945,         # 1170 + -225
        "Price Action IC": 210,
        "BIC Standard": 830,
        "BIC $4": 720,
        "BIC $6 $4": -1090,
        "Umbrella": -408,
    },
    date(2026, 4, 10): {
        "MOC IC": -219,
        "Price Action IC": 1395,
        "MT BF": 5072,
        "Umbrella": 5960,
        "BIC Standard": 14915,
        "BIC $6 $4": 6880,
        "Lunch Vol C Umb": 505,
        "Verticals": -1725,
    },
    date(2026, 4, 13): {
        "BIC $3": -870,
        "BIC Standard": -820,
        "BIC $6 $4": 595,
        "BIC $4": 450,
        "Price Action IC": 2080,
        "Umbrella": -22576,
        "BIC 1 DTE": 2200,
    },
    date(2026, 4, 14): {
        "MOC IC": -684,
        "BIC $3": 1904,           # 2165 + -261
        "Price Action IC": -670,
        "BIC Standard": -7525,
        "BIC $6 $4": 2490,
        "Lunch Vol C Umb": 565,
        "Verticals": 2495,
        "Wed Thu RIC": -270,
    },
    date(2026, 4, 15): {
        "MOC IC": 355,
        "BIC $3": 4570,           # 3055 + 1515
        "Price Action IC": -570,
        "BIC $4": -6180,
        "BIC Standard": -10640,
        "Verticals": -4113,       # 22 + -4135
        "Lunch Vol C Umb": 610,
        "BIC $6 $4": -3280,
    },
    date(2026, 4, 16): {
        "BIC $3": 2414,           # 1039 + 1375
        "MOC IC": 1512,
        "Price Action IC": 545,
        "BIC $4": -100,
        "BIC Standard": 6725,
        "Verticals": -565,        # 590 + -1155
        "BIC $6 $4": 2970,
        "Umbrella": 3160,
    },
    date(2026, 4, 17): {
        "MOC IC": 1412,
        "BIC $3": 1148,           # 468 + 680
        "MT BF": 1734,
        "Umbrella": 6568,
        "Price Action IC": 935,
        "BIC Standard": 5955,
        "BIC $6 $4": 3425,
        "Verticals": 2666,        # -104 + 2770
        "Lunch Vol C Umb": 1015,
        "BIC $4": 1480,
    },
    date(2026, 4, 20): {
        "MOC IC": -2681,
        "BIC Standard": 8945,
        "WUGA": 490,
        "BIC $4": 4460,
        "Price Action IC": 900,
        "BIC $6 $4": -550,
        "Umbrella": 1400,
        "Verticals": -1608,
        "BIC 1 DTE": 1260,
    },
    date(2026, 4, 21): {
        "MOC IC": 2645,
        "BIC $3": -6065,          # -5550 + -515
        "Price Action IC": -855,
        "BIC Standard": -23630,
        "BIC $4": -5320,
        "Verticals": -980,        # 590 + -1570
        "BIC $6 $4": -5555,
        "Umbrella": -11028,
    },
    date(2026, 4, 22): {
        "MOC IC": -155,
        "BIC $4": 1020,
        "BIC Standard": 8900,
        "Price Action IC": 1220,
        "Lunch Vol C Umb": 730,
    },
    date(2026, 4, 23): {
        "MOC IC": -425,
        "BIC $3": 4450,           # 540 + 3910
        "Price Action IC": -1715,
        "BIC Standard": -13895,
        "BIC $6 $4": -710,
        "Umbrella": 1040,
    },
    date(2026, 4, 24): {
        "MOC IC": 1744,
        "BIC $3": 2677,           # 916 + 1761
        "Umbrella": 3355,
        "Verticals": 790,
        "MT BF": 2022,
        "Price Action IC": 1990,
        "BIC Standard": -1340,
        "BIC $6 $4": -345,
        "Lunch Vol C Umb": 930,
    },
    date(2026, 4, 27): {
        "MOC IC": 312,
        "BIC $3": 150,
        "Price Action IC": 570,
        "BIC Standard": 16070,
        "WUGA": 460,
        "BIC $4": 6190,
        "Verticals": -755,
        "Umbrella": 2525,
        "BIC 1 DTE": 1255,
    },
    date(2026, 4, 28): {
        "MOC IC": 1515,
        "BIC Standard": -750,
        "WUGA": 550,
        "Price Action IC": 1330,
        "BIC $4": 1135,
        "BIC $3": 140,
        "Umbrella": 630,
        "BIC $6 $4": -280,
    },
    date(2026, 4, 29): {
        "MOC IC": -355,
        "FOMC Meeting": 8885,     # FOMC IC (200) + custom trades (8685)
        "Price Action IC": 295,
    },
}


def seed():
    database.init_db()
    database.seed_if_empty()
    for d, values in APRIL_DATA.items():
        database.save_day(d, values)
        total = sum(values.values())
        print(f"Saved {d}: {len(values)} entries, total ${total:,.2f}")
    print(f"\nDone. {len(APRIL_DATA)} days seeded.")


if __name__ == "__main__":
    seed()
