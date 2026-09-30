# Scalpel Levels → EV+ ES/SPX Trading System

You have full creative control over strategy design. You do NOT have control over
the validation protocol below. The goal is one system with positive expected value
after costs on data it has never seen. "No edge found" is an acceptable, useful answer.

## 1. What the levels are
`scalpel/levels.py` is a line-for-line port of the daily/weekly/monthly engines in
Chris's TradingView indicator `docs_scalpel_v37.pine` (ES params in `scalpel/params_es.py`):

    sigma = period_open * vol/100 / sqrt(periods_per_year)   # D 252, W 52, M 12
    upside scale ts = sigma * bias/0.5 ; downside scale bs = sigma * (1-bias)/0.5
    level = open + ts*mult (upper) or open - bs*mult (lower)
    GP boxes at 0.618/0.650 of inner range; range boxes = RH/RL ± sigma*half-width

ES vol = 18.54 (D/W) and 17.37 (M); bias = 0.481 (D/W) and 0.531 (M) — CONSTANTS.
So every level is a fixed % of its period open. `python validate_export.py <csv>` must
match any TradingView export to <0.01 pt (weekly currently matches to 1e-12).

Known limitations — state them in every report:
- Constant vol = a 2026 snapshot applied to all history → lookahead. Run every test in
  `fixed` mode AND `scaled` mode (vol = 252-day mean of VIX as of the prior period's
  close; for daily also try EWMA Rogers-Satchell, lambda≈0.924, prior bars only).
- Constant bias: the real TrueALGO bias history is unknown. We are testing Chris's
  clone levels, not TrueALGO.
- Week boundary: Sunday 18:00 ET, but a Friday exchange holiday (July 4 type, not Good
  Friday) starts the week Thursday 18:00. Implemented in `weekly_open()`.

## 2. Data (Chris provides into data/)
- `data/es_levels_*.csv` — TradingView exports with the EXPORT indicator (all 57 D/W/M
  levels). Use them for validation, and as the bar data if nothing better exists.
- Preferred bar data: ES 1-minute or 5-minute, 2010+ (Databento or FirstRate Data).
  Use UNADJUSTED front-month prices to compute levels (they are % of the actual traded
  open); flag roll weeks and test with and without them.
- Options: real historical quotes are needed to claim an options edge. SPX/XSP EOD
  chains (OptionsDX, CBOE DataShop) or ES options (Databento). If unavailable, you may
  SCREEN option ideas with a model (Black-Scholes, IV = VIX scaled to tenor, plus a skew
  adjustment calibrated to any real quotes you have) but label all such results
  "modeled" — nothing modeled goes to the final OOS test.
- VIX daily history (CBOE, free) for scaled mode and regime filters.

## 3. Hypotheses to explore (screen many, pick few)
Directional (ES/MES futures):
- Bounce: fade first touch of RL / TL1 / RB_TOP / GP_B (long) and mirror at the top.
- Break-and-go: close through a level → continue to the next level.
- Confluence: D, W, M levels within X pts of each other.
- Filters: position vs period open, day of week, VIX regime, trend (price vs 20/50d MA).
Options (weekly or 0-1DTE, SPX/XSP/ES):
- Credit spreads with short strikes at TL1/TL2 (puts) and TH1/TH2 (calls), sold at
  week open, held to expiry or managed.
- Iron condors: short strikes at the inner box edges or TH1/TL1, wings at GB_TOP / RB_BOT.
- Legging: sell the put spread when price touches RL/RB_TOP, the call spread on
  RH/GB_BOT, and complete the condor only if the second touch happens.
- Daily levels + 0DTE: same structures on D levels.

Required baselines for EVERY hypothesis (the level has to be the edge):
- Directional: same rules at randomly jittered level distances (±10–40%), 500 runs; and
  the same trades at fixed % bands with no level logic.
- Options: the same structure at DELTA-MATCHED strikes (e.g. 16Δ / 10Δ) with no level
  information, same entry days. Weekly short premium has a well-known baseline edge
  (volatility risk premium) — the levels must beat delta-matched selling, not just zero.

## 4. Validation protocol (non-negotiable)
1. Split once, now, before looking: DEVELOPMENT = 2010-01-01 → 2019-12-31;
   OUT-OF-SAMPLE = 2020-01-01 → present. Never tune on OOS.
2. Screening (DEV only): test broadly. Record EVERY variant tried in `results/log.csv`
   (the count matters for multiple-testing).
3. Pick at most 3 candidates. Criteria on DEV: EV/trade > 0 after costs, ≥100 trades,
   beats its baseline, bootstrap 95% CI of mean P&L excludes 0, stable in walk-forward
   (yearly), not dependent on a single year or one crisis.
4. Freeze the full rules (entry, exit, sizing, filters) in `results/frozen_rules.md`
   with a git commit BEFORE running OOS.
5. Run OOS once. Report: trades, win rate, EV/trade, profit factor, max drawdown, worst
   trade, worst month, Sharpe, results by year and VIX regime, and the deflated Sharpe
   ratio given the number of variants tried.
6. If OOS fails, say so. Do not rescue it by retuning on OOS.

## 5. Execution realism
- Signals on bar close, fill next bar open. If one bar hits both stop and target, the
  stop fills first unless finer data proves otherwise.
- ES: $12.50/tick, 1 tick slippage per side, $2.50 commission per side (MES scaled).
- Options: fill at mid minus 25% of the spread for sells (worse for wide markets),
  $0.65/contract commission; model early assignment only for American-style (ES).
- Risk: report results per 1 unit of defined risk and for a fixed-fractional account.

## 6. Deliverables
`results/log.csv` (all variants), `results/screen_summary.md`, `results/frozen_rules.md`,
`results/oos_report.md` with equity curve PNGs, and a plain-English verdict:
trade it / paper trade it / don't trade it, with the reason.
