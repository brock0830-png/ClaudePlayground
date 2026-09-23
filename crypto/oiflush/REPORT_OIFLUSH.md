# crypto/oiflush/REPORT_OIFLUSH.md: independent replication of OI Flush Signals v2

Protocol: `crypto/oiflush/PREREG_OIFLUSH.md` (commit `6807eae`, written before any run). Code: `src/replicate.py`. Tables: `reports/`.

Data: Binance USD-M perps, 1h, 2022-01-01 to 2026-09-22, with real 5-minute open interest and real funding. Costs: taker fee 5 bp plus 1-3 bp slippage per side, and funding.

## Verdict against the pre-registered checks: 7 of 8 pass

| Check | Result |
|---|---|
| O1 net per trade > 0 in 2022-23 and 2024-26 | **pass**: +0.32% and +0.55% (gross +0.46% and +0.71%) |
| O2 full-period weekly-P&L t >= 2 | **pass**: 2.27 (the day-clustered t is 3.0 and 3.2 by period, 4.4 overall) |
| O3 excess over the unconditional 24h long return > 0 | **pass**: +0.43% and +0.63% |
| O4 entry one hour late | **pass**: +0.23% and +0.49% |
| O5 parameter neighbourhood (72 cells: price, OI, hold) | **pass**: every cell is positive in both periods; medians +0.40% and +0.46% |
| O6 7 coins the other thread never reported (BNB DOT TRX BCH SUI NEAR APT) | **pass**: +0.43% and +0.50% per trade |
| O7 at a 20 bp round trip | **pass**: +0.27% and +0.50% (at 30 bp: +0.17% and +0.40%) |
| O8 capped portfolio (at most 5 open, 20% each): Sharpe >= 1 and max DD shallower than -25% | **fail**: Sharpe 0.81, max DD -40.9%, CAGR 23.6% |

This is the first short-horizon signal in this repository that replicates on independent data. It holds in both periods and in every nearby setting. It also holds on coins it was never built on, entered late, and after costs. The other thread's figures reproduce: +0.42% and +0.51% there; +0.32% and +0.55% net here, with the same per-coin pattern.

It fails as a standalone book. Signals bunch up in crashes, so a full book of dump-buying longs takes large drawdowns (2022 lost money).

## Where the edge comes from (exploratory, not pre-registered)

- **Open interest is the active ingredient.** 24h price dumps alone make +0.12% and +0.21% per trade. OI drops alone make -0.07% and +0.02%. The combination makes +0.32% and +0.55%. The bounce comes after forced deleveraging, not after any dump.
- **Profit is concentrated but not only outliers.** The best single day was 2022-05-12 (LUNA). Without the top 5 days it still makes +0.28% per trade, and without the top 10, +0.18%. The median day-average is +0.54%.
- **The edge is shrinking.** Net per trade by year: 2022 -0.13%, 2023 +1.06%, 2024 +0.85%, 2025 +0.46%, 2026 to date +0.09% (208 trades). The 2024-26 average leans on 2024.
- **Per coin** (my data, net, 2022-23 / 2024-26):

| Coin | 2022-23 | 2024-26 |
|---|---|---|
| ADA | +1.28% | +0.71% |
| AVAX | +0.67% | +0.79% |
| SOL | +0.13% | +1.11% |
| BTC | -0.19% | +1.05% |
| XRP | +0.39% | +0.65% |
| LINK | +0.52% | +0.47% |
| DOGE | +0.69% | +0.25% |
| LTC | -0.64% | +0.31% |
| ETH | -0.76% | -0.11% |

  ETH is negative in both periods, matching the other thread. As it said, single-coin numbers are noisy.
- **Size tiers.** Net per trade by tier, 2022-23 / 2024-26:

| Tier | 2022-23 | 2024-26 |
|---|---|---|
| 1x | +0.16% | +0.31% |
| 1.5x | +0.11% | +0.35% |
| 2x (OI -6% or deeper) | +0.66% | +1.42% |

  Only the deepest tier is clearly better, and it was chosen with both periods in view. Sizing up by tier raises the book's Sharpe (0.81 to 0.99) but deepens the drawdown (-41% to -59%). Using the tier as a priority when the position cap binds is safer than using it as leverage.
- **Alt/BTC mode** (long alt, short BTC, 30m): +0.71% and +1.19% net per trade, about 3 trades a week, day-clustered t 2.0 and 2.9. It still makes +0.51% and +1.05% entered 30 minutes late. The 2x tier (OI -8.4% or deeper) does better in both periods (+1.06% vs +0.58%, and +2.39% vs +0.92%).

## As a sleeve next to the trend basket (exploratory)

Daily returns, 2022-01 to 2026-09:

| Book | CAGR | Sharpe | Max DD |
|---|---|---|---|
| OI flush, at most 5 open x 20% | 23.6% | 0.81 | -40.9% |
| OI flush, 5 x 10% | 12.8% | 0.81 | -21.0% |
| Trend basket (Phase 1) | 25.4% | 0.81 | -39.5% |
| 70% trend + 30% flush | 27.8% | 1.02 | -34.0% |
| 50% trend + 50% flush | 28.0% | 1.09 | -33.5% |

The daily correlation between the two books is 0.10. The trend basket sits in cash during crashes, which is exactly when the flush book buys. That combination, rather than the flush book alone, is the interesting result. It is in-sample and was not pre-registered.

## What this means

- The rule has a real, replicable per-trade edge after realistic costs. It is the first such result in about 100 families tested here.
- It is not a smooth money-maker on its own. Expect losing stretches when dumps keep dumping (as in 2022), and treat the 2025-26 decay as a live risk.
- There is no untouched data left: both periods were used by the other thread, and both are now used here. The honest next step is a **paper forward test** at modest size (about 10% per position, at most 5 open), ideally run next to the trend basket, with the costs actually paid on Kraken measured per coin.
