# TradingView indicators for the researched systems

Two Pine v5 indicators. They draw every trade of each system whose out-of-sample profit factor was above 1.
The trading logic of both was replayed bar by bar in Python and matches the research engines on ES 2013-2026:

| System | Script | Trades, Pine logic vs research |
|---|---|---|
| P2A IBS < 0.30 & VIX > 20, hold 5 **(confirmed)** | `docs_buyfear_systems_es.pine` | 153 / 153 identical |
| P3B oversold score > 0.90, hold 5 **(confirmed; weaker since 2020)** | same | 111 / 111 |
| P3A P2A stacked, max 3 units **(confirmed)** | same | 314 / 314 |
| P2C VIX spike, hold 10 (drift only) | same | 71 / 71 |
| P3C 126-session momentum (drift only) | same | 45 / 45 |
| P2B overnight when below the 50-day SMA (drift only) | same (intraday charts) | 965 / 965 |
| C1 weekly GP B In touch (Scalpel levels; no edge vs jittered levels) | `docs_scalpel_level_trades_es.pine` | 223 / 224 |
| C2 weekly GP T In close-through (Scalpel levels; no edge) | same | 316 / 316 |

(`scripts/pine_replica.py`, `scripts/pine_replica_levels.py`. The one C1 difference comes from approximating
TradingView's roll date with "expiration week, Monday 17:00 ET".)

These scripts could not be compiled here, because there is no Pine compiler outside TradingView. If TradingView
reports an error, send it to me.

## Setup

1. Chart `CME_MINI:ES1!` (or `MES1!`), electronic session (the default for futures).
   - `docs_buyfear_systems_es.pine`: any timeframe from 1 hour to 1 day (P2B needs intraday).
   - `docs_scalpel_level_trades_es.pine`: 4-hour chart, like the research.
2. For point P&L that matches the research, turn on back-adjustment of the continuous contract (chart settings >
   Symbol > adjust for contract changes). Without it, trades held through a quarterly roll include the roll gap
   (up to 75 points in 2024). Entry and exit times are the same either way.
3. Add the indicator from the Pine editor.
   - The first script enables only the confirmed systems by default; tick the others in the settings.
   - The table (top right) shows trades, win rate, profit factor, net and average points for the history on your
     chart.

## What you will see

- **Shading** while a trade is open (one colour per system; P3A gets darker with each extra unit).
- **A triangle** at each entry bar.
- **A box** from entry to exit (green if the trade won after costs, red if it lost).
- **A label** with the net points.
- Turn on "Entry labels with IBS / VIX / score used" to see the inputs behind each signal.

## Checking against the research

`expected_trades_es.csv` and `expected_trades_levels_es.csv` list every research trade (entry and exit bar times,
ET, and net points on the switch-adjusted series).

- **P2A 2020-2026:** 111 trades, net about +3,320 pt.
- **C1 OOS:** 102 trades.
- **C2 OOS:** 178 trades.

Your chart's history length decides how many of these you see.

## Timing (why it does not repaint)

Every daily-session signal uses the session that has already closed (17:00 ET) and the VIX close of that date,
which is final at 16:15 ET. The trade is then entered at the next session's 18:00 ET open, exactly as in the
backtest. Weekly-level systems use the week's open, which is known at the week's first bar. They trigger on
4-hour bar closes and enter at the next bar's open.
