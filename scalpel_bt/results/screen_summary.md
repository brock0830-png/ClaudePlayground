# Screen summary — DEV only (2013-01-02 to 2019-12-31)

Everything here uses DEV bars only (`load_bars("dev")`). No OOS bar was loaded before the freeze commit.
Every variant is a row in `results/log.csv`: **12,514 rows** (12,264 directional backtests with baselines, and
250 modeled option screens). That count is the N used for the deflated Sharpe ratio.

## Known limitations (apply to every number below)

- **Constant vol = lookahead.** `fixed` mode uses the 2026 v37 constants (18.54 D/W, 17.37 M) for all history.
  `scaled` mode (252-day mean VIX as of the prior period's close) and, for daily levels, `ewma_rs`
  (EWMA Rogers-Satchell, lambda 0.924, prior sessions only) are the point-in-time versions. Every variant ran in
  both fixed and scaled mode (plus ewma_rs for D), and gate G1 requires EV > 0 in both.
- **Constant bias.** The real TrueALGO bias history is unknown. These are Chris's clone levels, not TrueALGO.
- **Week boundary.** Sunday 18:00 ET; a Friday exchange holiday starts the week Thursday 18:00 (`weekly_open()`).
  The 2013-2026 export shows TradingView does this for *observed* Friday holidays (July 3, Juneteenth) but not when
  July 4 itself is a Friday (2014, 2025): there the Thursday-evening bars are orphans carrying next week's open.
  Those bars, and the 2018 Memorial Day and Thanksgiving orphans, are flagged and never generate signals
  (`results/validation.md`).
- **Data.** 4-hour TradingView bars only (no 1-/5-minute ES), so DEV starts in 2013 instead of 2010 and a daily
  level trade is resolved at 4-hour granularity. Prices are unadjusted continuous ES1!. All 55 contract switches
  were dated from the ES-SPX basis jump. Positions are closed before each switch; weekly levels are stale in
  switch weeks and monthly levels after the switch, so W and M variants ran with and without those periods.
- **No real option quotes** for 2010-2019 were reachable. Option results are modeled (Black-76, ATM IV =
  0.92 x VIX9D, an assumed skew, modeled bid-ask) and are not eligible for OOS.

## What was screened

| Stage | Families | Timeframes | Variants |
|---|---|---|---|
| A | bounce (fade first touch; reject / touch / resting limit) x 12 levels x 3 stops x 4 exits | D, W, M | 4,752 |
| A | break-and-go (close through or buy-stop at a level; next level / 1R / 2R / week end) | D, W, M | 2,112 |
| A | reclaim (close back above a level after a close below it) | D, W, M | 1,056 |
| A | confluence (D level within 0.05-0.2% of any W/M level; W level within 0.1-0.4% of an M level) | D, W | 1,728 |
| B | filters: trend (20/50d MA), VIX regime (5 cuts), higher-TF open above/below, day of week, on 20 simple shapes per TF and on the 13 Stage-A all-gate shapes | D, W | 2,308 |
| B | multi-level ladders (4 levels per side, both sides) | D, W | 28 |
| B | hold past the level period (6/30 bars for D, 30/60 bars for W) | D, W | 280 |
| OPT | modeled weekly spreads / condors on W levels, legging on first touches, 0DTE on D levels, plus a sensitivity run | D, W | 250 |

Each directional variant ran in every vol mode (W/M: with and without roll periods) against three baselines:
500 jittered-level runs (each level's distance scaled by 1 +/- U[0.10, 0.40], independently per level),
the round-% grid (levels snapped to multiples of half a fixed-mode sigma, i.e. "fixed % bands with no level
logic"), and 500 random-entry runs with the same count, direction and holding times.
Costs: 0.60 pt per round trip (1 tick slippage per side + $2.50 commission per side). Signals on bar close,
fill at the next bar's open, stop first when a bar hits both.

## The main result: no evidence the level placement is the edge

| Directional variants | Count | EV > 0 | Mean EV/trade, real levels | Mean EV, jittered levels | Mean EV, round-% grid | Mean EV, random entry |
|---|---|---|---|---|---|---|
| Long | 6,366 | 63.9% | +1.57 pt | **+1.89 pt** | +1.14 pt | +1.77 pt |
| Short | 5,891 | 13.2% | -5.53 pt | -5.51 pt | -5.91 pt | -3.18 pt |

- Averaged over all long variants, the real levels do **worse** than randomly jittered levels (+1.57 vs +1.89 pt)
  and worse than random entries with the same holding times (+1.77 pt). Averaged over all shorts they are
  indistinguishable from jittered levels. Long trades win because ES rose from 1,440 to 3,230 in 2013-2019;
  shorts lose for the same reason.
- Percentile of each variant's EV within its own 500 jitter runs, deciles 0-10 ... 90-100:
  `1432, 896, 1042, 1049, 1455, 1489, 1082, 973, 1030, 1800` (uniform would be about 1,226 per decile). Both tails
  are fat, which is noise dispersion. The top decile's excess over the bottom is 368 variants (3%), which is no
  systematic level effect.
- Real levels beat the round-% grid in 54.8% of variants: near a coin flip.
- By family (mean jitter percentile / share at or above the 90th): bounce 52.2 / 15.7%, break 52.7 / 12.4%,
  confluence 50.1 / 13.8%, reclaim 47.6 / 14.8%. Confluence (D near W/M, W near M) adds nothing over single levels.
- By vol mode: fixed 52.4, scaled 51.6, ewma_rs 48.8 mean jitter percentile. Roll periods in/out: no difference.
- Monthly levels: at most 84 first-touch trades per level in DEV, so no M variant can reach 100 trades (G2).

## Gate pass counts (PROTOCOL section 6)

| Family | Variants | G1 (EV>0 fixed & scaled) | G2 (n>=100) | G3 (beats jitter p90 & grid) | G4 (CI > 0) | G5 (yearly) | G6 (walk-forward) | All six |
|---|---|---|---|---|---|---|---|---|
| bounce | 6,850 | 2,008 | 2,179 | 875 | 261 | 1,060 | 4,362 | 19 |
| bounce ladder | 28 | 14 | 28 | 3 | 3 | 4 | 16 | 1 |
| break-and-go | 2,602 | 890 | 1,085 | 235 | 284 | 532 | 1,214 | 6 |
| confluence | 1,728 | 358 | 634 | 213 | 50 | 221 | 432 | 0 |
| reclaim | 1,056 | 235 | 186 | 132 | 17 | 84 | 288 | 0 |

26 variants pass all six gates, and **every one is long**. Of the 84 variants that pass every gate except G3,
26 (31%) also clear G3. That is above the 10% a random jitter rank would give, but ranking by EV biases the
jitter percentile upward. With 1,800 variants in the top jitter decile (about 1,230 expected) and both tails fat,
26 survivors of a 12,264-row screen are what a no-edge world with a bull-market drift produces. The deflated
Sharpe ratio agrees: per-trade Sharpe ratios across the DEV trials have variance 0.063 (rows with n >= 100). With
N = 12,514 trials, the expected best Sharpe under no edge is **0.99 per trade**. The two selected candidates
have DEV per-trade Sharpe 0.29 and 0.23, so their **DEV DSR is about 0** (z = -6.8 and -9.4), although each is
individually significant against zero (PSR 0.998 and 0.997).

The 26 all-gate variants, ranked by the bootstrap lower bound of mean R (the pre-registered ranking):

| id | family | TF | mode | roll | level / rule | filter | n | EV pt | CI low | R CI low | jitter pct |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 11928 | bounce | W | scaled | incl | GP_B_IN touch, stop 0.25σ, 1R | VIX < 252d mean | 122 | 3.45 | 1.30 | 0.079 | 100 |
| 11847 | break | W | fixed | excl | GP_T_IN close-through, stop 0.25σ, week end | 20d trend up | 138 | 4.45 | 1.22 | 0.052 | 90.8 |
| 3316 | break | W | fixed | excl | GP_T_IN close-through, stop 0.25σ, week end | none | 175 | 4.38 | 0.85 | 0.047 | 96.8 |
| 3772 | bounce | W | scaled | incl | GP_B_OUT limit, stop 0.25σ, week end | none | 242 | 3.26 | 0.42 | 0.045 | 96.0 |
| 11887 | break | W | fixed | excl | GP_T_IN close-through, stop 0.5σ, target RH | M open below price | 127 | 3.38 | 1.02 | 0.031 | 99.2 |
| 1522 | bounce | D | ewma_rs | incl | TL1 reject, stop 1σ, 1R | none | 122 | 2.78 | 0.32 | 0.023 | 96.4 |
| 11957 | ladder | D | fixed | incl | GP_B_IN/RL/RB_TOP/TL1 reject, stop 0.5σ, day end | none | 808 | 1.70 | 0.58 | 0.022 | 99.4 |
| ... | | | | | 19 more, all long D/W bounces and W GP_T_IN breaks (see `log.csv`, `scripts/summarize_log.py`) | | | | | | |

## Modeled options (not eligible for OOS)

- 228 base option variants plus 22 sensitivity variants. **None has positive modeled EV after costs** under the
  base assumptions (weekly put spreads at TL1/TL2 about -0.3 pt, condors -1.0 pt, 0DTE on D levels -0.3 to -1.3 pt).
- The level strike beat the delta-matched strike (same entry days, same structure) on EV per unit risk in only
  39 of 228 variants. It beat fixed 16-delta/10-delta in 195, but that baseline sits much closer to the money and
  takes more risk. Legging on first touches was no better than delta-matched legging.
- Sensitivity (ATM IV = VIX9D, SPX-style 0.10 minimum spread): EV improves but stays negative except the
  RL/RB_TOP weekly put spread (+0.09 to +0.15 pt per spread, noise level). Calls lose in every configuration.
- Every one of these numbers depends on the assumed IV level, skew and bid-ask. Real SPX/XSP or ES option quotes
  (OptionsDX, CBOE DataShop, Databento) would be needed before any option claim.

## Candidates frozen for OOS (PROTOCOL: best by R CI lower bound, one per hypothesis family)

1. **C1 bounce: #11928**, weekly GP_B_IN touch in scaled mode with the VIX-below-mean filter.
2. **C2 break-and-go: #11847**, close through weekly GP_T_IN in fixed mode, roll weeks excluded, 20-day uptrend filter.

Confluence and reclaim produced no all-gate variant, so there is no third candidate. Full rules, DEV metrics and
the OOS plan are in `frozen_rules.md`; DEV equity curves are in `dev_C1_bounce_W_GPBIN_touch.png` and
`dev_C2_break_W_GPTIN.png`.

**Pre-OOS assessment (written before any OOS bar was loaded).** Both candidates are long-only weekly trades
chosen from a large screen in a strong bull market. C1's fixed-mode twin has EV +1.85 pt but a CI spanning zero
and a 43rd jitter percentile, and its VIX filter was chosen from nine filters. C2 is positive in nearly every
sibling configuration, but its edge over jittered levels is marginal (90th percentile) and looks like generic
"up this week, hold to Friday" momentum/drift. Because the DEV DSR is about 0, the pre-registered "trade it" bar
(DSR > 0.95) is out of reach for both. The best achievable verdict is "paper trade it".
