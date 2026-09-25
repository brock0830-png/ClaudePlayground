# CLAUDE CODE PROMPT — TrueALGO/Scalpel Level Strategy Search (v3, 2026-09-25)
Lineage tag for every output file: `SCALPEL-W-v42`

## MISSION
Find out whether the weekly TrueALGO levels (reproduced exactly by Doc's Scalpel v42 on the
tickers below) support one or more mechanical futures strategies that are EV+ after fees and
slippage, with complete rules: entry, stop, target, exit, and position size. A setup should
work across tickers, not on one chart. If nothing survives, say so plainly. That answer
decides whether weeks of hand-extracting native levels are worth it.

Work creatively first, then rigorously. Build the strongest version of each idea before trying
to kill it, but nothing graduates without passing Section 6.

## TICKERS (verified exact vs native TrueALGO — do not add others)
[CHRIS: fill in, e.g. ES, NQ, GC, ...]
Data: TradingView 4h OHLC exports (UTC-8 timestamps), one CSV per ticker, max history.
Level math: the attached `docs_scalpel_v42.pine`, WEEKLY engine only (static per-asset
vol / bias / SD multipliers). Weekly bucket = CME week opening Sunday 18:00 ET.
Levels per week: WO, GB Top, WTH2, WTH1, GB Bot, WRH (+range box), GP boxes, WRL
(+range box), RB Top, WTL1, WTL2, RB Bot.

## STEP 0 — CANARY (must pass before any result is quoted)
Week of 2026-09-21:
ES  WO 7722.00 | GB 8070.75 / 7912.99 | RB 7515.92 / 7370.84 | 1σ 198.54
GC  WO 4413.00 | GB 4666.18 / 4575.50 | RB 4299.14 / 4212.94
Error above 0.05 pt means stop and fix. Print "CANARY PASS" before continuing.

## STEP 1 — LEVEL STRENGTH MAP (answers "which levels are strongest")
For every level on every ticker-week, record each first touch (4h bar trades through the level):
- P(reject): price returns X σ back toward WO before extending X σ further, X in {0.25, 0.5}
- MFE / MAE over the next 1, 3, 6 bars and to week end, in σ units
- P(close through) by week end
CONTROL (required): repeat for placebo levels at the same distance from WO, shifted
±0.15σ and ±0.30σ. A level is "strong" only if it beats its placebos, not just 50%.
Weekly ranges mean-revert on their own, so an arbitrary line at the same distance may
"bounce" too. Rank levels by excess-over-placebo, pooled and per ticker.

## STEP 2 — STRATEGY SEARCH
Prior leads from earlier work [ARCHIVE; small samples, costs unclear]:
- WTL1 bounce: 57.7% WR, PF 1.80
- W RB Top long + momentum filter (DM < 0.40): 67 trades on SPY, 59.7% WR, PF 1.54
- WRL bounce: 69.4% WR, PF 1.44, 312 weeks
Start with these, the top levels from Step 1, and their mirrored short side. Then explore
freely: fades, breakouts through inner edges toward WTH/WTL, GP-box reversion to WO,
first-touch vs later-touch, time-of-week filters, confluence of two levels.
Each strategy must specify:
- Entry: limit at level (fills only if price trades 1 tick through) OR confirmation
  (4h close back across level, enter next bar open)
- Stop: a structural level or a fixed σ-fraction, set at entry
- Target(s): a level, WO, or an R-multiple; scaling out is allowed if pre-specified
- Time exit: flat by the final bar of the week
- Size: risk 0.5% of equity per trade on stop distance using micros (MES, MNQ, MGC...);
  round down; skip the trade if one micro exceeds the budget
Log every configuration tried (count N). No cap during exploration, but N feeds the deflation.


## STEP 2B — PIERCE GRID (required, run in full)
Price often stabs through a level before reacting, so the level acts as a zone. For each level
and side (bounce long/short, breakout long/short), sweep this full grid:
- Units: daily ATR(14) at week open, AND weekly sigma (two parallel runs; report both)
- Pierce depth d before a trade is valid: 0, 0.10, 0.25, 0.40, 0.50, 0.75, 1.00
- Entry style:
  (a) resting limit at level minus d (deeper fill)
  (b) reclaim: price pierces >= d, then a bar closes back across the level; enter next bar open
  (c) reclaim with a time limit: must reclaim within 1 / 2 / 3 bars of the pierce
- Stop: level minus (d + s), s in {0.10, 0.25, 0.40, 0.50, 0.75, 1.00}; or the next structural level
- Target: t in {0.25, 0.50, 0.75, 1.00, 1.50, 2.00} ATR; or the next level toward WO; or WO itself
- Max pierce: a touch that penetrates more than D (0.5 / 1.0 / 1.5) before reclaim is invalidated
Log every cell, including empty and losing ones.

## PATH RESOLUTION (required for any pierce/stop smaller than about 0.3 ATR)
On 4h bars, a small pierce, a tight stop and the target often land inside one bar, so
the fill order is unknown. Stop-first is the safe default, but it will bias results.
Re-run all finalists on 15m (or 5m) data exported for the same tickers, and report the
difference between the 4h and 15m versions. If a finalist's edge exists only under 4h fill
assumptions, it fails.

## STEP 3 — EXECUTION REALISM
- Levels are known at week open; no information from later in the week.
- When stop and target both fall inside one 4h bar, assume the STOP filled.
- Costs every round turn, per contract: $4.50 commission+fees plus 1 tick slippage on
  entries, stops and market exits (CME tick values). Limit target exits: no slippage.
- One position per ticker at a time.


## SEARCH ENGINE — EXHAUSTIVE, PERSISTENT, NON-STOPPING
Maintain these files on disk; every session starts by reading them and resumes, never restarts:
- `search_manifest.md`: the full parameter space (dimensions x values) and hypothesis families
- `coverage.csv`: which cells and families are done, pending, or errored
- `results_all.csv`: one row per configuration x ticker (IS metrics only until rules are frozen)
- `ideas_queue.md`: new hypothesis families generated during the search, with status
Loop:
1. SWEEP: run every pending cell of the manifest. A good result is not a stopping point.
2. MAP: for each level/side, plot PF and net expectancy as heatmaps over (pierce x stop x target).
3. REFINE: around any region that beats its placebo, add a finer grid and re-sweep.
4. EXPAND: every round, generate at least 5 new families nobody asked for
   (e.g. second touch vs first, day-of-week, touch after a prior-week close outside a box,
   confluence with monthly levels, gap opens into a level, overnight vs RTH touch, level
   touched after WO was already reclaimed, reward-to-risk scaling by distance to WO).
   Add them to the manifest and run them.
5. STOP only when the manifest is 100% covered AND two consecutive EXPAND rounds
   produce no new family that passes the in-sample screen. Print a coverage report.

## OVERFITTING GUARD FOR AN EXHAUSTIVE SEARCH
An exhaustive grid will contain PF 3+ cells by chance. A single cell is not a finding.
- PLATEAU RULE: a candidate counts only if its neighbors (±1 step on every grid dimension)
  are also net positive, with a median neighbor PF of at least 1.3. A real edge is a region, not a spike.
- Minimum 30 in-sample trades per ticker-config; 100 pooled.
- Deflation: count N honestly; estimate effective N by clustering correlated configs
  (e.g. trade-overlap > 0.7 means same cluster) and report the DSR floor for both.
- Sealed 2021+ data and held-out tickers are opened ONCE, for frozen finalists only.

## STEP 4 — VALIDATION (all required to call something EV+)
- Time split: design on 2013 through 2020; 2021 to present sealed until rules are frozen.
- Ticker split: leave-one-ticker-out. Rules frozen without ticker k must be net positive
  on ticker k, for most tickers.
- Net of costs on out-of-sample data: expectancy > 0 in R and $, PF ≥ 1.20, ≥ 100 trades pooled.
- Survives 2× slippage.
- Survives every SD multiplier scaled ×0.95 and ×1.05. An edge only at the exact values
  is fragile. Report it, but flag it.
- Beats the matched-placebo version of itself (same rules, placebo levels).
- Sharpe above the Deflated Sharpe floor for the logged N.

## STEP 5 — DELIVERABLES
1. Level strength table (Step 1), excess over placebo, pooled + per ticker.
2. For each surviving strategy: a one-paragraph rulebook a human could trade from,
   a frozen trade list CSV, and a per-ticker / per-year table (n, WR, PF, net R expectancy,
   max drawdown, $ at 0.5% risk).
3. A list of the closest failures and exactly which gate each failed.
4. A plain verdict. Status tag on every number: [NEW], [ARCHIVE], [RECONSTRUCTION].
   No "proven / confirmed / dead".

## BANNED
Changing thresholds after viewing 2021+ data; dropping tickers or years to rescue a result;
picking the best multiplier scaling after the fact; comparing against results from other lineages.
