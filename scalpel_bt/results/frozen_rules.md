# FROZEN RULES — committed before any OOS bar was loaded

Machine-readable specs: `results/frozen_candidates.json`. Code: `scalpel/` and `scripts/` at this commit.
The OOS runner is `scripts/run_oos.py`. It refuses to run unless `results/OOS_UNLOCKED` names this freeze
commit and none of `scalpel/`, `scripts/`, `frozen_rules.md` or `frozen_candidates.json` has changed since.

OOS window: first bar on or after 2020-01-01 00:00 ET through the last bar of the export (2026-09-30 14:00 ET).
The simulator runs over all bars, so first-touch state and open positions carry across 2020-01-01 as in live
trading; only trades whose entry is inside the window count.

Known limitations (as in every report): the fixed-mode constant vol is a 2026 snapshot (lookahead, which also
touches the 2020-2026 OOS window); the bias is a constant, not TrueALGO's history; week boundaries per
`weekly_open()` with the TradingView orphan-bar exceptions flagged; 4-hour bars only; unadjusted ES1! with dated
rolls; no real option quotes (no option candidate).

## Common definitions

- **Bars:** TradingView `CME_MINI:ES1!` 240-minute bars (18, 22, 02, 06, 10, 14 ET). **Week:** the TradingView
  weekly bar, identified by the exported weekly open WO (normally Sunday 18:00 ET to Friday 17:00 ET).
- **sigma (weekly):** `WO * (vol / 100) / sqrt(52)`.
  - fixed mode: vol = 18.54.
  - scaled mode: vol = mean of the last 252 VIX closes as of the last VIX close before the week's first
    trading day.
- **Levels (bias 0.481):** `GP_B_IN = WO - 0.338 * sigma`, `GP_T_IN = WO + 0.262 * sigma`. In fixed mode these
  are WO - 0.869% and WO + 0.674%, identical to the v37 indicator's W GP B In / W GP T In.
- **Execution:** a signal on a 4h bar's close fills at the next bar's open. Stops are stop-market orders (filled
  at the stop, or at the open if a bar gaps through). Targets are limits filled on touch. If one bar reaches both,
  the stop fills. The time exit is the close of the week's last bar. Any open position is closed at the close of
  the bar before a contract switch (TradingView switch dates in `data/roll_dates.csv`; live: the roll date).
  No signal on the last bar of a week, on the bar before a switch, or on flagged orphan (lookahead) bars.
- **Costs:** 1 tick slippage per side plus $2.50 commission per side = 0.60 pt per round trip per ES contract
  ($30; MES: same in points, $3).
- **Sizing:** (a) 1 contract per trade; results in points and in R = net points / (entry - stop).
  (b) Fixed-fractional: $100,000 start, MES contracts = floor(1% of equity / (stop distance x $5 + $3)).
- One trade per week at most per candidate; long only.

## C1 — Weekly GP_B_IN bounce, scaled vol, VIX below its 1-year mean (variant 11928)

1. Each week compute sigma in **scaled** mode and `L = GP_B_IN = WO - 0.338 * sigma`, stop `S = L - 0.25 * sigma`.
2. **Filter:** the prior trading day's VIX close is below the mean of the last 252 VIX closes as of that day.
3. **Trigger:** the first 4h bar of the week whose low is <= L *and* on which the filter holds. If that bar
   closes above S, buy 1 at the next bar's open, provided that open is above S and below the 1R target implied
   by it (always true unless the market gaps). If it closes at or below S, no trade this week. Only one trigger
   per week.
4. **Exit:** stop at S; target = entry + 1.0 x (entry - S); otherwise sell at the close of the week's last bar.
   Contract-switch rule as above. Roll weeks are included.

DEV (2013-2019): 122 trades, win 67.2%, EV +3.45 pt/trade (+$173 per ES), 95% CI [+1.30, +5.49] pt,
EV +0.24 R (CI [+0.079, +0.397]), profit factor 1.94, max DD -54 pt, worst trade -36.4 pt, worst month -36.4 pt
(2016-06), per-trade Sharpe 0.29, annualised daily Sharpe 1.17. Every year positive (2013 +21 ... 2019 +171 pt).
Jitter: actual EV above all 500 jittered runs (their mean +1.71, p90 +2.32). Round-grid: +1.85 pt (45 trades).
Fixed-fractional: $100k to $130.7k (3.9%/yr), max DD -4.0%.
Robustness (DEV): fixed twin 95 trades +1.85 pt (CI -1.09..+4.70); roll weeks excluded 117 trades +3.11 pt;
no VIX filter 194 trades +2.01 pt (CI +0.17..+3.80).

## C2 — Weekly GP_T_IN break-and-go, fixed vol, uptrend, roll weeks excluded (variant 11847)

1. Each week compute sigma in **fixed** mode (vol 18.54): `L = GP_T_IN = WO + 0.262 * sigma` (WO + 0.674%),
   stop `S = L - 0.25 * sigma` (L - 0.643% of WO).
2. Skip weeks that contain a contract switch (roll weeks).
3. **Filter:** the previous completed session's close is above the 20-session simple moving average of
   session closes (TradingView trading days, 17:00 ET closes).
4. **Trigger:** the first 4h bar of the week that closes above L (the week opens below L by construction) and on
   which the filter holds. Buy 1 at the next bar's open if that open is above S. One trigger per week.
5. **Exit:** stop at S; no profit target; sell at the close of the week's last bar.

DEV (2013-2019): 138 trades, win 58.0%, EV +4.45 pt/trade (+$223 per ES), 95% CI [+1.22, +7.76] pt,
EV +0.22 R (CI [+0.052, +0.401]), profit factor 1.79, max DD -73 pt, worst trade -35.3 pt, worst month
-62.2 pt (2019-10), per-trade Sharpe 0.23, annualised daily Sharpe 0.97. Every year positive (2014 only +7 pt).
Jitter: 90.2th percentile (jitter mean +3.42, p90 +4.43). Round-grid: +3.49 pt (77 trades).
Fixed-fractional: $100k to $132.2k (4.1%/yr), max DD -4.5%.
Robustness (DEV): scaled twin 159 trades +3.13 pt (CI +0.27..+6.16); roll weeks included 157 trades
+3.79 pt; no trend filter 175 trades +4.38 pt (CI +0.85..+8.16).

## OOS run (once) and what is reported

For each candidate, at exactly the rules above: trades, win rate, EV/trade (points, $ per ES, R) with bootstrap
95% CI, profit factor, max drawdown, worst trade, worst month, per-trade Sharpe and annualised daily Sharpe,
fixed-fractional equity, results by year and by VIX regime (prior close < 15, 15-20, 20-30, > 30), EV without
roll-week trades, 500 jittered-level runs and the round-grid baseline over the OOS window, an equity PNG,
PSR vs 0, and the **deflated Sharpe ratio**: per-trade Sharpe, T = OOS trades, trial variance = variance of
`sharpe_t` over directional `log.csv` rows with n >= 100 (0.0635), N = all 12,514 rows of `log.csv`.

Pre-declared robustness runs, reported but not used for the verdict:
C1: fixed-mode twin, roll weeks excluded, no VIX filter. C2: scaled-mode twin, roll weeks included, no trend filter.

## Verdict rules (from PROTOCOL.md, unchanged)

- **Trade it:** OOS EV/trade > 0 with bootstrap CI lower bound > 0, profit factor > 1.1, DSR > 0.95, and OOS EV
  at or above the 90th percentile of the OOS jitter runs.
- **Paper trade it:** OOS EV/trade > 0 but any other "trade it" condition fails.
- **Don't trade it:** OOS EV/trade <= 0.

Expectation stated now: both DEV DSRs are about 0 (expected best-of-N Sharpe 0.99 per trade vs 0.29 and 0.23),
so "trade it" is practically unreachable. No rule, parameter, filter or candidate will be changed after the
OOS run. If OOS fails, that is the result.
