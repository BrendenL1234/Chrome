"""Trend and pattern read-out for the latest day."""
from __future__ import annotations

import numpy as np
import pandas as pd


def analyze(close: pd.Series) -> dict:
    if len(close) < 200:
        raise ValueError(f"need at least 200 daily closes, got {len(close)}")
    price = close.iloc[-1]
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    mayer = (close / sma200).dropna()                     # price / 200-day average
    above = (close > sma200)[sma200.notna()]
    flips = above.ne(above.shift()).to_numpy().nonzero()[0]
    days_in_state = len(above) - flips[-1]
    rets = close.pct_change()
    vol30 = rets.rolling(30).std().iloc[-1] * np.sqrt(365)
    mom = {d: price / close.iloc[-d - 1] - 1 for d in (30, 90, 365) if len(close) > d}
    dd = price / close.max() - 1

    if price > sma200.iloc[-1] and sma50.iloc[-1] > sma200.iloc[-1]:
        regime = "uptrend"
    elif price < sma200.iloc[-1] and sma50.iloc[-1] < sma200.iloc[-1]:
        regime = "downtrend"
    else:
        regime = "transition"

    return {
        "date": close.index[-1].date().isoformat(),
        "price": price,
        "sma50": sma50.iloc[-1],
        "sma200": sma200.iloc[-1],
        "regime": regime,
        "above_sma200": bool(above.iloc[-1]),
        "days_in_state": int(days_in_state),
        "mayer_multiple": mayer.iloc[-1],
        "mayer_percentile": float((mayer < mayer.iloc[-1]).mean()),
        "momentum": mom,
        "vol30_annualised": vol30,
        "drawdown_from_high": dd,
    }


def format_report(a: dict) -> str:
    mom = "  ".join(f"{d}d {v:+.1%}" for d, v in a["momentum"].items())
    side = "above" if a["above_sma200"] else "below"
    return "\n".join([
        f"As of {a['date']}: price {a['price']:,.0f}",
        f"Regime: {a['regime']} ({side} the 200-day average for {a['days_in_state']} days)",
        f"50-day avg {a['sma50']:,.0f} | 200-day avg {a['sma200']:,.0f}",
        f"Price / 200-day avg: {a['mayer_multiple']:.2f} "
        f"(higher than {a['mayer_percentile']:.0%} of days in this history)",
        f"Momentum: {mom}",
        f"30-day volatility (annualised): {a['vol30_annualised']:.0%}",
        f"Drawdown from the high in this history: {a['drawdown_from_high']:.1%}",
    ])
