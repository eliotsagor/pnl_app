"""Live index quotes via yfinance, used to show the current SPX price/change
on the short-strikes risk dashboard. yfinance's fast_info is unreliable for
indices, so this pulls the last intraday bar and the prior day's close
instead."""
import yfinance as yf


def spx_quote() -> dict:
    """{'price': float, 'change': float, 'change_pct': float} for the S&P 500
    index (^GSPC), or {} if no data is available (market data provider down,
    no network, etc.) -- caller should treat that as 'unknown', not zero."""
    ticker = yf.Ticker("^GSPC")

    intraday = ticker.history(period="1d", interval="1m")
    if intraday.empty:
        return {}
    price = float(intraday["Close"].iloc[-1])

    daily = ticker.history(period="5d", interval="1d")
    if len(daily) < 2:
        return {"price": price, "change": None, "change_pct": None}
    prev_close = float(daily["Close"].iloc[-2])

    change = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else None
    return {"price": price, "change": change, "change_pct": change_pct}
