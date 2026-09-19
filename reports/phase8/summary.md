# Phase 8: base-substitution test (is the rule set sound, or was it riding the US wave?)

Same rules, fifteen bases, each judged against its own buy-and-hold over its own live ETF history (start = first print + 260 trading days of warm-up, end 2026-09-18; live data only, no proxies; costs 2 bp + 1 bp half spread; a 3x-cost row is in `base_substitution.csv`). "Engine" = the v2 core alone (250-day gate with 1% band, 10% vol target, 10-day-low dip boost, IEF fallback) run on the base at 100% of capital, unlevered. "Engine, vol target = base vol" removes the vol throttle (target set to the base's own realised vol) so the comparison is at the base's own risk budget. "Full v2 1.25x" swaps the base into the core and keeps the rotation and gold sleeves, so it is less clean (the rotation still holds SPY/QQQ/IWM). Ledger phase P8.

| Base | Market | From | B&H CAGR / MaxDD / MAR / Sharpe | Engine (v2 core, 1x) CAGR / MaxDD / MAR / Sharpe | Engine, vol target = base vol | Full v2 1.25x CAGR / MaxDD / MAR |
|---|---|---|---|---|---|---|
| SPY | S&P 500 | 1994-02-09 | 10.9% / -55.2% / 0.20 / 0.51 | 10.3% / -19.3% / 0.53 / 0.70 | 11.3% / -22.1% / 0.51 / 0.70 | 9.8% / -14.8% / 0.66 |
| QQQ | Nasdaq 100 | 2000-03-21 | 7.9% / -83.0% / 0.10 / 0.35 | 10.2% / -22.6% / 0.45 / 0.69 | 11.6% / -30.0% / 0.39 / 0.64 | 10.7% / -14.0% / 0.76 |
| DIA | Dow 30 | 1999-02-02 | 8.6% / -51.9% / 0.17 / 0.43 | 7.1% / -17.3% / 0.41 / 0.51 | 7.4% / -20.8% / 0.36 / 0.49 | 8.4% / -15.6% / 0.54 |
| IWM | Russell 2000 | 2001-06-11 | 8.5% / -59.0% / 0.14 / 0.39 | 7.1% / -23.5% / 0.30 / 0.48 | 8.2% / -26.1% / 0.31 / 0.48 | 9.0% / -15.4% / 0.58 |
| XLF | US financials | 2000-01-05 | 6.3% / -82.7% / 0.08 / 0.29 | 5.9% / -21.7% / 0.27 / 0.38 | 6.0% / -33.0% / 0.18 / 0.34 | 8.0% / -16.5% / 0.48 |
| XLE | US energy | 2000-01-05 | 8.7% / -71.3% / 0.12 / 0.37 | 6.9% / -35.8% / 0.19 / 0.44 | 7.8% / -53.9% / 0.15 / 0.39 | 8.7% / -15.8% / 0.55 |
| EFA | Developed ex-US | 2002-09-06 | 7.7% / -61.0% / 0.13 / 0.38 | 7.0% / -17.5% / 0.40 / 0.51 | 8.0% / -19.9% / 0.40 / 0.53 | 8.9% / -13.5% / 0.66 |
| VGK | Europe | 2006-03-23 | 5.8% / -63.6% / 0.09 / 0.29 | 4.3% / -21.2% / 0.20 / 0.28 | 5.8% / -24.5% / 0.24 / 0.35 | 7.4% / -13.6% / 0.55 |
| EWG | Germany | 1997-03-31 | 6.0% / -67.6% / 0.09 / 0.27 | 6.9% / -20.0% / 0.34 / 0.42 | 8.7% / -31.7% / 0.27 / 0.46 | 8.4% / -15.1% / 0.55 |
| EWU | UK | 1997-03-31 | 5.3% / -64.0% / 0.08 / 0.24 | 6.0% / -21.0% / 0.29 / 0.37 | 6.0% / -30.0% / 0.20 / 0.33 | 7.8% / -15.4% / 0.51 |
| EWJ | Japan | 1997-03-31 | 4.1% / -58.9% / 0.07 / 0.19 | 6.0% / -24.5% / 0.25 / 0.37 | 6.2% / -27.6% / 0.23 / 0.34 | 7.6% / -17.2% / 0.44 |
| EEM | Emerging markets | 2004-04-27 | 8.0% / -66.4% / 0.12 / 0.35 | 5.1% / -31.1% / 0.16 / 0.32 | 5.3% / -38.0% / 0.14 / 0.28 | 7.5% / -16.9% / 0.44 |
| FXI | China | 2005-10-20 | 5.1% / -72.7% / 0.07 / 0.26 | 6.0% / -34.9% / 0.17 / 0.40 | 5.0% / -55.4% / 0.09 / 0.26 | 8.7% / -22.5% / 0.39 |
| EWZ | Brazil | 2001-07-27 | 8.1% / -78.1% / 0.10 / 0.35 | 5.1% / -33.6% / 0.15 / 0.31 | 7.5% / -54.8% / 0.14 / 0.35 | 8.1% / -19.8% / 0.41 |
| ILF | Latin America | 2002-11-08 | 10.5% / -67.5% / 0.16 / 0.42 | 6.8% / -25.6% / 0.26 / 0.44 | 8.3% / -45.7% / 0.18 / 0.41 | 9.0% / -18.3% / 0.49 |

## Score, engine vs its own base (15 bases)

- MAR: engine wins 15/15 (median B&H 0.10 vs engine 0.27); with vol target = base vol 15/15; the plain v1 core (SMA200, no band, no dip) 15/15.
- Sharpe: engine wins 12/15 (median 0.35 vs 0.42); loses on VGK, EEM, EWZ.
- CAGR: engine wins 5/15 at the 10% vol target, 6/15 with the vol throttle removed; the v1 core 3/15. Wins on both CAGR and MAR at the 10% target: QQQ, EWG, EWU, EWJ, FXI.
- Full v2 at 1.25x: MAR 15/15, CAGR 9/15.

## Reading

The risk-adjusted result is uniform: on every one of the fifteen bases, US and non-US, bull and dead, the rules cut the worst drawdown to roughly a third of buy-and-hold's and raise MAR. That includes Japan (buy-and-hold 4.1%/yr with a 59% drawdown; engine 6.0% with 24.5%), Germany, the UK and China, where the engine also beats the base on CAGR. That is the evidence that the rule set is not a US-bull artefact: trend gating plus vol targeting works as a drawdown control wherever there are trends and crashes.

The CAGR result is not uniform and should not be over-read either way. A 10% vol target on a 20-30% vol asset holds 35-50% of the sleeve on average, so in strong bull markets (S&P 500, Latin America, Brazil, energy, emerging markets) it cannot keep pace with 100% exposure. Removing the throttle helps CAGR on the big movers (S&P 11.3% vs 10.9%, Nasdaq 11.6% vs 7.9%, Germany 8.7% vs 6.0%) at the cost of deeper drawdowns, but still trails buy-and-hold on the emerging-market bases, where the crashes are fast, the recoveries are V-shaped, and a 250-day gate gets whipsawed. The dip boost also hurts there: the v1 core (no dip boost) has higher MAR than the v2 core on EEM, Brazil, China and Japan, and lower on the US and European bases.

So: the drawdown-control half of the system generalises; the return half depends on the base having persistent trends with slow tops, which US large caps have had. Emerging markets are the weak spot and the honest caveat.
