# Order flow on the OI-flush signal, and day/week range structure: results

Run 2026-09-23 in Claude Code on the 35 Binance USDⓈ-M perps named in `SPEC_value_area_tests.md`, with data
from `data.binance.vision`. Every number below comes from files in `orderflow/results/`.

## Bottom line

1. **The pre-registered value-area test fails completely.** V1, V2, V3, F1r and the X1 exit all fail the
   rule fixed in advance. The flush signal stays as it is.
2. **The replication agrees with the claude.ai thread.** There are 2,028 signals on the 9 Kraken coins,
   against your 1,968. Net per trade is +0.36% in 2022-23 (your +0.42%) and +0.53% in 2024-26
   (your +0.51%). The earlier footprint result reproduces too: "trapped sellers" is worse in both periods,
   with pooled t = -1.89 against your -1.7.
3. **The flush signal is real on coins it has never seen:** +0.25% per trade over 7,089 trades on the 26
   holdout coins, day-clustered t = 5.2. **But it depends on the regime.** The edge is concentrated in
   2023-24, it is negative in 2022, and it is roughly flat or negative since 2025. Over the most recent
   14 months (2025-07 to 2026-08) it is -0.09% per trade across all 35 coins.
4. **No day or week structure trade survived out of sample.** The best candidate was a fade: buy after two
   hourly closes below the prior-day low. It passed validation (+0.21% to +0.28% per trade, t 3.5 to 5.8),
   then lost -0.26% per trade in the one-shot vault.
5. **One structural effect held in all three samples, but only as a relative ranking.** Coins trading low
   in their developing-day range, or below the prior-day VAL, beat coins trading high over the next 24h
   (vault spread t = 2.8 to 3.2). In a falling market even the "good" side lost money outright. It is a
   market-neutral idea that has not been tested as a strategy, not an EV+ long.

## 1. Replication of the base signal

"USD-mode" could not mean OI valued in USD. That definition gives 3,163 non-overlapping signals, because a
-4.6% price move alone takes USD-valued OI down about 4.6%, so the OI filter barely binds. With OI in
contracts and one position per coin at a time, the count is **2,028 (+3%)**. That definition was chosen on
counts only, before any feature was computed, and is recorded in `SPEC_implementation_notes.md`.
"USD-mode" almost certainly meant USDⓈ-M futures.

| Cell | Signals | Net per trade | Your thread | Win rate | Day-clustered t |
|---|---|---|---|---|---|
| Dev 2022-23 (9 coins) | 917 | +0.36% | +0.42% | 55.9% | 3.3 |
| Dev 2024-26 (9 coins) | 1,111 | +0.53% | +0.51% | 53.9% | 3.5 |
| Holdout 2022-26 (26 new coins) | 7,089 | **+0.25%** | n/a | 51.3% | **5.2** |

## 2. Pre-registered value-area test (`SPEC_value_area_tests.md`): all fail

All 9,117 of 9,117 signals got footprints, rebuilt from raw aggTrades using only trades up to the signal
bar's close. Tercile cutoffs come from dev 2022-23.

| Feature | Dev 22-23 good / bad (diff) | Dev 24-26 good / bad (diff) | Holdout good / bad (diff) | Holdout day-t | Result |
|---|---|---|---|---|---|
| V1 value reclaim (close >= P1 VAL) | +0.05% n=483 / +0.70% n=434 (-0.65) | +0.48% n=694 / +0.60% n=417 (-0.12) | +0.10% n=3953 / +0.43% n=3136 (-0.33) | -1.20 | **FAIL** (wrong way in all three cells) |
| V2 room to prior POC (top third) | +0.68% n=306 / +0.06% n=306 (+0.62) | +0.22% n=377 / +0.74% n=449 (-0.52) | +0.10% n=1885 / +0.38% n=3036 (-0.28) | 1.55 | **FAIL** |
| V3 value migration (bottom third) | +0.02% n=306 / +0.13% n=306 (-0.11) | +0.66% n=323 / +0.37% n=395 (+0.29) | +0.58% n=2389 / -0.08% n=2026 (+0.66) | 0.73 | **FAIL** |
| F1r selling spread out (bottom third; judged on holdout only) | +0.31% / +0.02% (+0.29) | +0.92% / +0.21% (+0.71) | +0.46% n=2209 / +0.33% n=3044 (+0.13) | -0.71 | **FAIL** |

| Exit X1 (limit at POC0, else 24h) | TP hit rate | 24h daily Sharpe | X1 daily Sharpe | Result |
|---|---|---|---|---|
| Dev 2022-23 | 37% | 0.71 | 1.74 | better |
| Dev 2024-26 | 41% | 1.26 | 1.27 | better (barely) |
| Holdout | 41% | 0.62 | 0.58 | worse, so **X1 FAILS** |

The full table with every cell is in `results/SPEC_RESULTS.md`.

Counting your earlier footprint test, 8 order-flow features have now been tested on this signal (4
footprint, 4 value area), plus 37 day/week structure filters in the exploration below. **None of them
improves the flush trade.** Its edge does not appear to live in the footprint.

## 3. The flush signal through time

Net per trade by half-year (`results/flush_by_halfyear.txt`):

| Half | Dev 9 coins | n | New 26 coins | n |
|---|---|---|---|---|
| 2022H1 | +0.10% | 319 | -0.46% | 699 |
| 2022H2 | -0.31% | 244 | -0.49% | 640 |
| 2023H1 | +1.15% | 191 | +0.43% | 751 |
| 2023H2 | +0.92% | 163 | +1.24% | 719 |
| 2024H1 | +1.19% | 214 | +0.95% | 952 |
| 2024H2 | +0.53% | 234 | +0.73% | 972 |
| 2025H1 | +0.17% | 258 | -0.15% | 859 |
| 2025H2 | +0.72% | 220 | +0.04% | 719 |
| 2026H1 | +0.05% | 164 | -0.63% | 646 |
| 2026 Jul-Aug | -0.27% | 21 | +0.42% | 132 |

Day-clustered t is 2.3 to 3.8 in every half of 2023-24 on the new coins, and 2.9 to 3.3 on the dev coins
except 2024H2 (1.4). It is below 2 in every half of 2022 and from 2025 on. As a portfolio
(at most 10 open positions, 1/10 of capital each, first come first served), it made Sharpe 0.72 on dev
2022-23 and 0.79 on the validation window, with max drawdowns of -21% and -51%. Over 2025-07 to 2026-08
the same portfolio made Sharpe -0.84 and a max drawdown of -50%. **Before sizing up, treat the flush as a
regime trade, not a constant edge.**

## 4. Exploration: day and week range structure (`EXPLORATION_PROTOCOL.md`)

For every hourly bar on every coin, the structure engine (`of/structure.py`) computes:

- previous day and previous week high, low, POC, VAH and VAL;
- developing day and developing week open, high, low, POC, VAH, VAL and cumulative delta (from taker-buy
  volume on 1m bars);
- forward 4h, 12h and 24h returns, net of 0.14% and funding.

It uses only bars up to that bar's close.

The splits were fixed before any data was downloaded:

- **Discovery:** 9 dev coins, 2022-23. 152 looks, free exploration.
- **Validation:** the 26 new coins through 2025H1, plus the dev coins for 2024 to 2025H1. 57 looks, only for
  candidates that passed discovery.
- **Vault:** all 35 coins, 2025-07 to 2026-08. Opened once for 5 finalists.

All 215 evaluations are in `results/EXPLORATION_LEDGER.csv`.

**Discovery (dev coins, 2022-23).**

- **Market-profile rules lose in crypto.** The 80% rule loses (t -2.2 and -2.8). Open location, value
  migration and weekly failed auctions show nothing.
- **Breakout "acceptance" fails.** Two hourly closes beyond the prior-day high or low: t -4.7 and -5.0 as
  continuation trades. Fading it only breaks even per trade, because costs are paid on both sides.
- **No flush filter moves the flush trade** (37 features, all |t| < 1.8).
- **Screen, strongest effect:** location of the close in the developing-day range (t -3.6), followed by
  prior-day range location, 24h return and OI change.

**Validation (candidates frozen in `VALIDATION_CANDIDATES.md` before any validation data was read).**

| Candidate | New coins, per trade | Dev coins later, per trade | Pooled day-t | Result |
|---|---|---|---|---|
| A9L buy after 2 closes below prior-day low | +0.21% (9,147) | +0.28% (1,565) | 5.9 | pass |
| A9S short after 2 closes above prior-day high | -0.21% | -0.27% | 5.4 | fail (per-trade loss) |
| A6L new day low on a positive-delta bar | +0.02% | +0.02% | 4.2 | pass on paper (EV ~0) |
| A6S new day high on a negative-delta bar | -0.12% | -0.20% | 3.8 | fail |
| A9L with a BTC market filter (added after diagnostics) | 0.00% | -0.03% | 2.9 | fail |
| Screen: developing-day location, below prior-day VAL, distance to prior-day VAL, OI change | spreads t 3.3 to 5.4 | same sign | | pass as relative rankings |

**Vault, one shot (`results/exploration/vault.txt`).**

| Finalist | Vault result |
|---|---|
| A9L | **-0.26% per trade** (n=5,166). Per-day mean +0.58% (t 2.6). K=10 portfolio: CAGR -46%, Sharpe -1.30, max DD -60%. **Fails.** |
| A6L | -0.20% per trade (n=7,864). **Fails.** |
| Developing-day location, low minus high | spread +0.03% per trade, day-t 3.2. Good side -0.21% per trade in absolute terms |
| Below prior-day VAL | spread +0.11%, day-t 2.8. Good side -0.17% |
| Distance to prior-day VAL, low minus high | spread +0.09%, day-t 2.8. Good side -0.19% |

**What the exploration taught us.**

- **Per-trade and per-day results diverge for every mean-reversion idea here.** On crash days dozens of
  coins trigger at once and lose together. Single-coin breakdowns revert well, but you cannot tell at entry
  which kind of day it is. A BTC filter made it worse, so causal sizing cannot capture the per-day edge.
- **The structure effect that survives is cross-sectional.** Coins that are low in their range beat coins
  that are high. That is a long/short, market-neutral idea, not a directional EV+ trade.

## 5. What I would do next

- **Leave the flush signal unfiltered.** Size it knowing the edge depends on the regime. The only clean test
  of any regime rule now is forward data, because all history through 2026-08 has been looked at. So
  pre-register the rule first (for example, "trade only when BTC is above its 200-day average"), then
  paper-trade it from 2026-09.
- **One idea deserves its own spec:** a market-neutral range-reversal book. At a fixed hour, go long the
  third of coins lowest in their developing-day range and short the highest third. Hold 24h, with capped
  slots. It has three-sample support as a ranking, but it has never been run as a strategy. It too can only
  be tested forward.
- **Stop testing footprint filters on the flush.** Eight order-flow features have failed, and the
  structure filters show nothing either.

## 6. Data and reproducibility

| What | Where | Persists? |
|---|---|---|
| 1m klines (with taker-buy volume = per-minute delta), 5m OI, funding for 35 coins, 2021-12 to 2026-09 (about 3.5 GB raw, 4 GB parquet) | `data/binance/` (gitignored) | container only |
| aggTrades: 17,855 coin-days, roughly 300 GB | streamed through memory, never stored (the disk is 30 GB) | no |
| Flush signals (9,117 trades), per-signal P0/P1 value-area features, **50-row buy/sell volume profiles for P0 and P1 of every signal** | `results/flush_signals.csv`, `results/va_features.parquet` (12 MB) | **in git** |
| Ledger, round logs, validation, vault | `results/`, `results/exploration/` | in git |

To rebuild in a fresh session:

```bash
python orderflow/run_data.py        # ~15 min
python orderflow/run_structure.py   # ~3 min
python orderflow/run_spec.py signals
python orderflow/run_spec.py features   # ~1 h of aggTrades streaming
python orderflow/run_spec.py report
```

The vault refuses to reopen for the same IDs (`results/VAULT_OPENED.txt`).

**Process notes.**

- The OI-unit change is documented in `SPEC_implementation_notes.md`.
- A units bug in a speed-up of the structure engine (pandas 3 keeps millisecond timestamps) blanked the
  developing-session columns for 20 holdout coins. A stricter check caught it before any validation read,
  the frames were rebuilt, and a regression test was added. Discovery used frames from the original code.
- The ledger's columns were misaligned between log calls. It was repaired block by block, with values
  checked against the printed runs, and now uses a fixed schema.
- 15 unit tests pass, including a no-lookahead test for the aggTrades features.
