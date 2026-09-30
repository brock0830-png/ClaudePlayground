# Phase 3 report — variations, a new take, and a test on seven untouched markets

- Pre-registration: `PROTOCOL_P3.md` (commit `3f5225b`). Freeze: `results/p3/frozen_rules.md` (commit `3fa0a31`).
- One-shot test: `python scripts/p3_test.py`. Raw output: `test_results.json`, `test_trades_*.csv`, `test_equity.png`.
- Development log: `log.csv` (258 variants).

## Bottom line

**P2A — buy when a session closes in the bottom 30% of its range while VIX > 20, sell 5 sessions later — is
confirmed.** Frozen in Phase 2 and never modified, it has now been positive on:

- ES 2020-2026: 111 trades, +29.9 pt per trade.
- 19 years of older SPY data (1994-2012) it never saw: 326 trades, +0.55%.
- **Seven untouched markets** (Nasdaq-100, Russell 2000, Dow, EAFE, Germany, Japan, UK; 1997-2026):
  2,739 trades, +0.54% per trade, profit factor 1.46.
  - Positive in 7 of 7 markets and in every decade.
  - Beats randomly timed long exposure in each market.
  - The 95% CI stays above zero even with trades clustered by month: +0.25% to +0.83%.

The new take (**P3B, composite oversold score**) also passed, with a higher profit factor (1.56). But its edge
faded in the 2020s (+0.10% per trade), while P2A's did not (+0.61%). Stacking up to 3 P2A positions (**P3A**)
passed but earns less per trade. 126-day momentum (**P3C**) made money only as much as randomly timed long exposure
would (drift), so it is not an edge.

## What the variations showed (development: SPY 1994-2012 + ES 2013-2019, pooled)

All returns are per trade, after costs, with the P2A entry (IBS < 0.3, VIX > 20) unless stated.

- **Holding period:**
  - Per-trade return: 1 session +0.16%, 3 +0.39%, 4 +0.53%, **5 +0.62%**, 7 +0.61%, 10 +0.70%, 15 +1.12%, 20 +1.16%.
  - t-statistic peaks at 4-5 sessions (3.7-3.8).
  - At 20 sessions it no longer beats random long exposure (88th percentile): longer holds mostly collect drift.
- **Profit targets** (5-session max hold, no stop): tight targets hurt. 0.5 ATR: +0.18%; 1 ATR: +0.33%;
  1.5 ATR: +0.45%; 2 ATR: +0.54%; 3 ATR: +0.63% (same as none, +0.62%).
- **Stops:** every stop lowered the return. With a 5-session hold: no stop +0.62%, 1 ATR +0.34%, 1.5 ATR +0.43%,
  2 ATR +0.47%, 3 ATR +0.48%. With 2 ATR target and 2 ATR stop: +0.48%. Mean reversion needs room to work.
- **Exit on strength** (sell at the first close above the prior day's high, max 10 sessions): +0.53% per trade over
  about 4 sessions. **Highest t-statistic of any P2A exit (4.07 vs 3.81)**, 91% of years positive.
  RSI2 > 70: +0.46%. IBS > 0.7: +0.34%. Close > MA5: +0.33%.
- **IBS x VIX thresholds** (5-session hold): a smooth plateau, not a spike. Return rises as IBS falls and the VIX gate
  rises:
  - IBS < 0.3 with no VIX gate: +0.34%.
  - IBS < 0.3 with VIX > 20: +0.62%.
  - IBS < 0.3 with VIX > 25: +0.85% (186 trades).
  - IBS < 0.1 with VIX > 30: +1.05% (58 trades).
  - P2A sits in the middle of the good region.
- **Trend:**
  - Adding "50-day MA above 200-day MA" to P2A: +0.69% per trade, 202 trades, PF 2.02, t 3.91.
  - Adding "above the 200-day MA": +0.64%, but only 19 ES trades (failed the minimum count).
  - Below the 200-day MA: +0.49% (CI touches zero).
  - Without the VIX gate, dips in uptrends are mostly drift (fail the random-exposure test).
  - Pure trend-following (MA50/100/200 regimes) failed the random-exposure test. 126-day momentum passed in development
    but not on the untouched markets.
- **Volume** (SPY volume > 1.2x its 50-day average, added to P2A): +0.74% per trade (182 trades, PF 1.96).
  At 1.5x: +0.86% (107 trades). Better per trade, half the signals.
- **Composite scores:**
  - k-of-4 oversold ensembles and the continuous oversold score all passed (68 of 72 variants).
  - The score > 0.90 with no VIX filter was the best by t-statistic (4.89).

## Test on untouched markets (QQQ, IWM, DIA, EFA, EWG, EWJ, EWU; market-on-close, 0.05% round trip)

| System | Trades | Avg trade | 95% CI | Month-clustered CI | PF | Markets positive | Random-exposure pct | Result |
|---|---|---|---|---|---|---|---|---|
| **P2A (unchanged)** | 2,739 | **+0.54%** | +0.39..+0.69 | +0.25..+0.83 | 1.46 | **7/7** | 100 | **Confirmed** |
| P3B composite score > 0.90 | 1,612 | +0.56% | +0.38..+0.73 | +0.27..+0.84 | **1.56** | 7/7 | 100 | Confirmed |
| P3A stacked P2A (max 3) | 6,017 | +0.48% | +0.38..+0.59 | +0.19..+0.78 | 1.37 | 7/7 | 100 | Confirmed |
| P3C 126-day momentum | 822 | +1.47% | +0.85..+2.16 | +0.64..+2.36 | 2.09 | 7/7 | **67** | **Not confirmed (drift)** |

**Per market, P2A** (avg trade / PF): QQQ +0.48% / 1.31, IWM +0.64% / 1.53, DIA +0.50% / 1.56, EFA +0.70% / 1.68,
EWG +0.49% / 1.36, EWJ +0.54% / 1.52, EWU +0.50% / 1.44.

**By decade** (avg trade, PF):

| | 1990s | 2000s | 2010s | 2020s |
|---|---|---|---|---|
| P2A | +0.61%, 1.60 | +0.28%, 1.19 | +0.90%, 2.09 | **+0.61%, 1.58** |
| P3B | +1.56%, 2.87 | +0.53%, 1.47 | +0.73%, 2.01 | **+0.10%, 1.08** |
| P3A | +0.71%, 1.68 | +0.24%, 1.16 | +0.91%, 1.91 | +0.44%, 1.36 |

**Next-open entry** (buying at the next morning's open instead of the close): P2A +0.40% (PF 1.33), P3B +0.52%
(1.51), P3A +0.41% (1.31). All still 7/7 markets positive.

**Deflated Sharpe** (N = 258 development variants; trial variance 0.0043 of per-trade Sharpe): P2A 0.006,
P3B 0.12, P3A ~0. None clears 0.95. That yardstick asks whether the test result could be the luckiest of 258 tries.
But only 4 frozen systems ever touched the test set, and P2A's test t-statistic is 7.2 (month-clustered CI above zero).

**ES 2020-2026** (third look at that window; not part of any verdict): P2A +29.9 pt/trade (111 trades);
P3A +23.8 pt (234); P3B +34.4 pt (63); P3C +150 pt (23 regime trades).

## Caveats

- The seven markets are correlated with each other and with the S&P 500, and share crash dates. The month-clustered
  CI accounts for part of that.
- IBS-style mean reversion in equity indices is a known, published effect. Its existence was not a surprise; the
  test shows these exact frozen rules still work on data they were not built on.
- No stops: the worst single test trade was -24% (IWM, 2008) and -584 pt on ES (April 2025). Size accordingly.
- Market-on-close execution for the ETFs; next-open results are shown as the conservative case.

## Correction (found after the test while verifying the Pine port)

`scalpel/p3.py::_simulate_target` exited **regime** trades one session early in next-open mode (ES only). It is
fixed, with a regression test (`tests/test_p3.py::test_regime_next_open_holds_the_last_on_session`).

- **Not affected:** everything in close mode, which covers all SPY development data and the seven-market test
  verdicts. P2A, P3A and P3B are not regime systems and are unaffected everywhere.
- **Affected:** the ES leg of the 7 trend variants (T1/T2) and P3C's ES and next-open figures.
- **Re-run with the fix** (`scripts/p3_regime_fix_check.py`, `regime_fix_check.json`): **no trend variant passes
  the development gates.** 126-day momentum falls to the 83rd random-exposure percentile, below the required 90.
  So P3C would not have been selected. It was selected only because of the bug, then failed the untouched test for
  being drift, so the conclusion is unchanged.
- **Corrected P3C figures:** ES 2020-2026 +104 pt per trade, PF 3.2 (reported above as +150 pt, PF 7.5).
  Next-open on the seven markets +1.62% per trade, PF 2.27 (reported above as +2.11%, PF 3.65).
- The test runner is locked to the freeze commit, so it was not re-run; the corrected numbers come from the check
  script.
