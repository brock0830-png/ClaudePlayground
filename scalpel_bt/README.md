# Scalpel levels backtest

Can Chris's Scalpel (TrueALGO-clone) D/W/M levels drive an EV+ ES/SPX system on data it has never seen?
**Phase 1 answer (Scalpel levels): no edge found.** Start with `results/oos_report.md`, then `results/screen_summary.md`.

**Start here: `results/SYSTEM.md`**, a one-page rundown of the system that survived every test, and
`pine/README.md` for the TradingView indicators that draw its trades.

**Phase 4 (stress tests before real money):** P2A passed on 15 more untouched ETFs (5,116 trades, +0.45% per trade
over random entries, 15/15 markets). Crash stress puts its 99th-percentile drawdown at 31.5% of notional, which means about
1 MES per $61k at a 20% tolerance. P3B failed its trend-gate, single-stock (point-in-time S&P 500) and combination tests.
See `results/p4/report.md`, `results/p4/sizing_table.md` and the forward logger in `results/live/README.md`.

**Phase 3 (variations + a different validation):** targets, stops, holding periods, trend, volume and composite
scores were tested on 27 years of development data (SPY 1994-2012 + ES 2013-2019). Then the frozen picks and the
unchanged P2A were tested once on seven untouched markets (QQQ, IWM, DIA, EFA, EWG, EWJ, EWU; 1997-2026).
**P2A confirmed:** 2,739 trades, +0.54% per trade, profit factor 1.46, positive in all 7 markets and every decade.
See `results/p3/test_report.md`.

**Phase 2 (directional ES rules from price and VIX, no options):** one rule held up out of sample. Buy ES when a
session closes in the bottom 30% of its range while VIX closes above 20, hold 5 sessions. OOS 2020-2026:
111 trades, +29.9 pt/trade (95% CI +4.6..+55.1), every year positive, beat randomly timed long exposure (96th pct).
Protocol verdict: paper trade it (it does not clear the deflated-Sharpe bar). See `results/p2/oos_report.md`.

| File | What |
|---|---|
| `PROTOCOL.md` | Pre-registration: split, execution model, baselines, gates, verdict rules (committed before any test) |
| `results/validation.md` | Level port vs the 2013-2026 TradingView export (exact to 1e-12), week-boundary quirks, roll dating |
| `results/log.csv` | Every variant tried (12,514 rows: 12,264 directional DEV backtests with baselines, 250 modeled option screens) |
| `results/screen_summary.md` | What was screened on DEV and what it showed |
| `results/frozen_rules.md`, `results/frozen_candidates.json` | The two candidates, frozen in commit 653c73f before OOS |
| `results/oos_report.md`, `results/oos_*.png`, `results/oos_results.json` | One-shot 2020-2026 OOS results and verdict |

Reproduce (Python 3.11):

    pip install -r requirements.txt
    python validate_export.py                    # level port vs TradingView export
    python -m pytest -q tests                    # simulator vs slow reference, coefficients vs level_frame
    python scripts/screen_stageA.py 4            # 9,648 DEV variants (about 12 min on 4 cores)
    python scripts/screen_stageB.py 4            # 2,616 DEV variants (filters, ladders, longer holds)
    python scripts/screen_options.py [--sens]    # modeled option screens (writes results/log_options_pending.csv)
    python scripts/summarize_log.py              # gate counts and rankings
    python scripts/dev_candidates.py             # DEV pages for the frozen candidates
    python scripts/run_oos.py                    # one-shot OOS; needs results/OOS_UNLOCKED = freeze commit

Phase 4: `PROTOCOL_P4.md`, `scripts/p4_*.py` (each test runs once, locked to `results/p4/TEST_UNLOCKED`),
`results/p4/`, `results/live/`.

Phase 3: `PROTOCOL_P3.md`, `scripts/p3_screen.py` (258 development variants), `scripts/p3_test.py` (one-shot
test, locked to the freeze commit), `results/p3/`. Pine logic checks: `scripts/pine_replica.py`,
`scripts/pine_replica_levels.py`.

Phase 2: `PROTOCOL_P2.md`, `scripts/p2_screen.py` (640 DEV variants), `results/p2/` (log, frozen rules, OOS report),
`python scripts/p2_candidates.py dev|oos` (OOS needs `results/p2/OOS_UNLOCKED` = Phase 2 freeze commit).

`scripts/detect_rolls.py` (re-dates contract switches) and `scripts/audit_stopfirst.py` (checks stop-first
fills against SPX 1-minute bars) need the public SPX 1-minute file from HuggingFace
`thillsss/SPX-MES-VIX-data`, which is not committed (96 MB).
