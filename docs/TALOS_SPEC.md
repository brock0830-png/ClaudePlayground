# TALOS — full specification of the tactical IRA system (v2 = configuration T7, 2026-09-19)

**Why the name.** Talos was the bronze automaton of Crete: a machine that patrolled the island's coast on a fixed daily circuit, applying the same rule every day without judgement or fatigue. This system is exactly that: one mechanical patrol of six closing prices after every close, no discretion, no news, no intraday input.

This document is written so that a future thread with no memory of this one can rebuild the system, its data, its backtest and its numbers from scratch. Everything below was computed in the build session; nothing is quoted from outside sources and nothing was taken from any other system. The code lives in GitHub repository `brock0830-png/ClaudePlayground`, branch `claude/building-session-0uw42p` (commit `7c205a3` at the time of writing); this document is self-sufficient without it. **v2 adopts T7 as the live rules** (client decision 2026-09-19); the pre-registered v1 rules and their clean holdout are kept in Appendix A. This file supersedes TALOS_SPEC v1, v1.1 and v1.2.

---

## 1. Objective, verdict, and what the evidence is worth

Client objective: CAGR ≥ 15% with MAR (CAGR ÷ |MaxDD|) ≥ 1.0, stretch 1.25, in a US self-directed IRA (long-only, no margin borrowing, no shorting; leveraged ETFs allowed as long positions; T+1 settlement, no limited margin).

Verdict: **not met on any window longer than a decade** by any configuration. Net results (execution one full day after the signal, 2 bp + half spread per trade, doubled on leveraged funds):

| Window | Config | CAGR | Vol | Sharpe | MaxDD | MAR | Trades/yr |
|---|---|---|---|---|---|---|---|
| 1991-01-04 → 2026-09-18 | **TALOS v2 (T7) 1.25x** | 11.7% | 11.1% | 0.81 | -14.0% | 0.83 | 100 |
| 1991-01-04 → 2026-09-18 | TALOS v2 (T7) 1.0x (no leveraged funds) | 10.2% | 9.2% | 0.81 | -11.3% | 0.91 | 85 |
| 1991-01-04 → 2015-12-31 | TALOS v2 (T7) 1.25x | 11.1% | 11.0% | 0.72 | -13.9% | 0.79 | — |
| 2016-01-04 → 2026-09-18 | TALOS v2 (T7) 1.25x | 13.1% | 11.4% | 0.99 | -13.2% | 1.00 | — |
| 1991-01-04 → 2026-09-18 | TALOS v1 1x | 10.3% | 10.2% | 0.75 | -15.5% | 0.67 | 74 |
| 1998-01-02 → 2026-09-18 | TALOS v1 1x | 9.7% | 10.2% | 0.75 | -15.5% | 0.63 | 75 |
| 2016-01-04 → 2026-09-18 (locked one-shot holdout) | TALOS v1 1x | 11.8% | 10.2% | 0.93 | -14.4% | 0.82 | 74 |
| 1991-01-04 → 2026-09-18 | TALOS v1 2.5x | 15.6% | 17.9% | 0.75 | -25.6% | 0.61 | 130 |
| 1991-01-04 → 2026-09-18 | SPY buy-and-hold | 11.3% | 18.2% | 0.53 | -55.2% | 0.21 | 0 |

**Evidence quality, stated plainly.** Only v1 has clean out-of-sample evidence: its rules were frozen on 1998-2015 and run once on 2016-2026 (deflated-Sharpe probability of beating the best-of-228-trials null: 0.89 in the holdout). Every v2 number is in-sample: the dip boost, gold sleeve, gate band and 250-day length were chosen after the holdout, with the full 1991-2026 record in view, using a 1991-2015 / 2016-2026 split that is a pseudo-holdout at best. What supports v2 beyond its numbers: the improvement over v1 has the same sign and size in both halves; the 20-cell parameter neighbourhood (gate band 0.5-2%, trend 200-300 days) gives full-window MAR 0.68-0.86 and CAGR 11.1-12.0%, all above v1; each added component is a standard, economically motivated rule (trend hysteresis, vol-scaled dip buying, trend-gated gold). The v2 results above 1.5x converge to v1's (identical worst drawdowns), so the multiplier should stay at 1.25 or below.

---

## 2. The rules (complete, TALOS v2 = T7)

One decision per trading day, after the close, from **dividend-adjusted closing prices**. Orders are executed at the **next day's close** (in the backtest, a target decided at close t is filled at close t+1 and first earns the return from close t+1 to close t+2).

### 2.1 Instruments

Underlyings: **QQQ, SPY, IWM, TLT, IEF, GLD**, plus a cash sleeve (BIL, SHV or a same-day-settling money-market fund). Leveraged expressions used only when the exposure multiplier is above 1.0: TQQQ (3x QQQ), UPRO (3x SPY), TMF (3x TLT), UST (2x IEF). At the recommended 1.25x only TQQQ is ever used. The gold sleeve is never levered (no UGL). IWM has no leveraged fund and is capped at 1x. No inverse funds.

### 2.2 Sleeve A — equity core, 49% of capital (= 70% × 0.7)

Each day compute for QQQ:
- `SMA250` = simple average of the last 250 adjusted closes (before 250 observations exist the sleeve is cash).
- `vol20` = standard deviation of the last 20 daily simple returns × √252.
- **Gate with hysteresis:** `gate = ON` if `close > 1.01 × SMA250`; `gate = OFF` if `close < 0.99 × SMA250`; otherwise `gate = yesterday's gate` (initial state OFF).
- `size = min(1, 0.10 / vol20)`.
- **Dip trigger:** `dip = (gate is ON) and (close ≤ min of the last 10 closes, today included)`. **Boost is active** on any day where a dip trigger occurred on that day or any of the previous 4 trading days, provided the gate is ON today.

Then:
- Gate ON, boost inactive: QQQ exposure = `size` of the sleeve; remainder cash.
- Gate ON, boost active: QQQ exposure = `max(size, min(1, 2 × size))` of the sleeve; remainder cash.
- Gate OFF: QQQ exposure 0. If `close_IEF > SMA250_IEF` hold 100% of the sleeve in IEF, otherwise cash.

### 2.3 Sleeve B — momentum rotation, 21% of capital (= 30% × 0.7)

On the **last trading day of each calendar month** only:
- For each of SPY, QQQ, IWM, TLT, GLD compute `mom = TR_index_today / TR_index_126_trading_days_ago − 1` (126-day total return), and the same for cash.
- Rank the five, take the top **3**; each whose `mom` is not greater than cash's is replaced by cash.
- Hold survivors at **1/3 of the sleeve each** until the next month-end signal. If any asset lacks 126 days of history, carry the previous month's weights (at the start, the sleeve is cash).

### 2.4 Sleeve C — gold, 30% of capital

Each day: if `close_GLD > SMA250_GLD` hold GLD at `min(1, 0.10 / vol20_GLD)` of the sleeve (vol20 of GLD's daily returns, annualised); otherwise the sleeve is cash.

### 2.5 Blend, exposure multiplier, and mapping to funds

Exposure per underlying (units of the underlying): `E_u = 0.49 × coreExposure_u + 0.21 × rotationExposure_u + 0.30 × goldExposure_u` (core contributes to QQQ and IEF; gold sleeve to GLD only).

Multiply every `E_u` by the **exposure multiplier m = 1.25** (or 1.0 for no leveraged funds). Map each `m·E_u` to fund weights per underlying:
- `m·E_u ≤ 1`: hold `m·E_u` in the 1x fund.
- `1 < m·E_u ≤ L` (L = 3 for QQQ/SPY/TLT, 2 for IEF, 1 for IWM and, by rule, GLD): weight in the L-x fund `b = (m·E_u − 1)/(L − 1)`, in the 1x fund `1 − b`.
- `m·E_u > L`: 100% in the L-x fund.
If all fund weights sum to more than 1, scale them down proportionally to sum to 1. Cash = 1 − sum. **No borrowing.** At m = 1.25 the only case above 1x is QQQ (max `m·E_u` = 1.25 × (0.49 + 0.07) = 0.70 from the core plus rotation… in practice ≤ 0.79), so the mapping only ever puts part of the QQQ exposure in TQQQ.

### 2.6 Rebalance band

Each day compare each fund's target weight with its current drifted weight; trade only if `|target − current| > 2%` of account equity.

### 2.7 The fourteen parameters (all fixed)

| # | Parameter | Value | # | Parameter | Value |
|---|---|---|---|---|---|
| 1 | Trend length (QQQ, IEF, GLD gates) | 250 days | 8 | Rotation lookback | 126 days |
| 2 | Gate hysteresis band | 1% | 9 | Rotation holdings | top 3 of 5 |
| 3 | Core vol target | 10% | 10 | Core : rotation split | 70 : 30 |
| 4 | Vol window | 20 days | 11 | Gold sleeve weight | 30% |
| 5 | Dip lookback | 10 days | 12 | Gold vol target | 10% |
| 6 | Dip hold | 5 days | 13 | Rebalance band | 2% |
| 7 | Dip multiplier | 2× | 14 | Exposure multiplier | 1.25 |

### 2.8 Costs assumed in every reported figure

2 bp commission + half the bid-ask spread per trade side (1 bp default half-spread for liquid ETFs; per-instrument values in `src/trials.py`), doubled for leveraged funds. Sensitivities at 1.25x over 1991-2026: zero costs MAR 0.87, triple costs 0.76, one extra day of delay 0.80, same-close fill 0.68.

---

## 3. Data and proxies (how the 1991/1997-start history was built)

### 3.1 Sources actually used
- **FMP (Financial Modeling Prep) dividend-adjusted daily closes** for every ETF: SPY, QQQ, IWM, DIA, TLT, IEF, SHY, BIL, SHV, GLD, SLV, DBC, USO, EDV, SSO, QLD, UPRO, TQQQ, SPXL, TMF, UBT, UST, UGL, SH, SDS, SPXU, PSQ, QID, SQQQ, TBT, TMV. Cross-checked against the Norgate total-return export on the two ETFs that could be loaded: agreement within 2–6 bp/yr.
- **FMP price indexes**: ^GSPC (from 1990), ^NDX (1985-10 → 2023-05-23 in the pull), ^RUT (1990), ^VIX (1990), GCUSD gold spot (1980), SIUSD silver spot (1990-02, used only in the rejected silver test).
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

## 5. Process discipline and where the biases are

1. Phase 0 data audit; Phase 1 proxies + engine + tests; Phase 2 pre-registration of hypotheses H1–H12, parameter grids, gates, cost model and the holdout lock (2016-01-04 → 2026-09-18), written before any trial.
2. Phase 3 development on **1998-01-02 → 2015-12-31 only**: 228 distinct trials, every one logged to `TRIAL_LEDGER.csv`. Baselines: SPY, 60/40, SPY 200-day timing, vol-targeted SPY.
3. Phase 4 freeze (commit `06a6f79`), one-shot holdout guarded by `HOLDOUT_UNLOCKED` + `RAN_ONCE`; deflated Sharpe with the full trial count. → **TALOS v1.**
4. Phase 5: history extension to 1991 on a 1990-start proxy panel (phase P5 in the ledger). Phases 6-7: add-on search and free-rein ideas on 1991-2015 / 2016-2026 (phases P6-P7, 129 + ~200 cells). → **T7 = TALOS v2**, adopted by the client.

Biases to know about, in order of importance:
- **Asset-selection hindsight.** QQQ as the core, gold as a sleeve, and Treasuries as the fallback were chosen knowing how those assets did over 1991-2026. A 1991 investor did not know the Nasdaq 100 would compound at ~13%/yr or that gold would triple after 2005. This is the largest bias and it affects v1 and v2 equally; no backtest on this history can remove it.
- **Component priors.** Trend gates, vol targeting, dual momentum and dip buying were pre-registered because they are known from public research to have worked on this same history. The pre-registration limits fishing inside the session, not the fact that the hypotheses came pre-fitted to the past.
- **Post-holdout selection (v2 only).** The dip, gold, band and 250-day choices were made after the one-shot holdout, with the full record in view, and the "both metrics in both windows" rule was widened once (disclosed) to admit the band and 250-day changes. v2's figures are in-sample.
- **Proxy calibration.** Pre-inception ETF carries and leveraged-fund financing spreads were calibrated on the live overlap, so the proxy eras are fitted to the ETF eras by construction (±1%/yr sensitivity in the ledger).
- **Disclosed v1 deviations:** the core's IEF-fallback overlay was chosen on a best cell; the 2% band was added after seeing 754 trades/yr unbanded; k=3 kept over k=2 to avoid a second best-cell pick.

No file from the Drive `RESEARCH_LIBRARY`, no file with a forbidden name, and no other strategy document on the Drive was opened; only file titles in the Drive root were listed to choose a name that was not taken. No external strategy's rules or returns were looked up.

---

## 6. What was tried and rejected

v1 design (1998-2015): inverse and leveraged-inverse funds (lost money in every cell); drawdown-control overlay (MAR +0.02 for CAGR −0.5%); VIX overlays and short-term reversal; rotation k=2; higher multipliers (all extra CAGR is leverage, MAR falls); cash instead of IEF fallback.
Post-holdout (1991-2015 / 2016-2026): trend-gated bonds in the core's idle cash (gains before 2016 reverse after); fixed-size dip buying (doubles the 2000 drawdown); silver in the metals sleeve (worse than gold in every cell); levered gold via UGL; momentum fallback instead of IEF; sizing on the higher of two vol windows; dropping or halving the rotation sleeve; gold at 20%/40% or a 15% gold vol target; 12% core vol target; 150-day trend. At 2.5x none of the add-ons improves v1 on both metrics.

---

## 7. Behaviour to expect live

- Roughly matches SPY's return at 1.25x with a quarter of SPY's worst drawdown; falls behind buy-and-hold in calm low-vol bull markets (1995-97, 2019, 2021), pulls ahead in bears it can sidestep (2000-02, 2008), and loses in years where equities and bonds fall together with whipsaw trends (v2 at 1.25x: 1994 −2.6%, 2004 −2.0%, 2005 −3.7%, 2015 −5.0%, 2022 −11.8%).
- Three things most likely to break it: (1) a grinding QQQ bear with bonds falling too, because the core's fallback is IEF; (2) a gold bear while equities chop, because the gold sleeve is 30% of capital and gold's proxy era (pre-2004) is the least tested; (3) data/execution drift on marginal gate days, and TQQQ mechanics for the slice of QQQ exposure above 1x (financing spread has drifted more than 1%/yr between halves of its live history).
- Settlement: keep cash in a same-day money fund; on the rare next-day cut, sell only settled shares. About 100 trades and 9 next-day round trips a year at 1.25x; no limited margin needed.

---

## 8. Daily procedure (live)

1. After the close, refresh adjusted closes for QQQ, SPY, IWM, TLT, IEF, GLD (and the cash fund).
2. Compute Sleeve A (§2.2) and Sleeve C (§2.4) every day; recompute Sleeve B (§2.3) only on the month's last trading day, else carry it.
3. Blend (§2.5) with multiplier 1.25; map to funds.
4. Compare with current holdings; place next-close orders only for funds whose |target − current| > 2% of equity.
In the repo: `python daily_signal.py --holdings holdings.json` prints exactly this (gate state and band levels, dip trigger and boost state, gold sleeve state) after `python src/proxies.py` has been rerun on refreshed data; `--v1` prints TALOS v1.

---

## 9. File map in the repository

`DATA_AUDIT.md`, `PROXY_VALIDATION.md` (+ `reports/proxies/*.png`), `PREREG.md`, `TRIAL_LEDGER.csv`, `RULES.md` (v2 with v1 at the end), `REPORT.md` (sections 1-10 = v1 and its holdout; 11a extension; 11b-11c the v2 search), `daily_signal.py`, `src/` (`data.py`, `proxies.py`, `engine.py`, `metrics.py`, `strategies.py`, `system.py` = v1, `system2.py` = v2 with `PARAMS_T7`, `trials.py`, `run_phase3*.py`, `run_holdout.py`, `run_extension.py`, `run_phase6*.py`, `run_phase7*.py`, `fmp_ingest.py`, `transcript_harvest.py`), `tests/test_engine.py`, `reports/{phase3,holdout,extension,phase6,phase7}/`, `data/proxies/` (frozen 1997 panel, committed), `data/proxies_ext/` (1990 panel, committed), `data/raw/fmp/*.parquet` (not committed; rebuild from FMP as in §3).

---

## Appendix A — TALOS v1 (pre-registered rules, the clean out-of-sample record)

Two sleeves: 70% core, 30% rotation; no gold sleeve. Core: QQQ at `min(1, 0.10/vol20)` of the sleeve while `close > SMA200` (plain gate, no band, no dip boost); otherwise IEF if `close_IEF > SMA200_IEF`, else cash. Rotation exactly as §2.3 with 30% of capital. Blend, multiplier, mapping, band and costs as in §2.5-2.8. Eight parameters: 200, 10%, 20, 126, top-3, 0.70, 2%, multiplier. Design 1998-2015 at 1x: CAGR 8.5%, Sharpe 0.64, MaxDD −15.5%, MAR 0.55. Locked holdout 2016-2026 at 1x: 11.8%, 0.93, −14.4%, 0.82 (deflated-Sharpe probability vs the best-of-228-trials null: 0.89). Full 1998-2026: 9.7%, 0.75, −15.5%, 0.63. Frontier: 2.5x gives 14.6% at −25.6% (MAR 0.57); 3.0x is the cap (15.6%, −27.9%). Differences v2 − v1: gate band 1%, trend 250 instead of 200, dip boost, 30% gold sleeve, multiplier 1.25.
