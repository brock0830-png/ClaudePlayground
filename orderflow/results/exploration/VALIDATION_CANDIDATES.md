# Validation candidates (frozen before any VALIDATION data was read)

Discovery = the 9 dev coins, 2022-2023. Four rounds were run: `discovery_round1.txt` to `discovery_round4.txt`,
and every row is in `../EXPLORATION_LEDGER.csv`. There were about 130 discovery evaluations in total,
so a discovery t of 2-2.5 on its own is roughly what chance produces.

Gate: day-clustered |t| >= 2.0 on discovery, in the stated direction. The post-hoc conditional slices from
round 4 (BTC state, same-day breadth) are **not** advanced. They were inconsistent across sides and are
treated as noise.

| ID | Kind | Discovery t | Direction to confirm |
|---|---|---|---|
| A:A9L_fade_accept_below_PDL | event trade (long after 2 closes below prior-day low) | +3.66 | mean net > 0 |
| A:A9S_fade_accept_above_PDH | event trade (short after 2 closes above prior-day high) | +3.01 | mean net > 0 |
| A:A6L_newlow_pos_delta | event trade (new day low on a positive-delta bar, long) | +2.21 | mean net > 0 |
| A:A6S_newhigh_neg_delta | event trade (new day high on a negative-delta bar, short) | +2.50 | mean net > 0 |
| C:pos_d:lo | screen: low location in the developing day range is better | -3.65 | spread > 0 |
| C:pos_pd:lo | screen: low location in the previous day's range is better | -3.21 | spread > 0 |
| C:below_pdval:hi | screen: close below the previous-day VAL is better | +2.63 | spread > 0 |
| C:swept_pdl:hi | screen: last 6h traded below the previous-day low | +2.21 | spread > 0 |
| C:cvd_d:lo | screen: lower day cumulative delta / volume is better | -2.49 | spread > 0 |
| C:mig_d:lo | screen: developing POC below the previous-day POC is better | -2.12 | spread > 0 |
| C:x_PDVAL:lo | screen: close nearer or below the previous-day VAL is better | -2.13 | spread > 0 |
| C:oi24:lo | control (not order flow): lower 24h OI change is better | -2.49 | spread > 0 |
| C:ret24:lo | control (not order flow): 24h reversal | -2.72 | spread > 0 |

No flush filter (family B) reached the gate (all |t| < 1.8), so none is advanced.
Validation pass = the same sign and day-clustered t >= 2.0 on pooled VALIDATION, with both parts (new coins
2022-25H1; dev coins 2024-25H1) the same sign. For event trades, the per-trade mean net must also be > 0.
