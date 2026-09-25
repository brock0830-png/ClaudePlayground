# search_manifest.md - SCALPEL-W-v42

Lineage `SCALPEL-W-v42`. Every session reads this file, `coverage.csv`, `results_all.csv.gz` and
`ideas_queue.md` and resumes; nothing restarts. In-sample (IS) = weeks starting 2013-01-28 to
2020-12-28 (6J from 2016-10-17). 2021+ is sealed (`OOS_UNSEALED` absent) until finalists are frozen.

## Tickers and data
ES, NQ, CL, 6J (the four supplied TradingView 4h exports, UTC-8/-9 timestamps converted exactly).
Levels: `docs_scalpel_v42.pine` WEEKLY engine, static per-asset vol / bias / SD multipliers, WO = open
of the first 4h bar of the CME week (Sunday 18:00 ET). Execution in micros: MES, MNQ, MCL, MJY.

## F0 - pierce grid (STEP 2B, run in full)
| dimension | values |
|---|---|
| level (18) | GB_TOP, WTH2, WTH1, GB_BOT, RNG_T_HI, WRH, RNG_T_LO, GP_T_IN, GP_T_OUT, GP_B_OUT, GP_B_IN, RNG_B_HI, WRL, RNG_B_LO, RB_TOP, WTL1, WTL2, RB_BOT |
| side (2) | bounce (fade toward WO), breakout (through, away from WO). Levels above WO give the short bounce / long breakout, levels below the mirror |
| unit (2) | ATR = daily ATR(14) at week open; SIG = weekly sigma (WO x vol / sqrt 52) |
| pierce d (7) | 0, 0.10, 0.25, 0.40, 0.50, 0.75, 1.00 |
| entry style (5) | a = resting limit at level +- d (bounce) / stop entry at level +- d (breakout); b = reclaim (bounce: pierce >= d then a 4h close back across the level) / close beyond level + d (breakout), enter next open; c1/c2/c3 = b with the close required within 1/2/3 bars of the pierce (first touch for breakouts) |
| max pierce D (3) | 0.5, 1.0, 1.5 (bounce reclaim styles only, D >= d) |
| stop (7) | level -+ (d + s) for bounce, level +- (d - s) for breakout, s in 0.10, 0.25, 0.40, 0.50, 0.75, 1.00 units; STRUCT = next ladder level beyond (bounce) / back toward WO (breakout) |
| target (8) | entry +- t units, t in 0.25, 0.50, 0.75, 1.00, 1.50, 2.00; NEXT = next ladder level toward WO (bounce) / outward (breakout); WO (bounce only) |
| exit | flat at the close of the week's final 4h bar |

Cells (entry definitions) = 4,248; configs = 229,068 per variant; x 4 tickers + pooled.
Ladder for STRUCT / NEXT: GB_TOP, WTH2, WTH1, GB_BOT, WRH, GP_T_IN, GP_T_OUT, WO, GP_B_OUT, GP_B_IN,
WRL, RB_TOP, WTL1, WTL2, RB_BOT (neighbours closer than 0.10 sigma skipped).

## Controls run on the whole F0 search
* placebo levels shifted outward by -0.30, -0.15, +0.15, +0.30 sigma (all levels and the ladder)
* every SD multiplier x0.95 and x1.05
* 2 ticks slippage

## EXPAND families (each = full F0 grid under a filter, real + 4 placebo shifts)
See `ideas_queue.md` for definitions, results and status. 39 variants in 3 rounds:
Round 1: TREND10 (with / counter), DM40 (prior-week |move| < / >= 0.40 sigma, the archive "DM < 0.40"
analogue), session RTH / ON, day of week (Mon-Tue, Wed-Thu, Fri), VOL regime, GAP against / with,
WO crossed first, second touch, monthly confluence / none, retest of a broken level.
Round 2: HOLD (no target), first-bar direction, prior-week box close, early / late week, prior-week
high / low confluence, first week of month.
Round 3: REFINE around DOW_WedThu (Wed, Thu, Tue-Thu), breakeven at +0.5R, 50% scale-out at 0.5
units, third touch, prior week touched the level, range week.

## Screens
Config screen (screen.py): pooled n >= 100, net expectancy > 0, PF >= 1.3; tickers with >= 30
trades (at least 2) all positive but at most one; plateau: every +-1-step neighbour net positive,
median neighbour PF >= 1.3.
Family screen (families.py): >= 1 config passes AND the real-level search beats >= 3 of its 4
placebo-level searches on both screen-pass count and top-10 mean expectancy.

## Stop rule
Stop when every manifest cell is covered and two consecutive EXPAND rounds yield no family that
passes the family screen. STATUS: met after round 3 (rounds 2 and 3 empty; 40 variants x 16,992
ticker-cells done, 0 errors, 0 pending). Finalists frozen in FREEZE.md; 2021+ opened once.
