# PREREG.md — pre-registered hypotheses, grids and pass/fail rules

Written 2026-09-19 before any strategy backtest was run. Committed before the first entry in `TRIAL_LEDGER.csv`. Anything not written here that later influences the design is a deviation and will be logged as such in REPORT.md.

**Amendment v2 (2026-09-19, still before any trial):** the client clarified that long positions in inverse and leveraged-inverse ETFs are permitted, and restated the objective as CAGR at least 15% with MAR at least 1.0 (stretch 1.25). Inverse funds were added to the instrument set and simulated exactly like the leveraged funds (negative L, collateral earns the cash rate); their validation is in PROXY_VALIDATION.md. Hypotheses H1, H3 and H6 gained one grid dimension, the "bear side": what is held when the trend gate is off. The ledger was empty when this amendment was committed.

## 0. Fixed protocol

| Item | Setting |
|---|---|
| Design window | 1998-01-02 to 2015-12-31 (signals warm up from 1997-01-02) |
| Locked holdout | 2016-01-04 to 2026-09-18, run once after the design is frozen and committed |
| Data | `data/proxies/returns.parquet`: FMP dividend-adjusted ETFs spliced to proxies (PROXY_VALIDATION.md) |
| Execution | Signal from data through close of day t, fill at close of day t+1 (engine lag 2). Same-close (lag 1) is a sensitivity only. One-extra-day delay (lag 3) is a required robustness check |
| Costs (1x) | 2 bp commission plus half spread per trade: SPY 0.5 bp, QQQ 0.5, IWM 1, TLT 1, IEF 1, SHY 0.5, GLD 1, BIL 0.5. Leveraged ETFs: (2 bp + 1 bp) doubled = 6 bp. Reported at 0x, 1x, 3x |
| Account | $1M cash IRA, long-only, no borrowing, weights sum to at most 1, cash sleeve earns the CASH series |
| Instruments allowed | SPY_X, QQQ_X, IWM_X, TLT_X, IEF_X, SHY_X, GLD_X, CASH; leveraged SSO_X, UPRO_X, QLD_X, TQQQ_X, UBT_X, TMF_X, UST_X, UGL_X; inverse SH_X (-1x SPY), SDS_X (-2x), SPXU_X (-3x), PSQ_X (-1x QQQ), QID_X (-2x), SQQQ_X (-3x), TBT_X (-2x TLT), TMV_X (-3x TLT). Signals may also use VIX level and the Treasury curve. Excluded: DBC, USO, SLV, DIA, EDV, SPXL (no pre-2006 history or redundant), all VIX ETPs |
| Leveraged-ETF caveat | Pre-inception segments are simulated. Every leveraged or inverse result is reported with +/-1%/yr extra drag on simulated segments. Inverse funds held during rising markets lose money by construction; no hypothesis holds them unconditionally |
| Complexity budget | At most 8 free parameters in the final system. A "free parameter" is any number a reader could change; fixed conventions like 252 trading days do not count |
| Trial ledger | Every backtest run, including baselines, failures and robustness cells, appends one row to `TRIAL_LEDGER.csv`. The final count feeds the deflated Sharpe ratio |
| Objective stated by the client | CAGR at least 15% and MAR (CAGR / max drawdown) at least 1.0, stretch 1.25. At 15% CAGR that means a max drawdown of 15% (stretch 12%). I record here, before testing, that this is a demanding target across 1998-2015 including 2000-02 and 2008, and that reporting a shortfall is an acceptable outcome. The frontier at 15%, 25% and 35% drawdown is reported regardless |

## 1. Baselines (every candidate is compared against all four)

| Baseline | Rule | Parameters |
|---|---|---|
| B1 SPY buy and hold | 100% SPY_X | 0 |
| B2 60/40 | 60% SPY_X, 40% IEF_X, rebalanced at month end | 0 |
| B3 SPY 200-day filter | 100% SPY_X when close > 200-day simple moving average of close, else CASH; evaluated daily | 1 |
| B4 Vol-targeted SPY | weight = min(1, 10% / realised 20-day vol) in SPY_X, rest CASH; also a 1.5x-capped variant using SSO_X for the excess | 2 |

The "simple timing baseline" the brief refers to is B3. A candidate that does not beat B3 on Sharpe and MAR at 1x costs is a fail regardless of CAGR.

## 2. Pass/fail criteria (applied on the design window only)

A hypothesis passes only if all of P1 to P5 hold at engine lag 2 and 1x costs:

- **P1 Edge.** Net Sharpe at least 0.10 above the better of B3 and B4, and MAR at least 1.25 times the better of B3 and B4.
- **P2 Neighbourhood.** Across the pre-registered grid, the median cell satisfies Sharpe at or above the better baseline Sharpe, and at least two thirds of cells beat B1's Sharpe. The best cell is never reported alone.
- **P3 Delay.** With one extra day of delay (lag 3), the cell keeps at least 70% of its excess Sharpe over the better baseline.
- **P4 Sub-period removal.** Removing each of 1998-2002, 2003-2007, 2008-2009, 2010-2015 in turn, Sharpe stays at or above the better baseline computed on the same reduced window.
- **P5 Costs.** At 3x costs Sharpe stays at or above the better baseline at 1x costs.

Metrics for P1 to P5 are always the neighbourhood-median cell unless a single cell is named in advance below. Turnover and the count of consecutive-day round trips are recorded for every run to answer the T+1 settlement question.

## 3. Hypotheses (12, the cap)

Each lists economic rationale, exact rule family, grid, and how it is judged. Grids are deliberately small; total planned cells are counted at the end.

**H1 Equity trend filter.** Rationale: time-series momentum and the tendency of large drawdowns to occur below long-term averages. Rule: hold 100% of E when close(E) > SMA(N) of close(E), else the bear side. E in {SPY_X, QQQ_X}. Grid: N in {100, 150, 200, 250}, bear side in {CASH, -1x fund of E, -2x fund of E}. 24 cells. This is B3 generalised; it passes only if some version beats B3 by the P1 margin at the neighbourhood median.

**H2 Equity volatility targeting.** Rationale: volatility clusters and realised vol forecasts next-day vol far better than returns; scaling exposure inversely to vol raises Sharpe and cuts left tail. Rule: w = min(cap, target / vol_N) where vol_N is the annualised standard deviation of the last N daily returns of E; exposure above 1 is obtained with the 2x fund of E (SSO_X or QLD_X) so that w in (1, 2] means (2 - w) in E and (w - 1) in the 2x fund. E in {SPY_X, QQQ_X}. Grid: target in {10%, 15%}, N in {20, 60}, cap in {1, 2}. 16 cells.

**H3 Trend gate times vol target (core "Tiger-like" candidate).** Rationale: H1 removes bear-market exposure, H2 sizes the remainder; the two signals are weakly correlated. Rule: w = H2 weight if H1 condition true, else the bear side sized by the same vol target (bear exposure = min(1, target / vol_N) in the -1x fund, or 0 for CASH). Grid: E in {SPY_X, QQQ_X}, N_trend in {150, 200}, target in {10%, 15%}, N_vol = 20 fixed, cap in {1.5, 2}, bear side in {CASH, -1x}. 32 cells.

**H4 Buy-the-dip with leverage ("Whale-like" candidate).** Rationale: short-horizon reversal in index returns after sharp pullbacks inside an uptrend; leverage applied only at the dip. Rule: base exposure 1.0 in E while close > SMA(200); when close is at least D% below its 20-day high and above SMA(200), add the 3x fund so that total exposure is L; remove the add-on when close makes a new 20-day high or falls below SMA(200). Below SMA(200): CASH. E in {SPY_X, QQQ_X}. Grid: D in {3, 5, 8}, L in {2, 3}. 12 cells.

**H5 Cross-asset momentum rotation.** Rationale: 6-12 month cross-sectional momentum across asset classes with an absolute-momentum gate. Rule: universe {SPY_X, QQQ_X, IWM_X, TLT_X, GLD_X}; each month end rank by total return over the last M days; hold the top k equally weighted, but any asset whose M-day return is below CASH's M-day return is replaced by CASH. Grid: M in {126, 252}, k in {1, 2, 3}. 6 cells.

**H6 Trend-gated inverse-vol multi-asset with vol target.** Rationale: risk parity across stocks, long bonds and gold gives diversification; a per-asset trend gate removes the 2022-style failure when all three fall; a portfolio vol target stabilises risk. Rule: assets {SPY_X, TLT_X, GLD_X}; asset i gets raw weight 1/vol_i(N) if close_i > SMA(N_trend) else 0; weights normalised to sum 1 then scaled by min(cap, target / portfolio_vol) where portfolio vol is from the last N days of the weighted return; exposure above 1 uses the 2x funds (SSO_X, UBT_X, UGL_X). Bear side: when an equity or bond asset is below its trend, its raw weight is either 0 (CASH) or the same 1/vol weight in the -1x fund (SH_X for SPY; for TLT the -2x fund TBT_X at half weight, since no -1x Treasury fund has history; gold has no inverse and stays 0). Grid: N_trend in {150, 200}, target in {9%, 12%}, cap in {1.5, 2}, bear side in {CASH, inverse}. 16 cells. N = 60 fixed.

**H7 Drawdown control overlay.** Rationale: the client's archetype includes a drawdown control; cutting exposure after losses caps the tail at the cost of slower recovery. Rule: overlay on the median cell of H3 and H6: multiply exposure by 0.5 when the strategy's own equity is more than D below its running peak, restore when within D/2 of the peak. Grid: D in {5%, 10%}. 4 cells. Judged by MAR change and by whether CAGR falls by less than the drawdown falls.

**H8 VIX regime filter.** Rationale: implied volatility above its recent average marks stress regimes with negative skew. Rule: overlay on the median cell of H3: exposure multiplied by 0.5 when VIX > SMA(50) of VIX and VIX > V. Grid: V in {20, 25}. 2 cells.

**H9 Bonds instead of cash.** Rationale: when the equity gate is off, a trend-gated Treasury position has historically earned more than bills with negative equity correlation. Rule: in the median H3 cell, replace CASH with TLT_X (or IEF_X) whenever that bond's close > SMA(200), else CASH. Grid: bond in {TLT_X, IEF_X}. 2 cells.

**H10 Short-term mean reversion.** Rationale: post-1990s indices show 1-5 day reversal after consecutive down closes. Rule: when E is above SMA(200) and has closed down for c consecutive days, buy E (or its 2x fund) and exit after the first up close or after 5 days. Grid: c in {2, 3}, fund in {1x, 2x}. 8 cells across E in {SPY_X, QQQ_X}. Turnover and consecutive-day round trips are the main thing this tests.

**H11 Gold trend sleeve.** Rationale: gold trends and is uncorrelated with equities; as a satellite it may raise MAR. Rule: 20% of equity held in GLD_X when GLD_X close > SMA(N), else in CASH, alongside 80% in the median H3 cell. Grid: N in {150, 200}. 2 cells.

**H12 Blend.** Rationale: the client's Tiger archetype is a multi-strategy blend. Rule: fixed-weight blend of the median H3 cell and the median H5 cell, plus H7 overlay at its better D. Grid: weight on H3 in {50%, 70%}. 2 cells. Passes only if MAR beats every component.

Planned cells: 24 + 16 + 32 + 12 + 6 + 16 + 4 + 2 + 2 + 8 + 2 + 2 = 126, plus 5 baselines, plus robustness runs (lag 3, sub-period removal, 3x costs, 0x costs) on passing hypotheses. Expected ledger size: about 200 to 350 rows.

## 4. Selection and frontier

1. Among hypotheses that pass P1 to P5, the final system is the one with the highest design-window MAR at the neighbourhood-median cell, subject to at most 8 free parameters. Ties go to fewer parameters and lower turnover.
2. The frontier at max drawdown tolerances of 15%, 25% and 35% is built by changing only the exposure cap of the final system (and nothing else) until the design-window max drawdown is just under each tolerance. The CAGR difference between frontier points is then attributable to leverage alone, and that is how "how much is just leverage" will be answered.
3. Freeze: RULES.md and the parameter values are committed. The holdout is run once by `src/run_holdout.py` and the commit hash of the freeze is recorded in REPORT.md. If the holdout is run a second time for any reason, REPORT.md will say so and label the result contaminated.

## 5. What I will not do

- No parameter added after seeing design-window results except through a new, numbered, logged hypothesis (H13+), which would exceed the cap and be reported as a deviation.
- No look at any holdout-period statistic of any candidate before the freeze. Proxy validation charts already include post-2016 data for the live ETFs; that is instrument data, not strategy performance, and is unavoidable.
- No machine learning, no optimiser beyond the listed grids.
