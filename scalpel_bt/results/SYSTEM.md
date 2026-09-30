# The system: "Buy Fear" (P2A) — quick rundown

## Rules (ES or MES, long only)

1. **After the 17:00 ET close**, compute the session's IBS = (close - low) / (high - low), using the full ES session
   (18:00-17:00 ET, as TradingView draws the daily bar).
2. **Signal:** IBS < 0.30 (closed in the bottom 30% of the day's range) **and** today's VIX close > 20,
   and you are not already in a P2A trade.
3. **Entry:** buy at the 18:00 ET open.
4. **Exit:** sell at the 18:00 ET open five sessions later. No stop, no target.

It trades about 11 times a year on average, clustered in volatile markets: 35 trades in 2022, none in 2017.
It is in the market about 22% of the time.

## How it has done (1 ES contract, net of 0.6 pt per round trip)

| Test | Trades | Win | Avg trade | Profit factor | Notes |
|---|---|---|---|---|---|
| ES 2013-2019 (where it was found) | 42 | 76% | +27.5 pt | 3.64 | |
| **ES 2020-2026 (frozen, then tested once)** | 111 | 66% | **+29.9 pt (+$1,495; +$150 per MES)** | 1.82 | every year positive; 90% of buy-and-hold's points with a third of the market time and half the drawdown |
| **SPY 1994-2012 (older data, never used to build it)** | 326 | - | +0.55% | - | includes the 2000-02 and 2008 bear markets |
| **7 untouched markets 1997-2026** (QQQ, IWM, DIA, EFA, Germany, Japan, UK) | 2,739 | 59% | **+0.54%** | 1.46 | positive in all 7 markets and all 4 decades; CI above zero even with month clustering |

ES 2013-2026 in full: 153 trades, 69% winners, +29.2 pt average, profit factor 2.0. Every year with trades was
positive (13 of 13). Maximum drawdown was -603 pt per ES contract.

## Risk

- **No stop by design.** In the research every stop *lowered* the return, because stops cut exactly the trades that
  were about to snap back.
- The price is occasional large losses:
  - worst trade -11.6% (-584 pt on ES, entered 30 March 2025 before the tariff crash);
  - 1st percentile -9.3%;
  - 5th percentile -4.3%.
- **Size so that a -12% move against you is survivable.** For example, 1 MES per $25-35k of account (about $3,000
  per MES in a -600 pt trade).
- It buys into falling, fearful markets. Expect trades to feel wrong at entry.

## Knobs the research supports (development data only, not re-tested on the untouched markets)

- **Exit on strength:** sell at the first close above the prior session's high (max 10 sessions) instead of after 5.
  Slightly lower return per trade (+0.53% vs +0.62%) but the best risk-adjusted P2A exit. Trades average about 4
  sessions.
- **Stricter fear gate:** VIX > 25 raises the average trade (+0.85% vs +0.62%) with half as many trades.
  The whole IBS 0.1-0.3 x VIX 20-25 region works: it is a plateau, not a lucky point.
- **Uptrend filter:** requiring the 50-day average above the 200-day lifts the average trade to +0.69% (PF 2.0),
  with fewer trades.
- **High volume day:** SPY volume > 1.2x its 50-day average lifts the average trade to +0.74%, with half the trades.
- **Avoid:** tight profit targets (0.5-1.5 ATR), and holding much longer than 5-10 sessions (the extra return is just
  market drift).

## The alternative ("new take", P3B)

- **Rule:** a composite oversold score > 0.90, hold 5 sessions, **no VIX needed**. The score averages IBS, RSI(2),
  the 3-day drop and the distance below the 5-day average, each ranked against the past year.
- **Record:** confirmed on the 7 untouched markets (+0.56% per trade, PF 1.56).
- **But its edge faded after 2020** (+0.10% per trade across those markets), while P2A's did not. Use it as a
  secondary signal, not a replacement.

## What did not work

- The Scalpel levels themselves (no edge versus randomly shifted levels).
- Plain trend-following and momentum.
- Overnight-only longs.
- Buying VIX spikes alone.
- Every option structure (modeled only).

## See it on the chart

`pine/docs_buyfear_systems_es.pine`: add it to a 1h-1D `ES1!` chart. It shades every P2A trade (and optionally the
others), labels P&L and shows running stats. Setup notes are in `pine/README.md`.
