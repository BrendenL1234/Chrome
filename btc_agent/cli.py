from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import backtest as bt
from . import config, data
from .agent import make_broker, run_once
from .signals import analyze, format_report

HISTORY = "data/btc_daily.csv"


def _prices(args, cfg):
    if args.prices:
        return data.load_csv(args.prices)
    return data.fetch_exchange(cfg.exchange, cfg.symbol)


def cmd_fetch(args, cfg):
    s = data.fetch_coinmetrics(args.out)
    print(f"saved {len(s)} daily closes ({s.index[0].date()} to {s.index[-1].date()}) to {args.out}")


def cmd_analyze(args, cfg):
    print(format_report(analyze(_prices(args, cfg))))


def _row(name, m):
    extra = f"{m['time_in_market']:>8.0%}{m['trades']:>8}" if "trades" in m else f"{'':>16}"
    return (f"{name:<26}{m['multiple']:>10.1f}x{m['cagr']:>9.1%}{m['sharpe']:>8.2f}"
            f"{m['max_drawdown']:>9.1%}{extra}")


def cmd_backtest(args, cfg):
    close = data.load_csv(args.prices or HISTORY)
    if args.start:
        close = close[close.index >= args.start]
    cost = args.cost
    print(f"{close.index[0].date()} to {close.index[-1].date()}, cost {cost:.2%} per trade (fee + slippage)\n")
    head = f"{'strategy':<26}{'growth':>11}{'CAGR':>9}{'Sharpe':>8}{'max DD':>9}{'in mkt':>8}{'trades':>8}"
    print("Full history (parameters fixed in advance, not tuned):\n" + head)
    for label, name, p in [
        ("buy & hold", "buy_hold", {}),
        ("200d trend", "sma_trend", {"sma_days": 200, "buffer": 0.0}),
        ("200d trend, 2% band", "sma_trend", {"sma_days": 200, "buffer": 0.02}),
        ("20/100 MA cross", "ma_cross", {}),
        ("200d trend, vol target 40%", "vol_target_trend", {"sma_days": 200, "buffer": 0.02}),
    ]:
        print(_row(label, bt.run(close, name, cost, **p)))

    w, eq, choices = bt.walk_forward(close, cost=cost)
    bh = close.loc[w.index]
    print(f"\nWalk-forward, out-of-sample only ({w.index[0].date()} onward):\n" + head)
    print(_row("buy & hold", bt.metrics(bh / bh.iloc[0])))
    print(_row("trend, SMA re-picked yearly", bt.metrics(eq, w)))
    print("SMA chosen per year: " + ", ".join(f"{y}:{n}" for y, n in choices))

    print(f"\nBy period (200d trend with 2% band vs buy & hold):\n{'period':<14}{'B&H CAGR':>10}{'trend CAGR':>12}"
          f"{'B&H max DD':>12}{'trend max DD':>14}")
    w2 = bt.target_weights(close, "sma_trend", sma_days=200, buffer=0.02)
    years = sorted(set(close.index.year))
    for a in range(years[0] + 1, years[-1] + 1, 4):
        seg = close[(close.index.year >= a) & (close.index.year < a + 4)]
        if len(seg) < 200:
            continue
        mb = bt.metrics(seg / seg.iloc[0])
        mt = bt.metrics(bt.simulate(seg, w2.loc[seg.index], cost))
        print(f"{a}-{min(a + 3, years[-1]):<9}{mb['cagr']:>10.1%}{mt['cagr']:>12.1%}"
              f"{mb['max_drawdown']:>12.1%}{mt['max_drawdown']:>14.1%}")

    d = bt.dca(close[close.index >= close.index[-1] - __import__('pandas').Timedelta(days=4 * 365)])
    print(f"\nWeekly $100 DCA over the last 4 years: invested ${d['invested']:,.0f}, worth ${d['value']:,.0f} "
          f"({d['multiple']:.2f}x), worst point {d['worst_underwater']:.0%} vs money put in")


def cmd_run(args, cfg):
    entry = run_once(cfg, _prices(args, cfg))
    print(json.dumps(entry, indent=2))


def cmd_status(args, cfg):
    cash, btc = make_broker(cfg).balances()
    print(f"mode {cfg.mode}: cash {cash:,.2f}, BTC {btc:.8f}")
    j = Path(cfg.state_dir) / "journal.jsonl"
    if j.exists():
        for line in j.read_text().splitlines()[-args.last:]:
            r = json.loads(line)
            print(f"{r['time']}  {r['action']:<9} {r.get('reason') or r.get('note') or ''}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="btc-agent", description=__doc__)
    p.add_argument("--config", default="config.toml" if Path("config.toml").exists() else None)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("fetch", help="download full BTC daily history (Coin Metrics community data)")
    s.add_argument("--out", default=HISTORY)
    s.set_defaults(fn=cmd_fetch)
    for name, fn, hlp in [("analyze", cmd_analyze, "current trend read-out"),
                          ("run", cmd_run, "one decision cycle (schedule this daily)")]:
        s = sub.add_parser(name, help=hlp)
        s.add_argument("--prices", help="CSV of daily closes instead of the exchange API")
        s.set_defaults(fn=fn)
    s = sub.add_parser("backtest", help="compare strategies after costs, with a walk-forward test")
    s.add_argument("--prices")
    s.add_argument("--start", default="2012-01-01")
    s.add_argument("--cost", type=float, default=0.005)
    s.set_defaults(fn=cmd_backtest)
    s = sub.add_parser("status", help="balances and recent decisions")
    s.add_argument("--last", type=int, default=10)
    s.set_defaults(fn=cmd_status)

    args = p.parse_args(argv)
    try:
        args.fn(args, config.load(args.config))
    except (PermissionError, ValueError, FileNotFoundError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
