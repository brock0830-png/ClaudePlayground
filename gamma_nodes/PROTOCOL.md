# 0DTE gamma nodes: pre-registered protocol

**Status: committed before any data was downloaded or analysed.** The hash of the commit that adds this
file is written into `results/TEST_UNLOCKED` before the one-shot test runs. Any later change goes in
"Amendments" at the end, with its commit hash and reason, before the analysis it affects is run.

## 0. Question

On Unusual Whales' directionalized-volume heatmap, one 0DTE SPX strike sometimes shows far more gamma than
its neighbours (e.g. 7680 at 26.8B vs about 5B nearby on 2026-10-01). The observation is that price moves
toward such a node, touches it, then moves on to the next large node that forms, and that pins arrive late
and from below. Nobody knows what "meaningfully larger than usual" means, so the node definition is
**chosen on development data from the pre-registered grid below, frozen, and then tested once** on held-out
data.

## 1. Hypotheses

Every comparison is against a control (§6). Only the difference between node and control counts.

| id | hypothesis | primary measure |
|---|---|---|
| H1 attraction | Price touches a qualifying node more often, and sooner, than a non-node strike at the same distance at the same moment. | P(touch within 60 min), node minus mirror control. Secondary: 30 min, by the close, time to touch. |
| H2 node to node | After a node is touched, the next node that qualifies is reached faster than its control. | Same measures as H1, on post-touch nodes only. |
| H3 late touch | When the dominant node is touched after 15:30, settlement lands on it more often than the option-implied probability at the touch. | Realised minus implied P(settle within ±2.5 pts of the node). Also reported: "through" and "back away" frequencies. |
| H4 where pins land | Settlement lands on the final dominant node more often when price approaches from below than from above ("pins arrive late, from below"). | Realised minus implied pin rate, from below vs from above. |
| H5 tradeability | A butterfly centred on the node, entered when the node first qualifies, has positive expected P&L after costs and beats the same butterfly centred on spot and on the control strike. | Mean P&L per trade (USD per 1-lot fly) and paired differences vs both baselines. |

H1 is the primary scientific hypothesis. H5 decides the verdict (§9). H2-H4 are secondary and are reported
with confidence intervals but no multiplicity correction.

## 2. Data

### 2.1 Sources

| what | source | used for |
|---|---|---|
| Full Tape | UW `GET /api/option-trades/full-tape/{date}`, one zip per trading day | rebuilt heatmaps, option quotes for P&L, implied probabilities |
| Live snapshots | `collector/collect.py`, every 5 min, 09:35-16:00 ET, from 2026-10-02 | ground truth for the step-3 validation gate only |
| SPX 1-minute price | UW `GET /api/stock/SPX/ohlc/1m?date=D` | spot S(t), touches, approach direction |
| SPX settlement | UW `GET /api/stock/SPX/ohlc/1d` regular-session close | settlement of SPXW PM 0DTE options |

Options P&L comes **only** from Full Tape NBBO bid/ask (plus the cash-settlement value at expiry). It never
comes from a pricing model. The Black-Scholes gamma in §3 is only one of the rebuild variants used to
reproduce UW's exposure numbers. It is never used to price a trade.

### 2.2 What is stored

Per trading day, rows with `underlying_symbol` in {SPX, SPXW, XSP} (the root also comes from
`option_chain_id`) and `expiry` ∈ {trade date, next trading day}. Only these columns are kept: `id,
executed_at, underlying_symbol, option_chain_id, expiry, option_type, strike, price, size, nbbo_bid,
nbbo_ask, underlying_price, implied_volatility, delta, gamma, open_interest, volume, ask_vol, bid_vol,
mid_vol, no_side_vol, multi_vol, canceled, tags, report_flags`. They are written to
`DATA_ROOT/tape/YYYY-MM-DD.parquet` and logged in `MANIFEST.csv`. Next-day-expiry rows are stored for
possible later work and are **not** used in any pre-registered test.

### 2.3 Data gates (fail → STOP and report; never substitute)

- **D1 history window.** The probe reports the earliest available tape date, expected about 730 trading
  days back.
- **D2 per-day ingest.** The filtered row count must equal the number of source rows matching the filter,
  counted independently in a second pass. All kept columns must be present, `executed_at` must have no
  nulls, and the file must re-read with the same row count and checksum. A day that fails is retried
  once, then listed as missing.
- **D3 price path.** The SPX 1-minute bars must cover 09:30-16:00 (13:00 on early-close days) with at
  most 5 missing minutes. The median |bar close − median tape `underlying_price` of SPXW trades in that
  minute| must be ≤ 1.0 index point. Failing days are excluded and listed. If more than 5% of days fail,
  STOP.
- **D4 storage.** The projected size for 60 days and for the full history is computed from the first 3
  days. If it exceeds the free Drive space or 100 GB, STOP and ask.
- **D5 live coverage.** Validation uses only days where at least 90% of the 78 live slots are complete.

### 2.4 Order of work

1. Pilot: the most recent 60 trading days of tape, ending 2026-10-01.
2. Live collection from 2026-10-02; tape for those days as it becomes available (after 20:00 ET).
3. Step-3 validation (§4) on days covered by both.
4. Only if step 3 passes: back-fill earlier tape, up to the history window and the storage gate.
5. Fix the analysis window and the dev/test split (§7). Development on dev only. Freeze. Then the
   one-shot test.

No outcome (touch, settlement, P&L) is computed for any day before step 5. Steps 1-4 look only at data
quality and at rebuild-vs-UW agreement.

## 3. Rebuilt 5-minute strike profile (step 3)

**Chain.** SPXW options with `expiry` = trade date (PM-settled 0DTE). SPX-root AM-settled monthlies
expire at the open and are excluded. An XSP profile is built the same way and stored but is not used in
the grid.

**Snapshot times.** t ∈ {09:35, 09:40, …, 16:00} ET (78 per day; up to 13:00 on early-close days). Only
trades with `executed_at` ≤ t that are not canceled are used. Spot S(t) is the close of the SPX 1-minute
bar that ends at t.

**Dollar gamma per trade or position:** `gamma × contracts × 100 × S² × 0.01`, summed by strike.

**Views.**
- **Directionalized (D, primary):** each trade is classified as ask side (the dealer sold, contributing
  −) or bid side (the dealer bought, contributing +). This gives four buckets: call-ask, call-bid,
  put-ask, put-bid. Net = the sum of the four, as UW defines it.
- **Open interest (O):** start-of-day `open_interest` per contract × gamma, with calls + and puts −
  (UW's convention).
- **Volume (V):** unsigned traded contracts × gamma, with calls + and puts −.

**Rebuild variants** (all logged; the variant used downstream is the one that best matches UW on the
validation days, and it must pass the gate):

| dimension | options |
|---|---|
| side rule (D only) | `tag`: UW's own side tag in `tags` · `quote`: x = (price − bid)/(ask − bid); ask side if x ≥ 0.75, bid side if x ≤ 0.25, otherwise mid; invalid or crossed quotes count as no side |
| mid trades (D only) | `exclude` · `split` (half to the ask bucket, half to the bid bucket). By construction both give the same **net** profile, so they differ only in the per-bucket comparison. |
| gamma | `G1` gamma and spot at trade time (from the tape row) · `G2` Black-Scholes gamma recomputed at t from S(t), the contract's latest IV at or before t, τ = minutes to the close / 525,600, r = q = 0 · `G3` the contract's latest observed tape gamma at or before t, with S(t)² |

D has 2 × 2 × 3 = 12 variants, O has 2 (G2, G3; G1 doesn't apply), V has 3. That makes 17 rebuild
variants.

Per-bucket sign conventions are read from UW's live response on the first collected day. This is a
convention match, not a tuned parameter, and it is logged.

## 4. Validation gate (must pass before step 5)

On every day that has both tape and live data (D5), each complete live snapshot is compared with the
rebuilt profile at the snapshot's request time, using the strikes within ±1.5% of spot (UW's snapshot
price; a strike missing on one side counts as 0):

- **rank agreement:** Spearman correlation of the net values across those strikes;
- **top node:** the strike with the largest |net| among those strikes, rebuilt vs UW; an exact match is
  required (matches within ±5 pts are also reported).

**Pass bar, per view, pooled over all validation snapshots:** top-node exact match in ≥ 80% of snapshots
**and** median Spearman ≥ 0.70, from at least 5 qualifying days and 300 snapshots.

- D (primary) fails for every variant → **STOP and report.** No back-fill, no tests.
- O or V fails → that view is dropped from the grid and reported. It is not substituted.

Results go to `results/validation.md`; every variant goes to `results/log.csv`.

## 5. Node definitions (step 4): the grid

At each snapshot t, using view v's net profile g_k over the strikes N(t) within ±1.5% of S(t):

- **Size** (leave-one-out, so a huge node doesn't inflate its own spread): with m_k and s_k the mean and
  sample standard deviation of |g_j| over j ∈ N(t), j ≠ k,
  - z-score: (|g_k| − m_k)/s_k ≥ **2, 2.5, 3**; or
  - ratio: |g_k| / median_{j≠k}|g_j| ≥ **3×, 5×, 10×**.
- **Dominance:** k has the largest |g| in N(t), and |g_k| ≥ **1.5×** or **2×** the second largest. So at
  most one node per snapshot. Its sign is the sign of g_k.
- **Persistence:** the same strike meets size and dominance in **2, 3 or 6** consecutive snapshots (10,
  15 or 30 minutes counting the first). It **qualifies** at the last of those snapshots. That is the
  first moment the data shows it, so there is no look-ahead.
- **Distance (fixed filter):** at the moment it qualifies, 0.2% ≤ |K − S(t)|/S(t) ≤ 1.0%. A strike that
  first qualifies outside this band is ignored for the rest of the day.
- **Sign:** positive and negative nodes are analysed separately.
- **One event per strike per day.** Events for H1, H2 and H5 must qualify by **15:00 ET** (12:00 on
  early-close days).

**Grid (60 definitions):**
- View D: size (6) × dominance (2) × persistence (3) = **36**
- Views O and V: size {z ≥ 2.5, ratio ≥ 5×} × dominance (2) × persistence (3) = **12 each**

Each definition is evaluated for both signs, which gives 120 (definition, sign) units. Every unit's dev
results go to `results/node_grid_log.csv` and `results/log.csv`, including units with too few events.

## 6. Tests (step 5)

**Touch.** Price touches strike K at the first 1-minute bar starting at or after the reference time whose
low ≤ K ≤ high.

**Controls, at the same moment as each event:**
- **Mirror control:** the listed strike nearest to 2·S(t) − K, i.e. the same distance on the other side
  of spot. If it is itself a node under the same definition, the event is dropped from paired comparisons
  and logged.
- **Random-distance control:** a strike at a distance drawn uniformly from 0.2-1.0%, on a random side
  (seed 20261001), rounded to the nearest listed strike.

1. **Attraction (H1).** Touch within 30 min, within 60 min, and by the close, plus time to touch
   (censored at the close; reported as restricted mean minutes). Node minus each control, paired by
   event.
2. **Node to node (H2).** After a node is touched at t1, take the next different node that qualifies at
   t2 ∈ (t1, 15:00]. Use the same measures as H1 from t2, vs its mirror control.
3. **Late touch (H3).** Take the first touch after 15:30 of a strike that is a currently qualifying node
   (it qualified at or before the touch). Approach direction is the close of the 1-minute bar before the
   touch bar relative to K. Settlement S_T is classified as *on* (|S_T − K| ≤ 2.5), *through* (beyond
   K + 2.5 in the approach direction), or *back away* (beyond 2.5 on the approach side). Implied
   probabilities come from call mids at the touch (latest quote at or before, ≤ 60 s old):
   P(S_T > x) ≈ (C(x − 2.5) − C(x + 2.5))/5 for x = K ± 2.5; P(on) is the difference. Puts are reported as
   a robustness check.
4. **Where pins land (H4).** The final dominant node is the latest qualifying node at or before the 15:55
   snapshot. Approach is from below if the SPX price at 15:30 < K, otherwise from above. The report gives
   the distribution of S_T − K, the pin rate (|S_T − K| ≤ 2.5) minus the implied P(on) at 15:30, from
   below vs from above, and the time of the first touch of K after 15:00.
5. **Tradeability (H5).** Entry is at the snapshot where the node first qualifies. The fly is centred on
   K with wing width w ∈ {10, 25} points, made of calls if K > S(t) and of puts if K < S(t). Each leg is
   priced from the latest Full Tape NBBO at or before the entry or exit time; a quote older than 60 s,
   crossed, or with ask ≤ 0 makes the trade **skipped and logged**. Bought legs pay mid + 25% of the
   spread; sold legs receive mid − 25%. Fees are $1.00 per contract per transaction, with no fee at cash
   settlement. P&L is in USD for one fly (× 100 multiplier).
   Exits:
   - (a) at settlement (intrinsic value at S_T);
   - (b) at the first touch of K (if never touched, held to settlement);
   - (c) at 15:45.

   Baselines use the same fly, width and exit, entered at the same moment, centred on (i) the listed
   strike nearest spot and (ii) the mirror control strike. For a baseline, "touch" in exit (b) means a
   touch of its own centre.
   The report gives, per trade: EV, hit rate (P&L > 0), profit factor, and worst losing streak, plus
   per-month figures.

## 7. Development / test split

- **Analysis window:** every trading day with tape from the earliest day back-filled (bounded by the
  history window and the storage gate) to the last trading day before the validation gate passes, minus
  days excluded by D2/D3.
- Sorted by date, the first ⌊2N/3⌋ days are **development** and the rest are **test**. The split date is
  written to `results/split.json` and committed before any step-5 code reads data.
- The analysis code refuses any test-period date unless `results/TEST_UNLOCKED` exists.
- **Selection on development only.** A (definition, sign) unit is eligible if it has ≥ 40 dev events.
  Eligible units are ranked by the lower bound of the month-clustered 95% CI of the H1 60-minute
  touch-rate difference vs the mirror control. **At most 3 units** are frozen. For each frozen unit, the
  trade variant (w, exit) with the highest dev mean P&L is frozen with it. The frozen rules go to
  `results/frozen_node_rules.md` and are committed. Then `results/TEST_UNLOCKED` is written with this
  protocol's commit hash and the frozen-rules commit hash, and the test is run **once**.

## 8. Statistics

- **Month-clustered bootstrap** on every pooled number: resample calendar months with replacement,
  10,000 replicates, seed 20261001, percentile 95% CI. Paired differences are resampled as pairs.
- **Every variant tried** (rebuild, validation, grid unit, test, trade variant, including failures and
  insufficient-sample cases) is one row in `results/log.csv`.
- **Deflated Sharpe ratio** (Bailey & López de Prado, 2014) on per-trade P&L. N is the number of
  trade-family rows in `results/log.csv`; the result with N = all rows is also reported. V[SR] is the
  variance of per-trade Sharpe across logged trade variants. Skew and kurtosis come from the trades.
- **Multiplicity in the verdict:** Holm adjustment across the ≤ 3 frozen rules.

## 9. Verdict rules (one-shot test, frozen rules only)

- **Trade it:** for at least one frozen rule, all of the following hold:
  - ≥ 30 test trades;
  - mean P&L > 0 with Holm-adjusted 95% month-clustered CI lower bound > 0;
  - the paired difference vs **both** baselines has CI lower bound > 0;
  - deflated Sharpe ≥ 0.95.
- **Paper trade it:** the point estimates are positive and beat both baselines, but at least one of the
  above fails.
- **Don't trade it:** otherwise.

The H1-H4 results are reported regardless of the verdict.

## 10. Deliverables

`collector/` · `results/data_coverage.md` · `results/validation.md` · `results/node_grid_log.csv` ·
`results/frozen_node_rules.md` · `results/log.csv` · `results/report.md` (numbers for each of the five
tests and a plain-English verdict with the reason). Data lives only on Google Drive under `DATA_ROOT`. It
is never committed to GitHub.

## Amendments

(none)
