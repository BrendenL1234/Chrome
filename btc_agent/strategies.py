"""Strategies map a close-price series to a target BTC weight in [0, 1] for each day.

The weight on day t uses only prices up to and including day t; the backtester
applies it to the following day's return, so there is no look-ahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def buy_hold(close: pd.Series, **_) -> pd.Series:
    return pd.Series(1.0, index=close.index)


def sma_trend(close: pd.Series, sma_days: int = 200, buffer: float = 0.0, **_) -> pd.Series:
    """In when price is above its moving average, out when below, with a hysteresis band."""
    sma = close.rolling(sma_days).mean()
    up = (close > sma * (1 + buffer)).to_numpy()
    down = (close < sma * (1 - buffer)).to_numpy()
    w = np.zeros(len(close))
    state = 0.0
    for i in range(len(close)):
        if up[i]:
            state = 1.0
        elif down[i]:
            state = 0.0
        w[i] = state
    return pd.Series(w, index=close.index)


def ma_cross(close: pd.Series, fast_days: int = 20, slow_days: int = 100, **_) -> pd.Series:
    fast = close.rolling(fast_days).mean()
    slow = close.rolling(slow_days).mean()
    return (fast > slow).astype(float)


def vol_target_trend(close: pd.Series, sma_days: int = 200, buffer: float = 0.0,
                     target_vol: float = 0.40, vol_days: int = 30, **_) -> pd.Series:
    """Trend filter, with the position scaled down when recent volatility is above target."""
    vol = close.pct_change().rolling(vol_days).std() * np.sqrt(365)
    scale = (target_vol / vol).clip(upper=1.0).fillna(0.0)
    return sma_trend(close, sma_days, buffer) * scale


STRATEGIES = {
    "buy_hold": buy_hold,
    "sma_trend": sma_trend,
    "ma_cross": ma_cross,
    "vol_target_trend": vol_target_trend,
}


def target_weights(close: pd.Series, name: str, **params) -> pd.Series:
    if name not in STRATEGIES:
        raise ValueError(f"unknown strategy {name!r}; choose from {sorted(STRATEGIES)}")
    return STRATEGIES[name](close, **params).clip(0.0, 1.0)
