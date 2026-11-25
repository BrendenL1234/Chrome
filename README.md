# btc-agent

A rules-based Bitcoin agent. Once a day it reads the trend, compares it with what
the account holds, and places at most one small, capped order. It starts in paper
mode (simulated money) and cannot withdraw funds in any mode.

## Read this first: what the research says

This is not a passive-income machine, and nothing here guarantees profit.

- **No trading rule reliably beats holding Bitcoin on return.** Academic tests find
  moving-average rules look good in-sample and weaken out-of-sample; one Springer
  study found no out-of-sample predictability for Bitcoin itself, and another found
  Sharpe ratios falling from 0.66 in-sample to 0.06 out-of-sample, wiped out by costs.
- **What trend rules do deliver is smaller drawdowns.** That is the repeatable part
  of the evidence, and it is what this agent is built around.
- **Most retail bots lose money.** The usual causes are overfitted backtests and fees.
  (The popular "73% fail" style numbers are unsourced; the direction is consistent.)
- **Real Bitcoin yield means taking a different risk.** Lending pays for counterparty
  risk (lenders have failed); covered calls give up the upside; grid bots keep buying
  into a falling market. DCA is a buying method, not income. None of these are automated here.

This repository's own backtest (`btc-agent backtest`, Coin Metrics daily prices,
2012-01-01 to 2026-05-23, 0.5% cost per trade) agrees:

| Strategy | CAGR | Sharpe | Worst drawdown | Trades |
|---|---|---|---|---|
| Buy & hold | 94.5% | 1.26 | -84.5% | 1 |
| 200-day trend, 2% band (agent default) | 86.0% | 1.31 | -70.9% | 50 |
| 20/100-day average cross | 94.1% | 1.38 | -70.5% | 53 |
| Walk-forward trend, 2016 onward (out-of-sample) | 64.2% | 1.22 | -64.0% | 53 |
| Buy & hold, 2016 onward | 64.5% | 1.08 | -83.8% | 1 |

The trend rule earned about the same or slightly less than holding, with shallower
losses. Past returns of this size came from Bitcoin's early growth and should not be
expected again: in 2025-2026 both lost money (-14.0% a year for holding, -7.5% for trend).

## Setup

```bash
pip install -e ".[dev]"
cp config.example.toml config.toml
pytest
```

## Commands

```bash
btc-agent fetch          # download full daily history to data/btc_daily.csv
btc-agent backtest       # strategy comparison after costs, plus walk-forward test
btc-agent analyze        # current trend read-out from the exchange's public prices
btc-agent run            # one decision cycle; schedule it once a day
btc-agent status         # balances and recent decisions
```

`analyze` and `run` take `--prices file.csv` to use a CSV instead of the exchange API.

Schedule with cron, shortly after the daily candle closes (00:00 UTC):

```
10 0 * * * cd /path/to/repo && btc-agent run >> state/cron.log 2>&1
```

## How it decides

1. Strategy gives a signal between 0 and 1 (default: 1 when price is more than 2%
   above its 200-day average, 0 when more than 2% below, otherwise unchanged).
2. Target BTC share = signal x `max_allocation`.
3. If the account is further than `rebalance_band` from target, it places one market
   order toward it, capped at `max_order_quote`.
4. Every decision goes to `state/journal.jsonl`; every fill goes to `state/trades.csv`
   with a running average cost base.

## Guardrails

- Paper mode is the default. `validate` mode sends orders to Kraken with its
  `validate` flag, so the exchange checks them and places nothing.
- Live mode needs `mode = "live"` **and** `BTC_AGENT_LIVE=yes-real-money`, plus
  `BTC_AGENT_API_KEY` / `BTC_AGENT_API_SECRET` in the environment.
- Per-order cap, allocation cap, one order a day, and a minimum order size.
- Creating a file named `STOP` in the repo or state directory halts all trading.
- It refuses to trade on price data more than 3 days old.
- There is no withdrawal code. Create the API key with only "Query Funds" and
  "Create & Modify Orders"; leave "Withdraw Funds" off and restrict it to your IP.

## Before going live

- Run in paper mode for several weeks and read the journal.
- **Live and validate modes have not been run against a real exchange.** They were
  written from the ccxt library and Kraken's documented behaviour; the build
  environment could not reach any exchange. Run `validate` first, then start with a
  small `max_order_quote`.
- Set `paper.fee` to your real tier. Kraken Pro's entry tier for Canada was listed
  at 0.40% maker / 0.80% taker when this was written.
- Tax (Canada): the CRA decides case by case whether crypto gains are business income
  (100% taxable) or capital gains (50%); regular automated trading points toward
  business income. Selling at a loss and rebuying within 30 days can trigger the
  superficial loss rule, which this ledger does not adjust for. Give `trades.csv` to
  your accountant.

## Sources

- [Technical trading and cryptocurrencies (Annals of Operations Research)](https://link.springer.com/article/10.1007/s10479-019-03357-1)
- [Bootstrap robust optimization for trading strategies (arXiv)](https://arxiv.org/pdf/2510.12725)
- [Bitcoin intraday time series momentum](https://www.researchgate.net/publication/355603160_Bitcoin_intraday_time_series_momentum)
- [Lump-sum or dollar cost averaging for bitcoin? (Amdax)](https://medium.com/amdax-asset-management/lump-sum-or-dollar-cost-averaging-42c8f5bb9938)
- [Dollar cost averaging into bitcoin (Blockstream)](https://help.blockstream.com/education/economics/bitcoin-economics/dollar-cost-averaging-into-bitcoin)
- [Bitcoin covered call strategy risks (Two Prime)](https://twoprime.com/resources/insights/bitcoin-covered-call-strategy-risks)
- [Are most retail crypto trading bots profitable? (Lenz)](https://lenz.io/q/are-retail-crypto-trading-bots-profitable)
- [Kraken API key permissions](https://docs.kraken.com/exchange/guides/rest/api-keys)
- [Kraken Pro fee schedule, Canada](https://www.kraken.com/ca/features/fee-schedule)
- [CRA: reporting income from crypto-asset transactions](https://www.canada.ca/en/revenue-agency/programs/about-canada-revenue-agency-cra/compliance/cryptocurrency-guide/income-crypto-transactions.html)
- [CIRO: crypto asset trading platforms](https://www.ciro.ca/firms/becoming-crypto-asset-trading-platform)
- [CCXT manual](https://github.com/ccxt/ccxt/wiki/Manual)
- [Coin Metrics community data](https://github.com/coinmetrics/data)
