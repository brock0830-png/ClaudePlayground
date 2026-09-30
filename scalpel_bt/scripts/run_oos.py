"""
ONE-SHOT OOS RUN (PROTOCOL 7). Refuses to run unless results/OOS_UNLOCKED names the commit
that froze results/frozen_rules.md and results/frozen_candidates.json.
Writes results/oos_results.json, results/oos_trades_<name>.csv, results/oos_<name>.png.
DSR: per-trade Sharpe, T = OOS trades, trial variance = variance of sharpe_t over the
directional rows of results/log.csv with n >= 100, N = all rows of results/log.csv.
"""
import sys, json, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
from scalpel.data import load_bars, RESULTS, OOS_LOCK, OOS_START
from scalpel.features import build_frame
from candidate_eval import evaluate_candidate, load_spec

ROOT = Path(__file__).resolve().parents[1]


def check_lock():
    if not OOS_LOCK.exists():
        raise SystemExit("OOS locked")
    h = OOS_LOCK.read_text().split()[0]
    froz = subprocess.run(["git", "log", "-1", "--format=%H", "--", "results/frozen_rules.md", "results/frozen_candidates.json"],
                          cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "results/frozen_rules.md", "results/frozen_candidates.json",
                            "scalpel", "scripts"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if h != froz or dirty:
        raise SystemExit(f"lock hash {h} != freeze commit {froz} or frozen files modified:\n{dirty}")
    return h


def verdict(c, prim, dev_all_gates: bool):
    m = prim["metrics"]
    if not dev_all_gates:
        return "DON'T TRADE IT (exploratory candidate)"
    if m.get("trades", 0) == 0 or m["ev_pts"] <= 0:
        return "DON'T TRADE IT (OOS EV/trade <= 0)"
    trade = (m["ev_ci95"][0] > 0 and m["profit_factor"] > 1.1 and prim["dsr"]["dsr"] > 0.95
             and prim["jitter"]["pct_rank_of_actual"] >= 90)
    return "TRADE IT" if trade else "PAPER TRADE IT"


def main():
    h = check_lock()
    log = pd.read_csv(RESULTS / "log.csv")
    d = log[~log["modeled"].astype(bool)]
    trial_var = float(d[d["n"] >= 100]["sharpe_t"].var())
    n_trials = int(len(log))
    fr = build_frame(load_bars("all"))
    end = fr.bars.index[-1]
    cands = json.loads((RESULTS / "frozen_candidates.json").read_text())
    out = {"freeze_commit": h, "n_trials": n_trials, "trial_var": trial_var, "oos_start": str(OOS_START),
           "oos_end": str(end), "candidates": []}
    for c in cands:
        spec = load_spec(c["spec"])
        prim, t = evaluate_candidate(fr, spec, OOS_START, end, trial_var, n_trials,
                                     plot_path=RESULTS / f"oos_{c['name']}.png",
                                     title=f"OOS {c['name']} (net pts per 1 ES; grey = 60 jittered-level runs)")
        t.to_csv(RESULTS / f"oos_trades_{c['name']}.csv", index=False)
        rob = {}
        for rname, rspec in c["robustness"].items():
            r, _ = evaluate_candidate(fr, load_spec(rspec), OOS_START, end, trial_var, n_trials)
            rob[rname] = r
        out["candidates"].append({"name": c["name"], "variant_id": c["variant_id"], "primary": prim,
                                  "robustness": rob, "verdict": verdict(c, prim, c["dev_all_gates"])})
        print(c["name"], json.dumps(prim["metrics"], default=str)[:400], out["candidates"][-1]["verdict"], flush=True)
    (RESULTS / "oos_results.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
