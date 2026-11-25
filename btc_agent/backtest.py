"""Backtesting with fees, slippage, and a walk-forward (out-of-sample) test."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .strategies import target_weights


def simulate(close: pd.Series, weights: pd.Series, cost: float = 0.005) -> pd.Series:
    """Equity curve starting at 1.0. `cost` is fee + slippage charged on each unit of turnover.

    The weight chosen at the close of day t is held over day t+1.
    """
    held = weights.shift(1).fillna(0.0)
    turnover = held.diff().abs().fillna(held.abs())
    growth = (1 + held * close.pct_change().fillna(0.0)) * (1 - cost * turnover)
    return growth.cumprod()


def metrics(equity: pd.Series, weights: pd.Series | None = None) -> dict:
    rets = equity.pct_change().dropna()
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    total = equity.iloc[-1] / equity.iloc[0]
    vol = rets.std() * np.sqrt(365)
    out = {
        "multiple": total,
        "cagr": total ** (1 / years) - 1,
        "vol": vol,
        "sharpe": (rets.mean() * 365) / vol if vol > 0 else 0.0,
        "max_drawdown": (equity / equity.cummax() - 1).min(),
    }
    if weights is not None:
        held = weights.shift(1).fillna(0.0)
        out["time_in_market"] = (held > 0).mean()
        out["trades"] = int((held.diff().abs() > 1e-9).sum())
    return out


def run(close: pd.Series, name: str, cost: float = 0.005, **params) -> dict:
    w = target_weights(close, name, **params)
    return metrics(simulate(close, w, cost), w)


def walk_forward(close: pd.Series, grid=(50, 100, 150, 200, 250), buffer: float = 0.02,
                 cost: float = 0.005, warmup_years: int = 4) -> tuple[pd.Series, pd.Series, list]:
    """Each calendar year, pick the SMA length with the best Sharpe on all *earlier* data,
    then trade the next year with it. Returns (stitched weights, equity, choices).

    This is the honest number: no parameter is ever chosen using the data it is scored on.
    """
    all_w = {n: target_weights(close, "sma_trend", sma_days=n, buffer=buffer) for n in grid}
    years = sorted(set(close.index.year))
    pieces, choices = [], []
    for y in years[warmup_years:]:
        past = close[close.index.year < y]
        best = max(grid, key=lambda n: metrics(simulate(past, all_w[n].loc[past.index], cost))["sharpe"])
        choices.append((y, best))
        pieces.append(all_w[best][close.index.year == y])
    w = pd.concat(pieces)
    return w, simulate(close.loc[w.index], w, cost), choices


def dca(close: pd.Series, every_days: int = 7, amount: float = 100.0, fee: float = 0.005) -> dict:
    """Fixed-amount recurring buys. Returns invested total, end value and worst mark-to-market loss."""
    buys = close.iloc[::every_days]
    units = (amount * (1 - fee) / buys).cumsum().reindex(close.index).ffill().fillna(0.0)
    invested = pd.Series(amount, index=buys.index).cumsum().reindex(close.index).ffill().fillna(0.0)
    value = units * close
    pnl = (value / invested - 1).replace([np.inf, -np.inf], np.nan).dropna()
    return {"invested": invested.iloc[-1], "value": value.iloc[-1],
            "multiple": value.iloc[-1] / invested.iloc[-1], "worst_underwater": pnl.min()}
