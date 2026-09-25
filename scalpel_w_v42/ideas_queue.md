# ideas_queue.md - SCALPEL-W-v42

Each family = the full F0 pierce grid (229,068 configs) under a filter, on the real levels and on four
placebo-shifted level sets. Family screen: (a) >= 1 config passes the config screen AND (b) the
real-level search beats >= 3 of 4 placebo searches on both screen-pass count and top-10 mean
expectancy. Status: done-PASS / done-fail (a) / done-fail (b). Nothing is pending.

## Round 0 (prompt-supplied)
| family | status | note |
|---|---|---|
| F0 pierce grid (all levels, both sides, ATR + sigma units) | done-fail (b) | 725 passers vs 498 / 937 / 990 / 756 on placebo levels; top-10 expR 0.450 vs 0.483 / 0.550 / 0.507 / 0.414 |
| ARCHIVE WTL1 bounce | in F0 | finalist F07; failed |
| ARCHIVE W RB Top long + DM < 0.40 | in DM40_lt | finalist F08; failed |
| ARCHIVE WRL bounce | in F0 | finalist F02; failed |

## Round 1 (EXPAND)
| variant | idea | real passers | placebo passers mean / max | real top-10 | placebo top-10 mean / max | status |
|---|---|---|---|---|---|---|
| TREND10_with | trade only with the trend: WO vs 10-week SMA of weekly closes | 658 | 554 / 778 | 0.289 | 0.327 / 0.444 | done-fail (b) |
| TREND10_counter | trade only against that trend | 906 | 1376 / 1502 | 0.703 | 0.572 / 0.681 | done-fail (b) |
| DM40_lt | prior-week |WC - WO| < 0.40 sigma (archive 'DM < 0.40' analogue) | 247 | 372 / 664 | 0.313 | 0.373 / 0.438 | done-fail (b) |
| DM40_ge | prior-week |WC - WO| >= 0.40 sigma | 2013 | 1650 / 2157 | 0.459 | 0.462 / 0.516 | done-fail (b) |
| RTH | entry bar in RTH (bars starting 06, 10, 14 ET) | 1083 | 1837 / 2421 | 0.420 | 0.427 / 0.446 | done-fail (b) |
| ON | entry bar overnight (18, 22, 02 ET) | 175 | 226 / 292 | 0.389 | 0.387 / 0.408 | done-fail (b) |
| DOW_MonTue | entries on Mon / Tue trading dates | 513 | 553 / 764 | 0.482 | 0.443 / 0.498 | done-fail (b) |
| DOW_WedThu | entries on Wed / Thu trading dates | 1192 | 931 / 1208 | 0.513 | 0.472 / 0.487 | done-PASS |
| DOW_Fri | entries on Friday | 0 | 0 / 1 | 0.087 | 0.094 / 0.122 | done-fail (a) |
| VOL_low | ATR/sigma below its trailing 52-week median | 22 | 63 / 185 | 0.182 | 0.194 / 0.291 | done-fail (b) |
| VOL_high | ATR/sigma at or above it | 3144 | 3504 / 4445 | 0.615 | 0.579 / 0.625 | done-fail (b) |
| GAP_against | weekend gap > 0.10 sigma against the trade | 4 | 30 / 90 | 0.651 | 0.393 / 0.627 | done-fail (b) |
| GAP_with | weekend gap > 0.10 sigma with the trade | 0 | 0 / 0 | 0.120 | 0.190 / 0.304 | done-fail (a) |
| WO_crossed_first | level touched only after price went >= 0.10 sigma past WO the other way | 1503 | 1785 / 2167 | 0.429 | 0.438 / 0.461 | done-fail (b) |
| TOUCH2 | second touch (after a 0.25 sigma move back toward WO) | 667 | 854 / 1330 | 0.398 | 0.461 / 0.486 | done-fail (b) |
| MCONF | level within 0.25 weekly sigma of a v42 monthly level | 257 | 918 / 1674 | 0.334 | 0.387 / 0.456 | done-fail (b) |
| MNONE | no monthly level within 0.25 sigma | 1513 | 1383 / 1977 | 0.463 | 0.498 / 0.553 | done-fail (b) |
| RETEST | retest of a broken level from outside (after a 0.25 sigma extension) | 307 | 395 / 626 | 0.487 | 0.491 / 0.643 | done-fail (b) |

## Round 2 (EXPAND)
| variant | idea | real passers | placebo passers mean / max | real top-10 | placebo top-10 mean / max | status |
|---|---|---|---|---|---|---|
| HOLD | no target: stop or week-end exit | 503 | 484 / 577 | 0.638 | 0.620 / 0.661 | done-fail (b) |
| FIRSTBAR_with | first 4h bar closes in the trade's direction | 1265 | 1585 / 1840 | 0.607 | 0.461 / 0.513 | done-fail (b) |
| FIRSTBAR_against | first 4h bar closes against it | 297 | 878 / 1564 | 0.353 | 0.436 / 0.543 | done-fail (b) |
| PRIORBOX_with | prior week closed outside its inner box in the trade's direction | 3 | 52 / 117 | 0.218 | 0.222 / 0.499 | done-fail (b) |
| PRIORBOX_against | prior week closed outside it against the trade | 0 | 0 / 0 | 0.057 | 0.001 / 0.028 | done-fail (a) |
| PRIORBOX_in | prior week closed inside its inner box | 1316 | 1820 / 2137 | 0.554 | 0.496 / 0.620 | done-fail (b) |
| EARLY_WEEK | entries in the first 15 bars of the week | 795 | 788 / 1039 | 0.648 | 0.636 / 0.721 | done-fail (b) |
| LATE_WEEK | entries in bars 15+ | 356 | 465 / 620 | 0.349 | 0.336 / 0.476 | done-fail (b) |
| PWHL_CONF | level within 0.15 sigma of prior-week high or low | 91 | 592 / 1196 | 0.287 | 0.382 / 0.494 | done-fail (b) |
| PWHL_NONE | not near prior-week high / low | 775 | 1074 / 1323 | 0.452 | 0.434 / 0.488 | done-fail (b) |
| MONTH_FIRSTWEEK | first CME week of the month | 644 | 679 / 1149 | 0.578 | 0.487 / 0.623 | done-fail (b) |
| MONTH_REST | other weeks | 470 | 641 / 730 | 0.473 | 0.477 / 0.592 | done-fail (b) |

## Round 3 (EXPAND + REFINE around DOW_WedThu)
| variant | idea | real passers | placebo passers mean / max | real top-10 | placebo top-10 mean / max | status |
|---|---|---|---|---|---|---|
| DOW_Wed | REFINE: Wednesday only | 685 | 583 / 847 | 0.485 | 0.502 / 0.593 | done-fail (b) |
| DOW_Thu | REFINE: Thursday only | 1 | 8 / 22 | 0.174 | 0.179 / 0.205 | done-fail (b) |
| DOW_TueWedThu | REFINE: Tue-Thu | 1209 | 1858 / 2352 | 0.625 | 0.559 / 0.587 | done-fail (b) |
| BE05 | stop to breakeven after +0.5R | 421 | 550 / 949 | 0.357 | 0.391 / 0.476 | done-fail (b) |
| SO05 | 50% scale-out at 0.5 units | 396 | 492 / 599 | 0.275 | 0.299 / 0.344 | done-fail (b) |
| TOUCH3 | third touch | 0 | 6 / 13 | -0.019 | 0.127 / 0.159 | done-fail (a) |
| PRIORTOUCH_yes | prior week traded through its own version of the level | 836 | 853 / 1387 | 0.500 | 0.458 / 0.568 | done-fail (b) |
| PRIORTOUCH_no | it did not | 681 | 996 / 1418 | 0.369 | 0.409 / 0.464 | done-fail (b) |
| RANGE_WEEK | trade only after the opposite GP box was touched | 1055 | 742 / 1247 | 0.429 | 0.467 / 0.515 | done-fail (b) |

## Stop rule
Round 1 had one passing family (DOW_WedThu). Rounds 2 and 3 had none, and the manifest is 100%
covered, so the search stopped after round 3. The only pass did not survive its own refinement (round 3).
