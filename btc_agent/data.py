"""Price history: daily closes as a pandas Series indexed by UTC date."""
from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import pandas as pd

COINMETRICS_URL = "https://raw.githubusercontent.com/coinmetrics/data/master/csv/btc.csv"


def _clean(s: pd.Series) -> pd.Series:
    s = s.dropna().astype(float)
    s = s[s > 0]
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s.name = "close"
    return s


def load_csv(path: str | Path) -> pd.Series:
    """Read a CSV with a date column (time/date/timestamp) and a price column (close/PriceUSD)."""
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    tcol = next(cols[c] for c in ("time", "date", "timestamp") if c in cols)
    pcol = next(cols[c] for c in ("close", "priceusd", "price") if c in cols)
    idx = pd.to_datetime(df[tcol], utc=True).dt.tz_localize(None).dt.normalize()
    return _clean(pd.Series(df[pcol].values, index=idx))


def fetch_coinmetrics(dest: str | Path, url: str = COINMETRICS_URL) -> pd.Series:
    """Download Coin Metrics' free community BTC archive (daily, 2010 onward) and cache close prices."""
    with urllib.request.urlopen(url, timeout=120) as r:
        raw = r.read().decode()
    df = pd.read_csv(io.StringIO(raw), usecols=["time", "PriceUSD"])
    s = _clean(pd.Series(df["PriceUSD"].values, index=pd.to_datetime(df["time"])))
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    s.rename_axis("time").to_csv(dest)
    return s


def fetch_exchange(exchange: str, symbol: str, days: int = 720) -> pd.Series:
    """Daily closes from an exchange's public API via ccxt. The still-forming candle for today is dropped."""
    import ccxt

    ex = getattr(ccxt, exchange)({"enableRateLimit": True})
    since = ex.milliseconds() - days * 86_400_000
    rows = ex.fetch_ohlcv(symbol, "1d", since=since, limit=days)
    df = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"])
    idx = pd.to_datetime(df["ts"], unit="ms").dt.normalize()
    s = _clean(pd.Series(df["c"].values, index=idx))
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    return s[s.index < today]
