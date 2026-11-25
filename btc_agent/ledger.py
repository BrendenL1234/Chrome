"""Trade log with a running adjusted cost base (average cost), for tax records.

Only trades made by the agent are tracked. BTC bought elsewhere has a cost base
this ledger does not know; sales beyond the tracked units are flagged.
Superficial-loss adjustments (selling at a loss and rebuying within 30 days) are
NOT applied - a trend strategy will trigger them, so give trades.csv to your accountant.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ["time", "side", "qty", "price", "fee", "units_after", "acb_after", "realized_gain", "order_id", "note"]


class Ledger:
    def __init__(self, state_dir: str | Path):
        self.dir = Path(state_dir)
        self.path = self.dir / "ledger.json"
        self.csv = self.dir / "trades.csv"
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {"units": 0.0, "acb": 0.0}

    def record(self, fill) -> float | None:
        """Apply a fill. Returns the realized gain for sells (None for buys)."""
        s, gain, note = self.state, None, fill.note
        if fill.side == "buy":
            s["units"] += fill.qty
            s["acb"] += fill.qty * fill.price + fill.fee
        else:
            known = min(fill.qty, s["units"])
            cost = s["acb"] * known / s["units"] if s["units"] > 0 else 0.0
            if known < fill.qty - 1e-12:
                note = (note + " " if note else "") + "sold units with unknown cost base"
            gain = fill.qty * fill.price - fill.fee - cost
            s["units"] -= known
            s["acb"] -= cost
            if s["units"] < 1e-12:
                s["units"], s["acb"] = 0.0, 0.0
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(s, indent=2))
        new = not self.csv.exists()
        with self.csv.open("a", newline="") as f:
            w = csv.DictWriter(f, FIELDS)
            if new:
                w.writeheader()
            w.writerow({
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "side": fill.side,
                "qty": f"{fill.qty:.8f}", "price": f"{fill.price:.2f}", "fee": f"{fill.fee:.2f}",
                "units_after": f"{s['units']:.8f}", "acb_after": f"{s['acb']:.2f}",
                "realized_gain": "" if gain is None else f"{gain:.2f}", "order_id": fill.order_id, "note": note,
            })
        return gain
