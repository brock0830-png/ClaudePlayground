# FREEZE_P2 - SCALPEL-W-v42 phase 2 (context / confluence)

Frozen 2026-09-25T15:51:48.736592+00:00 from 2013-2020 data only. GC holdout still sealed.
finalists_p2.csv sha256 `8de2a66e2583cf7e51b2ce84f7756c76dc4410970dd498f0ea9b4425b686ca7e`

Pool: 40094 screen-passing configs across 60 phase 2 variants. Family-screen passes: MPM20, MPM25, MPM30, MPM_VA30, MP_ANY20, MP_ANY25, MP_ANY30, MP_VA20, MP_VA30, MP_VAH30, MP_VAH40, OPENVA_against, TGT_POC, TGT_VA.

| id | tier | variant | config | why | IS n | IS PF | IS expR | t-stat |
|---|---|---|---|---|---|---|---|---|
| P01 | A | MP_ANY30 | `RNG_T_HI|breakout|SIG|d0.10|b_reclaim|Dinf|s0.50|t0.25` | A: level-specific phase 2 family (MP_ANY30), cluster rank 1 | 129 | 2.40 | 0.175 | 4.60 |
| P02 | A | OPENVA_against | `RNG_T_HI|breakout|SIG|d0.10|b_reclaim|Dinf|s0.25|t1.00` | A: level-specific phase 2 family (OPENVA_against), cluster rank 2 | 100 | 2.96 | 0.639 | 4.34 |
| P03 | A | MPM20 | `RNG_T_LO|breakout|ATR|d0.00|c3|Dinf|s0.75|t2.00` | A: level-specific phase 2 family (MPM20), cluster rank 3 | 133 | 2.35 | 0.381 | 4.14 |
| P04 | A | MPM25 | `RNG_T_LO|breakout|ATR|d0.25|b_reclaim|Dinf|s1.00|t1.50` | A: level-specific phase 2 family (MPM25), cluster rank 4 | 135 | 2.37 | 0.265 | 4.12 |
| P05 | A | MPM_VA30 | `WRH|breakout|ATR|d0.00|c3|Dinf|s1.00|t0.75` | A: level-specific phase 2 family (MPM_VA30), cluster rank 5 | 116 | 2.38 | 0.197 | 4.04 |
| P06 | A | MP_ANY30 | `RNG_T_LO|breakout|ATR|d0.00|c3|Dinf|s0.75|t2.00` | A: level-specific phase 2 family (MP_ANY30), cluster rank 6 | 225 | 1.89 | 0.271 | 3.98 |
| P07 | B | REG200_align | `GP_T_IN|breakout|ATR|d0.25|b_reclaim|Dinf|s1.00|t0.75` | B: user idea - generalized uptrend: longs only above the 200-day SMA, shorts only below | 358 | 1.37 | 0.079 | 2.51 |
| P08 | B | REGSTRONG_avoid | `GP_T_IN|breakout|ATR|d0.25|b_reclaim|Dinf|s1.00|t2.00` | B: user idea - no bullish setups in a strong bear market (and no bearish ones in a strong bull) | 410 | 1.54 | 0.133 | 3.41 |
| P09 | B | MP_ANY20 | `RNG_T_LO|breakout|SIG|d0.25|b_reclaim|Dinf|s0.75|t0.25` | B: user idea - level within 0.20 sigma of the prior-week POC / VAH / VAL | 116 | 2.26 | 0.112 | 3.71 |
| P10 | B | RSIDIV_4h | `GP_B_IN|bounce|SIG|d0.10|c3|D1.5|s0.40|t0.25` | B: user idea - RSI(14) divergence on 4h in the trade direction | 102 | 1.60 | 0.103 | 2.16 |
| P11 | B | SR_PDHL10 | `GP_T_IN|breakout|ATR|d0.40|b_reclaim|Dinf|s0.75|t0.75` | B: user idea - level within 0.10 sigma of the prior-day high / low | 189 | 1.85 | 0.174 | 3.67 |
| P12 | B | SCORE3 | `WRL|bounce|ATR|d0.00|b_reclaim|D1.5|s1.00|NEXT` | B: user idea - at least 3 of 5 supporting signals (regime, profile, S/R, divergence, open vs POC) | 141 | 1.77 | 0.104 | 2.58 |
| P13 | B | MPALONE | `PVAL_UP|breakout|SIG|d0.00|c1|Dinf|s0.50|t2.00` | B: user idea - prior-week POC / VAH / VAL traded as levels, no v42 level | 122 | 2.02 | 0.354 | 3.41 |
