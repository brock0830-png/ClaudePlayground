# PROTOCOL.md — pre-registration (written and committed before any strategy result was computed)

Date: 2026-09-30. This file fixes the split, the execution model, the baselines and the
pass/fail gates. Anything decided later is logged in `results/log.csv` or stated as a
deviation in the reports.

## 1. Data actually available

| Item | Source | Span | Notes |
|---|---|---|---|
| ES 4-hour bars + all 57 D/W/M levels | TradingView `CME_MINI:ES1!` 240m export with the EXPORT indicator (`data/es_levels_CME_MINI_ES1_240.csv.gz`) | 2013-01-02 06:00 ET to 2026-09-30 14:00 ET | Unadjusted continuous front month (TradingView switches contracts on its own schedule; roll weeks detected and flagged, see `scalpel/data.py`). **No bar data before 2013**, so DEV is effectively 2013-2019. |
| VIX, VIX9D, VIX3M daily | CBOE (`data/external/`) | VIX 1990+, VIX9D 2011+, VIX3M 2009+ | For scaled mode and regime filters. |
| SPX daily close | CBOE | 1975+ | Reporting only. |
| SPX 1-minute (RTH) | public HuggingFace dataset `thillsss/SPX-MES-VIX-data` | 2008+ | Used only to (a) date the TradingView roll by the ES-SPX basis jump and (b) audit the stop-first intrabar assumption. Never used for signals. |
| Option quotes | none reachable for 2010-2019 (OptionsDX / CBOE DataShop / Databento are paid; public HF/DoltHub sets start 2020+ with sparse strikes) | - | **All option results are "modeled" and no option idea can go to the OOS test.** |

Bar resolution is 4 hours (6 bars per session: 18, 22, 02, 06, 10, 14 ET). Daily-level
ideas are therefore coarse; nothing finer than one 4h bar can be resolved.

## 2. The split (fixed now)

- DEVELOPMENT (DEV): 2010-01-01 to 2019-12-31. Effective: 2013-01-02 to 2019-12-31.
- OUT-OF-SAMPLE (OOS): 2020-01-01 to 2026-09-30 (last bar in the export).
- Screening code loads bars through `scalpel.data.load_bars("dev")`, which truncates at
  2019-12-31 23:59 ET. Loading `"oos"` raises unless `results/OOS_UNLOCKED` exists; that
  file is created only after `results/frozen_rules.md` is committed, and it records that
  commit hash.
- DEV trades still open at the last DEV bar are closed at that bar's close.
- Level validation (`validate_export.py`) uses the whole file: it checks arithmetic, not
  performance.

## 3. Level modes (every test runs in both)

- `fixed`: v37 constants (vol 18.54 D/W, 17.37 M). Known lookahead: a 2026 snapshot applied
  to all history, and the OOS period precedes the snapshot, so a fixed-mode OOS result is
  also not fully clean.
- `scaled`: vol = mean of the last 252 VIX closes as of the last VIX close before the
  period opens (D: prior day; W: prior Friday; M: last day of prior month). Bias stays
  constant (0.481 D/W, 0.531 M).
- `ewma_rs` (daily only): vol = 100 * sqrt(252 * EWMA of the Rogers-Satchell daily variance,
  lambda 0.924), using only sessions strictly before the day being levelled.

## 4. Execution model

- Bars are ES 4h. Costs: 1 tick (0.25 pt, $12.50) slippage on every fill (entries, stops,
  targets, time exits) plus $2.50 commission per side. Round trip = 0.60 pt = $30 per ES
  contract (MES identical in points).
- Signal-driven orders (anything that depends on a bar's data): signal at bar close, fill at
  the next bar's open.
- Scheduled orders (known before the bar starts, e.g. "at week open", "at Friday close"):
  fill at that bar's open or close price.
- Resting limit entries at a level that is known before the period starts (allowed variant):
  a buy limit fills if the bar's low <= level, at min(level, bar open); in the entry bar
  only the stop is checked, never the target.
- Stops are stop-market orders: fill at the stop, or at the bar open if the bar gaps
  through. Targets are limits: filled when the bar touches them.
- If one bar reaches both stop and target, the stop fills first. The SPX 1-minute data
  may be used to audit how pessimistic this is, but never to change a backtest fill.
- Every directional variant has a defined initial stop, so results can be stated in R
  (units of initial risk) as well as points.
- Fixed-fractional account: $100,000 start, risk 1% of equity per trade in MES contracts
  ($5/pt), contracts = floor(0.01 * equity / (stop distance * $5 + $3 costs)), trade
  skipped if 0.

## 5. Baselines (required for every variant)

Directional:
1. **Jitter (500 runs).** Each run draws, independently for every level name, a
   multiplicative factor on that level's distance from the period open: 1 + s*u with
   s = +/-1 at random and u ~ U[0.10, 0.40]. Factors are constant within a run (each run is
   a slightly different indicator). The same rules are run on the jittered levels.
2. **Round-grid bands (no level logic).** Levels replaced by a symmetric grid around the
   period open at multiples of half a fixed-mode sigma: D 0.584%, W 1.286%, M 2.507%.
   Each level role maps to the nearest grid band on the same side of the open (the open
   maps to itself). Same rules.
3. **Random entry (informational).** Same number of trades, same direction and holding time,
   entry bars drawn at random from the eligible DEV bars; 500 runs. Measures drift and
   long bias.

Options (modeled only): the same structure with short strikes at matched deltas (the median
delta of the level strike over DEV, and fixed 16/10 delta), no level information, same
entry days.

## 6. Candidate gates (DEV only). A candidate must pass all of them

- G1. Net EV/trade > 0 after costs, in the chosen mode **and** in the other vol mode
  (the fixed/scaled twin must also have EV > 0).
- G2. At least 100 DEV trades.
- G3. Beats its baselines: EV/trade at or above the 90th percentile of the 500 jitter runs,
  and above the round-grid baseline's EV/trade.
- G4. Bootstrap (10,000 resamples of trades) 95% CI of mean net P&L per trade has a lower
  bound > 0.
- G5. Yearly stability: net P&L > 0 in at least 5 of the 7 DEV years; total stays > 0 with
  the best year removed; total stays > 0 with trades in 2015-08-17..2015-09-30,
  2018-01-29..2018-04-30 and 2018-10-01..2018-12-31 removed.
- G6. Walk-forward: within the variant's family grid, for each test year 2016-2019 pick the
  highest-EV variant on 2013..(year-1) and record its test-year P&L; the sum must be > 0.

Ranking when more than 3 pass: bootstrap lower bound of mean R per trade, at most one
candidate per hypothesis family.

If nothing passes all gates: the best variant (by bootstrap lower bound in R) that passes
G1, G2 and G4 is frozen as an **exploratory** candidate and run OOS once. It cannot get a
"trade it" verdict. If nothing passes G1, G2 and G4 either, OOS is not run.

## 7. OOS (run once, after freezing)

Report: trades, win rate, EV/trade, profit factor, max drawdown, worst trade, worst month,
Sharpe (per trade and annualised from daily P&L), results by year and by VIX regime
(prior close < 15, 15-20, 20-30, > 30), with and without roll weeks, both vol-mode twins,
the jitter baseline in OOS, and the deflated Sharpe ratio with N = number of rows in
`results/log.csv` and the variance of trial Sharpe ratios taken from that log.

Verdict rules:
- **Trade it**: passed every DEV gate, OOS EV/trade > 0 with bootstrap CI lower bound > 0,
  OOS profit factor > 1.1, DSR > 0.95, and OOS EV at or above the 90th percentile of
  the OOS jitter runs.
- **Paper trade it**: passed every DEV gate and OOS EV/trade > 0, but one of the other
  "trade it" conditions fails.
- **Don't trade it**: OOS EV/trade <= 0, or the candidate was exploratory, or nothing
  qualified.

## 8. Known limitations (repeated in every report)

- Constant vol is a 2026 snapshot applied to all history (lookahead); scaled mode is the
  clean version.
- Constant bias: the real TrueALGO bias history is unknown. These are Chris's clone levels,
  not TrueALGO.
- Week boundary: Sunday 18:00 ET, but a Friday exchange holiday (not Good Friday) starts
  the week Thursday 18:00 (`weekly_open()`).
- 4-hour bars only; DEV starts 2013, not 2010; no real option quotes.
- The continuous contract is unadjusted; roll weeks are flagged and tested with and
  without.
