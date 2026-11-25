"""Order execution. PaperBroker simulates fills; CcxtBroker talks to a real exchange.

Neither broker can withdraw: no withdrawal call exists anywhere in this package,
and the exchange API key should be created without that permission.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

LIVE_ENV = "BTC_AGENT_LIVE"
LIVE_PHRASE = "yes-real-money"


@dataclass
class Fill:
    side: str        # "buy" | "sell"
    qty: float       # BTC
    price: float     # quote per BTC, after slippage
    fee: float       # quote currency
    order_id: str = ""
    note: str = ""


class PaperBroker:
    def __init__(self, state_dir: str | Path, starting_cash: float, fee: float, slippage: float):
        self.path = Path(state_dir) / "paper.json"
        self.fee, self.slippage = fee, slippage
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
        else:
            self.state = {"cash": starting_cash, "btc": 0.0}
        self._price = None

    def set_price(self, price: float):
        self._price = price

    def price(self) -> float:
        return self._price

    def balances(self) -> tuple[float, float]:
        return self.state["cash"], self.state["btc"]

    def order(self, side: str, qty: float) -> Fill:
        px = self._price * (1 + self.slippage if side == "buy" else 1 - self.slippage)
        notional = qty * px
        fee = notional * self.fee
        if side == "buy":
            if notional + fee > self.state["cash"] + 1e-9:
                raise ValueError("paper account has insufficient cash")
            self.state["cash"] -= notional + fee
            self.state["btc"] += qty
        else:
            if qty > self.state["btc"] + 1e-12:
                raise ValueError("paper account has insufficient BTC")
            self.state["btc"] -= qty
            self.state["cash"] += notional - fee
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2))
        return Fill(side, qty, px, fee, order_id=f"paper-{int(time.time() * 1000)}")


class CcxtBroker:
    """Spot market orders on a real exchange.

    validate_only=True sends Kraken's `validate` flag: the exchange checks the
    order and places nothing. Real orders additionally require the environment
    variable BTC_AGENT_LIVE=yes-real-money.
    """

    def __init__(self, exchange: str, symbol: str, validate_only: bool):
        import ccxt

        if not validate_only and os.environ.get(LIVE_ENV) != LIVE_PHRASE:
            raise PermissionError(f"live trading needs {LIVE_ENV}={LIVE_PHRASE} in the environment")
        if validate_only and exchange != "kraken":
            raise ValueError("validate mode relies on Kraken's validate flag; use paper mode on other exchanges")
        key, secret = os.environ.get("BTC_AGENT_API_KEY"), os.environ.get("BTC_AGENT_API_SECRET")
        if not key or not secret:
            raise PermissionError("set BTC_AGENT_API_KEY and BTC_AGENT_API_SECRET in the environment")
        self.ex = getattr(ccxt, exchange)({"apiKey": key, "secret": secret, "enableRateLimit": True})
        self.symbol, self.validate_only = symbol, validate_only
        self.base, self.quote = symbol.split("/")

    def price(self) -> float:
        return float(self.ex.fetch_ticker(self.symbol)["last"])

    def balances(self) -> tuple[float, float]:
        total = self.ex.fetch_balance()["total"]
        return float(total.get(self.quote) or 0.0), float(total.get(self.base) or 0.0)

    def order(self, side: str, qty: float) -> Fill | None:
        qty = float(self.ex.amount_to_precision(self.symbol, qty))
        params = {"validate": True} if self.validate_only else {}
        placed = self.ex.create_order(self.symbol, "market", side, qty, None, params)
        if self.validate_only:
            return None
        oid = placed.get("id") or ""
        detail, note = placed, ""
        for _ in range(5):                       # market orders fill fast; poll briefly for the fill details
            time.sleep(2)
            try:
                detail = self.ex.fetch_order(oid, self.symbol)
            except Exception as e:               # noqa: BLE001 - order is already placed; record what we know
                note = f"could not read fill details: {e}"
                continue
            if detail.get("status") == "closed":
                note = ""
                break
        px = detail.get("average") or detail.get("price")
        filled = detail.get("filled") or qty
        fee = (detail.get("fee") or {}).get("cost")
        if px is None or fee is None:
            note = (note + " " if note else "") + "fill price or fee estimated; reconcile against the exchange statement"
            px = px or self.price()
            fee = fee or 0.0
        return Fill(side, float(filled), float(px), float(fee), order_id=oid, note=note)
