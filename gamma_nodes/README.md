# gamma_nodes: do large 0DTE gamma strikes attract SPX, and can a butterfly profit from it?

Standalone study, separate from the TALOS work in the rest of this repo.

- `PROTOCOL.md`: the pre-registration (hypotheses, data gates, node grid, tests, split, verdict rules).
  Read this first.
- `collector/`: the live 5-minute collector that runs on your own computer, with the scheduling README.
- `src/`: the tape ingest, heatmap rebuild, validation and test code.
- `tests/`: offline unit tests (`python -m pytest -q gamma_nodes/tests`).
- `results/`: committed outputs. Every variant tried goes in `log.csv`.

Data never goes to GitHub. It lives in Google Drive under `DATA_ROOT` (set in `gamma_nodes/.env`; see
`.env.example`):

```
DATA_ROOT/tape/YYYY-MM-DD.parquet       filtered Full Tape (SPX/SPXW/XSP, expiry <= next trading day)
DATA_ROOT/live/YYYY-MM-DD/HHMM_*.json   raw live collector snapshots
DATA_ROOT/heatmaps/YYYY-MM-DD.parquet   rebuilt 5-minute strike profiles
DATA_ROOT/MANIFEST.csv                  date, file, rows, bytes, checksum, created time (append-only)
```

## Status (2026-10-01, end of first session)

| step | state |
|---|---|
| Protocol | committed in `a22d942` before any data was touched; Amendment 1 is a clarification |
| Live collector | written and tested offline; **must be installed on your computer before 09:35 ET** (see `collector/README.md`) |
| Tape ingest, prices, rebuild, validation | written and unit-tested on synthetic data; not yet run on real data |
| Blocked on | `UW_API_KEY` in the session environment, setup A vs B, free Drive space |

Next commands once the key and `DATA_ROOT` are set (from `gamma_nodes/`):

```
python src/tape_ingest.py probe                 # D1: history window
python src/tape_ingest.py range 2026-09-28 2026-10-01 --confirm   # small first batch
python src/pipeline.py estimate                 # D4: projection -> STOP and ask if > free space or 100 GB
python src/tape_ingest.py pilot --confirm       # 60-day pilot
python src/pipeline.py validate 2026-10-02 ...  # step 3 once >= 5 live+tape days exist
```
