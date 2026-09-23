# crypto/flow/PREREG_FLOW.md: Phase 3 pre-registration, order flow, positioning, book depth, footprint, real funding

Written 2026-09-23 before any Phase 3 backtest. Committed before the first row of `crypto/flow/TRIAL_LEDGER.csv`. So far, the Phase 3 data has only been checked for coverage and file formats. One data comparison was run: Phase 2's reconstructed funding against the real Binance prints, now available. It showed the reconstruction was biased low: 2024-06 to 2026-08, real funding averaged 0.4 to 10 points a year higher (for example, ETH 5.0% real vs 1.9% reconstructed), with correlation 0.49 to 0.85. That comparison uses no forward price returns. It is why real-funding carry is re-tested below.

**The brief.** Using Binance's own archive (taker flow, positioning, book depth, tick trades, real funding), find something positive-EV that trades several times a week across several major coins and could help fund the Phase 1 trend basket.

## 0. Data (Binance public archive `data.binance.vision`, USD-M perps, read through its S3 origin)

| Set | Content | Coins | Period |
|---|---|---|---|
| klines 15m | OHLCV, trade count, **taker (aggressive) buy volume**. Aggressive sell = volume minus taker buy | U16: BTC ETH SOL XRP DOGE BNB ADA AVAX LINK LTC DOT TRX BCH SUI NEAR APT | 2022-01-01 to 2026-09-22 (SUI from 2023-05, APT from 2022-10) |
| metrics 5m -> 15m | open interest, top-trader long/short **position** ratio, top-trader **account** ratio, global **account** long/short ratio, taker buy/sell volume ratio | U16 | 2022-01-01 to 2026-09-22 |
| funding | actual funding prints with interval (8h, some 4h) | U16 | 2022-01 to 2026-08 |
| bookDepth -> 15m | resting (passive) bid vs ask notional within ±1%, ±2%, ±5% of mid | BOOK5: BTC ETH SOL XRP DOGE | 2023-01-01 to 2026-09-22 |
| aggTrades -> 1h footprint | per hour: aggressive buy and sell volume in the bottom 20% and top 20% of the hour's price range, and the point-of-control position | FOOT3: BTC ETH SOL | 2024-01-01 to 2026-09-22 |

All research uses **1h bars**, aggregated from 15m (flow is summed; metrics and book take the last or mean value in the hour).

## 1. Fixed protocol

| Item | Setting |
|---|---|
| Split | design to 2024-12-31 (klines, metrics, funding from 2022-01; book depth from 2023-01; footprint 2024 only); holdout 2025-01-01 to 2026-09-22 |
| Contamination, disclosed | Phase 1 and 2 holdouts covered Oct 2025 to Sep 2026 (dip-buying and OI-flush longs lost there), and Phase 2's design covered Jun 2024 to Sep 2025 with OI and premium signals. No OI or premium family is re-tested here. The Phase 3 families use data never looked at before (taker flow, positioning ratios, book depth, footprint). Carry is the exception: it is re-tested on real funding because the Phase 2 input was wrong |
| Lock | `crypto/flow/src/flow_research.py` refuses windows past 2024-12-31 until `crypto/flow/HOLDOUT_UNLOCKED` exists. The holdout runs once |
| Execution | signal on the close of 1h bar t, fill at the open of t+1, exit at the open of t+1+H; delay check +1 bar |
| Costs | perp taker 5 bp plus slippage (BTC and ETH 1 bp; SOL XRP DOGE BNB 2 bp; others 3 bp) per side. Carry spot leg: 10 bp plus Phase 1 spot slippage |
| Funding | actual prints, applied to positions open across each settlement time |
| Frequency | the reference cell must average at least 3 trades a week, pooled, in the design window |

Definitions (1h bars; each z-score uses the 168 prior bars, one week):
- delta = 2 x taker_buy - volume; **imb** = delta / volume; **imb_z** = z(imb).
- **r_z** = return / stdev(return, 168 prior).
- **flow4** = sum(delta, last 4 bars) / sum(volume, last 4 bars); **flow4_z** = z(flow4).
- **CVD** = cumulative delta.
- **spread_z** = z(log top-trader position ratio) - z(log global account ratio).
- **glob_z** = z(log global account ratio).
- **book_z** = z(hourly mean of the ±1% bid-ask notional imbalance).
- **sellbot_z** = z(aggressive sell volume in the bottom 20% of the hour's range / hour volume); **buytop_z** likewise for aggressive buys in the top 20%; **CLV** = (2 close - high - low) / (high - low).

## 2. Hypotheses

| ID | Idea | Long | Short | Grid | Reference |
|---|---|---|---|---|---|
| F1 absorption | heavy aggressive selling that fails to push price down means passive buyers are absorbing it | imb_z <= -k and bar return >= 0 | imb_z >= k and return <= 0 | k {2, 3} x H {1, 4, 12, 24} x side | k 2, H 4 |
| F2 flow exhaustion | extreme aggressive flow together with an extreme move marks forced exits, which revert | imb_z <= -k and r_z <= -k | imb_z >= k and r_z >= k | k {2, 3} x H {1, 4, 12, 24} x side | k 2, H 4 |
| F3 flow continuation | sustained aggressive buying is informed and continues | flow4_z >= k | flow4_z <= -k | k {1.5, 2.5} x H {1, 4, 12, 24} x side | k 1.5, H 4 |
| F4 CVD divergence | a new price low while CVD holds above its low marks hidden aggressive buying | close < min(close, N prior) and CVD > min(CVD, N prior) | mirror at highs | N {24, 72} x H {1, 4, 12, 24} x side | N 24, H 4 |
| F5 smart vs retail | top traders' positioning, measured against retail accounts, is informed | spread_z >= s | spread_z <= -s | s {1.5, 2.5} x H {4, 12, 24, 48} x side | s 1.5, H 12 |
| F6 retail contrarian | an unusually one-sided retail account ratio is wrong on average | glob_z <= -g | glob_z >= g | g {1.5, 2.5} x H {4, 12, 24, 48} x side | g 1.5, H 12 |
| F7 passive book | an unusually bid-heavy resting book supports price | book_z >= b | book_z <= -b | b {1.5, 2.5} x H {1, 4, 12, 24} x side; BOOK5 | b 1.5, H 4 |
| F8 footprint absorption | heavy aggressive selling at the hour's lows with a close in the upper half is absorption (mirror at highs) | sellbot_z >= f and CLV >= 0 | buytop_z >= f and CLV <= 0 | f {1.5, 2.5} x H {1, 4, 12, 24} x side; FOOT3 | f 1.5, H 4 |
| P5R real-funding carry | the Phase 2 P5 rule on real prints: spot-long / perp-short a coin while its trailing 3-day mean funding (per 8h) >= θ; exit below θ/2 | | | θ {0.01%, 0.02%, 0.03%}; U16 | θ 0.01% |

Cells: F1-F8 16 each = 128, plus P5R 3 = 131, plus delay and cost rows.

## 3. Pass rules

**Events F1-F8, design window, reference cell, base costs.** E1 to E8, exactly as in `crypto/perp/PREREG_PERP.md`:
- E1: mean net > 0 with day-clustered t >= 2.
- E2: positive in at least 3 of 4 horizons.
- E3: excess over drift > 0.
- E4: breadth >= 60% of symbols with 5+ trades.
- E5: one bar late keeps >= 50% and stays > 0.
- E6: 2x costs > 0.
- E7: at least 30 trades.
- E8: at least 3 trades a week.

**P5R, design 2022-2024.** Annualised return on capital >= 3%, Sharpe >= 2, max drawdown no deeper than -3%; at 2x costs, return > 0.

**Holdout, once, for families that pass only.**
- Events: mean net > 0, t >= 1.0, breadth >= 50%.
- Carry: return > 0 and Sharpe >= 1.

Nothing that fails is deployed. A family that passes goes to a paper bot first.
