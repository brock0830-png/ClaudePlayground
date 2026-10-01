"""Orchestration for the data and validation steps (run from gamma_nodes/).

  python src/pipeline.py estimate               D4: size per day from the first 3 tape days,
                                                projected to 60 days and to the full window
  python src/pipeline.py coverage               write results/data_coverage.md
  python src/pipeline.py validate DATE [DATE ...]
                                                step 3 on days with tape + live data:
                                                ingest, prices, D3, rebuild, compare, report
"""
from __future__ import annotations

import io
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gn_calendar as cal  # noqa: E402
import prices  # noqa: E402
import rebuild as rb  # noqa: E402
import tape_ingest as ti  # noqa: E402
import validate as va  # noqa: E402
from gn_config import RESULTS, WORK, load  # noqa: E402
from gn_log import log_rows  # noqa: E402
from gn_store import Store, sha256_file  # noqa: E402

DRIVE_CAP_BYTES = 100e9
FULL_HISTORY_DAYS = 730


def estimate(store: Store) -> str:
    man = [r for r in store.manifest() if r["file"].startswith("tape/")]
    if len(man) < 3:
        return f"need 3 ingested days for the estimate, have {len(man)}"
    first3 = sorted(man, key=lambda r: r["date"])[:3]
    per_day = sum(int(r["bytes"]) for r in first3) / 3
    p60, pfull = per_day * 60, per_day * FULL_HISTORY_DAYS
    live_day = 79 * 8 * 60_000  # rough: 79 slots x ~8 files x ~60 KB, refined once live data exists
    lines = [
        f"per-day filtered tape (mean of {', '.join(r['date'] for r in first3)}): {per_day / 1e6:.1f} MB",
        f"projected 60 days: {p60 / 1e9:.2f} GB",
        f"projected full history ({FULL_HISTORY_DAYS} trading days): {pfull / 1e9:.2f} GB",
        f"live collector, rough: {live_day / 1e6:.0f} MB per day",
        f"D4 gate: STOP and ask if the projection exceeds free Drive space or {DRIVE_CAP_BYTES / 1e9:.0f} GB",
        "full history exceeds 100 GB -> STOP" if pfull > DRIVE_CAP_BYTES else "full history within 100 GB",
    ]
    return "\n".join(lines)


def coverage(store: Store) -> Path:
    man = pd.DataFrame(store.manifest())
    log_txt = store.read_text("INGEST_LOG.csv")
    ing = pd.read_csv(io.StringIO(log_txt)) if log_txt else pd.DataFrame()
    out = ["# Data coverage", "", f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC from "
           "`DATA_ROOT/MANIFEST.csv` and `INGEST_LOG.csv`.", ""]
    if not man.empty:
        tape = man[man["file"].str.startswith("tape/")].sort_values("date")
        tape["bytes"] = tape["bytes"].astype(int)
        first, last = date.fromisoformat(tape["date"].iloc[0]), date.fromisoformat(tape["date"].iloc[-1])
        have = set(tape["date"])
        gaps = [d.isoformat() for d in cal.trading_days(first, last) if d.isoformat() not in have]
        out += ["## Full Tape (filtered)", "",
                f"- days: {len(tape)} ({first} to {last})",
                f"- total size: {tape['bytes'].sum() / 1e9:.2f} GB; mean {tape['bytes'].mean() / 1e6:.1f} MB/day",
                f"- missing trading days inside that range: {', '.join(gaps) if gaps else 'none'}", "",
                "| date | rows | MB |", "|---|---:|---:|"]
        out += [f"| {r.date} | {int(r.rows):,} | {r.bytes / 1e6:.1f} |" for r in tape.itertuples()]
    if not ing.empty and "status" in ing:
        bad = ing[ing["status"] != "ok"]
        if len(bad):
            out += ["", "## Failed ingests", "", "| date | note |", "|---|---|"]
            out += [f"| {r.date} | {str(r.note)[:200]} |" for r in bad.itertuples()]
    p = RESULTS / "data_coverage.md"
    p.write_text("\n".join(out) + "\n")
    return p


def heatmap_for(d: date, cfg, store: Store) -> pd.DataFrame:
    rel = f"heatmaps/{d.isoformat()}.parquet"
    if store.exists(rel):
        return pd.read_parquet(store.local_path(rel, WORK))
    tape = pd.read_parquet(store.local_path(f"tape/{d.isoformat()}.parquet", WORK))
    bars = prices.parse_1m(prices.fetch_1m(d, cfg, store).read_bytes(), d)
    spxw = tape[tape["option_chain_id"].str.startswith("SPXW") & (tape["expiry"] == d)]
    d3 = prices.check_day_d3(bars, spxw, d)
    log_rows([{"variant_id": f"D3-{d}", "family": "data", "dataset": "validation", "params_json": d3,
               "n": d3["matched_minutes"], "metric": "median_abs_diff_pts",
               "value": d3["median_abs_diff_pts"], "status": "ok" if d3["pass"] else "failed"}])
    if not d3["pass"]:
        raise ti.StopError(f"D3 price-path gate failed on {d}: {d3}")
    heat = rb.rebuild_day(tape, bars, d, cal.close_time_et(d))
    # XSP is stored alongside but not used in the grid (PROTOCOL §3); XSP = SPX / 10
    xsp_bars = bars[["open", "high", "low", "close"]] / 10.0
    heat = pd.concat([heat, rb.rebuild_day(tape, xsp_bars, d, cal.close_time_et(d), root="XSP")],
                     ignore_index=True)
    local = WORK / "heatmaps" / f"{d.isoformat()}.parquet"
    local.parent.mkdir(parents=True, exist_ok=True)
    heat.to_parquet(local, compression="zstd")
    store.put(local, rel)
    store.manifest_add(d.isoformat(), rel, len(heat), local.stat().st_size, sha256_file(local))
    return heat


def run_validation(days: list[date], cfg, store: Store) -> int:
    per_snap, signs, used, skipped = [], {}, [], []
    for d in days:
        live_dir = store.local_path(f"live/{d.isoformat()}", WORK)
        cov = va.slot_coverage(live_dir, d) if live_dir.is_dir() else 0.0
        if cov < va.MIN_SLOT_COVERAGE:
            skipped.append(f"{d} (live coverage {cov:.0%})")
            continue
        try:
            if not any(r["date"] == d.isoformat() and r["file"].startswith("tape/") for r in store.manifest()):
                ti.ingest_day(d, cfg, store)
            heat = heatmap_for(d, cfg, store)
        except ti.StopError as e:
            print(f"STOP: {e}")
            return 1
        live = va.load_live_day(live_dir)
        signs[d.isoformat()] = va.sign_report(live)
        per_snap.append(va.validate_day(d, live, heat[heat["root"] == "SPXW"]))
        used.append(d.isoformat())
    if not per_snap:
        print("no validation days with enough live coverage yet:", ", ".join(skipped))
        return 1
    ps = pd.concat(per_snap, ignore_index=True)
    summ = va.summarize(ps)
    log_rows([{"variant_id": f"VAL-{r.variant}", "family": "validation", "dataset": "validation",
               "params_json": {"variant": r.variant, "days": int(r.days)}, "n": int(r.snapshots),
               "metric": "top_exact", "value": round(r.top_exact, 4),
               "status": "pass" if r["pass"] else "fail",
               "note": f"spearman_median={r.spearman_median:.3f}; top_within5={r.top_within5:.3f}"}
              for _, r in summ.iterrows()])
    d_pass = bool(summ[summ["view"] == "D"]["pass"].any())
    lines = ["# Step 3 validation: rebuilt 0DTE profile vs UW live snapshots", "",
             f"Days used: {', '.join(used)}" + (f". Skipped: {', '.join(skipped)}" if skipped else ""), "",
             f"Pass bar per view: top-node exact match >= {va.PASS_TOP:.0%} and median Spearman >= "
             f"{va.PASS_SPEARMAN} over >= {va.MIN_DAYS} days and >= {va.MIN_SNAPS} snapshots "
             "(strikes within +-1.5% of UW's price).", "",
             f"**Gate: {'PASS' if d_pass else 'FAIL'}** (directionalized view).", "",
             "| view | variant | days | snapshots | top exact | top within 5 | median Spearman | pass |",
             "|---|---|---:|---:|---:|---:|---:|---|"]
    lines += [f"| {r.view} | {r.variant} | {r.days} | {r.snapshots} | {r.top_exact:.1%} | "
              f"{r.top_within5:.1%} | {r.spearman_median:.3f} | {'yes' if r['pass'] else 'no'} |"
              for _, r in summ.iterrows()]
    lines += ["", "## UW sign conventions observed (sign of median non-zero value)", "",
              "| date | " + " | ".join(va.UW_FIELDS) + " |", "|---|" + "---|" * len(va.UW_FIELDS)]
    lines += [f"| {k} | " + " | ".join(str(v.get(f)) for f in va.UW_FIELDS) + " |" for k, v in signs.items()]
    (RESULTS / "validation.md").write_text("\n".join(lines) + "\n")
    ps.to_csv(RESULTS / "validation_per_snapshot.csv", index=False)
    print("\n".join(lines[:8]))
    return 0 if d_pass else 1


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cfg = load()
    store = Store(cfg)
    if argv[0] == "estimate":
        print(estimate(store))
        return 0
    if argv[0] == "coverage":
        print(coverage(store))
        return 0
    if argv[0] == "validate":
        return run_validation([date.fromisoformat(a) for a in argv[1:]], cfg, store)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
