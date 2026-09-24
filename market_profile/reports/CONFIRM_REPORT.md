# Confirm stage report (ES 2017-2021)

**Ledger count: 53 evaluations in total** (explore rows 1-51 in `ledger/EXPLORE_LEDGER.csv`, confirm rows 52-53 in `ledger/CONFIRM_LEDGER.csv`).

Sample 2017-01-03 to 2021-12-31 (1259 RTH sessions), run once at 2026-09-24T17:23:42Z, code commit `19107a3ff1133ad83f703904997a309e5d0ced4f`. Nothing after 2021-12-31 was loaded. Rule: net-positive and t over matched baseline >= 2.5. Costs 2.4 ticks per round turn. The ledger schema is fixed, so on confirm rows the `meets_explore_rule` column holds the confirm-stage rule result.

| id | Candidate | Baseline | Trades | Win % | Mean net | Median net | Mean gross | t vs base | t alt base | Max DD | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 52 | MP10 rej | same open location | 27 | 51.9 | -13.33 | 0.60 | -10.93 | -0.78 | -0.83 | 360 | fails |
| 53 | MP16 P | all days | 49 | 71.4 | 2.91 | 7.60 | 5.31 | 0.70 | 0.75 | 235 | fails |

Explore-stage figures for the same candidates, for comparison:

| Candidate | Explore trades | Explore mean net | Explore t |
|---|---|---|---|
| MP10 rej | 32 | 14.79 | 2.58 |
| MP16 P | 111 | 2.47 | 2.26 |

By year (confirm trades, mean net ticks):

- MP10 rej: 2017: -13.4 (n=5), 2018: +2.6 (n=4), 2019: -9.0 (n=7), 2020: -14.6 (n=6), 2021: -30.6 (n=5)
- MP16 P: 2017: +0.6 (n=13), 2018: +3.3 (n=10), 2019: +6.1 (n=13), 2020: +15.6 (n=2), 2021: -0.8 (n=11)

Survivors to the final (2022-2026-08) look: none. The final stage has not been run.

## Notes

- Explore addendum 1 (MP2/MP4 `drive05`, ledger rows 50-51) added no candidates, so the confirm stage ran on the two
  candidates frozen at the first freeze.
- MP10 rejected leg reversed sign: -13.3 net ticks per trade (explore +14.8) and negative in 4 of 5 years. Its explore
  result rested on three large trades.
- MP16 stayed net-positive (+2.9 net ticks, 71% winners, 36 of 49 trades reached the target), but it barely beat its
  matched baseline (t 0.70 against the required 2.5). Entering at the open toward a nearby prior-day extreme did about
  as well without the "poor" condition, so the poor high/low adds little. It had only 2 setups in 2020: fewer poor
  extremes (24) and a 41-point median range meant the open was rarely within one IB width of an unrepaired one.
  An independent count of setups per year matches its trade count exactly.
- Under spec section 6 neither candidate advances. The final 2022-2026 look and the NQ stage have nothing to test and
  were not run.
