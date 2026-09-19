# TALOS — full specification of the tactical IRA system (v1, 2026-09-19)

**Why the name.** Talos was the bronze automaton of Crete: a machine that patrolled the island's coast on a fixed daily circuit, applying the same rule every day without judgement or fatigue. This system is exactly that: one mechanical patrol of six closing prices after every close, no discretion, no news, no intraday input.

This document is written so that a future thread with no memory of this one can rebuild the system, its data, its backtest and its numbers from scratch. Everything below was computed in the build session; nothing is quoted from outside sources. The code lives in GitHub repository `brock0830-png/ClaudePlayground`, branch `claude/building-session-0uw42p` (commit `07d4616` at the time of writing); this document is self-sufficient without it.

---

## 1. Objective and verdict

Client objective: CAGR ≥ 15% with MAR (CAGR ÷ |MaxDD|) ≥ 1.0, stretch 1.25, in a US self-directed IRA (long-only, no margin borrowing, no shorting; leveraged and inverse ETFs allowed as long positions; T+1 settlement, no limited margin required).

Verdict: **not met on any window longer than a decade.** What TALOS delivers instead (all figures net of costs, execution one full day after the signal):

| Window | Config | CAGR | Vol | Sharpe | MaxDD | MAR | Trades/yr |
|---|---|---|---|---|---|---|---|
| 1998-01-02 → 2026-09-18 | TALOS 1x | 9.7% | 10.2% | 0.75 | -15.5% | 0.63 | 75 |
| 1998-01-02 → 2026-09-18 | TALOS 2.5x | 14.6% | 17.9% | 0.73 | -25.6% | 0.57 | 132 |
| 1998-01-02 → 2026-09-18 | SPY buy-and-hold | 9.3% | 19.3% | 0.44 | -55.2% | 0.17 | 0 |
| 2016-01-04 → 2026-09-18 (locked holdout, one shot) | TALOS 1x | 11.8% | 10.2% | 0.93 | -14.4% | 0.82 | 74 |
| 2016-01-04 → 2026-09-18 | TALOS 2.5x | 17.7% | 17.3% | 0.90 | -25.3% | 0.70 | 130 |
| 1991-01-04 → 2026-09-18 (post-holdout proxy extension) | TALOS 1x | 10.3% | 10.2% | 0.75 | -15.5% | 0.66 | 74 |
| 1991-01-04 → 2026-09-18 | TALOS 2.5x | 15.6% | 17.9% | 0.75 | -25.6% | 0.61 | 130 |
| 1991-01-04 → 2026-09-18 | SPY buy-and-hold | 11.3% | 18.2% | 0.53 | -55.2% | 0.21 | 0 |

Deflated Sharpe (Bailey & López de Prado, 228 distinct design-phase trials, expected max null Sharpe 0.54 annualised): probability that the 1x Sharpe beats the best-of-trials null is 0.66 in the design window, 0.89 in the holdout, 0.86 over 1998-2026 (`reports/holdout/deflated_sharpe.json`). The worst calendar year at 1x is 2022 (-9.8%); at 2.5x it is 2022 (-20.4%).

---

## 2. The rules (complete)

One decision per trading day, after the close, from **dividend-adjusted closing prices**. Orders are executed at the **next day's close** (in the backtest, a target decided at close t is filled at close t+1 and first earns the return from close t+1 to close t+2).

### 2.1 Instruments

Underlyings: **QQQ, SPY, IWM, TLT, IEF, GLD**, plus a cash sleeve (BIL, SHV or a same-day-settling money-market fund).
Leveraged expressions used only when the exposure multiplier is above 1.0: TQQQ (3x QQQ), UPRO (3x SPY), TMF (3x TLT), UST (2x IEF), UGL (2x GLD). IWM has no leveraged fund in the set, so its exposure is capped at 1x. No inverse funds (every inverse variant tested lost money).

### 2.2 Sleeve A — equity core, 70% of capital

Each day compute for QQQ:
- `SMA200` = simple average of the last 200 adjusted closes (needs 200 observations; before that the sleeve is cash).
- `vol20` = standard deviation of the last 20 daily simple returns × √252.

Then:
- If `close_QQQ > SMA200_QQQ`: exposure to QQQ = `min(1, 0.10 / vol20)` of the sleeve. Remainder of the sleeve in cash.
- Else (QQQ at or below its SMA200): QQQ exposure 0. If `close_IEF > SMA200_IEF` hold 100% of the sleeve in IEF, otherwise 100% of the sleeve in cash.

### 2.3 Sleeve B — momentum rotation, 30% of capital

On the **last trading day of each calendar month** only:
- For each of SPY, QQQ, IWM, TLT, GLD compute `mom = TR_index_today / TR_index_126_trading_days_ago − 1` (126-day total return).
- Compute the same 126-day return of the cash sleeve.
- Rank the five by `mom`, take the top **3**. Each of the three whose `mom` is **not greater than** cash's 126-day return is replaced by cash.
- Hold the survivors at **1/3 of the sleeve each** (so the sleeve can be 0%, 33%, 67% or 100% invested) until the next month-end signal. If any of the five lacks 126 days of history the previous month's weights are carried forward (at the start, the sleeve is cash).

### 2.4 Blend, exposure multiplier, and mapping to funds

Target exposure per underlying (in units of the underlying):
`E_u = 0.70 × coreExposure_u + 0.30 × rotationExposure_u` (core contributes only to QQQ and IEF).

Multiply every `E_u` by the **exposure multiplier m** (1.0 base; 2.5 is the 25%-drawdown frontier point; 3.0 is the maximum the fund set allows).

Map each `m·E_u` to fund weights (fractions of account equity), per underlying:
- If `m·E_u ≤ 1`: hold `m·E_u` in the 1x fund.
- If `1 < m·E_u ≤ L` where L is the leverage of the biggest fund for that underlying (3 for QQQ, SPY, TLT; 2 for IEF, GLD; 1 for IWM): weight in the L-x fund `b = (m·E_u − 1)/(L − 1)`, weight in the 1x fund `1 − b`. (So fund weights for one underlying always sum to ≤ 1 and the combination delivers exactly `m·E_u` of exposure.)
- If `m·E_u > L`: capped at the L-x fund at 100% (exposure L).

If the fund weights across all underlyings sum to more than 1, scale all of them down proportionally so they sum to exactly 1. Cash = 1 − sum of fund weights. **No borrowing ever.**

### 2.5 Rebalance band

Each day compare each fund's target weight with its current (drifted) weight. Trade the fund only if `|target − current| > 2%` of account equity; otherwise leave it. This is what keeps trades near 75/yr at 1x and next-day round trips near 6/yr, so no limited margin is needed.

### 2.6 The eight free parameters (all fixed)

| # | Parameter | Value |
|---|---|---|
| 1 | Trend length (QQQ gate and IEF gate) | 200 days |
| 2 | Core volatility target | 10% annualised |
| 3 | Volatility window | 20 days |
| 4 | Rotation lookback | 126 trading days |
| 5 | Rotation holdings | top 3 of 5 |
| 6 | Core weight in the blend | 0.70 |
| 7 | Rebalance band | 2% of equity |
| 8 | Exposure multiplier | 1.0 (or 2.5 / 3.0) |

There is no drawdown-control overlay, no VIX input, no intraday logic, no options.

### 2.7 Costs assumed in every reported figure

2 bp commission + half the bid-ask spread per trade side (half-spread defaults: 1 bp for liquid ETFs; per-instrument values in `src/trials.py` `HALF_SPREAD`), doubled for leveraged funds. Sensitivities: zero costs and 3× costs are in the ledger.

---

## 3. Data and proxies (how the 1991/1997-start history was built)

### 3.1 Sources actually used
- **FMP (Financial Modeling Prep) dividend-adjusted daily closes** for every ETF: SPY, QQQ, IWM, DIA, TLT, IEF, SHY, BIL, SHV, GLD, SLV, DBC, USO, EDV, SSO, QLD, UPRO, TQQQ, SPXL, TMF, UBT, UST, UGL, SH, SDS, SPXU, PSQ, QID, SQQQ, TBT, TMV. Cross-checked against the Norgate total-return export on the two ETFs that could be loaded: agreement within 2–6 bp/yr.
- **FMP price indexes**: ^GSPC (from 1990), ^NDX (1985-10 → 2023-05-23 in the pull), ^RUT (1990), ^VIX (1990), GCUSD gold spot (1980).
- **FMP US Treasury constant-maturity yields** (1m…30y): 1990-01 → 2007-06 daily (paged quarterly; the endpoint returns ~63 rows per call), plus later spot checks. 20y yield is missing before 1993-10.
- FMP chart endpoints cap at 5000 rows per call; paginate by date.

### 3.2 Panel construction (identical for the 1997 frozen panel and the 1990 extension panel)
Trading calendar = SPY trading days (from 1993-01-29); before that, S&P 500 index dates.

- **Cash** (`CASH`): 3-month CMT yield ÷ 252 per day until BIL's first print (2007-05-30), then BIL's daily return + its expense ratio ÷ 252.
- **Equity ETF proxies** (`SPY_X`, `QQQ_X`, `IWM_X`): index price return + a constant daily carry calibrated as the mean of (live ETF return − index return) over the **first 5 years** of overlap; spliced to the live ETF from its first print. Calibrated carries (annualised): SPY +1.46%, QQQ −0.37%, IWM +1.19%. Live starts: SPY 1993-01-29 (in-panel from 1997-01-03), QQQ 1999-03-10, IWM 2000-05-26.
- **Gold** (`GLD_X`): GCUSD return + carry (−0.28%/yr, same method), spliced to GLD from 2004-11-18.
- **Bond proxies** (`TLT_X`, `IEF_X`, `SHY_X`): daily total return of a constant-maturity par bond with semiannual coupons priced off the CMT yield (yield today vs yesterday, plus accrual), minus expense ratio; maturity chosen among candidates by lowest tracking error vs the live ETF on 2002-07 → 2007-06: TLT ← 20y CMT at 20y maturity (TE 2.8%/yr, corr 0.96), IEF ← 7y CMT at 7y (TE 1.9%/yr, corr 0.95), SHY ← 2y CMT at 1.9y. Spliced to live ETFs from 2002-07-30. **Extension panel only:** 20y yield before 1993-10 = 30y yield − 10.8 bp (mean 30y−20y spread over 1993-10 → 1996-10).
- **Leveraged/inverse fund simulations** (`TQQQ_X` etc.): `L·r_base − (L−1)·(rf + spread) − ER/252` daily, with `spread` calibrated so the mean daily return matches the live fund over its whole live history; spliced to the live fund from its first print. Calibrated financing spreads: TQQQ 0.73%/yr, UPRO 0.66%, TMF 0.55%, UST −0.33%, UGL 1.52% (expense ratios from current prospectuses). Split-half drift of the spread exceeds 1%/yr for SSO and TQQQ; a ±1%/yr drag sensitivity on all simulated segments is in the ledger.
- Levels = cumulative product of (1 + return); momentum uses these total-return levels.

### 3.3 Known data caveats
- Pre-inception history is proxy: QQQ before 1999-03, IWM before 2000-05, TLT/IEF before 2002-07, GLD before 2004-11, everything before 1993-01. The 2000-02 episode is the least reliable of the stress windows.
- NDX pull ends 2023-05-23 (only matters for the QQQ proxy, which is not used after 1999).
- The FMP tool-result harvester must merge rows **field-wise per date** (last non-null wins); a naive "keep last row" merge once blanked eight SPY adjusted closes in March 2024. Fixed and verified.
- Drive connector limits (~6 MB practical, 10 MB hard) made the Norgate export unusable as the primary source; FRED, Ken French, CBOE, Stooq and Yahoo were blocked by the environment's egress policy.

---

## 4. Backtest engine (to reproduce the numbers)

Daily loop, vectorised over instruments, weights as fractions of equity:
1. Day i return: `gross = w_prev·r_i + (1 − Σw_prev)·cash_i`.
2. Drift: `w_drift = w_prev·(1 + r_i)/(1 + gross)`.
3. Execute at close i the target decided at close i − (lag − 1); base `lag = 2`. `delta = target − w_drift`; zero any `|delta| < band`; cost = Σ|delta|·unit_cost; `port_i = gross − cost`; `w_prev = w_drift + delta`.
4. Lag 1 (same-close fill) and lag 3 (extra day) are sensitivities only.
Metrics: CAGR (calendar-time), vol (√252·std), Sharpe vs the cash series, Sortino, MaxDD with peak/trough/recovery dates, longest underwater, worst day/month/12m, time in market, average gross leverage (Σ w_i·L_i), one-way turnover, trades/yr (instruments traded per day summed), consecutive-day round trips/yr (a buy followed by a sell of the same fund the next day, from executed deltas), correlation to SPY.
No-lookahead tests (`tests/test_engine.py`, 9 tests): base lag is two days; the return on day s depends only on weights through s−2; perfect foresight of the next day's return has no edge at base lag; a NaN return placed in the future does not change the past; buy-and-hold at zero cost matches the asset exactly; an all-cash target earns exactly the cash series; costs reduce return by turnover × rate; leverage above 1 or negative weights are rejected; one extra day of lag shifts holdings by exactly one day.

---

## 5. Process discipline used (so a rebuild can be judged)

1. Phase 0 data audit; Phase 1 proxies + engine + tests; Phase 2 pre-registration of hypotheses H1–H12, parameter grids, gates P1–P5, cost model, holdout lock (2016-01-04 → 2026-09-18) written **before** any trial.
2. Phase 3 development on **1998-01-02 → 2015-12-31 only**: 228 distinct trials, every one logged with parameters and metrics to `TRIAL_LEDGER.csv` (498 rows including annotated superseded/duplicate rows). Baselines: SPY, 60/40, SPY 200-day timing, vol-targeted SPY.
3. Phase 4 freeze (commit `06a6f79`), one-shot holdout run guarded by `HOLDOUT_UNLOCKED` + `RAN_ONCE` files; deflated Sharpe with the full trial count.
4. Phase 5 (post-holdout, exploratory, clearly labelled): history extension to 1991 on the 1990-start panel, logged as phase P5 and excluded from the DSR count.

Disclosed deviations: the core's IEF-fallback overlay was chosen on a best cell, not a median cell; the 2% band was added after seeing 754 trades/yr unbanded (changed CAGR by 0.0% and MAR by 0.001 in design); k=3 kept over k=2 to avoid a second best-cell pick.

---

## 6. What was tried and rejected (design window unless noted)

- Inverse and leveraged-inverse funds in any sleeve: lost money in every cell.
- Drawdown-control overlay (halve exposure below −10% from peak, restore at −5%): MAR +0.02, CAGR −0.5%, one more parameter. Dropped.
- VIX-based overlays, short-term reversal overlay: no MAR improvement worth a parameter.
- Rotation k=2: slightly higher MAR in one comparison; not adopted.
- Higher exposure multipliers: Sharpe flat (0.64–0.67), MAR falls monotonically from 0.63 to 0.56; all extra CAGR is leverage.
- Bond fallback to cash instead of IEF: lower CAGR and MAR.

---

## 7. Behaviour to expect live (from the record)

- Roughly matches SPY's return at 1x with half to two thirds of SPY's drawdown; falls behind buy-and-hold in calm low-vol bull markets (1995–97, 2019), pulls ahead in bears it can sidestep (2000–02, 2008), and loses in years where equities and bonds fall together with whipsaw trends (1994: −1.5%; 2022: −9.8%; 2005: −6.9%; 2015: −6.3%).
- Three things most likely to break it: (1) a grinding QQQ bear with bonds falling too, because the fallback is IEF; (2) leveraged-fund mechanics above 1x (UGL, UST, UBT fail a $1M liquidity screen; simulated history ±1%/yr); (3) data/execution drift on marginal 200-day-gate days.
- Settlement: keep cash in a same-day money fund; on the rare next-day cut, sell only settled shares. No limited margin needed at 1x or 2.5x.

---

## 8. Daily procedure (live)

1. After the close, refresh adjusted closes for QQQ, SPY, IWM, TLT, IEF, GLD (and the cash fund).
2. Compute Sleeve A (§2.2) every day; recompute Sleeve B (§2.3) only on the month's last trading day, else carry it.
3. Blend (§2.4) with the chosen multiplier; map to funds.
4. Compare with current holdings; place next-close orders only for funds whose |target − current| > 2% of equity.
In the repo: `python daily_signal.py --lever 1.0 --holdings holdings.json` prints exactly this after `python src/proxies.py` has been rerun on refreshed data.

---

## 9. File map in the repository

`DATA_AUDIT.md`, `PROXY_VALIDATION.md` (+ `reports/proxies/*.png`), `PREREG.md`, `TRIAL_LEDGER.csv`, `RULES.md`, `REPORT.md`, `daily_signal.py`, `src/` (`data.py`, `proxies.py`, `engine.py`, `metrics.py`, `strategies.py`, `system.py`, `trials.py`, `run_phase3*.py`, `run_holdout.py`, `run_extension.py`, `fmp_ingest.py`, `transcript_harvest.py`), `tests/test_engine.py`, `reports/phase3/`, `reports/holdout/`, `reports/extension/`, `data/proxies/` (frozen 1997 panel, committed), `data/proxies_ext/` (1990 panel, committed), `data/raw/fmp/*.parquet` (not committed; rebuild from FMP as in §3).
