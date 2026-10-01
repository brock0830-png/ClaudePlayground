# Forward paper-trade log (P2A and P3B, frozen rules)

`signals_log.csv` is the forward record. It is **append-only**: the logger opens it in append mode, never
rewrites a row, and skips any (date, market, system) already logged. Do not edit it by hand. If a row is
wrong, add a note in your journal, not in this file.

## Run it (every trading day, after 17:00 ET)

From the `scalpel_bt/` folder:

    pip install -r requirements.txt          # once
    python scripts/p4_signal_logger.py

Useful options:
- `--dry-run` prints without writing.
- `--date YYYY-MM-DD` evaluates a specific session.
- `--source local` uses the repo data (tests).

Example cron line, 17:20 ET on weekdays (adjust the path and time zone):

    20 17 * * 1-5  cd /path/to/ClaudePlayground/scalpel_bt && python scripts/p4_signal_logger.py >> results/live/cron.log 2>&1

## Columns

| Column | Meaning |
|---|---|
| `date` | the session the signal is computed from |
| `market` | ES, SPX, SPY, DIA or IWM |
| `system` | `P2A` (IBS < 0.30 and VIX > 20) or `P3B` (oversold score > 0.90) |
| `ibs`, `vix`, `score` | inputs on that session (score = the frozen P3B composite, 1 = most oversold) |
| `signal` | 1 = a new trade starts (the rule fired and no trade of that system was open) |
| `in_position` | 1 = a trade of that system, started on an earlier session, is still open |
| `planned_entry`, `planned_exit` | how the backtests executed it (see below) |
| `source` | the data source and symbol used |

## Execution conventions (same as the tests)

- **ES:** enter at the 18:00 ET open on the signal date. Exit at the 18:00 ET open after the 5th session.
- **SPY, DIA, IWM:** paper fill at the 16:00 ET close of the signal date. Exit at the close 5 sessions later.
  - The Phase 4 A4 test found that entering at the next 09:30 open instead changes the average trade by
    under 0.1%.
- **SPX:** not tradable itself. Its rows record the index signal. Trade it through SPY or ES.

## Data and caveats

- **Source:** Yahoo Finance daily bars (`ES=F`, `^GSPC`, `SPY`, `DIA`, `IWM`, `^VIX`). No key is needed.
- **Unfinished bars:** the logger drops the current day's bar until 17:00 ET (ES) or 16:15 ET (others), so it
  never logs an unfinished bar.
- **ES bar caveat:** Yahoo's `ES=F` daily bar can differ from TradingView's `ES1!` session bar. Check the ES
  IBS against your chart for the first weeks.
- **SPY vs SPX:** SPY's and SPX's bars often disagree near the threshold. Phase 4 found they agree on 56% of
  P2A signal days and 67% of P3B days. On 2026-09-30 the logger reproduces SPX 0.906 (P3B signal) and SPY
  0.886 (no signal).
- **Which signals to act on:** P3B rows are logged for comparison only. Phase 4 found P3B adds no edge on top
  of P2A (`results/p4/report.md`).
