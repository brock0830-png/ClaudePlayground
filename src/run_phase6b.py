"""Phase 6b: frontier comparison at matched drawdown. TALOS vs TALOS+dipvol vs TALOS+dipvol+gold across the exposure
multiplier, 1991-2026 (design / confirm / full). Logged as P6 'frontier'."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_phase6 as P6   # re-uses its panel, evaluate() and ledger de-duplication (cells already logged are not re-logged)
import system2 as S2

OUT = P6.OUT
P0 = dict(S2.PARAMS2, lever=1.0)
V = {"TALOS": P0,
     "TALOS+dipvol": dict(P0, dip_n=10, dip_hold=5, dip_mult=2.0),
     "TALOS+dipvol+gold": dict(P0, dip_n=10, dip_hold=5, dip_mult=2.0, w_gold=0.3, gold_vt=0.10)}
rows = []
for name, p in V.items():
    for lev in [1.0, 1.25, 1.5, 1.75, 2.0, 2.5]:
        m = P6.evaluate(f"{name} lever={lev}", "FRONTIER", dict(p, lever=lev), periods=("design", "confirm", "full"), note="P6 frontier at matched drawdown")
        for per, mm in m.items():
            rows.append({"variant": name, "lever": lev, "period": per, **{k: mm[k] for k in ("CAGR", "Vol", "Sharpe", "MaxDD", "MAR", "AvgLeverage", "TradesPerYear", "ConsecRoundTripsPerYear")}, "MaxDD_trough": mm["MaxDD_trough"]})
df = pd.DataFrame(rows); df.to_csv(OUT / "frontier.csv", index=False)
for per in ("full", "design", "confirm"):
    print("\n==", per)
    print(df[df.period == per].pivot(index="lever", columns="variant", values=["CAGR", "MaxDD", "MAR"]).round(3).to_string())
