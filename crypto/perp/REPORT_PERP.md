# crypto/perp/REPORT_PERP.md: Phase 2, perp signals from open interest, funding and OBV

Protocol: `crypto/perp/PREREG_PERP.md` (commit `c4ba92a`, before any backtest). Freeze `65ae0b7`. Numbers are read from `crypto/perp/TRIAL_LEDGER.csv` and `crypto/perp/reports/`. Costs: perp taker fee 5 bp plus 1-3 bp slippage per side, plus funding reconstructed from Binance's premium index and charged at 00/08/16 UTC.

## Verdict

**Nothing passed.** None of the 28 directional families built on open interest, funding/premium or OBV passed the design stage (Jun 2024 to Sep 2025), and neither did funding carry. The best near-misses also lost money on the holdout (Oct 2025 to Sep 2026). None of this can responsibly fund the trend basket.

## Design results (reference cell of each hypothesis; bp per trade, after costs and funding)

| Family | Trades/week | Gross | Net | Day-clustered t | Win % | 1 bar late | Why it fails |
|---|---|---|---|---|---|---|---|
| P1 OI flush, long (price dump + OI collapse) | 4.2 | +73 | +61 | 0.8 | 60% | -26 | edge is one bar long; the top 5 days make 160% of the profit |
| P1 OI flush, short (squeeze + OI collapse) | 2.5 | -168 | -183 | -2.3 | 40% | -181 | fading squeezes loses |
| P2 crowding fade, long (prem low + OI building) | 3.5 | +49 | +37 | -0.5 | 60% | -3 | not significant, delay-fragile |
| P2 crowding fade, short (prem high + OI building) | 6.5 | -36 | -48 | -1.0 | 50% | -38 | loses |
| P3 OI-confirmed breakout, long (N 20) | 22.7 | +41 | +24 | -1.9 | 50% | +17 | median trade -31 bp; profit comes from a few market-wide rally days |
| P3 same, OI filter off (ablation) | 29.3 | +42 | +25 | -2.1 | 50% | +18 | the OI filter adds nothing |
| P3 OI-confirmed breakout, short | 15.8 | +27 | +10 | -3.1 | 50% | +12 | not significant |
| P4 OBV divergence, long / short | 13-17 | -32 / -50 | -45 / -63 | 0.6 / -0.7 | 50% | <0 | loses |
| P5 funding carry, θ 0.01% | 2.0 entries | | 0.15%/yr on capital, Sharpe 0.52 | | | | funding was too low in 2024-25 to pay four legs of fees |
| P5 funding carry, θ 0.02% (best cell) | 0.3 entries | | 0.93%/yr, Sharpe 5.2, max DD -0.1% | | | | steady but tiny, below the 3%/yr bar |

All 28 families and every horizon are in `reports/design_events.csv`.

**The recurring pattern.** Liquidation flushes and breakouts hit all 16 coins on the same few days. Counted per trade, several signals look good (the OI-flush long has naive t 2.4). Counted per independent day, which is what the pre-registration requires, they are noise. In practice that means a bot running them would make most of its money on two or three days a year and bleed on the rest.

## Holdout, information only (declared at the freeze; nothing here could be deployed)

| | Trades/week | Net per trade | t | Win % |
|---|---|---|---|---|
| P1 OI flush long, 4h, 16 coins | 5.0 | -19 bp | -1.7 | 44% |
| P1 same, 1h, 9 coins | 13.0 | -19 bp | -0.4 | 45% |
| P3 OI breakout long (N 60), 4h | 10.4 | +5 bp | -1.1 | 45% |
| P3 same, 1h | 15.4 | -11 bp | -1.8 | 41% |
| P5 carry θ 0.02% | 8 entries in the year | 0.06%/yr, Sharpe 0.82 | | |

## What was not tested, and why

- **Aggressive vs passive flow (taker buy/sell), CVD, footprint.** These need Binance taker volume or tick trades from `data.binance.vision`, which this environment's network policy blocks. With that host allowed, they can be tested the same way. Temper expectations, though: order-flow edges in the literature live at seconds-to-minutes horizons and usually need maker (passive) execution. After taker fees, they are the hardest place for a retail bot to win.
- **Actual funding prints.** Funding is rebuilt from the premium index with Binance's formula. It has not been checked against real prints, for the same network reason. A bias in either direction would not change the verdict: carry was below the bar with any plausible bias, and funding moves directional P&L by only a few bp per trade.

## Honest bottom line for the brief

Every higher-frequency idea tried across both phases lost money after costs: 6 TDZ variants, SigmaJanus, capitulation buying, OI flushes, crowding fades, OI breakouts, OBV divergences and carry. That covers 70 signal families on 30m, 1h and 4h bars. The one thing that held up is the slow daily trend basket.

If the aim is to put the basket's idle cash to work, its backtest sat in stablecoins about 65% of the time. Any yield on that cash adds roughly 0.65 x the yield per year (for example, about +2.6%/yr at 4%). That is a treasury decision with counterparty risk (exchange earn products, tokenised T-bills), not a trading edge, and it was not backtested here.
