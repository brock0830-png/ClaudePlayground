# Implementation notes for SPEC_value_area_tests.md

Written and committed **before any data was downloaded or any test was run**. They cover the points the
spec leaves open. None of them changes a feature, a direction, a cutoff rule or the pass rule.

## Base signal (replication)

- Price: 1h bars resampled from Binance USD-M futures 1m klines (`data.binance.vision`, monthly files).
- OI: `sum_open_interest_value` (USD) from the Binance `metrics` daily files (5-minute stamps). The OI of
  bar t is the latest stamp at or before the bar's close (t+1h) and no older than 15 minutes. Otherwise
  it's missing, and so is the signal.
- Signal bar t: `close[t]/close[t-24h] - 1 <= -4.6%` and `oi_usd[t]/oi_usd[t-24h] - 1 <= -1.8%`.
  Signal bars run from 2022-01-01 to 2026-08-31 (UTC).
- Trade: entry at the open of bar t+1h, exit at the open of bar t+25h.
  `net = exit/entry - 1 - 0.14% - sum(funding rates stamped in [entry, exit))`.
- Dedup: three rules are counted on the 9 dev coins: every signal bar, first bar of each run, and
  one position per coin (non-overlapping 24h trades). **The rule whose count is closest to 1,968 is the
  signal definition.** The choice is made on counts only, before any feature or return is looked at,
  because its purpose is to match the trades used in the claude.ai thread. All three counts are reported.

## Profiles and features

- Volume is aggTrades `quantity` (base units), as in `footprint_test.py`.
- Row of a trade at price p: `min(floor((p - L) / (H - L) * 50), 49)`.
- POC ties: the row nearest the middle of the range; if still tied, the lower row.
- Value-area ties (row above and row below have equal volume): take the row above. If one side is
  exhausted, take the other. VAL = lower edge of the lowest VA row; VAH = upper edge of the highest;
  POC price = midpoint of the POC row.
- P0 = trades in [t-29h, t-5h); P1 = trades in [t-5h, t+1h). "Signal close" = close of the 1h
  signal bar (= last trade before t+1h).
- ATR(14): Wilder smoothing (RMA) of true range on the 1h bars, value at the signal bar (includes the
  signal bar's own true range).
- Signals with a missing aggTrades day or fewer than 100 trades in P0 or P1 are dropped. The count
  is reported.
- The earlier F1-F4 (`footprint_test.py`) are recomputed on P1 for the dev coins as a
  replication check on the footprint side. They are **not** re-judged.

## Pass-rule arithmetic

- Terciles: `q1, q2 = quantile(1/3, 2/3)` of the feature over dev 2022-23 signals. "Top third" =
  `> q2`, "bottom third" = `<= q1`, as in `fp_analyze.py`. Cutoffs are frozen for every other cell.
- good-minus-bad in a cell = difference of trade-level mean `net`.
- Day-clustered t = Welch t of good-minus-bad on per-day means (signals on the same UTC calendar day of
  the signal bar averaged into one observation), as `diff_t` in `fp_analyze.py`.
- Holdout cell = all 26 holdout coins, all signal bars 2022-01-01 to 2026-08-31. Coins listed later
  contribute from their first data.

## X1 exit

- A limit sell at POC0 is placed at entry. It fills at POC0 at the first 1m bar in [entry, entry+24h)
  whose high is >= POC0. If POC0 is at or below the entry price, it fills at the entry price at entry.
  If it doesn't fill, the exit is the plain 24h exit.
- Same 0.14% round-trip cost. Funding is charged for stamps in [entry, fill).
- Daily-P&L Sharpe: fixed notional per trade, each trade's net booked on its UTC exit day, calendar days
  with no exits = 0, from the cell's start to the later of its end and its last exit. Annualized with
  sqrt(365). The same definition is used for the 24h exit. Total return = sum of trade nets.

## Deviation recorded after the replication count (before any feature or return was computed)

The notes above fixed OI = `sum_open_interest_value` (USD). The first thing run on real data was the
signal count on the 9 dev coins (counts only):

| OI measure | every bar | first bar of run | non-overlap | (extra: first-of-run then non-overlap) | (extra: 48h cooldown) |
|---|---|---|---|---|---|
| USD value (`sum_open_interest_value`) | 30,200 | 5,674 | 3,163 | 2,963 | 2,491 |
| contracts (`sum_open_interest`) | 16,473 | 3,534 | **2,028** | 1,950 | 1,726 |

No USD-value rule comes near 1,968. In USD value, a -4.6% price move by itself takes OI value down about
4.6%, so the -1.8% OI filter barely binds. With OI in contracts and one position per coin, the count is
2,028 (+3%). "USD-mode" in the thread most likely meant Binance **USDⓈ-M** futures, not USD-valued OI.

**Signal definition used: OI in contracts (`sum_open_interest`), non-overlap dedup.** Per the rule above,
this is the closest of the three pre-listed dedup rules, now applied over both OI measures. It was
chosen on counts only. The extra variants were counted for information and not used.
