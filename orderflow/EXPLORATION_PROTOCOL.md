# Exploration protocol: order-flow structure on day and week ranges

Committed before any data was downloaded. This is **not** the pre-registered test.
`SPEC_value_area_tests.md` is that, and it runs first and unchanged. This file covers the open-ended
search the client asked for: "find repeatable alpha and an EV+ trade in sample and out of sample"
using order-flow structure on the developing day, previous day, previous week and developing week.

Because it is a search, its protection against overfitting is the data split and the trial
ledger, not a fixed hypothesis list.

## Data

Binance USD-M futures for the same 35 coins as the spec, 2021-12 to 2026-09:

- 1m klines with taker-buy volume, so every minute has its aggressive buy volume, sell volume
  and delta (a "footprint-lite" at 1-minute resolution).
- OI value (5m `metrics`) and funding.
- aggTrades only where the spec needs them.

Profiles for day/week structure are built from 1m bars. Each bar's volume is spread evenly over
the rows its high-low range touches, with 50 rows per profile and a 70% value area, using the same
VA algorithm as the spec.

Sessions are the UTC day (00:00) and the UTC week (Monday 00:00).

## Splits (fixed now)

| Split | Coins | Dates (signal bar) | Use |
|---|---|---|---|
| DISCOVERY | 9 dev coins | 2022-01-01 to 2023-12-31 | free exploration, any number of looks |
| VALIDATION | 26 holdout coins, and the 9 dev coins | holdout 2022-01-01 to 2025-06-30; dev 2024-01-01 to 2025-06-30 | only for candidates that pass the discovery gate; reported per part and pooled |
| VAULT | all 35 coins | 2025-07-01 to 2026-08-31 | one look, finalists only (at most 5), reported whatever the result |

The spec test separately uses the holdout coins over all dates for V1-V3, F1r and X1 only. It does not
look at any structure feature below.

## Trade template and costs

Decision at the close of an hourly bar. Entry at the next bar's open. Costs are 0.14% round trip,
plus funding over the hold (longs pay positive funding; shorts receive it). Default hold is 24h. Any
other exit (structural target, stop) is a separate trial row.

## Families to look at (starting list; the search may add more, and every addition is logged)

- **C, structure screen.** At fixed decision times (00:00 and 12:00 UTC, which gives
  non-overlapping 24h outcomes per time slot), compute the features and the next-24h net return. Report
  the top-third minus bottom-third spread for each feature (cutoffs from DISCOVERY). Features:
  - Location of the close within the previous day's range, previous week's range, developing day's range and
    developing week's range.
  - Distance from the close to the previous-day POC, VAH and VAL, the previous-week POC, VAH and VAL,
    and the developing day and week POC, in ATR.
  - Value migration: developing POC minus previous POC (day and week).
  - Delta: day and week cumulative delta / volume, and last-4h delta / volume.
  - Controls that are not order flow: 24h and 4h return, 24h OI change, funding.
- **A, event trades.** Each is mirrored long and short.
  - A1: failed break of the previous-day low or high (trades through it, then an hourly close back
    inside), first occurrence per day.
  - A2: the same for the previous-week low or high, first occurrence per week.
  - A3: acceptance beyond the previous-day low or high (2 consecutive hourly closes outside), as the
    continuation twin of A1.
  - A4: the 80% rule. The day opens outside the previous-day VA, then 2 consecutive hourly closes back
    inside it. Trade toward the opposite VA edge.
  - A5: open location. The day opens above the previous-day VAH (long) or below the VAL (short).
  - A6: delta divergence. A new session low made on a bar with positive delta (long); mirrored for
    highs.
  - A7: value migration by 12:00 UTC. The developing POC is above the previous-day VAH (long) or
    below the VAL (short).
  - A8: the weekly 80% rule.
- **B, OI-flush filters.** Structure as a filter on the base flush signal. The flush low swept the
  previous-day low or the previous-week low. Signal close reclaimed it. Position within the
  previous-week range. Close vs the previous-day VAL and the developing-week VAL. Flush-window delta
  and day delta.

## Gates

- DISCOVERY to VALIDATION: day-clustered t >= 2.0 for the tested quantity (mean net for an event trade;
  good-minus-bad for a filter or screen feature), with the sign stated in the trial ledger.
- VALIDATION pass: same sign, and day-clustered t >= 2.0 on the pooled validation set, with
  both parts (new coins, dev coins later) the same sign.
- An **EV+ trade** claim needs mean net > 0 after costs in DISCOVERY, VALIDATION and VAULT, and a
  day-clustered t >= 2.5 on VALIDATION and VAULT pooled. Anything short of that is reported as
  in-sample only.

## Ledger

Every evaluated variant is one row in `orderflow/results/EXPLORATION_LEDGER.csv`, with family, id,
parameters, split, n, signal days, mean net, day-clustered t and timestamp. That includes the
variants that go nowhere. The final report states the number of discovery trials, so any
surviving t can be read against it.
