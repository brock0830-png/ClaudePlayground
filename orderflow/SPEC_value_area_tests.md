# Order-flow tests on the OI-flush signal: value area (POC / VAH / VAL)

Pre-registered. Write these rules into the repo and commit **before** running anything.
Do not add, drop, or re-define features after seeing results.

## Background (already done in the claude.ai thread)

- Base signal: USD-mode OI flush on 1h Binance USDT perps: 24h price change <= -4.6% and
  24h OI change <= -1.8%. Entry next bar open, 24h hold, net of 0.14% round trip + funding.
- On the 9 Kraken coins (BTC ETH SOL XRP ADA LINK DOGE LTC AVAX): 1,968 signals.
  Net per trade: +0.42% in 2022-23, +0.51% in 2024-26.
- Footprint test already run with `footprint_test.py` / `fp_analyze.py`. Four features
  (trapped sellers, absorption, thin low, stacked sell imbalances) **all failed**.
  "Trapped sellers" was worse in BOTH periods (t = -1.7). Its reversed version is tested
  below on unseen coins only.

## Data

Build everything from Binance futures aggTrades (free, no key):
`https://data.binance.vision/data/futures/um/daily/aggTrades/{SYM}/{SYM}-aggTrades-{YYYY-MM-DD}.zip`
Columns: agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time,
is_buyer_maker (true = aggressive SELL). Cache the coin-days you download; they get reused.
Use only trades up to the signal bar's close for features (no lookahead).

## Profiles

Rows = 50 equal price rows spanning each profile's range. Value area = 70% of volume,
built by expanding outward from the POC one row at a time toward the higher-volume side.

- **P0 (pre-flush value):** the 24 hourly bars ending 6 hours before the signal bar closes.
- **P1 (flush window):** the 6 hourly bars ending at the signal bar's close.
- ATR = ATR(14) on 1h bars at the signal bar.

## Features (direction fixed now)

| ID | Definition | Good side |
|---|---|---|
| V1 value reclaim | signal close >= VAL of P1 (binary) | 1 |
| V2 room to prior value | (POC0 - signal close) / ATR | higher (top third) |
| V3 value migration | (POC0 - POC1) / ATR | lower (bottom third) = lower prices were rejected, not accepted |
| F1r selling spread out (reversed trapped sellers) | share of P1 aggressive-sell volume in the bottom 10% of P1's range (0 if close is still in that zone) | lower (bottom third) |

Exit test (one variant only):
| X1 | take profit with a limit at POC0 if hit within 24h, otherwise exit at 24h. Compare daily-P&L Sharpe and total return with the plain 24h exit. |

## Universes and pass rule

- **Dev:** the 9 Kraken coins, reported separately for 2022-23 and 2024-26.
  Tercile cutoffs are set on dev 2022-23 signals only.
- **Holdout (decisive):** the 26 coins never used for order-flow work:
  AAVE UNI FIL ETC BCH ICP APT ARB OP SUI INJ SEI TIA WIF 1000PEPE 1000SHIB FET XLM HBAR ALGO
  SAND MANA AXS GALA CRV LDO (USDT perps), all dates 2022-01 to 2026-08, same frozen cutoffs.
- F1r is judged on the holdout ONLY (its direction was chosen after seeing dev results).

A feature PASSES only if:
1. good-minus-bad > 0 in dev 2022-23 AND dev 2024-26 (except F1r), AND
2. on the holdout, good-minus-bad > 0 with day-clustered t >= 2.5
   (signals on the same calendar day averaged into one observation).

X1 passes if its daily Sharpe beats the 24h exit on dev 2022-23, dev 2024-26 AND holdout.

Report every feature, pass or fail, in one table with n per cell.
A fail means the flush signal stays as it is. That is an acceptable outcome.

## Notes

- Memory: stream files with a bounded prefetch (<= 8 in flight). Loading everything at
  once ran out of memory in the first attempt.
- Expect roughly 2 coin-days per signal (29h lookback). The holdout will be the bigger download.
- If anything passes, the live version can use TradingView `request.footprint()`
  (Premium), which exposes POC / VAH / VAL per bar.
