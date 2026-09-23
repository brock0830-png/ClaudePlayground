# crypto/REPORT.md: finding a repeatable positive-EV crypto signal, and the bot that trades it

Protocol: `crypto/PREREG.md`, committed before any backtest (`11c5c61`, amendment v1 `e91c90b`). Every number below is read from `crypto/TRIAL_LEDGER.csv`, `crypto/reports/design/` or `crypto/reports/holdout/`. Costs are included everywhere: 10 bp fee plus 2-6 bp slippage per side, and perp fees plus funding for USDT shorts.

## 1. Verdict

- **Your two indicators have no tradable edge on their own.** The TDZ confluence, in both the version you pasted and the version in your CSV exports, and SigmaJanus re-risk lose money after costs in every pre-registered test, on your 30m BTC pairs and on 16 pairs at 4h. Gross of costs, the TDZ signal on your own pairs makes +6.5 bp per trade on the long side (design). That is roughly zero, so this is not a cost problem: there is no signal to pay the costs with.
- **One strategy passed both stages:** a daily trend basket. Equal slots across 28 coins; hold a coin while it closes above its 50-day SMA; hold alts only while BTC is above its 100-day SMA. Design 2018-2023: CAGR 70.5%, Sharpe 1.38, max drawdown -39.5%, against 14.1% / 0.59 / -84.0% for buying and holding the same coins. **One-shot holdout 2024-01-01 to 2026-09-22:** CAGR 31.9%, Sharpe 0.90, max drawdown -39.5%, against 9.2% / 0.47 / -70.4% for the basket and 29.8% / 0.79 / -53.0% for BTC buy and hold.
- **Its edge is trend-following exposure management, not stock-picking.** On the holdout it roughly matches the simplest benchmark, BTC above its 100-day SMA (28.0% / 0.91 / -36.4%), at higher CAGR but similar Sharpe. What it reliably adds is keeping you out of alts in BTC downtrends. Treat the holdout numbers, not the design numbers, as the expectation.
- **Deployed:** `crypto/bot/` trades exactly this rule. Replayed through all 996 holdout days, it reproduces the backtest to machine precision. It runs in paper mode by default, and live trading needs a double opt-in.

## 2. What was tested

| Hypothesis | Rule | Grid | Data |
|---|---|---|---|
| H1 TDZ (yours) | TD 9 / 13 + z-score ±2.5 in the last 4 bars, fade it (6 variants: your Pine, looser z, TD only, z only, DeMark countdown + z, **your export's** TD + EMA-stack). The last one was found by reproducing your CSV columns bar for bar | 5 horizons x long/short | your SOLBTC/AVAXBTC 30m; 16 pairs at 4h |
| H2 SigmaJanus (yours) | Fast = RSI(8) of WMA(7) < 15 (or 20) and turning up: buy | 4 horizons | 30m, 4h, daily x 28 coins |
| H3 Capitulation (added) | bar return z <= -2.5 / -3 on volume >= 2x median, optional close-location (CVD proxy) filter: buy | 4 horizons | 30m, 4h, daily |
| H4 Trend basket (added) | per-coin SMA 20/50/100/200 or Donchian 20/50/100, optional BTC gate | 14 cells | daily, 28 coins, 2017-2026 |
| H5 Cross-sectional momentum (added) | weekly top 3/5 by 14/28/56-day return, optional absolute gate | 12 cells | daily, 28 coins |

Splits: daily design 2018-2023, holdout 2024-01-01 to 2026-09-22. Intraday design to 2025-09-30, holdout 2025-10-01 onward. The 1h data (9 coins) and your ETHBTC 15m were used only as holdout confirmation. Pass rules were fixed in advance (PREREG sections 1-2): positive net edge with day-clustered t >= 2, positive in 3 of 4 horizons, above drift, breadth across symbols, survives a one-bar delay and 2x costs. For portfolios: Sharpe at least BM1 + 0.2 with max drawdown at most 0.75x BM1, a grid neighbourhood that holds up, a one-day delay, removal of each sub-period, and 2x costs.

## 3. Results

### 3a. Signal families (design window, reference horizon; net = after costs, bp per trade)

| Family | Trades | Gross | Net | t | Excess vs drift | Verdict |
|---|---|---|---|---|---|---|
| H1 your Pine, long, 30m BTC pairs | 102 | +6.5 | -23.5 | -1.33 | +7.0 | fail |
| H1 your Pine, short, 30m BTC pairs | 119 | -2.0 | -32.0 | -1.50 | -2.6 | fail |
| H1 your export (TD + EMA stack), long, 30m | 32 | +25.9 | -4.1 | 0.81 | +26.7 | fail |
| H1 your export, short, 30m | 45 | +31.5 | +1.5 | 0.19 | +30.9 | fail |
| H1 your Pine, long, 4h | 216 | -28.3 | -56.1 | -1.03 | -47.6 | fail |
| H1 TD only / Z only, 30m (ablations) | 288-349 | -0.8 to +0.8 | -29 to -31 | -1.8 to -3.5 | ~0 | fail |
| H1 DeMark countdown + z, long, 4h | 32 | +137.5 | +109.2 | -0.11 | +116.2 | "promising", not significant |
| H2 SigmaJanus OS 15, 30m / 4h / daily | 349 / 564 / 703 | -5.8 / +38.0 / -12.3 | -35.8 / +10.0 / -42.2 | -1.8 / -0.6 / -0.2 | -5 / +21 / -165 | fail |
| H3 capitulation k 3, 4h | 335 | +155.5 | +127.9 | 1.77 | +139.8 | fail (t < 2, delay) |
| H3 capitulation, 30m / daily | 133-364 | -71 to +27 | -101 to -2 | <0 | <0 | fail |

None of the 42 families passed. All 42 are in `crypto/reports/design/event_families.csv`. For information only (declared at the freeze, and unable to change any verdict), the holdout showed the same thing:

- Your Pine TDZ lost 43 bp per trade long (t -5.2, 25% winners) and 36 bp short on the 30m pairs, and 27-30 bp on ETHBTC 15m.
- The "promising" countdown family lost 35 bp at 4h.
- Capitulation lost 35 bp at 4h.

On the author's SigmaJanus claim (shallower forward drawdowns after re-risk): after the signal, the average worst excursion over the next 8 bars was -3.14% against -3.38% unconditional at 4h, -10.5% against -11.0% daily, and the same at 30m. The drawdowns are slightly shallower, but not by enough to trade.

### 3b. Daily portfolios

| Window | Rule | CAGR | Vol | Sharpe | Max DD | MAR | Invested |
|---|---|---|---|---|---|---|---|
| Design 2018-2023 | **Trend basket SMA50 + BTC gate (selected)** | **70.5%** | 47% | **1.38** | **-39.5%** | 1.78 | 36% |
| | H4 grid median (14 cells) | | | 1.12 | | | |
| | BM1 equal-weight buy and hold | 14.1% | 84% | 0.59 | -84.0% | 0.17 | 97% |
| | BM2 BTC buy and hold | 24.3% | 67% | 0.67 | -76.6% | 0.32 | 97% |
| | BM3 BTC > SMA100 | 50.2% | 46% | 1.12 | -38.6% | 1.30 | 50% |
| | H5 best cell (momentum top 5, 28d, gated) | 58.1% | 85% | 0.94 | -78.6% | 0.74 | 68% |
| **Holdout 2024-01 to 2026-09** | **Trend basket SMA50 + BTC gate** | **31.9%** | 40% | **0.90** | **-39.5%** | 0.81 | 35% |
| | same, 1 day late | 22.9% | 40% | 0.72 | -44.1% | 0.52 | 35% |
| | same, 2x costs | 27.7% | 40% | 0.81 | -41.9% | 0.66 | 35% |
| | same, 40 bp fee per side | 23.5% | 40% | 0.73 | -44.4% | 0.53 | 35% |
| | H4 grid median (14 cells) | | | 0.77 | | | |
| | BM1 equal-weight buy and hold | 9.2% | 68% | 0.47 | -70.4% | 0.13 | 100% |
| | BM2 BTC buy and hold | 29.8% | 47% | 0.79 | -53.0% | 0.56 | 100% |
| | BM3 BTC > SMA100 | 28.0% | 33% | 0.91 | -36.4% | 0.77 | 56% |

The design checks all passed: 12 of 14 H4 cells met the edge test; the neighbourhood median Sharpe was 1.12 against BM1's 0.59; a one-day delay gave Sharpe 1.51; with each sub-period removed, Sharpe ranged 0.81 to 1.62 (BM1 0.11 to 0.99); 2x costs gave 1.33. The deflated Sharpe probability, over 307 design trials, is 0.97 on design and 0.67 on the holdout. H5 failed: every cell had a drawdown of 75-95%.

Calendar years for the trend basket against BTC buy and hold: 2018 -25% / -68%, 2019 +46% / +94%, 2020 +117% / +302%, 2021 +656% / +60%, 2022 -19% / -64%, 2023 +70% / +156%, 2024 +60% / +121%, 2025 -10% / -6%, 2026 to date +49% / -2%. It lags in strong BTC-led bull years and wins by losing less in bear years. The 2021 alt season dominates the design CAGR, so it is not a typical year. Sub-period removal shows the rule still beats BM1 without 2021 (Sharpe 0.81 vs 0.11).

## 4. Caveats that matter for real money

1. **Survivorship.** The universe is 28 coins still listed on TradingView in 2026. It includes coins down 80-99% (NEO, IOTA, QTUM, XTZ, DASH, ALGO, FIL), but not coins that went to zero and were delisted (LUNA, FTT). A trend filter exits collapses early, which limits the damage, but real results would be somewhat worse.
2. **Fees decide a lot.** At 40 bp per side (a US retail tier), holdout CAGR drops from 31.9% to 23.5%.
3. **One regime per window.** The holdout is 2.7 years of one crypto cycle. The drawdown from December 2024 to April 2026 was -39.5%, and on 2026-09-22 the rule was still 5% below its December 2024 peak.
4. **The simplest alternative is about as good.** BTC-only trend (BM3) matched the basket's holdout Sharpe with fewer trades. It was a benchmark, not a pre-registered candidate, so it is not what the bot trades, but it is a reasonable second bot if you want one.
5. **Intraday work used short windows.** 4h covers 2.3 years and 1h covers 7 months. The failure of the short-term signals is clear, but a small edge could hide inside that noise. None of it survives these costs, though.
6. **Your data vs. the bot's data.** The research used Binance spot bars from TradingView. On another venue, prices, listings and daily closes differ slightly.

## 5. Deviations and bugs, in order (all disclosed in the ledger's note column)

1. Amendment v1, before any backtest: your export's confluence differs from your pasted Pine, so it was added as variant V6.
2. PREREG says 15 symbols at 4h. The pull has 16 (13 USDT pairs including BCH, plus 3 BTC pairs), and all 16 were used.
3. The first design run crashed on a family with zero trades. Its partial ledger is kept at `reports/design/crashed_first_run_partial_ledger.csv`, unread.
4. A t-statistic dtype bug returned NaN whenever any symbol had no trades. It was fixed and the design rerun. The 307 affected rows are marked superseded, and returns were identical.
5. The first holdout attempt crashed on a pandas attribute before printing anything. It was fixed and rerun (a deterministic computation), and those rows are marked superseded.
6. **The portfolio engine could borrow.** On days a coin switched on while the rest of the book had drifted up, the engine bought a full slot even when cash fell short (up to 9.6% of equity on 391 of 3,324 days). The bot's replay test exposed this. The engine now scales buys to available cash. Design and holdout were rerun on the unchanged frozen rule: the selection and every verdict were unchanged, and the numbers moved by less than 1 point (holdout CAGR 32.3% to 31.9%, Sharpe 0.899 to 0.895). The earlier outputs are kept in `reports/holdout_v1_borrowing_engine/` and `reports/design/*_v1_borrowing_engine.*`.

## 6. Files

| Path | What |
|---|---|
| `crypto/PREREG.md` | the pre-registration |
| `crypto/src/indicators.py` | TD setup/countdown, z-score, EMA stack, SigmaJanus, CVD proxy, trend rules. It reproduces every signal column of your three exports |
| `crypto/src/events.py`, `portfolio.py`, `research.py`, `holdout.py` | the engines and runners |
| `crypto/TRIAL_LEDGER.csv` | every trial (1,005 rows, 339 live) |
| `crypto/bot/` | the bot, config, and runbook (`crypto/bot/README.md`) |
| `crypto/pine/trend_basket.pine` | the rule on your TradingView charts, with ON/OFF alerts |
| `.github/workflows/crypto-trend-bot.yml` | daily scheduled paper run |
| `crypto/tests/` | 18 tests: indicator parity with your exports, causality, engine fills, no borrowing, bot/backtest parity, live-gate safety, fake-exchange live path |
