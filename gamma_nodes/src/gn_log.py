"""results/log.csv: one row per variant tried, including failures (PROTOCOL §8)."""
from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timezone

from gn_config import PROJECT, RESULTS

LOG = RESULTS / "log.csv"
FIELDS = ("variant_id", "family", "dataset", "params_json", "n", "metric", "value", "ci_lo",
          "ci_hi", "status", "note", "code_commit", "logged_at_utc")


def code_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def log_rows(rows: list[dict]) -> None:
    commit = code_commit()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            r = dict(r)
            if isinstance(r.get("params_json"), dict):
                r["params_json"] = json.dumps(r["params_json"], sort_keys=True)
            r.setdefault("code_commit", commit)
            r.setdefault("logged_at_utc", now)
            w.writerow(r)
