# crypto/flow/REPORT_FLOW.md: Phase 3, order flow, positioning, book depth, footprint and real-funding carry

Protocol: `crypto/flow/PREREG_FLOW.md` (commit `0853b8c`, before any backtest). Engine `ffab181`, freeze `7d87086`. Numbers are read from `crypto/flow/TRIAL_LEDGER.csv` and `crypto/flow/reports/`.

Data comes from Binance's public archive (data.binance.vision, read through its S3 origin), for USD-M perps:
- 15m klines with taker (aggressive) buy volume, 16 coins, 2022-01 to 2026-09.
- 5-min open interest, top-trader and global long/short ratios.
- Real funding prints.
- Order-book depth at ±1-5%: BTC ETH SOL XRP DOGE, 2023 on.
- Tick-level aggTrades condensed into hourly footprints: BTC ETH SOL, 2024 on. The footprint volume matches the kline volume exactly.

Costs: perp taker fee 5 bp plus 1-3 bp slippage per side, and real funding.

## Verdict

**Nothing passed, with the best available data.** None of 32 order-flow, positioning, book-depth or footprint families passed the design stage (2022-2024), and neither did carry on real funding. The declared near-misses lost money on the holdout (2025-01 to 2026-09).

## Design results (1h bars, bp per trade after costs and funding)

| Family | Idea | Trades/week | Gross | Net | Day-clustered t | Result |
|---|---|---|---|---|---|---|
| F1 absorption, long / short | heavy aggressive selling (buying) while price holds | 5.3 / 4.7 | -1 / -11 | -16 / -27 | -3.1 / -4.0 | fail |
| F2 flow exhaustion | extreme aggressive flow plus an extreme move, faded | 5.4 / 5.0 | +5 / -21 | -10 / -35 | -0.5 / -2.8 | fail |
| F3 flow continuation | 4h aggressive-flow surge, followed | 88 / 89 | +3 / -3 | -12 / -18 | -9.3 / -10.1 | fail |
| F4 CVD divergence | new price low while CVD holds (and mirror) | 48 / 98 | +5 / 0 | -10 / -15 | +4.7 / +3.9 | fail (mean < 0) |
| F5 smart vs retail, long / short | top traders long relative to retail accounts | 48 / 44 | +27 / -2 | **+11** / -17 | -2.0 / -6.3 | fail |
| F6 retail contrarian, long / short | fade an unusually one-sided retail account ratio | 42 / 40 | +24 / +7 | **+9** / -7 | -3.7 / -6.6 | fail |
| F7 passive book imbalance | bid-heavy resting book within 1% of mid | 31 / 29 | +6 / -12 | -8 / -24 | -0.8 / -4.9 | fail |
| F8 footprint absorption | heavy aggressive selling at the hour's low with a close in the upper half (and mirror at highs) | 8.8 / 7.4 | -2 / -12 | -15 / -24 | -1.2 / -2.6 | fail |
| P5R carry on real funding, θ 0.01% | spot long / perp short while funding is elevated | 1.7 entries | | **2.3%/yr on capital, Sharpe 4.9, max DD -0.8%** | | fail (below the 3%/yr bar) |

The non-reference cells are in `reports/design_events.csv`. The best were F6 at g 2.5 long (+31 bp) and F5 at s 2.5 long (+20 bp).

**What the numbers say:**
1. **Aggressive order flow has essentially no predictive power at 1h and beyond.** Across absorption, exhaustion, continuation and CVD divergence, the reference cells' gross edges run -21 to +5 bp, and the frequent families sit within ±5 bp. Taker round trips cost 12-16 bp, so everything loses. Whatever information taker flow carries is priced within the hour.
2. **Passive book imbalance and footprint absorption add nothing either.** Gross is near zero or negative.
3. **Positioning is the only family with a consistent long-side tilt.** Top traders long against retail, or retail unusually short, earns +9 to +31 bp per trade, positive on 69-94% of coins. But it fails the day-clustered test: the gains come from a few market-wide days. It is also long-only in a period (2023-2024) when longs were paid.
4. **Carry works as arithmetic but is small, and it faded.** 2022-2024 real funding gave 2.3%/yr on capital at Sharpe 4.9. In 2025-2026 funding roughly halved (BTC from about 8%/yr to about 4%/yr annualised), and the trailing 3-day mean never reached 0.02% per 8h on any coin.

## Holdout, information only (declared in `FREEZE.json`; nothing here could be deployed)

| | Trades/week | Net per trade | t | Win % | Breadth |
|---|---|---|---|---|---|
| F5 smart vs retail long (s 2.5) | 31.8 | -8 bp | -3.7 | 47% | 38% |
| F6 retail contrarian long (g 2.5) | 13.1 | -7 bp | -2.3 | 45% | 38% |
| P5R carry θ 0.02% (declared) | 0 entries | 0% | | | |
| P5R carry θ 0.01% (extra look, added after the declared row returned no entries) | 1.1 entries | -0.5%/yr, Sharpe -2.6 | | | |

## Deviations and fixes

- The footprint condenser was rewritten in pyarrow/numpy mid-download, for speed. It matches the pandas reference to 1e-12 on a real BTC day.
- The carry holdout got one extra, disclosed look at θ 0.01%, because the declared θ 0.02% row had no entries.
- This phase found that Phase 2's funding reconstruction was biased low. `crypto/perp/REPORT_PERP.md` is corrected.

## Bottom line across all three phases

About 100 pre-registered short-horizon signal families were tested on 15m to 4h bars, using price, volume, your TD/Z and SigmaJanus indicators, open interest, funding, OBV, taker flow, positioning ratios, order-book depth and tick footprints. Every one lost money after costs out of sample, or never passed its design stage. The daily trend basket from Phase 1 is still the only rule with a clean pass.
