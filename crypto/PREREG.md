# crypto/PREREG.md: pre-registered hypotheses, grids and pass/fail rules for the crypto bots

Written 2026-09-23 before any crypto strategy backtest was run, and committed before the first row of `crypto/TRIAL_LEDGER.csv`. Up to this point the only things looked at were file headers, bar counts, date ranges and how often each column of the client's CSV exports is non-zero (for example, the TDZ confluence buy flag is set on 23 of 30,265 SOLBTC 30m bars). No forward returns were computed. Anything not written here that later shapes the design is a deviation, and REPORT.md logs it as one.

The client's brief: find a positive-EV signal that can be traded repeatedly by small bots, starting from their two indicators (TD Sequential + Z-score confluence, and SigmaJanus RSI re-risk), and adding price action, volume or CVD as needed. Then deploy it.

**Amendment v1 (2026-09-23, still before any backtest; the ledger does not exist yet).** A parity check of `crypto/src/indicators.py` against the client's CSV columns found that the exported `scr_conf_buy`/`scr_conf_sell` is not the Pine script the client pasted. It is a TD 9, 13-consecutive or countdown-13 bar that occurs while close is at least 3%, 4% and 5% below (buy) or above (sell) EMA 50, 100 and 200 (`scr_stack_dn`/`scr_stack_up`), with no z-score condition. The exported countdown is DeMark's, with recycle and no bar-8 qualifier. My code reproduces every signal column of all three exports bar for bar (z, 9s, 13s, countdowns, z_hi/z_lo, stacks, confluence). The export version is added to H1 as variant V6, and V5 uses the recycle countdown. H1 grows from 100 to 120 cells. Nothing else changes.

## 0. Fixed protocol

| Item | Setting |
|---|---|
| Data | TradingView Binance spot bars pulled 2026-09-23 (`crypto/data/tv`), plus the client's exports (`crypto/data/user`). Daily: 28 USDT pairs, 2017-08 to 2026-09-22, plus ETHBTC. 4h: 12 USDT pairs + ETHBTC, SOLBTC, AVAXBTC, 2024-06-12 to 2026-09-23. 1h: 9 USDT pairs, 2026-02-27 to 2026-09-23. Client: SOLBTC 30m and AVAXBTC 30m from 2025-01-01, ETHBTC 15m from 2026-02-01 |
| Daily universe | BTC ETH BNB XRP ADA DOGE SOL LINK AVAX DOT LTC TRX BCH ATOM NEAR ETC XLM FIL UNI NEO XTZ ALGO IOTA ZEC DASH VET QTUM HBAR (all vs USDT). It includes several coins that are down 80-99% from their peaks (NEO, IOTA, QTUM, XTZ, DASH, ALGO, FIL, DOT). It is still survivorship-biased: coins delisted outright (LUNA, FTT, EOS and others) are missing because TradingView no longer serves them. A coin is eligible from 200 days after its first bar |
| Design / holdout split | **Daily:** design 2018-01-01 to 2023-12-31, holdout 2024-01-01 to 2026-09-22. **All intraday (4h, 30m):** design up to 2025-09-30, holdout 2025-10-01 onward. **1h and ETHBTC 15m are holdout-only** confirmation sets: they fall inside the intraday holdout period and are never used for design. Indicators may warm up on bars before a window starts |
| Holdout lock | `crypto/src/research.py` refuses any evaluation that reaches past the design end until `crypto/HOLDOUT_UNLOCKED` exists. That file is created only at the freeze commit, and the holdout is run once |
| Execution | Signal uses bars through the close of bar t. Fill at the open of bar t+1. A holding period of H bars exits at the open of bar t+1+H. Robustness check: one extra bar of delay on entry and exit |
| Costs, per side | Exchange fee 10 bp (Binance spot VIP0 taker; similar at OKX and Bybit spot) plus slippage and half-spread: BTCUSDT and ETHUSDT 2 bp, other USDT pairs 4 bp, BTC-quoted pairs (ETHBTC, SOLBTC, AVAXBTC) 5 bp, and the thinner daily-universe coins (ATOM NEAR ETC XLM FIL UNI NEO XTZ ALGO IOTA ZEC DASH VET QTUM HBAR) 6 bp. "Other USDT pairs" means BNB XRP SOL DOGE ADA LINK AVAX LTC TRX BCH DOT. A base round trip is therefore 24 to 32 bp. Stress checks: 2x costs, and a "US retail" fee of 40 bp per side (Kraken Pro taker at the lowest tier) for the finalists |
| Short side | Spot bots cannot short USDT pairs. Short-side results on USDT pairs are reported for information, and they assume a perpetual future with 5 bp taker fee plus 1 bp funding per 8h held. On BTC-quoted pairs, "short" means holding BTC instead of the alt. That is a spot rotation, costed like a long trade |
| Trial ledger | Every evaluated cell, including baselines, failures and robustness checks, appends one row to `crypto/TRIAL_LEDGER.csv`. The count feeds the deflated Sharpe ratio of any finalist |
| Annualisation | 365 days a year. Risk-free rate 0 |

## 1. Event hypotheses (a signal opens one fixed-length trade)

A trade opens on a signal bar only if no trade from the same family is already open on that symbol (no pyramiding). Metrics, pooled across symbols in a dataset group: trade count; mean gross and net return per trade; median; win rate; profit factor; t-statistic of the mean net return, clustered by entry calendar day (trades starting on the same UTC day are averaged into one observation first); and **excess**, meaning mean gross trade return minus the unconditional mean H-bar return of the same symbols over the same window, averaged over trades. Excess separates signal from market drift.

Dataset groups: **G30** = the client's SOLBTC and AVAXBTC 30m; **G4h** = the 15 4h symbols; **GD** = the 28 daily coins (used only by H2 and H4). The confirmation-only sets **C1h** (9 symbols, 1h) and **C15** (ETHBTC 15m) are used at the holdout stage only.

### H1. TD Sequential + Z-score confluence (the client's TDZ indicator)

Rationale: exhaustion counts at statistical extremes should mean-revert. The client's code, verbatim, gives the base variant: setup counts of consecutive closes above or below close[4]; a signal when the count is exactly 9 or exactly 13 and the 20-bar z-score of close reached ±2.5 within the last 4 bars. Buy = long, sell = short.

| Variant | Definition |
|---|---|
| V1 client | as above (z length 20, threshold 2.5, lookback 4, "13" = 13 consecutive) |
| V2 looser z | V1 with threshold 2.0 |
| V3 TD only | setup count exactly 9 or 13, no z condition (ablation) |
| V4 Z only | z-score crosses beyond ±2.5 on this bar, no TD condition (ablation) |
| V5 countdown | DeMark buy/sell countdown 13 (after a completed 9 setup, count bars with close <= low[2] for buys or close >= high[2] for sells, cancelled by an opposite completed setup, restarted by a new same-side setup) with the z condition of V1 |
| V6 export | the client's exported confluence: TD 9, 13-consecutive or countdown 13, while the EMA 50/100/200 stack is stretched by at least 3%/4%/5% in the signal's direction |

Grid: variant (6) x holding H in {4, 8, 16, 32 bars, "z-exit" = exit at the first open after z crosses 0, capped at 32 bars} x side {long, short} x group {G30, G4h}. 120 cells. **Reference cell: H = 8.**

### H2. SigmaJanus re-risk (the client's RSI indicator)

Fast = RSI(8) of WMA(7, close). Signal: Fast < OS, Fast > Fast[1] and Fast[1] <= Fast[2] (the client's code). Long only. Grid: OS in {15 (client), 20} x H in {4, 8, 16, 32} x group {G30, G4h, GD}. 24 cells. Reference cell: OS 15, H 8. The indicator's author claims shallower forward drawdowns after the signal. That claim is also reported descriptively (mean worst low over the next H bars, signal vs unconditional), but it is not a pass criterion.

### H3. Capitulation reversal (price action + volume + CVD proxy)

Rationale: forced selling (liquidation cascades) overshoots, and a high-volume flush bar that closes off its lows marks absorption. Definitions: bar return r_t = close/close[1] - 1; return z = r_t / stdev(r, 50 bars before t); relative volume = volume / median(volume, 50 bars before t). CVD proxy: the close-location value CLV = (2*close - high - low)/(high - low), times volume. TradingView bars have no taker buy/sell split, so true CVD is unavailable. CLV only approximates the sign of bar delta, and REPORT.md says so. Signal: return z <= -k and relative volume >= 2, and, when the CLV filter is on, CLV >= 0 (close in the upper half of the bar). Long only.

Grid: k in {2.5, 3.0} x CLV filter {off, on} x H in {3, 6, 12, 24} x group {G30, G4h, GD}. 48 cells. Reference cell: k 3.0, CLV on, H 6.

### Pass criteria for event families

A family is a (hypothesis, variant, side, group) combination. It passes the design stage only if all of E1 to E7 hold at base costs on the design window:

- **E1 edge.** Reference-cell pooled mean net return > 0, with day-clustered t >= 2.0.
- **E2 horizon neighbourhood.** Mean net return > 0 in at least 3 of the 4 fixed horizons.
- **E3 not drift.** Reference-cell excess > 0.
- **E4 breadth.** Mean net return > 0 in at least 60% of the symbols that have 5 or more trades (checked only when 3 or more symbols qualify; for G30 both symbols must be positive).
- **E5 delay.** With one extra bar of delay, reference-cell mean net return > 0 and at least 50% of the base value.
- **E6 costs.** Reference-cell mean net return > 0 at 2x costs.
- **E7 sample.** At least 30 pooled trades in the reference cell.

A family that passes every criterion except E1's t-threshold (so its mean net return is still > 0) is labelled "promising, not significant". It is not eligible for live deployment.

**Holdout for event families** (families that pass only, reference cell, run once): pooled mean net return > 0 with t >= 1.0 on the intraday holdout, and breadth of at least 50% of symbols. It is repeated on C1h, and on C15 for H1 on BTC pairs. A failure on C1h is reported but does not veto, because 1h is a different bar length.

## 2. Portfolio hypotheses (daily, long or flat spot, 28-coin universe)

Each eligible coin gets an equal slot of capital (1 / number of eligible coins, rebalanced when eligibility changes or once a month, whichever comes first). The slot is either fully in the coin or in USDT (earning 0). Weights are decided at the daily close and filled at the next daily open. Benchmarks: **BM1** equal-weight buy and hold of the eligible universe, rebalanced monthly; **BM2** BTC buy and hold; **BM3** BTC long above its 100-day SMA, else flat.

### H4. Time-series trend, per coin

Rationale: time-series momentum is the best-documented anomaly in crypto, and large crypto drawdowns happen mostly below the long-term trend. Rules: (a) SMA filter: hold the coin while close > SMA(N). (b) Donchian: enter when close makes an N-day high, exit when close makes an N/2-day low. Option **BTC gate**: an alt (not BTC itself) may be held only while BTC's close > BTC's SMA(100).

Grid: {SMA N in 20, 50, 100, 200; Donchian N in 20, 50, 100} x BTC gate {off, on}. 14 cells.

### H5. Cross-sectional momentum

Every Sunday close, rank the eligible coins by L-day return and hold the top k in equal weight (the full book is split across k slots). Option: **absolute gate**, under which a selected coin with a negative L-day return is replaced by USDT. Grid: L in {14, 28, 56} x k in {3, 5} x gate {off, on}. 12 cells.

### Pass criteria for portfolio families (design window 2018-2023, base costs)

The cell deployed from a family is the one with the highest design Sharpe among cells that individually meet P1, provided its grid neighbours along N (or along L) also meet P1. It is not the headline number by itself: the neighbourhood median is always reported next to it.

- **P1 edge.** Sharpe >= BM1 Sharpe + 0.20, and max drawdown <= 0.75 x BM1 max drawdown.
- **P2 neighbourhood.** The median Sharpe across the family's grid >= BM1 Sharpe + 0.10, and at least two thirds of cells beat BM1's Sharpe.
- **P3 delay.** With one extra day of delay, the selected cell keeps at least 70% of its Sharpe excess over BM1.
- **P4 sub-period removal.** With each of 2018, 2019-2020, 2021 and 2022-2023 removed in turn, the selected cell's Sharpe >= BM1's Sharpe on the same reduced window.
- **P5 costs.** At 2x costs the selected cell still meets P1.

**Holdout for portfolio families (run once):** CAGR > 0; Sharpe >= BM1 holdout Sharpe; max drawdown <= BM1 holdout max drawdown. BM2 and BM3 are reported next to it. Beating BTC is not required, because BTC is one coin and the universe is 28, but the shortfall is reported.

## 3. What happens after the holdout

- Only families that pass the design stage and the holdout are eligible for live trading. The bot ships with those, in **paper mode by default**. Live mode requires the client to supply exchange API keys and to flip a flag.
- If no family passes, the report says so. The bot ships with the best design-stage candidate in paper mode only, as a forward test, clearly labelled as unproven.
- Post-holdout ideas (combinations, filters, new parameters) go in a separate exploratory section of the ledger, and are in-sample by construction. They can only be promoted after a fresh forward-test period.
- The deflated Sharpe ratio of each portfolio finalist is computed with the total ledger count at the freeze.

## 4. Planned cell count

H1 120 + H2 24 + H3 48 + H4 14 + H5 12 = 218 design cells, plus delay, cost, sub-period and benchmark rows. Every row is ledgered.
