# PROTOCOL_P4: stress tests of P2A and P3B before real money

Written and committed **before any Phase 4 test data is loaded**. The commit hash goes in
`results/p4/TEST_UNLOCKED`. Each test runs once, through `scripts/p4_*.py`, which refuse to run unless that
lock names the commit of this file. Every evaluated variant, failures included, is a row in `results/p4/log.csv`.

## 0. Frozen systems (unchanged; `results/p3/frozen_candidates.json`)

- **P2A:** IBS < 0.30 and VIX close > 20, no position open. Buy 1 unit, hold 5 sessions.
- **P3B:** composite oversold score `os_score` > 0.90 (as defined in `results/p3/frozen_rules.md`), no position
  open. Buy 1 unit, hold 5 sessions.
- **Execution:**
  - ETFs and stocks: market-on-close. Enter at the signal day's 16:00 close and exit at the close 5 sessions
    later.
  - ES: enter at the next 18:00 ET open and exit at the 18:00 open after the 5th session (`scalpel/p3.py`).
- No stops, no targets, no sizing changes. **No options structures are modeled or tested anywhere in Phase 4.**

## 1. Costs

| Case | ETFs and stocks | ES / MES |
|---|---|---|
| Base (all verdicts) | 0.05% round trip | ES 0.60 pt + 0.60 pt per roll; MES 0.84 pt per round trip (0.25 pt slippage per side + $0.85 commission per side) + 0.84 pt per roll |
| High-VIX slippage (robustness, VIX at the signal > 25) | add 2 ticks ($0.01 each) per side = $0.04 per share. As a fraction of the adjusted price (conservative, since adjusted ≤ traded price), or of `closeunadj` for stocks | add 2 ticks per side = 1.0 pt per round trip on top of base |

Verdicts use base costs. The high-VIX case is reported next to every verdict, flagged if it would flip it.

## 2. Primary metric: excess return per trade over random entries

For each market (or stock), draw 1,000 sets of random entries:
- the same number of trades and the same holding periods;
- the same execution mode and cost model;
- entry days uniform over that market's eligible window. For B4 the window is only the days the stock is an
  S&P 500 member.

The random benchmark of a market is the mean random-entry return. A trade's excess is its return minus its
market's benchmark. The pooled excess is the trade-weighted mean.

- **CI:** every pooled number gets a month-clustered bootstrap 95% CI. Signal months are resampled with
  replacement, 10,000 draws, and all trades signalled in a month move together. Paired comparisons resample
  the same months for both arms.
- **Secondary:** raw return per trade, profit factor, per-market numbers, and the random-entry percentile (share
  of draws whose mean is below the actual mean).
- **Deflated Sharpe (DSR):**
  - Per-trade Sharpe of the pooled raw returns, and separately of the excess.
  - Trial variance 0.0043: the per-trade Sharpe variance over Phase 3 variants with n ≥ 60, as in Phase 3.
  - Number of trials = the **cumulative count**: Phase 1 12,514 + Phase 2 640 + Phase 3 258 = **13,412**, plus
    the number of Phase 4 rows logged at the time of the run. The count is printed and logged.

## 3. Data

| Data | Source | Status |
|---|---|---|
| ES sessions 2013-01-02 to 2026-09-30 | TradingView 4h export (repo) | seen |
| SPY, QQQ, IWM, DIA, EFA, EWG, EWJ, EWU | FMP dividend-adjusted (repo) | seen |
| VIX close | CBOE file (repo), to 2026-09-29 | |
| SPY update to 2026-09-30, `^GSPC` OHLC 1990-2026 | FMP (MCP) | seen markets |
| **Fresh ETFs:** XLV XLY XLP XLI XLB XLU XLRE EWZ EWA EWC EWY EWT FXI INDA EWW | FMP dividend-adjusted (MCP) | **untouched**; fetched only after this commit |
| **Single stocks** | Sharadar SEP (`stocks.csv.zip`), SP500 membership (`sp500.csv`), EVENTS (`events.csv.zip`) from the client's Drive (public-link download) | **untouched**; fetched only after this commit |
| 3-month T-bill | FMP treasury curve (repo, to 2026-09-18; forward-filled after) | |

- **Windows:**
  - Each ETF trades from its 253rd session (the score needs 252 days) to the last VIX date, 2026-09-29.
  - Stocks trade from 2005-01-03, when EVENTS earnings coverage begins, to the last SEP date.
- **Seen names excluded from every untouched test:**
  - Index and futures markets: SPY, ES, QQQ, IWM, DIA, EFA, EWG, EWJ, EWU.
  - Stocks: AAPL, AMZN, NVDA, MSFT, GOOGL (and GOOG), META (FB), TSLA, JPM, AVGO, NFLX, LLY, AMD.
  - ETFs: GLD, SLV, TLT, XLE, XLF, XLK, SMH.

**Stop rule.** If a required dataset turns out to be unavailable or broken, the test stops and the report
says so. A modeled or survivorship-biased substitute is never used.

## 4. Tests

### A1. Forward paper-trade logger (tool, not a test)

`scripts/p4_signal_logger.py`, run after 17:00 ET. For ES, SPX, SPY, DIA and IWM it computes IBS, VIX and the
P3B score, plus the P2A and P3B signal and in-position state. Position state is replayed from history with the
frozen rules. For each day, market and system it appends one row to `results/live/signals_log.csv` with the
planned entry and exit times.

- It is append-only and never rewrites or edits an existing row.
- A row already logged for a (date, market, system) is skipped.
- The README gives the exact run command.
- Correctness check: on 2026-09-30 it must reproduce SPX score 0.906 (signal) and SPY 0.886 (no signal).

### A2. Crash stress and sizing (ES 2013-2026)

- **Systems:**
  - P2A on ES (points) and on SPY (% of position), each from its own signals, 2013-01 to the end of data.
  - The same for P3B.
  - P2A + P3B combined (1 unit each, independent positions).
- **Paths:**
  - Daily mark-to-market P&L at session closes.
  - Block bootstrap by calendar month: resample whole months, months with no trades included, to the
    historical length; 10,000 paths, seed fixed.
- **Report:**
  - Max drawdown of daily equity (fixed size, no compounding) at the 50th, 95th and 99th percentiles.
  - Longest losing streak (consecutive losing trades within each path) at the same percentiles.
- **Sizing table** (`results/p4/sizing_table.md`) for 15%, 20% and 25% drawdown tolerance at the 99th
  percentile:
  - Account $ per MES = DD99 (pt) × $5 / tolerance, and MES count for $25k, $50k, $100k and $250k accounts.
  - SPY $ per $ of account = tolerance / DD99 (fraction of position).

### A3. P2A on the fresh set (pass/fail)

- **Setup:** frozen P2A on the 15 fresh ETFs, market-on-close.
- **Pass:**
  - pooled excess per trade > 0 with month-clustered CI lower bound > 0, **and**
  - at least 60% of markets (9 of 15) have positive excess.
- **Also reported:** raw return per trade, next-open execution, the high-VIX slippage case, per market, by
  decade, and DSR.

### A4. Execution realism (descriptive)

- **Signals:** P2A signals from SPY's own bar and, separately, from SPX (`^GSPC`) bars.
- **Fills:**
  - (i) 16:00 close, exit at the close 5 sessions later (SPY prices);
  - (ii) next 09:30 open, exit at the open 5 sessions after entry (SPY prices);
  - (iii) ES at 18:00 the same evening, exit at 18:00 after 5 sessions (ES prices, ES costs).
- **Windows:** 2013-01 to 2026-09 for the 3-way comparison; also (i) vs (ii) on SPY from 1994.
- **Report:**
  - Mean return per trade for each fill.
  - Paired differences on the same signals, with month-clustered CIs.
  - The same for signals with VIX > 25.

### A5. Vehicle comparison, no options (descriptive with a pre-set decision rule)

- **Trades:** the same P2A ES signals, 2013-2026.
- **Vehicles:** MES futures, SPY shares (1x), and SPY at 2x on margin.
- **Return per $ of capital** at 1x and 2x exposure:
  - MES: the futures price return, plus T-bill interest on the capital (it stays in bills; margin is posted
    from it), minus MES costs.
  - SPY: total return minus costs.
  - SPY 2x: 2 × SPY return, minus borrowing on the second notional at 3m T-bill + 1.5% (IBKR-like), minus
    2 × costs. Sensitivity: 3m T-bill + 5% (typical retail).
- **Tax:** every trade is short-term for SPY (ordinary rate 37% top bracket). MES is Section 1256 60/40
  (0.6 × 20% + 0.4 × 37% = 26.8%). Report after-tax return per trade at those rates.
- **Decision rule:**
  - Recommend the vehicle with the highest after-tax return per $ of capital at the exposure the A2 sizing
    table allows.
  - Exception: if the A2 size for a $50k account is under 1 MES, recommend SPY shares for accounts below the
    1-MES threshold.

### B1. P3B trend gate (pass/fail)

- **Setup:** on the fresh set, run ungated P3B and gated P3B (P3B and `ma50 > ma200`), once each.
- **Pass:** pooled excess(gated) − pooled excess(ungated) > 0 with a paired month-clustered CI lower bound
  > 0.
- **Also reported:** each arm's own excess and CI.

### B2. Decay analysis (descriptive; labelled post-hoc, since the 2020s fade was already seen)

- **Markets:** dev (SPY 1994-2012, ES 2013-2019), the Phase 3 test ETFs, the fresh ETFs, and the B4 stocks.
- **P3B excess by year:** the benchmark is random entries in the same market and year.
- **By VIX bucket at the signal** (<15, 15-20, 20-25, >25) and by trend state (ma50 > ma200): the benchmark
  is random entries on days of the same market in the same bucket or state.
- **Explanation of the post-2020 fade, index ETFs vs stocks:**
  - Compare 2005-2019 with 2020-2026 on signal count, VIX mix and trend mix, and excess within each bucket.
  - The question is whether the fade is a composition shift or a within-bucket decline.

### B3. P3B threshold sensitivity (dev data only)

- **Setup:** score thresholds 0.86 to 0.94 in steps of 0.01 (9 variants) on SPY 1994-2012 (MOC) and ES
  2013-2019 (next open), pooled.
- **0.90 is "on a plateau" if:**
  - every threshold from 0.88 to 0.92 has pooled excess > 0 with month-clustered CI lower bound > 0, **and**
  - the excess at 0.89 and at 0.91 are each at least 50% of the excess at 0.90.
- **Also reported:** dev-window agreement of SPX vs SPY score signals at 0.90.

### B4. Single stocks, point-in-time (pass/fail)

- **Universe:**
  - Sharadar SP500 membership history, including later-removed and delisted names.
  - A stock is eligible on a day only if it is an S&P 500 member that day.
  - Equities only; seen names excluded.
  - Features use the stock's full price history.
- **Prices:**
  - Sharadar SEP split-adjusted OHLC, scaled by `closeadj / close` (dividends included).
  - Market-on-close, 0.05% round trip.
  - A hold that runs past the last SEP bar (delisting) exits at the last close. Any post-delisting return is
    unknown and not modeled.
- **Earnings:** EVENTS code 22 (8-K Item 2.02, results of operations) filing dates, used as point-in-time
  earnings release dates.
- **Variants (both pre-registered, both reported):**
  - (a) all P3B signals;
  - (b) excluding signals whose window, from the signal day through the exit day, contains an earnings date.
- **Primary metric:** pooled excess over random entries in the same stock (member days only), with
  month-clustered CI.
- **Pass, for each variant:** pooled excess > 0 with month-clustered CI lower bound > 0.
- **Also reported:** raw return, 2005-2019 vs 2020-2026, sector-free, DSR.

### B5. Combine P3B with P2A (pass/fail)

- **Windows:** ES 2013-2026 (next open) and SPY 1994-2026 (MOC), 1 unit each, independent positions.
- **Report:**
  - Signal overlap: the share of P3B entries made while a P2A trade is open, or on the same day.
  - Correlation of daily mark-to-market P&L on days both are in position, and on all days.
  - Combined max drawdown and worst month, against P2A alone.
- **P3B earns a place only if:**
  - ungated P3B passes on the fresh set (B1's ungated arm: pooled excess CI lower bound > 0), **and**
  - on both windows, the combined return / max-drawdown ratio is ≥ P2A alone's ratio.

## 5. Reporting

- `results/p4/report.md`: for each test, the numbers, the verdict, and one line saying "trade it", "paper trade
  it" or "don't trade it".
- `results/SYSTEM.md` is updated only with conclusions that passed.
