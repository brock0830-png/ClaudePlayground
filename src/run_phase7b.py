"""Phase 7b: frontier across the multiplier for the two MAR-only improvements found in phase 7 (gate hysteresis 1%,
SMA 250) and their combination, vs T6. Rule widened after phase 7 (disclosed): an idea that leaves CAGR flat but lifts
MAR at 1x is judged at matched drawdown through the multiplier, not rejected outright."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_phase7 as P7   # importing re-runs phase 7 idempotently (ledger de-duplicated by cell name)
import system2 as S2

OUT = P7.OUT; T6 = P7.T6
V = {"T6": T6, "T6+gate1%": dict(T6, gate_band=0.01), "T6+SMA250": dict(T6, sma_len=250), "T6+gate1%+SMA250": dict(T6, gate_band=0.01, sma_len=250)}
rows = []
for name, p in V.items():
    for lev in [1.0, 1.25, 1.5, 1.75, 2.0, 2.5]:
        m = P7.ev(f"{name} lever={lev}", "P7-frontier", dict(p, lever=lev), note="P7 frontier at matched drawdown")
        for per, mm in m.items():
            rows.append({"variant": name, "lever": lev, "period": per, **{k: mm[k] for k in ("CAGR", "Vol", "Sharpe", "MaxDD", "MAR", "AvgLeverage", "TradesPerYear", "ConsecRT")}, "MaxDD_trough": mm["MaxDD_trough"]})
df = pd.DataFrame(rows); df.to_csv(OUT / "frontier.csv", index=False)
for per in ("full", "design", "confirm"):
    print("\n==", per); print(df[df.period == per].pivot(index="lever", columns="variant", values=["CAGR", "MaxDD", "MAR"]).round(3).to_string())
pd.DataFrame({k: v.returns for k, v in P7.curves.items()}).to_parquet(OUT / "daily_returns.parquet")
