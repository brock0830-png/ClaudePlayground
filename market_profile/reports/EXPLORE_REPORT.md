# Explore stage report (ES)

**Ledger count: 49 evaluations** (`ledger/EXPLORE_LEDGER.csv`, ids 1-49); 45 eligible for freezing, 4 robustness-only.

Spec `SPEC_market_profile_ES_v3.md` sha256 `dd382184a08dac2b5ff579b2d2ed61874ca78921615dc9a4f5c4c8787d92db35`; code commit `9520bc4ce3caf33006cd8e57f24eb33fff9b087a`; run 2026-09-24T15:01:40Z.

## Data

- Databento `GLBX.MDP3` `ohlcv-1m`, `ES.v.0` + `NQ.v.0` (volume roll), full history. Billed $40.97 (equal to the free estimate); first available date 2010-06-06.
- Explore sample: 2010-06-07 to 2016-12-30, 1650 RTH sessions. Nothing after 2016-12-31 was loaded into the explore run.
- Rolls in the explore sample: 27 (full list in `rolls_ES.csv`). Sessions dropped as unusable: 6 (`sessions_dropped_ES.csv`).
- 2-tick rows (profile > 400 one-tick rows): 1 explore session(s) (`ledger/row_size_log_ES.csv`).
- Costs: 1 tick slippage per side + $5 round turn = 2.4 ticks per trade.

## Rule

Advance to confirm if eligible variant, mean net ticks > 0 and t over matched baseline >= 2.0 (spec section 6). Matched baseline: same entry clock time, side and exit rule, over all sessions or sessions with the same open location (CONVENTIONS.md C20).

## Frozen candidates

| Family | Variant | Ledger id | Trades | Mean net ticks | t vs baseline |
|---|---|---|---|---|---|
| MP10 | rej (rejected-into-VA leg only) | 15 | 32 | 14.79 | 2.58 |
| MP16 | P (spec definition) | 35 | 111 | 2.47 | 2.26 |

## All evaluations

| id | Family | Variant | Baseline | Trades | Win % | Mean net | Median net | Mean gross | t vs base | t alt base | Max DD | Meets |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | MP1 | P | open loc | 523 | 43.4 | -0.46 | -2.40 | 1.94 | 2.44 | 2.34 | 501 |  |
| 2 | MP1 | volVA (robustness) | open loc | 504 | 42.5 | -0.46 | -1.40 | 1.94 | 2.56 | 2.44 | 552 |  |
| 3 | MP1c | P | open loc | 60 | 51.7 | -0.62 | 0.60 | 1.78 | 0.97 | 0.55 | 140 |  |
| 4 | MP1c | volVA (robustness) | open loc | 61 | 47.5 | -0.81 | -0.40 | 1.59 | 0.80 | 0.38 | 119 |  |
| 5 | MP2 | P | all | 1068 | 31.8 | -2.33 | -11.40 | 0.07 | 0.12 | 0.13 | 2929 |  |
| 6 | MP3 | P | all | 161 | 26.7 | -4.93 | -13.40 | -2.53 | -1.37 | -1.38 | 886 |  |
| 7 | MP4 | P | all | 26 | 46.2 | 15.45 | -4.90 | 17.85 | 1.63 | 1.68 | 75 |  |
| 8 | MP5 | P | open loc | 36 | 41.7 | -2.48 | -7.40 | -0.08 | 0.27 | -0.02 | 117 |  |
| 9 | MP6 | P | open loc | 18 | 16.7 | -3.57 | -7.40 | -1.17 | -0.75 | -0.61 | 90 |  |
| 10 | MP7 | P | all | 260 | 18.8 | -3.41 | -6.40 | -1.01 | -1.39 | -1.41 | 890 |  |
| 11 | MP8 | P | all | 400 | 55.5 | -2.61 | 9.60 | -0.21 | -0.18 | -0.19 | 1138 |  |
| 12 | MP9 | P | open loc | 92 | 54.3 | 0.99 | 4.10 | 3.39 | 1.24 | 1.23 | 198 |  |
| 13 | MP10 | P | open loc | 1061 | 49.2 | -1.85 | -0.40 | 0.55 | 0.18 | 0.20 | 2041 |  |
| 14 | MP10 | acc | open loc | 1029 | 48.7 | -2.37 | -0.40 | 0.03 | -0.22 | -0.19 | 2489 |  |
| 15 | MP10 | rej | open loc | 32 | 65.6 | 14.79 | 6.60 | 17.19 | 2.58 | 2.49 | 98 | yes |
| 16 | MP10 | volVA (robustness) | open loc | 1016 | 48.5 | -2.05 | -0.90 | 0.35 | 0.04 | 0.06 | 2276 |  |
| 17 | MP11 | P | all | 653 | 43.3 | -2.57 | -3.40 | -0.17 | -0.12 | -0.01 | 1781 |  |
| 18 | MP12 | P | all | 244 | 20.9 | -1.70 | -8.40 | 0.70 | 0.28 | 0.24 | 841 |  |
| 19 | MP12 | bal5 | all | 22 | 18.2 | -3.81 | -8.40 | -1.41 | -0.64 | -0.54 | 97 |  |
| 20 | MP12 | hold3 | all | 240 | 12.5 | -2.57 | -8.40 | -0.17 | -0.50 | -0.43 | 942 |  |
| 21 | MP12 | bal5_hold3 | all | 22 | 9.1 | -7.85 | -8.40 | -5.45 | -3.14 | -3.12 | 173 |  |
| 22 | MP12b | P | all | 4 | 25.0 | 0.35 | -8.40 | 2.75 | 0.36 | 0.37 | 17 |  |
| 23 | MP12b | bal5 | all | 0 |  |  |  |  |  |  |  |  |
| 24 | MP12b | hold3 | all | 4 | 25.0 | 6.85 | -8.40 | 9.25 | 0.73 | 0.85 | 17 |  |
| 25 | MP12b | bal5_hold3 | all | 0 |  |  |  |  |  |  |  |  |
| 26 | MP13 | P | all | 178 | 41.0 | -6.24 | -5.40 | -3.84 | -1.15 | -1.15 | 1433 |  |
| 27 | MP13 | nextclose | all | 178 | 48.9 | -8.59 | -1.40 | -6.19 | -1.30 | -1.30 | 1770 |  |
| 28 | MP14 | P | all | 155 | 46.5 | -4.39 | -3.40 | -1.99 | -0.78 | -0.80 | 789 |  |
| 29 | MP14 | nextclose | all | 155 | 50.3 | -3.20 | 0.60 | -0.80 | -0.46 | -0.46 | 830 |  |
| 30 | MP14b | P | all | 73 | 52.1 | 1.09 | 0.60 | 3.49 | 0.67 | 0.63 | 404 |  |
| 31 | MP14b | nextclose | all | 73 | 47.9 | 2.93 | -0.40 | 5.33 | 0.60 | 0.56 | 416 |  |
| 32 | MP15 | P | all | 128 | 7.8 | -3.22 | -6.40 | -0.82 | -1.09 | -1.40 | 434 |  |
| 33 | MP15b | P | all | 158 | 82.9 | 0.94 | 5.60 | 3.34 | 1.76 | 1.72 | 232 |  |
| 34 | MP15c | P | all | 182 | 48.4 | 1.05 | -2.40 | 3.45 | 1.13 | 1.14 | 571 |  |
| 35 | MP16 | P | all | 111 | 69.4 | 2.47 | 5.60 | 4.87 | 2.26 | 2.37 | 115 | yes |
| 36 | MP17 | P | all | 614 | 16.1 | -2.23 | -6.40 | 0.17 | 0.05 | 0.00 | 1460 |  |
| 37 | MP18 | P | all | 208 | 22.6 | -2.73 | -10.40 | -0.33 | -0.29 | -0.27 | 637 |  |
| 38 | MP19 | P | open loc | 499 | 51.1 | -1.13 | 0.60 | 1.27 | 0.31 | 0.33 | 954 |  |
| 39 | MP19 | volVA (robustness) | open loc | 494 | 50.8 | -0.85 | 0.60 | 1.55 | 0.45 | 0.47 | 1023 |  |
| 40 | MP20 | P | all | 49 | 59.2 | 10.33 | 10.60 | 12.73 | 1.65 | 1.68 | 207 |  |
| 41 | MP21 | P | open loc | 323 | 54.2 | 2.10 | 2.60 | 4.50 | 1.69 | 1.74 | 455 |  |
| 42 | MP22 | P | all | 366 | 22.1 | -0.76 | -10.40 | 1.64 | 1.17 | 1.16 | 992 |  |
| 43 | MP23 | P | all | 713 | 10.4 | -2.73 | -6.40 | -0.33 | -1.09 | -1.10 | 2009 |  |
| 44 | MP24 | P | all | 687 | 8.9 | -3.56 | -6.40 | -1.16 | -2.78 | -2.69 | 2445 |  |
| 45 | MP25 | P | all | 171 | 18.7 | -3.83 | -6.40 | -1.43 | -1.76 | -1.70 | 654 |  |
| 46 | MP26 | P | all | 275 | 42.2 | -8.82 | -16.40 | -6.42 | -1.04 | -1.07 | 4003 |  |
| 47 | MP27 | P | all | 81 | 37.0 | -3.36 | -18.40 | -0.96 | 0.38 | 0.38 | 1280 |  |
| 48 | MP28 | P | all | 182 | 19.2 | -5.20 | -9.40 | -2.80 | -1.87 | -1.83 | 1073 |  |
| 49 | MP28 | bal5 | all | 14 | 28.6 | -2.11 | -8.90 | 0.29 | 0.17 | 0.16 | 64 |  |

Net and gross are ticks per trade; max drawdown is in ticks on cumulative net.

## Book descriptive statistics (explore period)

- **MP3**: orr_days = 497; initial_extreme_held = 0.207; book = initial extreme holds < 50% of the time
- **MP13**: n = 178; traded_beyond_va_first_90min = 0.826; closed_within_or_beyond_va = 0.775; book = next day beyond prior VA in first 90 min: 64% (T-bonds 86-87)
- **MP14**: n = 155; traded_beyond_va_first_90min = 0.600; closed_within_or_beyond_va = 0.742; book = 94% beyond VA in first 90 min; 97% closed within or beyond
- **MP14b**: n = 73; traded_beyond_va_first_90min = 0.726; closed_within_or_beyond_va = 0.795; book = 71% / 82%
- **MP25**: narrow_days = 189; next_range_above_median = 0.222; all_days_range_above_median = 0.487; book = narrow days come before big days
- **MP26**: n_days = 1324; over43 = {'n': 36, 'frac_next3_against': 0.3888888888888889}; under18 = {'n': 580, 'frac_next3_with': 0.4517241379310345}; middle = {'n': 708, 'frac_next3_with': 0.5084745762711864}; book = 0-18 trend continuation; 43+ price should move opposite

## Reading the result

45 eligible evaluations were tested at t >= 2.0 (one-sided p about 0.023 each), so about 1.0 would pass by chance alone if no hypothesis had any edge. That is why the confirm stage (t >= 2.5 on 2017-2021, frozen definitions only) exists. The confirm stage has not been run.

Observations on the explore results (no definitions changed): `reports/EXPLORE_NOTES.md`.

Profile parity against TradingView for the 3 latest sessions: `reports/PARITY_ES.md`.
