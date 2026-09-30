# Phase 2 OOS report — directional ES rules from price and VIX (2020-01-01 to 2026-09-30)

- Pre-registration: `PROTOCOL_P2.md` (commit `51c37fb`), 640 variants screened on DEV (`results/p2/log.csv`).
- Rules frozen in commit `01bcc31` (`results/p2/frozen_rules.md`) before any Phase 2 rule touched 2020-2026.
- One OOS run (`python scripts/p2_candidates.py oos`); output in `oos_results.json`, `oos_trades_*.csv`,
  `oos_equity.png`. Nothing was changed afterwards.

## Verdict

| Candidate | Rule | Protocol verdict | In plain English |
|---|---|---|---|
| **P2A** | Session closes in the bottom 30% of its range (IBS < 0.3) while VIX closes > 20 → buy ES at the next open, hold 5 sessions | **PAPER TRADE IT.** Every "trade it" test passed except the deflated Sharpe | **The one real finding.** Positive in every OOS year, CI above zero, beats randomly timed long exposure. Worth paper trading now; if traded, MES at small size, because it has no stop. |
| P2B | Long overnight (18:00→10:00 ET) only when the close is below its 50-day MA | PAPER TRADE IT, *drift only* | Its OOS profit is what random long exposure earns. Not worth the daily round trip. |
| P2C | VIX closes > 1.2 × its 10-day average → buy, hold 10 sessions | PAPER TRADE IT, *drift only* | Positive but not significant (CI -31..+98 pt), 70th percentile vs random exposure. Not an edge on this evidence. |

**Why P2A is not "trade it" under the protocol.** The deflated Sharpe ratio (DSR) with N = 640 trials is about 0
(verdict version) and 0.15 using sampling-noise variance. An OOS annualised Sharpe of 0.79 is not enough to rule out
"best of 640 tries" luck by that yardstick. Two more reasons for caution: this OOS window was used once before (Phase 1),
and I know the broad 2020-2026 market history. In its favour, the effect was not invented here. Buying equity-index
weakness (low IBS, short-term oversold) when volatility is high is a published, long-studied pattern, and its close-only
siblings with the same VIX > 20 filter were positive on SPX 1990-2012 as well.

## Known limitations

- 4-hour TradingView ES bars and daily VIX only; **no volume** anywhere before 2020-11, so volume signals were not testable.
- Sessions follow TradingView's trading days. IBS uses the full 23-hour session's high and low, not the cash session's.
- Continuous ES1! with every switch gap removed; each roll held costs 0.60 pt.
- Costs 0.30 pt per side. No stops, so fills are always at bar opens (no intrabar ambiguity).

## P2A in detail (1 ES per signal, net of costs)

| Metric | DEV 2013-2019 | **OOS 2020-2026** |
|---|---|---|
| Trades | 42 | **111** |
| Win rate | 76% | **66%** |
| EV / trade | +27.5 pt | **+29.9 pt (+$1,495 per ES, +$150 per MES)** |
| Bootstrap 95% CI of EV | [+10.8, +42.5] | **[+4.6, +55.1]** |
| Profit factor | 3.64 | **1.82** |
| Total | +1,154 pt | **+3,319 pt** |
| Max drawdown (trade sequence) | | **-603 pt** |
| Worst trade | | **-584 pt** (entered 2025-03-30, into the April 2025 tariff crash) |
| Best trade | | +418 pt |
| Worst month | | -365 pt (2020-03) |
| Annualised Sharpe (daily P&L, all days) | 0.97 | **0.79** (ES buy-and-hold: 0.64) |
| Random-exposure percentile (same count and holding times) | 100 | **96.4** |
| Timing excess over drift | +931 pt | **+2,120 pt** |
| Sessions in the market | 214 | 565 (about 33% of sessions) |
| PSR (Sharpe > 0) | | 0.98 |
| DSR, N = 640 (verdict / noise-variance) | ~0 / 0.30 | **~0 / 0.15** |
| Fixed-fractional, $100k, MES sized at 1% per 2×ATR20 | | $109.4k (+1.3%/yr), max DD -4.9% |

For comparison, ES buy-and-hold over OOS made +3,675 pt per contract with a -1,211 pt max drawdown. P2A made 90% of
that while in the market a third of the time, with half the drawdown.

The fixed-fractional sizing (1% of equity per two average daily ranges) is deliberately small, hence the small
percentage return. At 1 MES per $25k of equity, P2A's OOS average trade is about 0.6% of equity, and its worst trade
(-584 pt = -$2,918 per MES) would have been about -11.7%.

**By year (OOS) — every year positive**

| Year | Trades | Win | EV pt | Total pt |
|---|---|---|---|---|
| 2020 | 27 | 67% | +18.9 | +511 |
| 2021 | 14 | 64% | +27.0 | +379 |
| 2022 | 35 | 57% | +6.3 | +222 |
| 2023 | 9 | 67% | +51.7 | +465 |
| 2024 | 6 | 67% | +34.4 | +207 |
| 2025 | 11 | 82% | +51.7 | +569 |
| 2026 (to Sep) | 9 | 78% | +107.5 | +967 |

Not dependent on one period: without 2020, +33.4 pt/trade (84 trades); without 2022, +40.8; without both, +52.8;
without its five best trades, +16.7 pt/trade.

**By VIX regime (signal-day VIX close):** 20-30: 89 trades, +19.7 pt; above 30: 22 trades, +71.2 pt. It never trades
below 20 by construction. Higher VIX means bigger moves and bigger average payoffs, and bigger losses too
(2020-03-11 at VIX 54: -327 pt).

## P2B and P2C (OOS)

| | P2B overnight in pullbacks | P2C VIX spike, hold 10 |
|---|---|---|
| Trades | 507 | 35 |
| EV / trade (95% CI) | +1.41 pt (-2.63, +5.62) | +36.3 pt (-31.0, +98.1) |
| Profit factor | 1.08 | 1.57 |
| Sharpe (annualised) | 0.25 | 0.36 |
| Random-exposure percentile | 61 | 70 |
| Timing excess | -9 pt | +516 pt |
| Worst trade | -225 pt | -491 pt |
| Positive years | 5 / 7 | 5 / 7 |

Both lost their DEV timing edge: their OOS profits are what ES drift pays for the same time in the market.

The pre-declared 1+1+1 combination made +5,303 pt at Sharpe 0.60 with a -2,310 pt max drawdown, worse on risk than
buy-and-hold (0.64, -1,211). P2B and P2C add risk without adding edge. **P2A alone is the system.**

## If you run P2A

- **Signal (after the 17:00 ET close):** today's ES session IBS = (close - low) / (high - low) < 0.30 and today's VIX close > 20,
  and no P2A position is open.
- **Entry:** buy at the 18:00 ET open. **Exit:** sell at the 18:00 ET open after the 5th session close.
- It signals about 16 times a year, clustered in volatile periods (35 trades in 2022, 6 in 2024).
- **Risk:** no stop by design; the worst OOS trade was -584 pt. Size in MES so a -600 pt hold is survivable.
  Adding a stop now would be tuning on OOS. It could be tested on DEV in a new pre-registered round.
- **Forward test:** at about 16 signals a year, a few months of paper trading checks execution, not the edge.
  Whether to risk capital rests on the OOS result above plus the published record of this effect.
- An exact live signal script can be added on request (the rule is `scripts/p2_candidates.py` + `scalpel/p2.py`).
