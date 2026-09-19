"""Phase 3: baselines and the pre-registered grids on the design window. Writes reports/phase3/*.csv and a summary md."""
from __future__ import annotations
import itertools, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trials import load_panel, trial, evaluate, DESIGN
from strategies import *
from engine import BASE_LAG

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "phase3"; OUT.mkdir(parents=True, exist_ok=True)
R, L, VIX = load_panel()
rows = []


def rec(hyp, cell, params, m, **extra):
    rows.append({"hyp": hyp, "cell": cell, **params, "CAGR": m["CAGR"], "Vol": m["Vol"], "Sharpe": m["Sharpe"],
                 "Sortino": m["Sortino"], "MaxDD": m["MaxDD"], "MAR": m["MAR"], "Turnover": m["Turnover_ann"],
                 "TradesPY": m["TradesPerYear"], "ConsecRT": m["ConsecRoundTripsPerYear"], "AvgLev": m["AvgLeverage"],
                 "TIM": m.get("TimeInMarket"), "CorrSPY": m.get("CorrSPY"), "trial": m["trial_id"], **extra})


which = sys.argv[1] if len(sys.argv) > 1 else "all"

if which in ("all", "base"):
    for name, fn, params in [("B1", b1_spy, {}), ("B2", b2_6040, {}), ("B3", b3_spy_sma, {"n": 200}),
                             ("B4", b4_voltarget, {"target": 0.10, "n": 20, "cap": 1.0}),
                             ("B4x", b4_voltarget, {"target": 0.10, "n": 20, "cap": 1.5})]:
        m, _ = trial("P3", name, name, params, fn(R, L, **params), R)
        rec(name, name, params, m)

if which in ("all", "H1"):
    for E, n, bear in itertools.product(["SPY", "QQQ"], [100, 150, 200, 250], [0, 1, 2]):
        p = {"E": E, "n": n, "bear": bear}
        m, _ = trial("P3", "H1", f"H1_{E}_{n}_b{bear}", p, h1_trend(R, L, **p), R); rec("H1", f"{E}/{n}/b{bear}", p, m)
if which in ("all", "H2"):
    for E, target, n, cap in itertools.product(["SPY", "QQQ"], [0.10, 0.15], [20, 60], [1.0, 2.0]):
        p = {"E": E, "target": target, "n": n, "cap": cap}
        m, _ = trial("P3", "H2", f"H2_{E}_{target}_{n}_{cap}", p, h2_vol(R, L, **p), R); rec("H2", f"{E}/{target}/{n}/{cap}", p, m)
if which in ("all", "H3"):
    for E, nt, target, cap, bear in itertools.product(["SPY", "QQQ"], [150, 200], [0.10, 0.15], [1.5, 2.0], [0, 1]):
        p = {"E": E, "n_trend": nt, "target": target, "cap": cap, "bear": bear}
        m, _ = trial("P3", "H3", f"H3_{E}_{nt}_{target}_{cap}_b{bear}", p, h3_trend_vol(R, L, **p), R); rec("H3", f"{E}/{nt}/{target}/{cap}/b{bear}", p, m)
if which in ("all", "H4"):
    for E, D, lev in itertools.product(["SPY", "QQQ"], [0.03, 0.05, 0.08], [2, 3]):
        p = {"E": E, "D": D, "lev": lev}
        m, _ = trial("P3", "H4", f"H4_{E}_{D}_{lev}", p, h4_dip(R, L, **p), R); rec("H4", f"{E}/{D}/{lev}", p, m)
if which in ("all", "H5"):
    for M, k in itertools.product([126, 252], [1, 2, 3]):
        p = {"M": M, "k": k}
        m, _ = trial("P3", "H5", f"H5_{M}_{k}", p, h5_rotation(R, L, **p), R); rec("H5", f"{M}/{k}", p, m)
if which in ("all", "H6"):
    for nt, target, cap, bear in itertools.product([150, 200], [0.09, 0.12], [1.5, 2.0], [0, 1]):
        p = {"n_trend": nt, "target": target, "cap": cap, "bear": bear}
        m, _ = trial("P3", "H6", f"H6_{nt}_{target}_{cap}_b{bear}", p, h6_multi(R, L, **p), R); rec("H6", f"{nt}/{target}/{cap}/b{bear}", p, m)
if which in ("all", "H10"):
    for E, c, fund in itertools.product(["SPY", "QQQ"], [2, 3], [1, 2]):
        p = {"E": E, "c": c, "fund": fund}
        m, _ = trial("P3", "H10", f"H10_{E}_{c}_{fund}", p, h10_reversal(R, L, **p), R); rec("H10", f"{E}/{c}/{fund}", p, m)

df = pd.DataFrame(rows)
df.to_csv(OUT / f"grid_{which}.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
print(df.drop(columns=[c for c in df.columns if c in ("Sortino", "TIM")]).round(3).to_string())
