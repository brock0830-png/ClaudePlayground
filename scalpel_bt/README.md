# Scalpel levels backtest

Can Chris's Scalpel (TrueALGO-clone) D/W/M levels drive an EV+ ES/SPX system on data it has never seen?
**Answer: no edge found.** Start with `results/oos_report.md` (verdict), then `results/screen_summary.md`.

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

`scripts/detect_rolls.py` (re-dates contract switches) and `scripts/audit_stopfirst.py` (checks stop-first
fills against SPX 1-minute bars) need the public SPX 1-minute file from HuggingFace
`thillsss/SPX-MES-VIX-data`, which is not committed (96 MB).
