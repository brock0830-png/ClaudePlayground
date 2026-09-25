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

# Phase 2 - context / confluence / market profile (families_p2.py)

Same machinery and screens. Features: features.py (no look-ahead). Stop rule applied to NEW families:
rounds P2-4 and P2-5 produced no new passing family (their passes were refinements), so the search stopped.

## Round P2-1
| variant | real passers | placebo passers mean / max | real top-10 | placebo top-10 mean / max | status |
|---|---|---|---|---|---|
| REG200_align | 139 | 419 / 487 | 0.323 | 0.443 / 0.510 | done-fail (b) |
| REG5020_align | 938 | 1327 / 1381 | 0.502 | 0.598 / 0.644 | done-fail (b) |
| REGSTRONG_avoid | 826 | 1210 / 1322 | 0.458 | 0.407 / 0.461 | done-fail (b) |
| BEAR20_avoid | 1112 | 1628 / 1894 | 0.479 | 0.403 / 0.448 | done-fail (b) |
| MP_POC10 | 0 | 19 / 57 | 0.208 | 0.318 / 0.426 | done-fail (a) |
| MP_VA10 | 117 | 446 / 1093 | 0.474 | 0.354 / 0.377 | done-fail (b) |
| MP_ANY20 | 817 | 664 / 1133 | 0.572 | 0.529 / 0.617 | done-PASS |
| OPENVA_with | 123 | 114 / 256 | 0.321 | 0.291 / 0.454 | done-fail (b) |
| OPENVA_in | 82 | 328 / 570 | 0.305 | 0.317 / 0.327 | done-fail (b) |
| OPENVA_against | 1915 | 1446 / 2169 | 0.858 | 0.752 / 0.830 | done-PASS |
| RSIDIV_4h | 117 | 216 / 525 | 0.400 | 0.473 / 0.566 | done-fail (b) |
| RSIDIV_D | 0 | 0 / 0 | 0.132 | 0.051 / 0.185 | done-fail (a) |
| SR_PDHL10 | 481 | 1157 / 2173 | 0.348 | 0.440 / 0.463 | done-fail (b) |
| SR_SWING10 | 402 | 578 / 1074 | 0.424 | 0.376 / 0.601 | done-fail (b) |
| SCORE2 | 426 | 710 / 991 | 0.370 | 0.365 / 0.392 | done-fail (b) |
| SCORE3 | 113 | 200 / 411 | 0.208 | 0.315 / 0.496 | done-fail (b) |
| TGT_POC | 166 | 80 / 156 | 0.383 | 0.382 / 0.450 | done-PASS |
| MPALONE | 341 | 354 / 451 | 0.587 | 0.445 / 0.598 | done-fail (b) |

## Round P2-2
| variant | real passers | placebo passers mean / max | real top-10 | placebo top-10 mean / max | status |
|---|---|---|---|---|---|
| OVA_ag_poc | 2663 | 2971 / 3623 | 0.699 | 0.578 / 0.616 | done-fail (b) |
| OVA_ag_far | 1194 | 1011 / 1764 | 0.806 | 0.735 / 0.833 | done-fail (b) |
| OVA_ag_pwl | 0 | 0 / 0 | - | nan / nan | done-fail (a) |
| MP_ANY15 | 309 | 535 / 945 | 0.624 | 0.549 / 0.633 | done-fail (b) |
| MP_ANY30 | 1539 | 989 / 1134 | 0.680 | 0.570 / 0.647 | done-PASS |
| MP_POC20 | 78 | 115 / 250 | 0.375 | 0.394 / 0.505 | done-fail (b) |
| MP_VA20 | 598 | 534 / 1032 | 0.554 | 0.551 / 0.684 | done-PASS |
| TGT_VA | 284 | 161 / 240 | 0.428 | 0.422 / 0.479 | done-PASS |
| TGT_POC_naked | 277 | 344 / 606 | 0.340 | 0.425 / 0.467 | done-fail (b) |
| MP80 | 742 | 508 / 642 | 0.464 | 0.497 / 0.530 | done-fail (b) |
| MP4W20 | 1315 | 761 / 1943 | 0.572 | 0.611 / 0.681 | done-fail (b) |
| REG200_MP20 | 63 | 147 / 212 | 0.269 | 0.255 / 0.417 | done-fail (b) |
| RSI_EXT | 11 | 80 / 172 | 0.249 | 0.300 / 0.418 | done-fail (b) |
| TREND_D20 | 397 | 570 / 997 | 0.304 | 0.322 / 0.419 | done-fail (b) |

## Round P2-3
| variant | real passers | placebo passers mean / max | real top-10 | placebo top-10 mean / max | status |
|---|---|---|---|---|---|
| MP_ANY25 | 1147 | 854 / 1149 | 0.679 | 0.581 / 0.632 | done-PASS |
| MP_ANY40 | 1473 | 1200 / 1870 | 0.651 | 0.684 / 0.825 | done-fail (b) |
| MP_ANY50 | 1430 | 1444 / 2394 | 0.621 | 0.741 / 0.922 | done-fail (b) |
| MP_VA30 | 1291 | 809 / 1018 | 0.729 | 0.605 / 0.674 | done-PASS |
| MP_VA40 | 1664 | 1137 / 1782 | 0.670 | 0.706 / 0.821 | done-fail (b) |
| MP30_TGT_VA | 57 | 48 / 77 | 0.157 | 0.172 / 0.193 | done-fail (b) |
| MP_IN_VA | 387 | 768 / 1200 | 0.479 | 0.502 / 0.581 | done-fail (b) |
| MP_OUT_VA | 328 | 355 / 846 | 0.404 | 0.458 / 0.523 | done-fail (b) |
| LVN | 468 | 604 / 997 | 0.468 | 0.451 / 0.589 | done-fail (b) |
| HVN | 0 | 24 / 76 | - | 0.383 / 0.385 | done-fail (a) |
| MPM20 | 1166 | 860 / 1436 | 0.877 | 0.661 / 0.771 | done-PASS |

## Round P2-4
| variant | real passers | placebo passers mean / max | real top-10 | placebo top-10 mean / max | status |
|---|---|---|---|---|---|
| VAMIG_with | 927 | 1129 / 1778 | 0.266 | 0.405 / 0.469 | done-fail (b) |
| VAMIG_against | 623 | 758 / 952 | 0.444 | 0.520 / 0.611 | done-fail (b) |
| BALANCE | 69 | 94 / 207 | 0.277 | 0.282 / 0.325 | done-fail (b) |
| TRENDWK | 1983 | 2849 / 3374 | 0.573 | 0.489 / 0.507 | done-fail (b) |
| DEVPOC_below | 390 | 182 / 220 | 0.396 | 0.398 / 0.414 | done-fail (b) |
| DEVPOC_above | 466 | 769 / 1103 | 0.508 | 0.548 / 0.644 | done-fail (b) |
| MPM15 | 797 | 610 / 958 | 0.390 | 0.558 / 0.693 | done-fail (b) |
| MPM30 | 1742 | 1172 / 1675 | 0.870 | 0.604 / 0.712 | done-PASS |
| MPM_POC20 | 44 | 160 / 414 | 0.595 | 0.526 / 0.575 | done-fail (b) |
| MP_VAH30 | 489 | 218 / 367 | 0.595 | 0.452 / 0.602 | done-PASS |
| MP_VAL30 | 163 | 182 / 316 | 0.455 | 0.373 / 0.458 | done-fail (b) |
| MPWM20 | 49 | 46 / 150 | 0.183 | 0.295 / 0.529 | done-fail (b) |

## Round P2-5
| variant | real passers | placebo passers mean / max | real top-10 | placebo top-10 mean / max | status |
|---|---|---|---|---|---|
| ACCEPT_VA | 125 | 180 / 399 | 0.334 | 0.330 / 0.389 | done-fail (b) |
| OPENIN_VA30 | 121 | 185 / 339 | 0.324 | 0.289 / 0.382 | done-fail (b) |
| PCLOSE_Q | 626 | 488 / 737 | 0.302 | 0.387 / 0.476 | done-fail (b) |
| POC2W25 | 580 | 795 / 1392 | 0.544 | 0.522 / 0.558 | done-fail (b) |
| PWHL30 | 312 | 292 / 610 | 0.430 | 0.337 / 0.375 | done-fail (b) |
| MPM25 | 1626 | 1069 / 1517 | 0.879 | 0.633 / 0.766 | done-PASS |
| MPM_VA30 | 1125 | 747 / 1071 | 0.844 | 0.543 / 0.628 | done-PASS |
| MP_VAH20 | 53 | 215 / 507 | 0.297 | 0.347 / 0.450 | done-fail (b) |
| MP_VAH40 | 788 | 302 / 581 | 0.632 | 0.505 / 0.600 | done-PASS |

Definitions of every variant are in the docstrings of src/families_p2.py and src/features.py.
Frozen finalists: FREEZE_P2.md. Results: REPORT_P2.md.
