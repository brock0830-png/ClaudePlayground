"""DEV pages for the frozen candidates (same evaluation code as the OOS run, DEV bars only)."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
from scalpel.data import load_bars, RESULTS, DEV_START, DEV_END
from scalpel.features import build_frame
from candidate_eval import evaluate_candidate, load_spec

log = pd.read_csv(RESULTS / "log.csv")
d = log[~log["modeled"].astype(bool)]
trial_var = float(d[d["n"] >= 100]["sharpe_t"].var())
n_trials = int(len(log))
fr = build_frame(load_bars("dev"))
cands = json.loads((RESULTS / "frozen_candidates.json").read_text())
out = {"n_trials": n_trials, "trial_var": trial_var, "candidates": []}
for c in cands:
    prim, t = evaluate_candidate(fr, load_spec(c["spec"]), DEV_START, DEV_END, trial_var, n_trials,
                                 plot_path=RESULTS / f"dev_{c['name']}.png",
                                 title=f"DEV {c['name']} (net pts per 1 ES; grey = 60 jittered-level runs)")
    t.to_csv(RESULTS / f"dev_trades_{c['name']}.csv", index=False)
    rob = {k: evaluate_candidate(fr, load_spec(v), DEV_START, DEV_END, trial_var, n_trials, n_jit=100)[0]["metrics"]
           for k, v in c["robustness"].items()}
    out["candidates"].append({"name": c["name"], "primary": prim, "robustness_metrics": rob})
    m = prim["metrics"]
    print(c["name"], m["trades"], round(m["ev_pts"], 3), m["ev_ci95"], round(m["profit_factor"], 3), prim["jitter"], prim["grid"], prim["dsr"])
(RESULTS / "dev_candidates.json").write_text(json.dumps(out, indent=1, default=str))
