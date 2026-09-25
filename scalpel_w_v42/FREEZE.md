# FREEZE - SCALPEL-W-v42

Frozen 2026-09-25T13:31:36.660085+00:00 from in-sample data only (weeks before 2021-01-01).
finalists.csv sha256 `cb8b97376b6e5a2466d9643193c9ecabb984fadad2e38962725184a25c88c7e0`

Pool: 26728 screen-passing configs across 36 variants, 786 entry-overlap clusters. Family-screen passes: DOW_WedThu.

| id | variant | config | why | IS n | IS PF | IS expR | t-stat |
|---|---|---|---|---|---|---|---|
| F01 | DOW_WedThu | `GP_T_IN|breakout|ATR|d0.25|b_reclaim|Dinf|s1.00|t0.50` | A: level-specific pool (F0 + DOW_WedThu), cluster rank 1 | 249 | 1.72 | 0.110 | 3.90 |
| F02 | F0 | `WRL|bounce|ATR|d0.25|c1|D1.0|STRUCT|NEXT` | A: level-specific pool (F0 + DOW_WedThu), cluster rank 2 | 106 | 2.48 | 0.136 | 3.65 |
| F03 | DOW_WedThu | `WRL|bounce|SIG|d0.50|a_limit|Dinf|s0.50|t0.50` | A: level-specific pool (F0 + DOW_WedThu), cluster rank 3 | 139 | 1.92 | 0.274 | 3.63 |
| F04 | DOW_WedThu | `RNG_T_LO|breakout|ATR|d0.10|c3|Dinf|s1.00|t1.50` | A: level-specific pool (F0 + DOW_WedThu), cluster rank 4 | 154 | 2.08 | 0.207 | 3.57 |
| F05 | DOW_WedThu | `RNG_T_LO|breakout|ATR|d0.00|b_reclaim|Dinf|s1.00|t0.50` | A: level-specific pool (F0 + DOW_WedThu), cluster rank 5 | 217 | 1.72 | 0.106 | 3.54 |
| F06 | F0 | `RNG_T_LO|breakout|SIG|d0.00|c3|Dinf|s0.50|t1.50` | A: level-specific pool (F0 + DOW_WedThu), cluster rank 6 | 472 | 1.49 | 0.154 | 3.46 |
| F07 | F0 | `WTL1|bounce|SIG|d0.00|b_reclaim|D1.0|s0.50|t2.00` | B: ARCHIVE WTL1 bounce (57.7% WR, PF 1.80) | 124 | 1.67 | 0.213 | 2.02 |
| F08 | DM40_lt | `RB_TOP|bounce|SIG|d0.10|b_reclaim|D1.5|s0.50|t0.25` | B: ARCHIVE W RB Top long + momentum filter DM<0.40 (67 SPY trades, PF 1.54) [fails IS screen, carried as lead] [no config reaches 100 IS trades; best with >= 30 carried] | 34 | 2.46 | 0.152 | 2.39 |
| F09 | MONTH_REST | `WRL|bounce|ATR|d0.25|c3|D1.5|s1.00|NEXT` | C: whole pool, next-best cluster 1 | 109 | 4.09 | 0.156 | 5.91 |
| F10 | MONTH_REST | `WRL|bounce|ATR|d0.25|b_reclaim|D1.0|s1.00|NEXT` | C: whole pool, next-best cluster 2 | 142 | 2.82 | 0.118 | 4.80 |
| F11 | DOW_Wed | `GP_T_IN|breakout|ATR|d0.25|b_reclaim|Dinf|s1.00|t0.50` | C: whole pool, next-best cluster 3 | 140 | 2.14 | 0.160 | 4.26 |
| F12 | PRIORTOUCH_no | `WRL|bounce|ATR|d0.25|b_reclaim|D1.0|STRUCT|NEXT` | C: whole pool, next-best cluster 4 | 109 | 2.74 | 0.140 | 4.22 |

Notes (written at freeze, before unsealing):
- F02 is also the best-scoring screen-passing F0 WRL bounce, so it doubles as the ARCHIVE WRL
  bounce lead (69.4% WR, PF 1.44); the duplicate was dropped by the selection code.
- F08 (archive RB Top long + DM<0.40): no configuration of RB_TOP bounce under DM40_lt reaches 100
  in-sample trades; the best with >= 30 trades is carried as a lead and cannot pass G1 unless the
  out-of-sample period alone supplies >= 100 trades.
- The only family that passed the in-sample family screen (level specificity) was DOW_WedThu; its
  refinement in round 3 (Wed, Thu, Tue-Thu) did not pass. Rounds 2 and 3 produced no passing family,
  which meets the stop rule. Search: 40 variants x 229,068 configs, 100% coverage, 0 errors.
- Gates and the one-shot out-of-sample procedure are fixed in src/validate.py and src/finalize.py.
