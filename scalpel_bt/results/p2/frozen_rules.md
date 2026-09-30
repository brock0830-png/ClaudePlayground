# PHASE 2 FROZEN RULES — committed before any Phase 2 rule was run on 2020-2026

Selected from `results/p2/log.csv` (640 pre-registered variants, `PROTOCOL_P2.md`) by the pre-registered rule:
pass all six gates P1-P6, then the best DEV timing-excess t-statistic per family, at most 3.
Nine variants passed every gate, in three families (F2 mean reversion 6, F4 volatility 2, F1 session 1).
Machine-readable specs: `results/p2/frozen_candidates.json`. The OOS run is
`python scripts/p2_candidates.py oos`, which refuses to run unless `results/p2/OOS_UNLOCKED` names this commit and
nothing in `scalpel/`, `scripts/` or these two files has changed.

## Common execution (ES or MES, 1 contract per signal)

- **Session:** the TradingView ES trading day, 18:00 ET to 17:00 ET, with holiday sessions merged as TradingView
  does. Session close = close of the 14:00-17:00 bar. VIX = CBOE VIX close of the same date (16:15 ET).
- Signals are evaluated at the session close. Orders fill at the next 4h bar's open (normally 18:00 ET).
  Exits fill at a bar open. **No stops.**
- **Costs:** 0.30 pt per side (1 tick + $2.50), plus 0.60 pt for each contract roll while in a position.
  P&L is measured on the switch-adjusted continuous price.
- **Sizing:** (a) 1 contract per signal; (b) fixed-fractional, $100,000 start,
  MES contracts = floor(1% of equity / (2 x ATR20 x $5 + $3)), where ATR20 is the 20-session mean of session
  high minus low.

## P2A — short-term mean reversion in high volatility (variant 440)

- IBS = (session close - session low) / (session high - session low).
- **Entry:** at a session close, if IBS < 0.30 **and** VIX close > 20, and no position is open (and none was closed at
  this same close), buy 1 at the next open.
- **Exit:** after holding 5 sessions, sell at the open following the 5th session close. One position at a time.
- DEV 2013-2019: 42 trades, win 76%, EV +27.5 pt (CI +10.8..+42.5), PF 3.64, annualised Sharpe 0.97,
  timing excess +931 pt, beat random exposure 100%. SPX pre-DEV not computable (needs highs/lows); positive
  timing excess in both DEV halves. Its close-only siblings with VIX > 20 (RSI2 < 20, 5-day closing low) were
  positive on SPX 1990-2012.

## P2B — overnight long in pullbacks (variant 7)

- **Condition:** the session close is below the 50-session simple moving average of session closes.
- **Trade:** if the condition holds at a session close, buy 1 at the 18:00 ET open and sell at the 10:00 ET open next
  morning (the 18:00, 22:00, 02:00 and 06:00 bars). Repeat every session the condition holds.
- DEV: 458 trades, win 58%, EV +1.77 pt (CI +0.21..+3.26), PF 1.32, Sharpe 0.83, timing excess +489 pt, beat
  random exposure 99%. Positive timing excess in both DEV halves (+44, +446 pt). The unconditional overnight long
  was positive (+0.39 pt/trade) but below drift after costs.

## P2C — VIX spike reversal (variant 615)

- **Entry:** at a session close, if the VIX close > 1.2 x the 10-day average of VIX closes (including today) and no
  position is open, buy 1 at the next open.
- **Exit:** after holding 10 sessions, sell at the open following the 10th session close.
- DEV: 36 trades, win 72%, EV +26.1 pt (CI +1.1..+49.1), PF 2.29, Sharpe 0.67, timing excess +556 pt, beat
  random exposure 98%. SPX 1990-2012: EV +0.94%/trade, timing excess +39% cumulative.

## Pre-declared combination (reported, not a separate candidate)

P2A + P2B + P2C at 1 contract each, P&L summed. DEV: +2,905 pt, Sharpe 1.01, max DD -505 pt. ES buy-and-hold on
the same window: +1,857 pt, Sharpe 0.88, max DD -601 pt.

## OOS report (once) and verdict

- Window 2020-01-01 to 2026-09-30. This is the second use of the window (see `PROTOCOL_P2.md`), and I know the broad
  2020-2026 market history.
- Reported: trades, win rate, EV with CI, PF, max DD, worst trade and month, annualised Sharpe vs buy-and-hold,
  by year, by VIX regime, random-exposure percentile, timing excess, fixed-fractional equity, PSR vs 0, and DSR.
- **DSR** uses per-day Sharpe, T = sessions in the window, N = 640. It is computed two ways:
  (i) **the verdict version:** trial variance = cross-sectional variance of per-day Sharpe over Phase 2 variants
  with n >= 30 (0.00275). This implies an expected best-of-640 annualised Sharpe of about 2.6, because the variants
  differ in drift exposure, not only in noise.
  (ii) reference: sampling-noise variance 1/T.
- **Verdict:** as in `PROTOCOL_P2.md` section 7 (trade it / paper trade it / don't trade it), per candidate.
  DEV DSR is about 0 under (i) and 0.10-0.30 under (ii), so "trade it" is realistically out of reach. The
  practical question is whether OOS EV is positive with a CI above zero and still beats random exposure.
- No rule, parameter or candidate changes after the OOS run.
