# PROTOCOL_P2.md — Phase 2 pre-registration: directional ES signals from price and VIX

Written and committed before any Phase 2 result was computed (2026-09-30), after Phase 1 (Scalpel levels)
found no edge. Question: is there a meaningfully positive directional ES/MES system (long, short or one side
only) built from price trends/indicators and VIX, net of costs, on data it was not tuned on?

## 1. Data

- ES 4-hour bars (TradingView ES1!, `data/es_levels_CME_MINI_ES1_240.csv.gz`), 2013-01-02 to 2026-09-30.
  P&L uses a **switch-adjusted** price series: each TradingView contract switch gap (the basis jump in
  `data/roll_dates.csv`) is removed. A position held through a switch pays one extra round trip (0.60 pt) for
  the roll.
- **No volume.** The export has none, and no ES volume series before 2020-11 was reachable (HF 1-minute ES sets
  cover 2020-11 to 2024-07, MES starts 2019-05). Volume ideas cannot be tested on DEV and are out of scope.
  The export's "DIX 1" and "Z-Score" columns are undocumented and not used.
- VIX (1990+), VIX3M (2009-09+), VIX9D (2011+) daily closes from CBOE. SPX daily closes 1990+ (CBOE, close only).

## 2. Windows

- DEV: ES 2013-01-02 to 2019-12-31 (same as Phase 1). Screening uses `load_bars("dev")` only.
- PRE-DEV robustness: SPX daily closes 1990-01-02 to 2012-12-31, for every rule that can be computed from
  daily closes and VIX. Execution there is at the next day's close, cost 0.03% per round trip.
- OOS: ES 2020-01-01 to 2026-09-30. **Second use of this window.** Phase 1 used it once for two Scalpel-level
  candidates, no indicator rule was ever evaluated on it, and the researcher (me) knows the broad market
  history of 2020-2026. So this OOS is weaker than a virgin hold-out; forward paper trading is the real test.
  Phase 2 has its own lock: `results/p2/OOS_UNLOCKED` must name the Phase 2 freeze commit.

## 3. Execution (ES 4h bars)

- The target position (-1, 0, +1 contract) is decided at a bar's close from information available then;
  it changes at the next bar's open. A daily signal is evaluated at the session's last bar (14:00-17:00 ET)
  and executes at the 18:00 ET open. The same-day VIX close (16:15 ET) is known by then.
- Bar P&L = old position x (open - prior close) + new position x (close - open), on the switch-adjusted series.
- Costs: 0.30 pt per contract per side (1 tick slippage + $2.50 commission), i.e. 0.60 pt per round trip,
  plus 0.60 pt per contract per roll held.
- No intrabar stops in Phase 2 (signal-in / signal-out rules), so no fill-order ambiguity.

## 4. Families (grids fixed in `scripts/p2_screen.py` before running)

- F1 session / overnight drift: long (or short) only during fixed 4h bars of each session, with trend/VIX filters.
- F2 short-term mean reversion (daily): RSI(2), N-day closing low, down streaks, IBS; exits on close > MA5,
  RSI(2) > 70, or after N sessions; trend and VIX filters; long, plus a mirrored short in downtrends.
- F3 trend / regime (daily): close vs MA(20/50/100/200), N-day momentum, Donchian breakouts, MA crosses;
  long-only and long/short.
- F4 volatility regime (daily): VIX/VIX3M term structure, VIX level, VIX vs its own MA, VIX spike reversal.
- F5 calendar (daily): turn of month, pre-holiday session, weekend.

## 5. Baselines and measures

- **Random exposure** (500 runs): the same number of trades with the same holding times and direction,
  started at random bars of the same window. Its percentile is the test of timing skill beyond drift.
- **Timing excess** = net P&L - (bars in position x mean bar return of the window x direction): what the rule
  earned beyond simply being exposed to drift for the same time. 95% CI by weekly block bootstrap.
- Buy-and-hold ES over the same window, for Sharpe and drawdown comparison.

## 6. Gates (DEV) — a candidate passes all

- P1. Net EV/trade > 0 and net total > 0 on DEV ES.
- P2. At least 30 trades and 100 sessions in position.
- P3. Beats random exposure: percentile >= 90, and timing excess > 0.
- P4. Weekly block-bootstrap 95% CI of mean daily net P&L excludes 0.
- P5. Net P&L > 0 in at least 5 of 7 DEV years, and still > 0 with the best year removed.
- P6. Out-of-DEV robustness: rules computable from daily closes must show timing excess > 0 and EV/trade > 0 on
  PRE-DEV SPX 1990-2012. Session (F1) and VIX3M rules, which have no pre-2013 data, must instead have
  positive timing excess in both DEV halves (2013-2016 and 2017-2019).

Selection: at most 3 candidates, at most one per family, ranked by the t-statistic of DEV timing excess.
Every variant is logged in `results/p2/log.csv`.

## 7. OOS report and verdict

Report trades, win rate, EV/trade with CI, profit factor, max drawdown, worst trade, worst month, annualised
Sharpe from daily P&L versus buy-and-hold, by year, by VIX regime, the random-exposure percentile and timing
excess, and DSR with N = Phase 2 variants (and, for reference, N = Phase 1 + Phase 2).

- **Trade it (small, alongside forward paper trading):** OOS EV/trade > 0 with CI lower bound > 0, profit factor
  > 1.1, random-exposure percentile >= 90 and timing excess > 0, and DSR (Phase 2 N) > 0.95.
- **Paper trade it:** OOS EV/trade > 0 but some other condition fails.
- **Don't trade it:** OOS EV/trade <= 0.
- A candidate whose OOS profit is only drift (random-exposure percentile < 90) is labelled as such: holding
  ES/SPY would have done as well per unit of time in the market.
