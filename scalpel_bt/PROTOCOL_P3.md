# PROTOCOL_P3.md — Phase 3 pre-registration: a different pass at the "buy fear" system

Written and committed before any Phase 3 result was computed (2026-09-30).

## Why a Phase 3, and what is different

Phase 2 found one rule that held up on ES 2020-2026. **P2A:** buy when the session closes in the bottom 30% of its range
(IBS < 0.3) while VIX > 20, and hold 5 sessions. Phase 2 left three gaps, which Phase 3 addresses:

1. **Untested variations:** Phase 2 tried only 1/3/5-session holds plus signal exits, and no profit targets or stops.
   Trend was only tested as a single filter, never combined with the VIX gate, and volume was never tested.
2. **The window is spent:** ES 2020-2026 has now been looked at twice and P2A's result there is known. Any variant
   "tested" on it would be biased toward what already worked, so it cannot decide anything in Phase 3.
3. **Short development history:** 2013-2019 was one bull market.

What changes:

- **Development:** S&P 500 over 27 years = SPY daily OHLC 1993-01-29 to 2012-12-31 (dividend-adjusted, FMP, with
  volume) plus ES sessions 2013-01-02 to 2019-12-31 (the Phase 1-2 DEV). This covers the 2000-2002 and 2008 bear markets.
- **Decisive test, untouched:** seven markets never used for any rule in Phases 1-3: **QQQ, IWM, DIA, EFA, EWG, EWJ,
  EWU**. Full histories (1996/1998/1999/2000/2001 starts) to 2026-09-18, daily OHLC, dividend-adjusted. The loader
  refuses them until `results/p3/TEST_UNLOCKED` names the Phase 3 freeze commit. **P2A itself, unchanged, is tested
  there too:** that is the independent check it lacked.
- ES 2020-2026 is reported for the Phase 3 picks but flagged as a third look. It does not enter any verdict.
- New approaches: composite oversold scores instead of one hard rule; exit engineering (targets, stops,
  exit-on-strength); trend and volume context.

## Engine (`scalpel/p3.py`)

- Daily bars. ES: signal at the 17:00 ET session close, entry at the 18:00 ET open, time exits at the open after the
  N-th session close (identical to Phase 2: the engine reproduces P2A's DEV result, 42 trades, +27.48 pt, exactly).
  ETFs: market-on-close at the signal close, time exits at a close; next-open entry reported as a robustness check.
- Stops and targets in ATR20 (mean daily high-low of the 20 sessions up to the signal). Checked on each held day's
  high/low; a day reaching both fills the stop; gaps fill at the open.
- Costs: ES 0.60 pt per round trip + 0.60 pt per roll carried; ETFs 0.05% per round trip.
- All results in % of entry price (ES also in points).
- VIX features come from the full CBOE series (no warm-up loss). SPY volume stands in for ES volume, which is
  unavailable before 2020.

## Grids (fixed in `scripts/p3_screen.py`)

Base entry E0 = IBS < 0.3 and VIX > 20 (P2A's entry).

| Family | What varies | Variants |
|---|---|---|
| V1 hold | E0, hold 1,2,3,4,5,6,7,8,10,12,15,20 sessions | 12 |
| V2 exit | E0, exit on close > prior high / IBS > 0.7 / RSI2 > 70 / close > MA5 / close > MA10 (max 10 sessions) | 5 |
| V3 target x stop | E0, target 0/0.5/1/1.5/2/3 ATR x stop 0/1/1.5/2/3 ATR x max hold 5/10 | 60 |
| V4 thresholds | IBS < 0.1..0.5 x VIX gate none/15/20/25/30 x hold 3/5 | 50 |
| V4b relative VIX | IBS < 0.1..0.5 x VIX > its 1y mean / VIX 1y percentile > 0.7 / VIX > 1.2 x its 1y mean x hold 3/5 | 30 |
| V5 trend | E0 or IBS < 0.3 alone, plus close vs MA200/MA50, MA50 vs MA200, 126-day momentum; hold 5 | 14 |
| V6 volume | E0 or IBS < 0.3 alone, plus SPY volume > 1.2/1.5/2.0 x its 50-day mean; hold 5 | 6 |
| V7 stacking | E0, hold 5, up to 2 or 3 overlapping positions | 2 |
| C1 ensemble | k of {IBS<0.3, RSI2<15, close < prior 5-day low, 2+ down closes}, k = 2/3/4 x gate VIX>20 / VIX pct>0.7 / VIX>1.1 x 1y mean / none x exit hold 3 / hold 5 / close > prior high | 36 |
| C2 score | continuous oversold score (mean of 4 trailing ranks) > 0.75/0.85/0.90 x same gates x same exits | 36 |
| T1 trend-following | long while close > MA50 / MA100 / MA200 / 126d momentum > 0 / 252d momentum > 0 | 5 |
| T2 trend + dips | long while close > MA200 (or MA50), plus 5 sessions after any E0 signal | 2 |

Total 258 Phase 3 variants, all logged in `results/p3/log.csv`.

## Development gates (pooled = SPY 1993-2012 trades + ES 2013-2019 trades, in %)

- D1. Mean trade return > 0 on **both** SPY 1993-2012 and ES 2013-2019.
- D2. At least 20 trades in each, 60 in total.
- D3. Beats random exposure (same count, same holding sessions, random days) at the pooled 90th percentile or better.
- D4. Pooled bootstrap 95% CI of the mean trade return has a lower bound > 0.
- D5. Plateau, not a spike: the one-step neighbours in the family grid (numeric parameters only) have a mean pooled
  return > 0 and at least half the variant's own.
- D6. At least 60% of calendar years with trades are positive (pooled, 1993-2019).

Selection: rank by the pooled t-statistic of trade returns. At most one pick from each group: (A) refinements of
P2A (V1-V7), (B) composite scores (C1-C2), (C) trend (T1-T2). Up to 3 picks, frozen with a commit before the test.

## Test (once, after the freeze)

Each pick and the unchanged P2A are run on QQQ, IWM, DIA, EFA, EWG, EWJ, EWU with market-on-close execution, from
each market's first date with a full year of history to 2026-09-18.

- **Confirmed** if the pooled mean trade return > 0 with bootstrap CI lower bound > 0, **and** at least 5 of 7 markets
  have a positive mean, **and** it beats pooled random exposure at the 90th percentile or better.
- Also reported: per-market results, next-open entry, profit factor, by-decade results, and DSR with N = 258.
