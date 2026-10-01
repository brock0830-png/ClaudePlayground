# Phase 4 report: stress tests of P2A and P3B before real money

- **Pre-registration:** `PROTOCOL_P4.md`, commit `5434a3d`, recorded in `results/p4/TEST_UNLOCKED` before any
  fresh ETF or single-stock data was loaded. Every test script checks that lock and refuses to run twice.
- **Frozen rules:** P2A and P3B were unchanged (`results/p3/frozen_candidates.json`), run by the unchanged
  Phase 3 engine.
- **Ledger:** `results/p4/log.csv` has 78 rows, failures included.
- **Cumulative variants for deflated Sharpe:** 12,514 (Phase 1) + 640 (Phase 2) + 258 (Phase 3) + 78
  (Phase 4) = **13,490**.
- **Scope:** stocks, ETFs and futures only. No options were modeled or tested.
- **Primary metric:** excess return per trade over random entries in the same market, with the same number of
  trades, the same holding period and the same costs (1,000 draws). Every pooled number has a month-clustered
  bootstrap 95% CI (10,000 draws).

## Bottom line

**P2A passed its hardest test yet.** Frozen since Phase 2, it beat random entries on **15 of 15** untouched
ETFs:
- seven US sector ETFs and eight country ETFs, 5,116 trades, 1997-2026;
- **+0.45% per trade over random entries**, CI +0.18% to +0.72%;
- it holds with high-VIX slippage and with next-morning fills.

**What changes before real money is the size.** A crash bootstrap puts P2A's 99th-percentile drawdown at
**31.5% of the position's notional**. The old guidance of 1 MES per $25-35k means accepting a 35-50% drawdown
in a 1-in-100 path. At a 20% drawdown tolerance it is **1 MES per ~$61k** (or $0.61 of SPY per $1 of
account). Use MES for accounts that size allows, and SPY shares below it.

**P3B failed every test that would justify trading it:**
- the trend gate makes it worse;
- on 937 point-in-time S&P 500 stocks, delisted names included, its excess CI just touches zero;
- since 2020 its edge has faded everywhere, in index ETFs, country/sector ETFs and stocks alike;
- next to P2A it mostly doubles up on the same trades (daily P&L correlation 0.93+ when both are open) and
  raises drawdown more than return.

Keep logging it. Don't trade it.

| Test | Result | Verdict | Line |
|---|---|---|---|
| A1 logger | built; reproduces the 2026-09-30 SPX 0.906 / SPY 0.886 scores; first rows logged | tool | **Paper trade it:** run it daily |
| A2 crash stress / sizing | P2A DD p99 = 31.5% of notional; losing streak p99 = 9 trades | descriptive | **Size it:** ≤ 1 MES per $61k (20% tolerance) |
| A3 P2A on 15 fresh ETFs | +0.45% excess per trade (CI +0.18..+0.72), 15/15 markets | **PASS** | **Trade it** (P2A, at the A2 size) |
| A4 execution timing | close vs next open vs ES 18:00: differences < 0.1%, CIs span 0 | descriptive | Execution time doesn't matter; keep ES at 18:00 |
| A5 vehicle | MES best after tax (+0.63% vs SPY +0.53% per trade at 1x) | decision rule | **MES** at ≥ $61k accounts, **SPY shares** below; no 2x |
| B1 P3B trend gate | gated − ungated = −0.08% (CI −0.22..+0.04) | **FAIL** | **Don't trade it** (no gate) |
| B2 P3B decay | fade since 2020 is within-cell (VIX > 25 signals turned negative), in every asset group | descriptive | Explains why P3B is off |
| B3 P3B threshold | 0.88-0.92 is a plateau on dev data (all CIs > 0) | **PASS** | The threshold isn't fragile; it doesn't rescue P3B |
| B4 P3B on PIT stocks | +0.24% excess (CI −0.002..+0.49); ex-earnings +0.25% (CI −0.002..+0.51) | **FAIL** (both) | **Don't trade it** on single stocks |
| B5 P3B with P2A | 55-59% overlap; ES return/max-DD 5.5 combined vs 6.6 P2A alone | **FAIL** | **Don't trade it** alongside P2A; log only |

## A. P2A

### A1. Forward paper-trade logger

- **Script and log:** `scripts/p4_signal_logger.py` writes `results/live/signals_log.csv`. The run command and
  cron line are in `results/live/README.md`.
- **What it does:**
  - Pulls Yahoo daily bars (no key needed) for ES, SPX, SPY, DIA, IWM and VIX.
  - Drops any unfinished bar.
  - Computes IBS, VIX and the P3B score, and replays the frozen rules over three years of history to know
    whether a trade is already open.
  - Appends one row per (date, market, system). It never rewrites the file and skips rows already logged.
- **Check:** for 2026-09-30 it gives SPX score **0.9056** (P3B signal) and SPY **0.8862** (no signal),
  matching what you saw.
- **First rows (2026-09-30):** P3B fired on SPX, DIA and IWM. P2A was quiet (VIX 16.3).
- **Unit-tested:** a signal is followed by "in position" the next session, and earlier rows are never altered.

### A2. Crash stress and sizing (`results/p4/sizing_table.md`)

- **Method:** daily mark-to-market P&L for 2013-01 to 2026-09, block-bootstrapped by calendar month,
  10,000 paths, fixed size. ES uses MES costs.
- **Use the % table** at the end of `sizing_table.md`, not the pre-registered table in points (see
  Corrections).

| System (ES, % of notional) | Trades | Hist. max DD | DD p50 | DD p95 | DD p99 | Losing streak p50 / p95 / p99 | Worst month |
|---|---|---|---|---|---|---|---|
| P2A | 153 | 22.1% | 20.5% | 26.2% | **31.5%** | 4 / 7 / 9 | −7.3% |
| P3B | 111 | 19.7% | 20.0% | 34.5% | 42.9% | 4 / 7 / 8 | −8.9% |
| P2A + P3B (1 unit each) | 264 | 38.8% | 32.2% | 48.2% | 57.5% | 6 / 9 / 12 | −14.1% |

**Sizing at a 99th-percentile drawdown of 15% / 20% / 25% of the account.** ES is 7,750, so 1 MES is $38,750
of notional.

| | 15% | 20% | 25% |
|---|---|---|---|
| P2A: account per MES | $81k | **$61k** | $49k |
| P2A: SPY $ per $1 of account (SPY's own P2A, DD p99 32.7%) | 0.46 | **0.61** | 0.77 |
| P3B: account per MES | $111k | $83k | $66k |
| P2A + P3B: account per MES (each) | $149k | $111k | $89k |

**Trade it at this size.** A $100k account holds 1 MES of P2A at a 20% tolerance. A $50k account holds no MES
at 15-20% tolerance; trade about $30k of SPY instead (0.61 × $50k).

### A3. Fresh-market test (pass/fail): **PASS**

Frozen P2A ran market-on-close on XLV, XLY, XLP, XLI, XLB, XLU, XLRE, EWZ, EWA, EWC, EWY, EWT, FXI, INDA and
EWW, from each fund's 253rd session to 2026-09-29.

| | Trades | Raw per trade (CI) | **Excess over random (CI)** | PF | Markets with positive excess |
|---|---|---|---|---|---|
| Base costs | 5,116 | +0.61% (+0.34..+0.88) | **+0.45% (+0.18..+0.72)** | 1.50 | **15/15** |
| High-VIX slippage | 5,116 | +0.47% | +0.36% (+0.09..+0.64) | 1.36 | 15/15 |
| Next-open entry | 5,116 | +0.49% | +0.33% (+0.07..+0.59) | 1.37 | 15/15 |

- **Per market** (excess per trade / random-entry percentile):
  - US sectors: XLV +0.31 / 99, XLY +0.54 / 100, XLP +0.38 / 100, XLI +0.34 / 99, XLB +0.41 / 99,
    XLU +0.18 / 92, XLRE +0.05 / 57 (122 trades, from 2016).
  - Countries: EWZ +0.67 / 99, EWA +0.72 / 100, EWC +0.30 / 98, EWY +0.66 / 100, EWT +0.58 / 100,
    FXI +0.52 / 98, INDA +0.44 / 97, EWW +0.44 / 99.
- **By decade** (excess per trade): 1990s +0.29%, 2000s +0.33%, 2010s +0.78%, **2020s +0.38%**. No fade.
- **Worst single trades:** −27.8% (EWZ and EWW, October 2008) and −24.9% (EWZ, March 2020). Size for
  them.
- **Deflated Sharpe** with 13,412 cumulative trials at the time of the run: about 0 (per-trade Sharpe 0.14
  against an expected maximum of 0.26 for 13,412 random tries). That yardstick asks whether the best of
  13,412 tries could look this good by luck. P2A was not picked from this test: it was frozen in Phase 2 and
  has now been confirmed on 22 untouched ETFs, on ES 2020-2026, and on 19 years of older SPY data. I read the
  DSR as a warning about the research process, not as evidence against P2A.

**Line: trade it**, at the A2 size, with the paper log running alongside.

### A4. Execution realism (descriptive)

Paired comparison on the same signals; each cell is the average return per trade.

| Signals | Period | 16:00 close | Next 09:30 open | ES 18:00 | Open − close (CI) | ES − close (CI) |
|---|---|---|---|---|---|---|
| SPY bar | 1994-2026 (475) | +0.68% | +0.65% | | −0.03% (−0.13..+0.07) | |
| SPY bar | 2013-2026 (149) | +0.99% | +0.91% | +0.95% | −0.08% (−0.26..+0.12) | −0.04% (−0.12..+0.04) |
| SPY bar, VIX > 25 | 2013-2026 (61) | +1.39% | +1.39% | +1.38% | +0.00% | −0.00% |
| SPX bar | 1994-2026 (479) | +0.46% | +0.48% | | +0.02% (−0.09..+0.12) | |
| SPX bar | 2013-2026 (147) | +0.65% | +0.72% | +0.64% | +0.07% | −0.01% |

- **When you fill barely matters.** No difference is distinguishable from zero, and the gap does not widen
  when VIX > 25.
- **Which bar you read matters more.** SPY's and SPX's P2A signal days agree only 56% of the time. On
  1994-2026, SPY-bar signals earned +0.68% per trade and SPX-bar signals +0.46%. Pick one source and keep
  it. For ES, use the ES session bar the system was built on.

### A5. Vehicle comparison (no options)

The same 153 ES P2A signals, 2013-2026. MES enters at 18:00; SPY at the next 09:30 open. Per $ of capital,
per trade:

| Vehicle | Pre-tax (CI) | Financing / interest | Tax rate | **After tax** |
|---|---|---|---|---|
| MES, 1x notional (capital in T-bills) | +0.86% (+0.48..+1.24) | +0.02% T-bill income | 26.8% (Sec. 1256 60/40) | **+0.63%** |
| SPY shares, 1x | +0.84% (+0.45..+1.24) | none | 37% (all short-term) | +0.53% |
| MES, 2x | +1.69% | +0.02% | 26.8% | +1.24% |
| SPY 2x on margin (T-bill + 1.5%) | +1.63% | −0.05% | 37% | +1.02% |
| SPY 2x on margin (T-bill + 5%) | +1.56% | −0.12% | 37% | +0.98% |

- **Decision rule (pre-set):**
  - MES has the best after-tax return per $ of capital, mostly from the 60/40 tax treatment.
  - A2 allows only about 0.6x notional at a 20% tolerance, so 2x is never used.
  - At that tolerance a $50k account is below the 1-MES threshold.
- **Line:** use **MES for accounts ≥ $61k** (≥ $49k at a 25% tolerance) and **SPY shares below that**.
  Don't use 2x.
- Holding periods are 5-7 calendar days, so SPY gains are always short-term. MES gets 60/40 treatment
  regardless of holding period.

## B. P3B

### B1. Trend gate (pass/fail): **FAIL**

- **Fresh set, market-on-close:**
  - Ungated P3B: 3,168 trades, excess **+0.25% (CI +0.01..+0.49)**, 13 of 15 markets positive.
  - Gated with ma50 > ma200: 2,261 trades, excess +0.17% (CI −0.09..+0.42).
  - **Gated minus ungated: −0.08% per trade (paired CI −0.22..+0.04).** The gate removes good trades.
- **High-VIX slippage:** the ungated lower bound falls just below zero (−0.01%).

**Line: don't trade it** (no gate).

### B2. Decay analysis (descriptive, post-hoc)

- **Method:** P3B excess by year, VIX bucket and trend state. Each is measured against random entries drawn
  from the same market and the same year, bucket or state.
- **Universe:** every market tested so far.
  - Index markets: SPY, QQQ, IWM, DIA and ES.
  - Other ETFs: EFA, EWG, EWJ, EWU and the 15 fresh ETFs.
  - Stocks: the B4 point-in-time universe.

| Group | Excess 2005-2019 (CI) | Excess 2020-2026 (CI) | Composition effect | Within-cell effect |
|---|---|---|---|---|
| Index markets | +0.58% (+0.25..+0.93), 618 trades | +0.23% (−0.57..+0.95), 302 | +0.09% | **−0.45%** |
| Other ETFs | +0.34% (+0.05..+0.64), 2,176 | +0.07% (−0.50..+0.60), 1,028 | +0.12% | **−0.39%** |
| S&P 500 stocks (PIT) | +0.39% (+0.13..+0.69), 66,151 | +0.09% (−0.43..+0.56), 28,842 | +0.09% | **−0.44%** |

**The fade is not "index ETFs fade, stocks don't".** Measured properly, all three groups lost a similar
0.27-0.36% per trade:
- **The mix is not the cause.** Since 2020 a larger share of P3B signals came in VIX > 25 markets, which
  helps (+0.09% to +0.12%).
- **The cause is the high-VIX signals themselves.** They carried the edge before 2020 and turned negative
  after:
  - index markets, VIX > 25 in downtrends: +1.28% → −1.29%;
  - stocks, VIX > 25 in downtrends: +1.60% → −0.40%;
  - stocks, VIX > 25 in uptrends: +0.97% → −0.34%.
- **The likely mechanism** is how P3B's score is built. It ranks the 3-day drop and the distance below the
  5-day average against the past year. In fast crashes (March 2020, 2022, April 2025) the score maxes out
  while prices are still falling, so it buys too early.
- **P2A is unaffected.** It needs only a weak close plus VIX > 20, and kept its edge in the 2020s
  (+0.38% per trade in A3).
- **Why the chat scan looked better on stocks:** it used today's surviving mega-caps (now excluded), and
  survivorship flatters exactly this kind of buy-the-dip signal.
- **Caveat:** after 2020 there are only a handful of independent crash episodes, so those CIs are wide.

### B3. Threshold sensitivity (development data only): **PASS (plateau)**

Development data: SPY 1994-2012 (market-on-close) plus ES 2013-2019 (next open), pooled.

| Score > | 0.86 | 0.87 | 0.88 | 0.89 | **0.90** | 0.91 | 0.92 | 0.93 | 0.94 |
|---|---|---|---|---|---|---|---|---|---|
| Trades | 343 | 321 | 299 | 273 | **249** | 227 | 199 | 164 | 129 |
| Excess per trade | +0.42% | +0.50% | +0.57% | +0.66% | **+0.68%** | +0.69% | +0.65% | +0.79% | +0.79% |
| CI lower bound | +0.14% | +0.20% | +0.25% | +0.34% | **+0.36%** | +0.34% | +0.29% | +0.38% | +0.27% |

- **0.90 sits on a smooth plateau.** 0.90 reproduces Phase 3's 249 development trades.
- **SPX vs SPY on dev data:** their score > 0.90 days agree 67% of the time.
- **The 2026-09-30 split** (SPX 0.906 fired, SPY 0.886 missed) is normal disagreement between two bars, not
  a sign that the threshold is fragile.

### B4. Single stocks, done properly: **FAIL** (both variants)

- **Data:** the client's Sharadar export, downloaded via the public Drive links.
  - Point-in-time S&P 500 membership rebuilt from the add/remove events. It matches all 114 quarterly
    snapshots and today's list exactly.
  - SEP prices, including every delisted member. All 959 members since 2005 have prices.
  - 8-K Item 2.02 filing dates as earnings dates.
- **Universe:**
  - 946 stocks after removing the seen names; 937 traded. Seven had under 300 bars and two never signalled.
  - Entries only on days the stock was an index member, 2005-01-03 to 2026-08-03.

| Variant | Trades | Raw per trade | **Excess over random (CI)** | Stocks with positive excess | High-VIX case |
|---|---|---|---|---|---|
| (a) All signals | 94,993 | +0.41% | **+0.24% (−0.002..+0.49)** | 65% | +0.23% (−0.01..+0.48) |
| (b) Excluding earnings windows | 86,162 | +0.42% | **+0.25% (−0.002..+0.51)** | 66% | +0.24% (−0.01..+0.50) |

- **Both fail by a hair.** The point estimate is positive, but the month-clustered CI touches zero. Stock
  signals pile up in crash months: March 2020 alone has thousands.
- **Excluding earnings changes almost nothing** (+0.01%). Against an earnings-free random benchmark, (b) is
  +0.25% (CI −0.0003..+0.52).
- **2005-2019:** +0.32% (CI +0.07..+0.62). **2020-2026:** +0.04% (CI −0.49..+0.52).
- **By sector:** Financials are best (+0.58%), Utilities worst (−0.08%). This was looked at after the fact.
- **Delisting:** 162 trades ran into a delisting and exited at the last close. The worst trades are real
  failures: Lehman −96%, WaMu −93% and AIG −80% in September 2008, and First Republic −66% in 2023.

**Line: don't trade it** on single stocks.

### B5. Combine with P2A: **FAIL**

| | ES 2013-2026 (pt) | ES 2013-2026 (% of raw notional) | SPY 1994-2026 (% of position) |
|---|---|---|---|
| P3B entries made while P2A is open or on the same day | 55% | 55% | 59% |
| Daily P&L correlation, days both are in position | 0.94 | 0.93 | 1.00 |
| Daily P&L correlation, all days | 0.63 | 0.60 | 0.54 |
| Max DD: P2A alone → combined | 674 → 1,332 pt | 22% → 39% | 30% → 44% |
| Worst month: P2A → combined | −280 → −453 pt | −7.3% → −14.1% | −18.8% → −23.0% |
| Return / max DD: P2A → combined | 6.6 → **5.5** | 5.8 → **4.9** | 11.0 → 12.9 |

- **P3B mostly re-buys the same dips P2A is already holding.** Its losses land on P2A's losing days more than
  half the time.
- **On the live vehicle (ES) it lowers return per unit of drawdown.** On SPY 1994-2026 it slightly improves
  it, but the rule needed both windows.

**Line: don't trade it** alongside P2A. Keep it in the log only.

## Corrections and caveats found during Phase 4

1. **ES prices are roll-adjusted forward.** The engine's ES series is anchored to the 2013 contract, with each
   later roll gap subtracted, which puts it about 730 points below the traded price by 2026.
   - Point P&L is correct.
   - A % return computed on it is overstated. Phase 2-3 ES % figures are overstated by roughly 0-10%, more in
     later years. Every point figure, and every ETF figure, is unaffected.
   - Phase 4 % figures for ES use the raw traded price. The B3 ES leg used an average rescaling, since it
     covers only 2013-2019, when the gap was small.
2. **The pre-registered A2 sizing in points understates today's risk.** Point drawdowns come mostly from years
   when ES was at 1,500-4,000. The addendum `scripts/p4_A2b_pct_sizing.py`, written after A2 ran, repeats the
   bootstrap in % of the raw notional and converts at today's price. Use it.
   - A first version of that addendum divided by the roll-adjusted price. Its rows stay in the append-only log,
     marked as superseded.
3. **`^GSPC` 1990-2009 hit FMP's 5,000-row cap.** The ingest check caught it and the span was re-fetched in two
   halves.
4. **The Yahoo ES bar may differ from TradingView's.** Yahoo's `ES=F` daily bar (logger source) can differ from
   TradingView's `ES1!` session bar. Cross-check ES IBS against your chart for the first weeks.
5. **The DSR fails for every system against 13,490 cumulative trials.** That number counts Phase 1's 12,514
   level variants, a different family. The out-of-sample record on untouched markets is the stronger evidence.

## Reproduce

- **Data:**
  - Fresh ETFs and `^GSPC`: FMP via MCP, ingested by `scripts/p4_ingest_fmp.py` (files in
    `data/external/etf/` and `data/external/GSPC.csv.gz`).
  - Sharadar: `scripts/p4_fetch_sharadar.sh` then `scripts/p4_sharadar_prep.py` (about 1 GB, not committed).
- **Tests, each run once:** `scripts/p4_A2_stress_sizing.py`, `p4_A2b_pct_sizing.py`, `p4_A3_fresh_p2a.py`,
  `p4_A4_execution.py`, `p4_A5_vehicles.py`, `p4_B1_trend_gate.py`, `p4_B2_decay.py`, `p4_B3_threshold.py`,
  `p4_B4_stocks.py`, `p4_B5_combine.py`.
- **Unit tests:** `python -m pytest -q tests` (24 pass).
