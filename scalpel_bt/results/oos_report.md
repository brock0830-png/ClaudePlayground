# OOS report — one-shot run, 2020-01-01 to 2026-09-30

- Rules frozen in commit `653c73f` (`frozen_rules.md`, `frozen_candidates.json`, all code) before any OOS bar was loaded.
- `results/OOS_UNLOCKED` records that hash. `scripts/run_oos.py` ran once and nothing was retuned afterwards.
- Raw output: `oos_results.json`; trades: `oos_trades_*.csv`; equity curves: `oos_*.png`.

## Verdict

| Candidate | Protocol verdict | Why |
|---|---|---|
| C1: weekly GP_B_IN bounce (scaled vol, VIX below its 1-year mean) | **PAPER TRADE IT** | OOS EV is positive in points (+3.67 pt/trade) but the 95% CI is [-3.8, +11.1]; in risk units it is +0.008 R and the 1%-risk account finished flat after 6.75 years. DSR ≈ 0. Below the jitter 90th percentile (86th). |
| C2: weekly GP_T_IN break-and-go (fixed vol, uptrend, no roll weeks) | **PAPER TRADE IT** | OOS EV +5.19 pt/trade, CI [-2.8, +13.5], +0.05 R. **Jittered levels did just as well (54th percentile)** and the round-% grid did better. One year (2025) supplies two thirds of the profit. DSR ≈ 0. |

**In plain English: no edge was found.** "Paper trade it" is what the pre-registered rules give when OOS EV
is above zero but nothing else holds, and it is the most either candidate could earn. The DEV deflated Sharpe
was already about 0 after 12,514 variants. Both systems made money in points from 2020 to 2026, but so did
randomly nudged levels and randomly timed long entries held for the same time. The profit is ES going up, not
the Scalpel levels. **Don't put money on either.** Paper trading would test execution, not an edge. I would
not expect it to show one.

## Known limitations (apply to every number)

- Fixed-mode constant vol (C2) is a 2026 snapshot, i.e. lookahead, and the snapshot postdates this OOS window
  too. C2's scaled-mode twin (point-in-time) is reported below. C1 runs in scaled mode.
- Constant bias: the real TrueALGO bias history is unknown. These are Chris's clone levels, not TrueALGO.
- Week boundary: Sunday 18:00 ET; a Friday holiday starts the week Thursday 18:00 (`weekly_open()`), except the
  TradingView orphan bars documented in `validation.md` (flagged, no signals).
- 4-hour TradingView bars, unadjusted ES1! with dated contract switches; no real option quotes (no option
  candidate was possible; option results in `screen_summary.md` are modeled only).
- Points-based EV overweights recent trades because ES traded at 3,000-7,800 in OOS versus 1,400-3,200 in DEV.
  R-multiples and the fixed-fractional account normalise for that; read them first.

## Required metrics (1 ES contract per trade, net of 0.60 pt round-trip costs)

| Metric | C1 bounce | C2 break-and-go |
|---|---|---|
| Trades | 102 | 178 |
| Win rate | 52.0% | 46.6% |
| EV / trade | +3.67 pt (+$184) | +5.19 pt (+$259) |
| Bootstrap 95% CI of EV | [-3.81, +11.11] pt | [-2.80, +13.49] pt |
| EV in R (units of initial risk) | +0.008 R, CI [-0.18, +0.19] | +0.050 R, CI [-0.13, +0.24] |
| Profit factor | 1.24 | 1.28 |
| Total | +375 pt ($18.7k per ES) | +924 pt ($46.2k per ES) |
| Max drawdown (trade sequence) | -295 pt | -461 pt |
| Worst trade | -87.8 pt | -96.7 pt (best +305.7) |
| Worst month | -92.8 pt (2021-09) | -120.1 pt (2022-02) |
| Sharpe per trade | 0.096 | 0.094 |
| Sharpe, annualised from daily P&L | 0.37 | 0.47 |
| PSR (Sharpe > 0) | 0.83 | 0.91 |
| **Deflated Sharpe** (N = 12,514, trial var 0.0635, expected max SR 0.99/trade) | **≈ 0** (z = -8.9) | **≈ 0** (z = -12.7) |
| Fixed-fractional, 1% risk in MES, $100k start | $99,799 (-0.0%/yr), max DD -8.6% | $105,494 (+0.8%/yr), max DD -13.8% |
| Avg holding time | 6.0 bars (1 day) | 11.7 bars (2 days) |

## Is the level the edge? OOS baselines

| | C1 | C2 |
|---|---|---|
| Actual EV | +3.67 pt | +5.19 pt |
| 500 jittered-level runs: mean / p90 | +0.10 / +4.56 pt | +5.41 / +7.67 pt |
| Actual's percentile among jitter runs | 86th | **54th** |
| Round-% grid ("fixed % bands, no level logic") | -3.77 pt (83 trades) | **+7.32 pt** (122 trades) |
| Random long entries, same count and holding time (post-hoc, 1,000 runs): mean / p90 | +1.46 / +6.15 pt | +4.32 / +9.29 pt |
| Actual's percentile among random entries (post-hoc) | 71st | 57th |
| ES long drift x average holding time, minus costs (post-hoc) | +1.58 pt | +3.67 pt |

The random-entry and drift rows come from `scripts/oos_posthoc.py`, run after the verdict as a diagnostic;
they do not enter the verdict. C1's placement looks better than jitter in points (the jittered versions lost
money in 2021-2025), but not in risk terms, where the account is flat.

## DEV vs OOS

| | C1 DEV | C1 OOS | C2 DEV | C2 OOS |
|---|---|---|---|---|
| Trades | 122 | 102 | 138 | 178 |
| EV pt (CI) | +3.45 (+1.30, +5.49) | +3.67 (-3.81, +11.11) | +4.45 (+1.22, +7.76) | +5.19 (-2.80, +13.49) |
| EV R | +0.24 | +0.01 | +0.22 | +0.05 |
| Win rate | 67% | 52% | 58% | 47% |
| Profit factor | 1.94 | 1.24 | 1.79 | 1.28 |
| Jitter percentile | 100 | 86 | 90 | 54 |
| Positive years | 7 / 7 | 4 / 7 | 7 / 7 | 5 / 7 |

In risk terms (R), both candidates lost almost all their DEV edge out of sample. Win rates fell 11-15 points.

## By year (OOS)

| Year | C1 trades | C1 EV pt | C1 total | C1 EV R | C2 trades | C2 EV pt | C2 total | C2 EV R |
|---|---|---|---|---|---|---|---|---|
| 2020 | 7 | +18.5 | +130 | +0.52 | 33 | +8.7 | +287 | +0.22 |
| 2021 | 21 | -4.3 | -89 | -0.19 | 29 | +12.2 | +354 | +0.28 |
| 2022 | 11 | +10.7 | +118 | +0.12 | 22 | -10.1 | -222 | -0.43 |
| 2023 | 21 | +1.7 | +37 | -0.04 | 26 | -7.1 | -185 | -0.19 |
| 2024 | 15 | -0.7 | -10 | -0.15 | 26 | +0.6 | +17 | -0.04 |
| 2025 | 12 | -10.1 | -122 | -0.18 | 25 | +24.3 | +608 | +0.39 |
| 2026 (to Sep) | 15 | +20.8 | +312 | +0.33 | 17 | +3.8 | +65 | -0.04 |

## By VIX regime (prior VIX close, OOS)

| VIX | C1 trades | C1 EV pt | C1 EV R | C2 trades | C2 EV pt | C2 EV R |
|---|---|---|---|---|---|---|
| < 15 | 29 | +1.6 | +0.02 | 36 | -3.6 | -0.06 |
| 15-20 | 47 | +2.3 | -0.08 | 77 | +6.4 | +0.05 |
| 20-30 | 26 | +8.5 | +0.16 | 60 | +6.2 | +0.01 |
| > 30 | 0 | - | - | 5 | +38.1 | +1.33 |

C1 took no trade with VIX above 30 (its filter requires VIX below its own 1-year mean). It could trade at
VIX 20-30 in OOS because that 1-year mean stayed above 20 from April 2020 to September 2023.

## Roll weeks and pre-declared robustness runs (OOS)

| Run | Trades | EV pt | 95% CI | EV R | PF | Jitter pct |
|---|---|---|---|---|---|---|
| C1 as frozen (roll weeks included) | 102 | +3.67 | [-3.8, +11.1] | +0.008 | 1.24 | 86 |
| C1 without roll-week trades | 97 | +3.24 | [-4.1, +10.9] | -0.003 | 1.21 | 86 |
| C1 fixed-mode twin | 112 | +1.20 | [-5.4, +7.8] | -0.119 | 1.08 | 79 |
| C1 without the VIX filter | 179 | +2.32 | [-3.3, +7.8] | -0.010 | 1.15 | 92 |
| C2 as frozen (roll weeks excluded) | 178 | +5.19 | [-2.8, +13.5] | +0.050 | 1.28 | 54 |
| C2 with roll weeks | 196 | +3.22 | [-4.4, +11.5] | +0.014 | 1.16 | 33 |
| C2 scaled-mode twin (no lookahead) | 173 | +4.37 | [-3.8, +13.0] | +0.030 | 1.22 | 27 |
| C2 without the trend filter | 218 | +5.49 | [-3.5, +14.7] | +0.156 | 1.24 | 72 |

No variation rescues either candidate. No robustness CI excludes zero, and every EV in R is within ±0.16.
The filters chosen on DEV made no real difference OOS: C1's VIX filter raised points EV (+3.67 vs +2.32) but
not R (+0.008 vs -0.010), and C2 did slightly better without its trend filter.

## Equity curves

- `oos_C1_bounce_W_GPBIN_touch.png`: top, cumulative net points for 1 ES against 60 jittered-level runs (grey);
  bottom, the 1%-risk MES account.
- `oos_C2_break_W_GPTIN.png`: same layout. The real-level curve sits in the lower half of the jitter bundle for
  most of 2022-2025.
- DEV counterparts: `dev_C1_bounce_W_GPBIN_touch.png`, `dev_C2_break_W_GPTIN.png`.

## What would change this conclusion

- Real option quotes (SPX/XSP EOD chains or Databento ES options, 2010+) to test the level-strike idea against
  delta-matched strikes for real. Modeled screens found no advantage, but they cannot settle it.
- Finer bars (1- or 5-minute ES, 2010+) for the daily-level ideas, which 4-hour bars resolve poorly.
- The real TrueALGO vol/bias history, if the claim is about TrueALGO rather than the clone.

Any new test needs a fresh, untouched hold-out. This 2020-2026 window has now been used.
