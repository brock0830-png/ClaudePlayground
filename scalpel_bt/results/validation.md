# Gate 1 — level port validation

Command: `python validate_export.py data/es_levels_CME_MINI_ES1_240.csv.gz`
(TradingView `CME_MINI:ES1!` 240m, EXPORT indicator, 2013-01-02 06:00 ET to 2026-09-30 14:00 ET, 21,164 bars).

| Timeframe | Level columns checked | Max abs error vs TradingView |
|---|---|---|
| D | 18 (+ DO) | 9.1e-13 pt |
| W | 18 (+ WO) | 9.1e-13 pt |
| M | 18 (+ MO) | 9.1e-13 pt |

The port is exact on the whole file (the small 2025-26 export `data/tv_export_es_240m.csv` also passes).

## Period boundaries

Levels in the backtest use the exported period opens (DO/WO/MO) directly, and period blocks are defined by
changes in those opens (`scalpel/data.py::build_bars`). The derived `weekly_open()` disagrees with the
TradingView WO on 132 of 21,164 bars, in six episodes:

| Episode | Bars | What TradingView does | Treatment |
|---|---|---|---|
| 2013-01-02 (data start) | 15 | WO is the 2012-12-30 open, before the file starts | known value, used |
| 2013-12-26, 2014-01-02 | 9 + 9 | Christmas/New Year gap >= 40 h inside the data but TV keeps the same week | TV week used |
| 2014-07-03 18:00 and 2025-07-03 18:00 (July 4 on a Friday) | 5 + 5 orphan bars | TV does **not** start the week on Thursday 18:00; the orphan Thursday-evening bars carry the *next* Sunday's open (lookahead) | bars flagged `lookahead_W/D`, no signals or entries |
| 2015-07-02, 2020-07-02, 2026-07-02 (observed Friday holiday), 2026-06-18 (Juneteenth) | 0 | TV starts the week Thursday 18:00, as `weekly_open()` says | agrees |
| 2018-05-27 18:00 (Memorial Day) | 5 | TV's week starts Monday 18:00; Sunday-evening bars carry Monday's open (lookahead) | flagged, no signals |

So the "Friday holiday starts the week Thursday 18:00" rule in `weekly_open()` is right for *observed*
Friday holidays (July 3, Juneteenth) but not for a July 4 that falls on a Friday (2014, 2025), where TradingView
leaves the Thursday-evening session orphaned. The D series has 5 more orphan bars on Thanksgiving 2018, also flagged.

DO: TradingView folds holiday-Monday sessions (Sunday-evening start) into the next trading day's daily bar
(87 cases); using DO changes as day boundaries reproduces that exactly with no lookahead.

## Contract rolls (unadjusted continuous ES1!)

`scripts/detect_rolls.py` dates every TradingView contract switch from the jump in the ES minus SPX basis
(ES 4h open at 10:00/14:00 ET vs the SPX 1-minute open at the same minute). All 55 quarterly switches
2013-03 to 2026-09 are unambiguous (jump / noise from 7x to 75x); 52 fall on a Tuesday trading day, 3 on a
Monday: TradingView switches at the 18:00 ET session start about 3-4 days before expiry.
Output: `data/roll_dates.csv`. The spread ranges from -11 pt (2020) to +75 pt (2024-12).

Consequences handled in the backtest:
- Weekly levels in a switch week are stale by the spread after the switch (`roll_week`); monthly levels
  from the switch to month end (`roll_month_after`). Every test runs with and without these.
- No position is carried across a switch bar: it is closed at the prior bar's close (a scheduled exit).
