# crypto/oiflush/PREREG_OIFLUSH.md: independent replication of "OI Flush Signals v2"

Written 2026-09-23 before running anything on this rule. The rule is the client's Pine indicator `crypto/pine/oi_flush_signals_v2.pine`, developed in another thread. That thread reports that the 9 Kraken-listed coins made +0.42% per trade in 2022-23 and +0.51% in 2024-26, about 8 signals a week. It is not said whether those figures are before or after costs. Its size tiers were chosen using both periods.

## Rule under test (taken verbatim from the Pine)

- **USD mode, 1h bars, per coin.** Signal when the 24h price change is <= -4.6% and the 24h change in the coin's Binance USDT-perp open interest is <= -1.8%.
  - Long at the next bar's open, exit 24 bars later.
  - One trade per hold window per coin.
  - Tier by 24h OI change: 1x above -3.2%, 1.5x from -3.2% to -6.0%, 2x at -6.0% or deeper.
- **Alt/BTC mode, 30m bars on ALT/BTC.** Signal when close is at least 3%, 4% and 5% below EMA50, EMA100 and EMA200, and the alt perp's 24h OI change is <= -3.1%.
  - Long the alt and short BTC, equal notional, for 24h.
  - Tier: 2x at OI <= -8.4%.

## Data

Binance USD-M perps from the public archive, 2022-01-01 to 2026-09-22. That means 1h bars aggregated from 15m klines, OI as the last 5-minute print in each bar, and real funding prints. ALT/BTC is built as ALTUSDT perp / BTCUSDT perp on 30m bars.

The client's 9 coins are BTC ETH SOL XRP ADA LINK DOGE LTC AVAX. The 7 Binance majors the other thread did not report are BNB DOT TRX BCH SUI NEAR APT. They form a **cross-sectional out-of-sample set**. ATOM has no perp data here and is omitted.

## Costs

- **Base:** perp taker fee 5 bp plus 1-3 bp slippage per side, plus real funding (longs pay, shorts receive).
- **Stress:** 20 bp round trip, the other thread's own ceiling; and 30 bp.

## What is reported

For each period (2022-23, 2024-26, full):
- trades, trades a week, mean gross, mean net, win rate;
- day-clustered t, and t of weekly P&L sums;
- excess over the unconditional 24h long return of the same coins;
- a one-hour-late entry;
- a parameter neighbourhood (24h price -3/-4/-4.6/-5/-6/-7% x 24h OI -1/-1.8/-2.5/-3.5% x hold 12/24/48h);
- tier monotonicity;
- a capped portfolio (at most 5 open positions, 1/5 of equity each, deepest OI first when the cap binds).

## Pass rules, fixed now

The rule is worth paper trading only if all of the following hold for the 9-coin USD mode:

- **O1:** mean net per trade > 0 in both 2022-23 and 2024-26 at base costs.
- **O2:** full-period weekly-P&L t >= 2.0.
- **O3:** excess over drift > 0 in both periods.
- **O4:** one hour late keeps mean net > 0 in both periods.
- **O5:** the neighbourhood median mean net is > 0 in both periods.
- **O6:** the 7-coin cross-sectional set has mean net > 0 over the full period.
- **O7:** mean net > 0 in both periods at 20 bp round trip.
- **O8:** the capped portfolio has a full-period Sharpe >= 1.0, and its max drawdown is no deeper than -25%.

Alt/BTC mode is reported against the same checks, with costs on both legs.

This test has no untouched holdout: the other thread already used 2024-26 to set its size tiers. A pass would therefore mean "worth a paper forward test", not "proven".
