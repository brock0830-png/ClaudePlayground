"""Print gate pass counts, jitter-percentile distributions and top variants from results/log.csv."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from scalpel.data import RESULTS
from scalpel.gates import add_gates

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
log = pd.read_csv(RESULTS / "log.csv")
stage = sys.argv[1] if len(sys.argv) > 1 else None
g = add_gates(log)
if stage:
    g = g[g["stage"].astype(str) == stage]
print("rows in log:", len(log), " directional rows shown:", len(g))
grp = ["family", "tf"]
agg = g.groupby(grp).agg(n_var=("ev", "size"), ev_pos=("ev", lambda x: (x > 0).mean()),
                         med_n=("n", "median"), jit_pct_mean=("jit_pct", "mean"),
                         jit_ge90=("jit_pct", lambda x: (x >= 90).mean()),
                         beat_grid=("ev", lambda x: np.nan),
                         G1=("G1", "sum"), G2=("G2", "sum"), G3=("G3", "sum"), G4=("G4", "sum"),
                         G5=("G5", "sum"), G6=("G6", "sum"), G124=("G124", "sum"), ALL=("ALL", "sum"))
agg["beat_grid"] = g.assign(b=g["ev"] > g["grid_ev"]).groupby(grp)["b"].mean()
print(agg.round(3).to_string())
print("\nby side/mode:")
print(g.groupby(["side", "mode"]).agg(n=("ev", "size"), ev_pos=("ev", lambda x: (x > 0).mean()),
                                      jit_mean=("jit_pct", "mean"), G4=("G4", "sum")).round(3).to_string())
print("\njitter percentile histogram (all directional variants with trades):")
h, e = np.histogram(g["jit_pct"].dropna(), bins=10, range=(0, 100))
print(dict(zip([f"{int(a)}-{int(b)}" for a, b in zip(e[:-1], e[1:])], h)))
cols = ["variant_id", "family", "tf", "mode", "roll", "side", "level", "trig", "stop", "target", "filters", "n", "ev", "ci_lo",
        "ev_R", "ciR_lo", "pf", "pos_years", "jit_pct", "grid_ev", "rand_pct", "wf_pnl", "G1", "G2", "G3", "G4", "G5", "G6"]
print("\nALL gates:")
print(g[g["ALL"]].sort_values("ciR_lo", ascending=False)[cols].head(30).to_string())
print("\nG1+G2+G4 (top 40 by ciR_lo):")
print(g[g["G124"]].sort_values("ciR_lo", ascending=False)[cols].head(40).to_string())
print("\nTop 25 by ciR_lo with n>=100 regardless of gates:")
print(g[g["n"] >= 100].sort_values("ciR_lo", ascending=False)[cols].head(25).to_string())
