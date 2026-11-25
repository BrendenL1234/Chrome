from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

MODES = ("paper", "validate", "live")


@dataclass
class Config:
    mode: str = "paper"
    exchange: str = "kraken"
    symbol: str = "BTC/USD"
    state_dir: str = "state"
    strategy: dict = field(default_factory=lambda: {"name": "sma_trend", "sma_days": 200, "buffer": 0.02})
    max_allocation: float = 0.50
    rebalance_band: float = 0.05
    max_order_quote: float = 250.0
    min_order_quote: float = 10.0
    max_orders_per_day: int = 1
    starting_cash: float = 1000.0
    fee: float = 0.004
    slippage: float = 0.001

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {self.mode!r}")
        if not 0 <= self.max_allocation <= 1:
            raise ValueError("risk.max_allocation must be between 0 and 1")
        if self.max_order_quote <= 0:
            raise ValueError("risk.max_order_quote must be positive")


def load(path: str | Path | None) -> Config:
    if path is None:
        return Config()
    raw = tomllib.loads(Path(path).read_text())
    flat = {k: v for k, v in raw.items() if not isinstance(v, dict)}
    flat.update(raw.get("risk", {}))
    flat.update(raw.get("paper", {}))
    if "strategy" in raw:
        flat["strategy"] = raw["strategy"]
    return Config(**flat)
