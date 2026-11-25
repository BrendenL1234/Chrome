"""One decision cycle: read the trend, compare with holdings, place at most one capped order."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .broker import CcxtBroker, PaperBroker
from .config import Config
from .ledger import Ledger
from .signals import analyze
from .strategies import target_weights

MAX_DATA_AGE_DAYS = 3


def make_broker(cfg: Config):
    if cfg.mode == "paper":
        return PaperBroker(cfg.state_dir, cfg.starting_cash, cfg.fee, cfg.slippage)
    return CcxtBroker(cfg.exchange, cfg.symbol, validate_only=(cfg.mode == "validate"))


def _journal(cfg: Config, entry: dict, now: datetime) -> dict:
    entry = {"time": now.isoformat(timespec="seconds"), "mode": cfg.mode, **entry}
    d = Path(cfg.state_dir)
    d.mkdir(parents=True, exist_ok=True)
    with (d / "journal.jsonl").open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def _orders_today(cfg: Config, today: str) -> int:
    p = Path(cfg.state_dir) / "journal.jsonl"
    if not p.exists():
        return 0
    rows = (json.loads(line) for line in p.read_text().splitlines() if line.strip())
    return sum(1 for r in rows if r.get("action") in ("buy", "sell") and r["time"][:10] == today
               and r.get("mode") == cfg.mode)


def run_once(cfg: Config, close: pd.Series, broker=None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()

    if Path("STOP").exists() or (Path(cfg.state_dir) / "STOP").exists():
        return _journal(cfg, {"action": "halt", "reason": "STOP file present"}, now)
    age = (pd.Timestamp(now.date()) - close.index[-1]).days
    if age > MAX_DATA_AGE_DAYS:
        return _journal(cfg, {"action": "halt", "reason": f"price data is {age} days old"}, now)

    info = analyze(close)
    signal = float(target_weights(close, **cfg.strategy).iloc[-1])
    target = signal * cfg.max_allocation

    broker = broker or make_broker(cfg)
    if isinstance(broker, PaperBroker):
        broker.set_price(float(close.iloc[-1]))
    price = broker.price()
    cash, btc = broker.balances()
    equity = cash + btc * price
    current = btc * price / equity if equity > 0 else 0.0
    base = {"regime": info["regime"], "price": price, "signal": signal, "target_weight": target,
            "current_weight": current, "equity": equity}

    delta = (target - current) * equity
    if abs(delta) < max(cfg.rebalance_band * equity, cfg.min_order_quote):
        return _journal(cfg, {**base, "action": "hold", "reason": "within rebalance band"}, now)
    if _orders_today(cfg, today) >= cfg.max_orders_per_day:
        return _journal(cfg, {**base, "action": "hold", "reason": "daily order limit reached"}, now)

    side = "buy" if delta > 0 else "sell"
    size = min(abs(delta), cfg.max_order_quote)
    if side == "buy":
        size = min(size, cash / (1 + cfg.fee + cfg.slippage))
    else:
        size = min(size, btc * price)
    if size < cfg.min_order_quote:
        return _journal(cfg, {**base, "action": "hold", "reason": "order below minimum size"}, now)

    fill = broker.order(side, size / price)
    if fill is None:
        return _journal(cfg, {**base, "action": "validated", "side": side, "quote_size": size}, now)
    gain = Ledger(cfg.state_dir).record(fill)
    return _journal(cfg, {**base, "action": side, "qty": fill.qty, "fill_price": fill.price, "fee": fill.fee,
                          "realized_gain": gain, "order_id": fill.order_id, "note": fill.note}, now)
