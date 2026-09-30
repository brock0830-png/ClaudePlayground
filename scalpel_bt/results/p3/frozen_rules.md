# PHASE 3 FROZEN RULES — committed before any test market was loaded

Selected from `results/p3/log.csv` (258 pre-registered variants, `PROTOCOL_P3.md`). Development data: SPY
1994-2012 (market-on-close) and ES 2013-2019 (next open). Of the 258 variants, 184 passed all six development
gates. Pre-registered selection: best pooled t-statistic per group, at most one per group. The unchanged P2A goes
to the test as a reference. Machine-readable specs: `results/p3/frozen_candidates.json`. The test is
`python scripts/p3_test.py`, locked to this commit.

## Definitions (daily bars; ES sessions = TradingView trading days, 18:00-17:00 ET)

- IBS = (close - low) / (high - low) of the day.
- RSI2 = 2-period Wilder RSI of closes.
- ATR20 = mean of (high - low) over the last 20 days including today.
- VIX = CBOE VIX close of the same date.
- Execution: ETFs at the signal day's close; ES at the next 18:00 ET open. Time exits after N sessions (at a
  close for ETFs, at the next open for ES). Costs: ETF 0.05% per round trip; ES 0.60 pt + 0.60 pt per roll.
  No stops, no targets.

## P3A — P2A with stacking (group A, variant 179)

- Signal: IBS < 0.30 and VIX > 20.
- Each signal buys 1 unit, held for 5 sessions. A new signal while units are open adds another unit, up to
  **3 open units**.
- Development: 809 trades (SPY 729, ES 80), +0.56% per trade (CI +0.32..+0.79%), PF 1.54, t 4.65,
  random-exposure percentile 100, 86% of years positive.
- **Caveat stated before the test:** overlapping units are correlated, which inflates the t-statistic that ranked
  this variant first. The test will show whether stacking beats the unstacked P2A.

## P3B — composite oversold score, no VIX filter (group B, variant 250) — the "new take"

- Score = mean of four readings, each scaled 0 to 1 (1 = most oversold):
  1. 1 - IBS.
  2. 1 - RSI2/100.
  3. 1 - (share of the last 252 days whose 3-day change in ATR20 units was below today's).
  4. 1 - (share of the last 252 days whose (close - MA5)/ATR20 was below today's).
- Signal: score > 0.90, and no position open. Buy 1 unit, hold 5 sessions.
- Development: 249 trades (SPY 201, ES 48), +0.83% per trade (CI +0.51..+1.16%), PF 2.45, t 4.89,
  random-exposure percentile 100, 96% of years positive. ES 2014-2019: +15.4 pt per trade.
- Its VIX > 20 twin (variant 241) had almost the same t (4.885) and a higher return per trade (+1.17%) but
  fewer trades.

## P3C — 126-day momentum regime (group C, variant 255)

- Long while the close is above the close 126 sessions earlier; flat otherwise (checked every close).
- Development: 85 trades (holds average about 60 sessions), +4.1% per trade, PF 6.2, t 2.08,
  random-exposure percentile 90.4. It was the only trend variant to pass all gates.

## Reference — P2A unchanged (variant 5)

- Signal: IBS < 0.30 and VIX > 20, no position open; hold 5 sessions.
- Development: 368 trades (SPY 1994-2012: 326 trades, +0.55%; ES 2013-2019: 42 trades, +1.20% / +27.5 pt),
  CI +0.30..+0.94%, PF 1.70.
- SPY 1994-2012 was never used when P2A was chosen in Phase 2, so this is already an independent confirmation
  on 19 years of older data.

## Test (once): QQQ, IWM, DIA, EFA, EWG, EWJ, EWU, from each market's second year to 2026-09-18

- **Confirmed** if the pooled mean trade return > 0 with bootstrap CI lower bound > 0, at least 5 of 7 markets
  have a positive mean, and it beats pooled random exposure at the 90th percentile or better.
- Also reported: next-open execution; per market; by decade; DSR (N = 258; trial variance = variance of per-trade
  Sharpe over variants with n >= 60); ES 2020-2026 in points (third look, not in the verdict).
- No rule changes after the test.
