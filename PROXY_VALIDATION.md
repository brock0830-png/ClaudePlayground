# PROXY_VALIDATION.md

All series are daily total-return on the SPY trading calendar from 1997-01-02. Live ETF data is FMP dividend-adjusted closes (validated against Norgate total-return closes in DATA_AUDIT.md). Suffix `_X` denotes a spliced series: the live ETF from its first trading day, the proxy before that. Charts are in `reports/proxies/`; each shows growth of 1 for actual versus proxy over the overlap (top, log scale) and the cumulative ratio actual/proxy minus 1 (bottom).

## Method

- Equity and gold: price-index daily return plus a constant carry, calibrated as the mean daily gap between the ETF total return and the index over the first five years of overlap (the regime nearest the pre-inception years). S&P 500 uses `^GSPC`, Nasdaq-100 uses `NDX`, Russell 2000 uses `^RUT`, gold uses front-month gold futures `GCUSD`.
- Treasuries: constant-maturity par-bond total return from the FMP daily Treasury curve (same data as FRED DGS). Each day the par bond bought at yesterday's yield is revalued at today's yield with maturity M, plus accrued coupon, minus the ETF expense ratio. The (yield, M) pair with the lowest tracking error over the 2002-07 to 2007-06 overlap was chosen from three candidates per fund; all candidates are listed in `data/proxies/meta.json`.
- Cash: 3-month CMT yield / 252 until BIL lists on 2007-05-30, then BIL daily total return plus its expense ratio / 252. Over the 22 overlapping days the two agree to within 0.4%/yr annualised, which is inside the noise of such a short window.
- Leveraged ETFs: `L x base return - (L-1) x (cash + spread) - expense ratio / 252`, with the spread calibrated so the mean daily return matches the live fund over its whole history. Two honesty checks are reported: the geometric drift after full-sample calibration (near zero by construction, the brief's 1%/yr criterion), and the change in implied spread between the first and second halves of the live history, which is what an out-of-sample calibration would have missed.

## Equity and gold proxies

| ETF | Proxy | Live from | Tracking error (ann.) | Split-half drift (ann.) | Used |
|---|---|---|---|---|---|
| SPY | GSPC + carry | 1997-01-03 | 3.26% | -0.02% | yes |
| QQQ | NDX + carry | 1999-03-11 | 5.16% | +1.33% | yes |
| IWM | RUT + carry | 2000-05-30 | 3.55% | +0.05% | yes |
| GLD | GCUSD + carry | 2004-11-19 | 8.88% | -0.24% | yes |

Carry values (annual): SPY +1.46% (full-overlap +1.72%), QQQ -0.37% (full-overlap +0.55%), IWM +1.19% (full-overlap +1.21%), GLD -0.28% (full-overlap -0.50%).

The Nasdaq-100 carry moved from about -0.1%/yr in the first half of the QQQ history to +1.2%/yr in the second half as index dividend yields rose; the early-window calibration (-0.4%/yr) is the right one for the 1997-1999 proxy segment, which is only 14 months long. Gold and Russell carries are stable across halves. The SPY proxy is not used (SPY is live from 1993) and is shown only to demonstrate the method on a long overlap.

## Treasury proxies

| ETF | Proxy | Live from | Tracking error (ann.) | Drift (ann.) | Used |
|---|---|---|---|---|---|
| TLT | par bond y20 M=20.0 | 2002-07-31 | 2.84% | +0.04% | yes |
| IEF | par bond y7 M=7.0 | 2002-07-31 | 1.87% | +0.87% | yes |
| SHY | par bond y2 M=1.9 | 2002-07-31 | 0.75% | +0.24% | yes |

Candidate comparison (tracking error, drift, beta of live on proxy):

- TLT: y20 M=20.0: TE 2.84%, drift +0.04%, beta 0.96, corr 0.96
- TLT: y20 M=25.0: TE 3.29%, drift -0.17%, beta 0.85, corr 0.96
- TLT: y30 M=30.0: TE 11.92%, drift -7.98%, beta 0.31, corr 0.62
- IEF: y7 M=7.0: TE 1.87%, drift +0.87%, beta 1.02, corr 0.95
- IEF: y10 M=8.5: TE 1.94%, drift +0.26%, beta 0.94, corr 0.95
- IEF: y10 M=10.0: TE 2.29%, drift +0.29%, beta 0.82, corr 0.95
- SHY: y2 M=2.0: TE 0.78%, drift +0.29%, beta 0.79, corr 0.89
- SHY: y2 M=1.9: TE 0.75%, drift +0.24%, beta 0.83, corr 0.89
- SHY: y1 M=1.0: TE 1.12%, drift +0.16%, beta 2.09, corr 0.78

The 30-year CMT is missing from 2002-02 to 2006-02 (the Treasury stopped issuing), so TLT uses the 20-year yield. IEF's proxy carries a +0.87%/yr drift versus the live fund over the overlap, which is a limitation of a single-point constant-maturity approximation of a 7-to-10-year ladder; it is used only for the 1997 to 2002-07 segment and flagged here. The SHY proxy has beta 0.83, meaning the 2-year par bond is a little more volatile than the 1-3 year ladder; its tracking error is under 0.8%/yr.

## Simulated leveraged ETFs

| Fund | Base | L | ER | Spread (full) | Spread 1st half | Spread 2nd half | TE (ann.) | Geometric drift after calibration | Split-half drift | Corr | Live from | Passes 1% rule | Split-half > 1% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SSO | SPY | 2 | 0.89% | -0.17% | -0.74% | +0.40% | 4.7% | +0.23% | -1.14% | 0.993 | 2006-06-22 | yes | yes |
| UPRO | SPY | 3 | 0.91% | +0.66% | +0.49% | +0.83% | 3.7% | +0.05% | -0.69% | 0.997 | 2009-06-26 | yes | no |
| SPXL | SPY | 3 | 0.91% | +0.78% | +0.72% | +0.84% | 4.6% | +0.39% | -0.24% | 0.997 | 2008-11-06 | yes | no |
| QLD | QQQ | 2 | 0.95% | +0.49% | +0.32% | +0.66% | 5.1% | -0.01% | -0.34% | 0.993 | 2006-11-02 | yes | no |
| TQQQ | QQQ | 3 | 0.84% | +0.74% | +0.41% | +1.06% | 4.1% | +0.47% | -1.30% | 0.998 | 2010-02-12 | yes | yes |
| UBT | TLT | 2 | 0.95% | -0.28% | -0.41% | -0.15% | 5.2% | +0.13% | -0.26% | 0.985 | 2010-01-22 | yes | no |
| TMF | TLT | 3 | 1.06% | +0.55% | +0.65% | +0.46% | 3.7% | +0.10% | +0.37% | 0.997 | 2009-04-17 | yes | no |
| UST | IEF | 2 | 0.95% | -0.33% | -0.35% | -0.32% | 3.1% | +0.02% | -0.02% | 0.972 | 2010-01-25 | yes | no |
| UGL | GLD | 2 | 0.95% | +1.52% | +1.23% | +1.82% | 2.8% | -0.06% | -0.59% | 0.997 | 2008-12-04 | yes | no |

All nine simulated funds pass the brief's criterion (geometric drift within 1%/yr after calibrating the financing spread on the live history). Two of them, SSO and TQQQ, have an implied spread that shifted by more than 1%/yr between the halves of their live history (SSO -0.74% to +0.40%, TQQQ +0.41% to +1.06%), so a spread calibrated on one half would have drifted by about 1.1 to 1.3%/yr on the other. This is the honest uncertainty on the pre-inception simulated segments (1997 to 2006 for 2x, 1997 to 2009/2010 for 3x). Phase 3 therefore reports every leveraged result with a sensitivity of plus and minus 1%/yr of extra drag on the simulated segments. Correlations of 0.97 to 0.998 and tracking errors of 3 to 5%/yr are consistent with daily-rebalanced funds whose intraday and financing details are not modelled.

## Series availability

| Series | First date | Note |
|---|---|---|
| CASH | 1997-01-02 | 3m CMT then BIL |
| SPY | 1997-01-03 | live only |
| QQQ | 1999-03-11 | live only |
| IWM | 2000-05-30 | live only |
| DIA | 1998-01-21 | live only |
| TLT | 2002-07-31 | live only |
| IEF | 2002-07-31 | live only |
| SHY | 2002-07-31 | live only |
| GLD | 2004-11-19 | live only |
| SLV | 2006-11-02 | live only |
| DBC | 2006-11-02 | live only |
| USO | 2006-11-02 | live only |
| EDV | 2007-12-14 | live only |
| BIL | 2007-05-31 | live only |
| SHV | 2007-01-12 | live only |
| QQQ_X | 1997-01-03 | NDX proxy before 1999-03-11 |
| IWM_X | 1997-01-03 | RUT proxy before 2000-05-30 |
| SPY_X | 1997-01-03 | GSPC proxy before 1997-01-03 (unused) |
| GLD_X | 1997-01-03 | GCUSD proxy before 2004-11-19 |
| TLT_X | 1997-01-03 | par bond proxy before 2002-07-31 |
| IEF_X | 1997-01-03 | par bond proxy before 2002-07-31 |
| SHY_X | 1997-01-03 | par bond proxy before 2002-07-31 |
| SSO_X | 1997-01-03 | simulated before live start |
| UPRO_X | 1997-01-03 | simulated before live start |
| SPXL_X | 1997-01-03 | simulated before live start |
| QLD_X | 1997-01-03 | simulated before live start |
| TQQQ_X | 1997-01-03 | simulated before live start |
| UBT_X | 1997-01-03 | simulated before live start |
| TMF_X | 1997-01-03 | simulated before live start |
| UST_X | 1997-01-03 | simulated before live start |
| UGL_X | 1997-01-03 | simulated before live start |

## Charts

![SPY](reports/proxies/SPY.png)
![QQQ](reports/proxies/QQQ.png)
![IWM](reports/proxies/IWM.png)
![GLD](reports/proxies/GLD.png)
![TLT](reports/proxies/TLT.png)
![IEF](reports/proxies/IEF.png)
![SHY](reports/proxies/SHY.png)
![SSO](reports/proxies/SSO.png)
![UPRO](reports/proxies/UPRO.png)
![SPXL](reports/proxies/SPXL.png)
![QLD](reports/proxies/QLD.png)
![TQQQ](reports/proxies/TQQQ.png)
![UBT](reports/proxies/UBT.png)
![TMF](reports/proxies/TMF.png)
![UST](reports/proxies/UST.png)
![UGL](reports/proxies/UGL.png)
