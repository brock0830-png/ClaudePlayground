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

## Storage decision (2026-10-01)

**Setup A: everything runs on your own computer.** `DATA_ROOT` is the Google Drive for desktop folder
`My Drive/uw_gamma_data`. Files are written on the computer and Drive uploads them automatically, so
there's a local copy and a cloud backup, and nothing is lost when a Claude Code session ends.

- Free Drive space reported: about 150 GB, more available on request. The D4 stop-and-ask threshold
  stays at 100 GB, as in the brief.
- Claude Code's cloud container is *not* used for data: it is deleted when the session ends and has
  about 30 GB of disk.
- Bandwidth: each day's raw tape is about 2 GB to download (deleted after filtering), so the 60-day pilot
  is about 120 GB of downloads. The full ~730-day history would be about 1.5 TB of downloads, which may
  hit a home-internet data cap. That decision is made after the pilot, with the measured numbers.

## Running the tape work on your computer (setup A)

1. Do the collector setup in `collector/README.md` first: Google Drive for desktop, Python, clone,
   `gamma_nodes/.env`.
2. `python -m pip install -r gamma_nodes/requirements.txt`
3. Open Claude Code on the computer (the desktop app's Code tab, or the `claude` CLI) in the
   `ClaudePlayground` folder, on branch `claude/new-session-9iepkd`, and say: *"Continue the gamma_nodes
   study from the status in gamma_nodes/README.md."* It reads the key and `DATA_ROOT` from
   `gamma_nodes/.env`.

## Status (2026-10-01, end of first session)

| step | state |
|---|---|
| Protocol | committed in `a22d942` before any data was touched; Amendment 1 is a clarification |
| Live collector | written and tested offline; **must be installed on your computer before 09:35 ET** (see `collector/README.md`) |
| Tape ingest, prices, rebuild, validation | written and unit-tested on synthetic data; not yet run on real data |
| Storage | decided: setup A, about 150 GB free on Drive |
| Blocked on | a session that can read `UW_API_KEY`: Claude Code on your computer with `gamma_nodes/.env` |

Next commands (from `gamma_nodes/`):

```
python src/tape_ingest.py probe                 # D1: history window
python src/tape_ingest.py range 2026-09-29 2026-10-01 --confirm   # first 3 days
python src/pipeline.py estimate                 # D4: projection -> STOP and ask if > 100 GB
python src/tape_ingest.py pilot --confirm       # 60-day pilot (skips days already done)
python src/pipeline.py coverage                 # results/data_coverage.md
python src/pipeline.py validate 2026-10-02 ...  # step 3 once >= 5 live+tape days exist (about Oct 9)
```
