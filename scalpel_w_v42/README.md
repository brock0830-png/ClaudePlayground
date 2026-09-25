# SCALPEL-W-v42: can the weekly TrueALGO / Doc's Scalpel v42 levels be traded for an edge?

Answer: **no strategy survived.** See [REPORT.md](REPORT.md), and [REPORT_P2.md](REPORT_P2.md) for phase 2
(context filters and market profile; the one lead, P13, is a pure market-profile rule). Across 9.0M configurations
(pierce grid + 39 filter variants) on ES, NQ, CL and 6J, the real levels did no better than the
same levels shifted 0.15-0.30 sigma. The 12 finalists, frozen in [FREEZE.md](FREEZE.md), each
failed at least one gate when 2021-2026 was opened once.

Reproduce (Python 3.11, `pip install numpy pandas scipy numba pyarrow matplotlib pytest`):

```
python3 -m pytest -q tests      # fill-model unit tests
./run_all.sh                    # canary, Step 1 inputs, F0 + control grids, EXPAND rounds 1-3, exports
python3 src/strength.py         # Step 1 level strength map (bootstrap, ~5 min)
python3 src/heatmaps.py         # PF / expectancy heatmaps
```

Files: `search_manifest.md` (search space), `ideas_queue.md` (families and results),
`coverage.csv.gz` (every cell, 100% done), `results_all_F0.csv.gz` / `results_expand_round*.csv.gz`
(in-sample metrics), `outputs/` (Step 1 tables, validation, trade lists, charts). Every output
carries the lineage tag `SCALPEL-W-v42`. The input data are the four TradingView exports in `data/`,
and the task spec is `PROMPT_v3.md`.
