# ideas_queue.md - SCALPEL-W-v42

Each family = the full F0 pierce grid (229,068 configs) run under a filter, on the real levels and
on four placebo-shifted level sets. Family screen: (a) >= 1 config passes the config screen AND
(b) the real-level search beats >= 3 of 4 placebo searches on both screen-pass count and top-10
mean expectancy. Status values: pending / running / done-pass / done-fail.

## Round 0 (prompt-supplied)
| family | status | note |
|---|---|---|
| F0 pierce grid (all levels, both sides, ATR + sigma units) | done-fail (b) | 725 passers vs 498 / 937 / 990 / 756 on placebo levels; top-10 expR 0.450 vs 0.483 / 0.550 / 0.507 / 0.414 |
| ARCHIVE WTL1 bounce | in F0 | carried to finalists |
| ARCHIVE W RB Top long + DM < 0.40 | in DM40_lt | carried to finalists |
| ARCHIVE WRL bounce | in F0 | carried to finalists |

## Round 1 (EXPAND, generated this session)
| family | variants | status |
|---|---|---|
| Trend filter: WO vs 10-week SMA of closes | TREND10_with [done-fail (b)], TREND10_counter [done-fail (b)] | done |
| Prior-week move (archive "DM < 0.40" analogue, DM = abs(prior WC - WO) / sigma) | DM40_lt [done-fail (b)], DM40_ge [done-fail (b)] | done |
| Session of the entry bar | RTH (06, 10, 14 ET bars), ON (18, 22, 02) | done |
| Day of week (CME trading date) | DOW_MonTue [done-fail (b)], DOW_WedThu, DOW_Fri [done-fail (a)] | done |
| Vol regime: ATR/sigma vs trailing 52-week median | VOL_low [done-fail (b)], VOL_high [done-fail (b)] | done |
| Weekend gap vs prior close (> 0.10 sigma) | GAP_against [done-fail (b)], GAP_with [done-fail (a)] | done |
| Level touched only after WO was crossed first (>= 0.10 sigma the other way) | WO_crossed_first [done-fail (b)] | done |
| Second touch (after a 0.25 sigma move back toward WO) | TOUCH2 [done-fail (b)] | done |
| Confluence with a v42 monthly level (within 0.25 weekly sigma) | MCONF [done-fail (b)], MNONE [done-fail (b)] | done |
| Retest of a broken level from the outside (after a 0.25 sigma extension) | RETEST [done-fail (b)] | done |

## Round 2 (EXPAND)
| family | variants | status |
|---|---|---|
| No target: stop or week-end exit only | HOLD [done-fail (b)] | done |
| First 4h bar direction vs trade direction | FIRSTBAR_with [done-fail (b)], FIRSTBAR_against [done-fail (b)] | done |
| Prior week closed outside its own inner box | PRIORBOX_with [done-fail (b)], PRIORBOX_against, PRIORBOX_in [done-fail (b)] | done |
| Touch time: first half vs second half of the week | EARLY_WEEK [done-fail (b)], LATE_WEEK [done-fail (b)] | done |
| Confluence with prior week high / low (within 0.15 sigma) | PWHL_CONF [done-fail (b)], PWHL_NONE [done-fail (b)] | done |
| Calendar: first week of the month vs the rest | MONTH_FIRSTWEEK [done-fail (b)], MONTH_REST [done-fail (b)] | done |

## Round 3 (EXPAND; required because round 1 had a passing family)
| family | variants | status |
|---|---|---|
| REFINE around DOW_WedThu: single days and Tue-Thu | DOW_Wed, DOW_Thu, DOW_TueWedThu | running |
| Breakeven stop after +0.5R | BE05 | running |
| Pre-specified 50% scale-out at 0.5 units | SO05 | running |
| Third touch | TOUCH3 | running |
| Prior week also traded through its own version of the level | PRIORTOUCH_yes, PRIORTOUCH_no | running |
| Range week: trade only after the opposite GP box was touched | RANGE_WEEK | running |

## Parked
- (none; parked ideas were promoted to round 3)
