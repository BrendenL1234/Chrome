import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from btc_agent import backtest as bt
from btc_agent.agent import run_once
from btc_agent.broker import CcxtBroker, Fill, PaperBroker
from btc_agent.config import Config
from btc_agent.ledger import Ledger
from btc_agent.signals import analyze
from btc_agent.strategies import target_weights


def series(values, end="2026-01-31"):
    return pd.Series(np.asarray(values, float), index=pd.date_range(end=end, periods=len(values)), name="close")


def rising(n=400):
    return series(100 * 1.005 ** np.arange(n))


def falling(n=400):
    return series(100 * 0.995 ** np.arange(n))


NOW = datetime(2026, 2, 1, tzinfo=timezone.utc)


def cfg(tmp_path, **kw):
    return Config(state_dir=str(tmp_path), **kw)


def test_trend_weights_follow_direction():
    assert target_weights(rising(), "sma_trend", sma_days=200).iloc[-1] == 1.0
    assert target_weights(falling(), "sma_trend", sma_days=200).iloc[-1] == 0.0


def test_no_lookahead():
    # A one-day spike must not earn anything for a strategy that was flat going into it.
    close = series([100.0] * 300 + [200.0])
    w = target_weights(close, "sma_trend", sma_days=200)
    assert bt.simulate(close, w, cost=0).iloc[-1] == pytest.approx(1.0)


def test_costs_reduce_equity():
    close = series(100 + 20 * np.sin(np.arange(900) / 20) + np.arange(900) * 0.05)
    w = target_weights(close, "sma_trend", sma_days=50)
    assert bt.simulate(close, w, 0.01).iloc[-1] < bt.simulate(close, w, 0.0).iloc[-1]


def test_buy_hold_matches_price():
    close = rising()
    eq = bt.simulate(close, target_weights(close, "buy_hold"), cost=0)
    assert eq.iloc[-1] == pytest.approx(close.iloc[-1] / close.iloc[0])


def test_analyze_regime():
    assert analyze(rising())["regime"] == "uptrend"
    assert analyze(falling())["regime"] == "downtrend"


def test_paper_buy_respects_caps(tmp_path):
    c = cfg(tmp_path, max_allocation=0.5, max_order_quote=100, starting_cash=1000)
    e = run_once(c, rising(), now=NOW)
    assert e["action"] == "buy"
    assert e["qty"] * e["fill_price"] <= 100 * 1.0011
    cash, btc = PaperBroker(tmp_path, 1000, c.fee, c.slippage).balances()
    assert btc > 0 and cash == pytest.approx(1000 - e["qty"] * e["fill_price"] - e["fee"])
    # second run the same day is blocked by the daily order limit
    assert run_once(c, rising(), now=NOW)["reason"] == "daily order limit reached"


def test_holds_in_downtrend_with_no_btc(tmp_path):
    assert run_once(cfg(tmp_path), falling(), now=NOW)["action"] == "hold"


def test_sells_when_trend_breaks(tmp_path):
    c = cfg(tmp_path, max_order_quote=10_000)
    (tmp_path / "paper.json").write_text(json.dumps({"cash": 500.0, "btc": 5.0}))
    e = run_once(c, falling(), now=NOW)
    assert e["action"] == "sell" and e["qty"] == pytest.approx(5.0)


def test_stop_file_halts(tmp_path):
    (tmp_path / "STOP").touch()
    assert run_once(cfg(tmp_path), rising(), now=NOW)["action"] == "halt"


def test_stale_data_halts(tmp_path):
    e = run_once(cfg(tmp_path), rising(), now=datetime(2026, 3, 1, tzinfo=timezone.utc))
    assert e["action"] == "halt" and "days old" in e["reason"]


def test_ledger_average_cost(tmp_path):
    led = Ledger(tmp_path)
    led.record(Fill("buy", 1.0, 100.0, 1.0))
    led.record(Fill("buy", 1.0, 200.0, 1.0))        # ACB 302 over 2 units = 151 each
    gain = led.record(Fill("sell", 1.0, 300.0, 2.0))
    assert gain == pytest.approx(300 - 2 - 151)
    assert led.state == {"units": pytest.approx(1.0), "acb": pytest.approx(151.0)}


def test_live_needs_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("BTC_AGENT_LIVE", raising=False)
    with pytest.raises(PermissionError):
        CcxtBroker("kraken", "BTC/USD", validate_only=False)
