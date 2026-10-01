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
