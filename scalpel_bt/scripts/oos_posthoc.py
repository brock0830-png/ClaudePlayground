"""
POST-HOC diagnostic after the one-shot OOS run (not part of the pre-registered verdict,
no rule changed): how much of each frozen candidate's OOS P&L is plain long drift?
(1) random-entry baseline: same number of trades, same holding times, entry bars drawn at
random from the candidate's eligible OOS bars, 1,000 runs; (2) ES buy-and-hold drift per
4h bar over the OOS window, with contract-switch gaps removed.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
from scalpel.data import load_bars, RESULTS, OOS_START
from scalpel.features import build_frame
from scalpel.screen import run_spec, random_entry_ev
from scalpel.options import roll_adjusted_close
from candidate_eval import load_spec

fr = build_frame(load_bars("all"))
start = int(np.searchsorted(fr.bars.index, OOS_START))
end = len(fr.o)
adj = roll_adjusted_close(fr.bars)
c_adj = fr.c - adj
drift_per_bar = (c_adj[-1] - fr.o[start]) / (end - start)
out = {"oos_bars": end - start, "es_buy_hold_pts_switch_adjusted": float(c_adj[-1] - fr.o[start]),
       "drift_pts_per_4h_bar": float(drift_per_bar), "candidates": []}
for c in json.loads((RESULTS / "frozen_candidates.json").read_text()):
    spec = load_spec(c["spec"])
    parts = run_spec(fr, spec, 0, end)
    keep = [p["ei"] >= start for p in parts]
    parts = [{k: (v[m] if isinstance(v, np.ndarray) else v) for k, v in p.items()} for p, m in zip(parts, keep)]
    ev = float(np.concatenate([p["net"] for p in parts]).mean())
    held = float(np.concatenate([p["xi"] - p["ei"] + 1 for p in parts]).mean())
    rev = random_entry_ev(fr, spec, parts, start, end, np.random.default_rng(99), n_runs=1000)
    out["candidates"].append({"name": c["name"], "oos_ev_pts": ev, "avg_bars_held": held,
                              "random_entry_mean_ev": float(np.nanmean(rev)),
                              "random_entry_p90_ev": float(np.nanquantile(rev, 0.9)),
                              "pct_rank_vs_random_entry": float((rev < ev).mean() * 100),
                              "drift_expectation_pts": float(drift_per_bar * held - 0.60)})
(RESULTS / "oos_posthoc.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
