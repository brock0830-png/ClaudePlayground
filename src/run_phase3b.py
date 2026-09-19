"""Phase 3b: H1 rerun (sign fix), overlays H7/H8/H9/H11/H12, robustness on P1-passing cells."""
from __future__ import annotations
import itertools, json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trials import load_panel, trial, evaluate, DESIGN
from strategies import *
from engine import BASE_LAG

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "phase3"
R, L, VIX = load_panel()
META = json.loads((ROOT / "data/proxies/meta.json").read_text())
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
COLS = ["CAGR", "Vol", "Sharpe", "MaxDD", "MAR", "Turnover_ann", "TradesPerYear", "ConsecRoundTripsPerYear", "AvgLeverage"]


def row(tag, m):
    return {"cell": tag, **{k: m[k] for k in COLS}, "trial": m["trial_id"]}


def drag_panel(R, ann):
    """Add `ann` per year of extra drag on simulated (pre-inception) segments of leveraged and inverse funds."""
    R2 = R.copy()
    for c in LEVERAGED_COLS:
        fund = c[:-2]
        if f"{fund}_sim" in META:
            start = pd.Timestamp(META[f"{fund}_sim"]["live_start"])
            R2.loc[R2.index < start, c] = R2.loc[R2.index < start, c] - ann / 252
    return R2


which = sys.argv[1] if len(sys.argv) > 1 else "all"
rows = []

if which in ("all", "H1"):
    for E, n, bear in itertools.product(["SPY", "QQQ"], [100, 150, 200, 250], [0, 1, 2]):
        p = {"E": E, "n": n, "bear": bear}
        m, _ = trial("P3", "H1", f"H1_{E}_{n}_b{bear}", p, h1_trend(R, L, **p), R, note="rerun after bear-sign fix")
        rows.append(row(f"H1 {E}/{n}/b{bear}", m))

# core cells used by overlays (registered: grid-median cell; plus the P1-passing core cell, disclosed)
H3_CORE = {"E": "QQQ", "n_trend": 200, "target": 0.10, "cap": 1.5, "bear": 0}
H3_MED = {"E": "SPY", "n_trend": 200, "target": 0.15, "cap": 1.5, "bear": 0}
H6_CORE = {"n_trend": 200, "target": 0.09, "cap": 1.5, "bear": 0}
H6_MED = {"n_trend": 150, "target": 0.09, "cap": 1.5, "bear": 0}

if which in ("all", "overlays"):
    for name, fn, base_p in [("H3core", h3_trend_vol, H3_CORE), ("H3med", h3_trend_vol, H3_MED), ("H6core", h6_multi, H6_CORE), ("H6med", h6_multi, H6_MED)]:
        w = fn(R, L, **base_p)
        m0, res0 = evaluate(w, R)
        base_eq = res0.equity.reindex(R.index).ffill()   # design-window equity of the un-overlaid rule
        for D in [0.05, 0.10]:
            m, _ = trial("P3", "H7", f"H7_{name}_D{D}", {"base": name, **base_p, "D": D}, dd_overlay(w, base_eq, D), R)
            rows.append(row(f"H7 {name} D={D}", m))
        if name.startswith("H3"):
            for V in [20, 25]:
                m, _ = trial("P3", "H8", f"H8_{name}_V{V}", {"base": name, **base_p, "V": V}, vix_overlay(w, VIX, V), R)
                rows.append(row(f"H8 {name} V={V}", m))
            for bond in ["TLT_X", "IEF_X"]:
                m, _ = trial("P3", "H9", f"H9_{name}_{bond}", {"base": name, **base_p, "bond": bond}, bonds_instead_of_cash(w, L, bond), R)
                rows.append(row(f"H9 {name} {bond}", m))
            for n in [150, 200]:
                m, _ = trial("P3", "H11", f"H11_{name}_{n}", {"base": name, **base_p, "n": n}, gold_sleeve(w, L, n), R)
                rows.append(row(f"H11 {name} gold{n}", m))
    # H12 blend of H3 core and H5 median cell (126/2) with H7 at better D
    w3 = h3_trend_vol(R, L, **H3_CORE); w5 = h5_rotation(R, L, M=126, k=2).reindex(R.index).ffill().fillna(0.0)
    for wt in [0.5, 0.7]:
        wb = wt * w3 + (1 - wt) * w5
        m0, res0 = evaluate(wb, R)
        base_eq = res0.equity.reindex(R.index).ffill()
        m, _ = trial("P3", "H12", f"H12_w{wt}", {"w_h3": wt, "h5": "126/2"}, wb, R); rows.append(row(f"H12 blend w3={wt} (no DD)", m))
        m, _ = trial("P3", "H12", f"H12_w{wt}_D0.1", {"w_h3": wt, "h5": "126/2", "D": 0.10}, dd_overlay(wb, base_eq, 0.10), R); rows.append(row(f"H12 blend w3={wt} D=0.10", m))

if which in ("all", "robust"):
    cands = {"H1 QQQ/250/b0": h1_trend(R, L, E="QQQ", n=250, bear=0),
             "H1 QQQ/200/b0": h1_trend(R, L, E="QQQ", n=200, bear=0),
             "H3 QQQ/200/0.10/1.5/b0": h3_trend_vol(R, L, **H3_CORE),
             "H5 126/3": h5_rotation(R, L, M=126, k=3), "H5 252/3": h5_rotation(R, L, M=252, k=3),
             "H6 200/0.09/1.5/b0": h6_multi(R, L, **H6_CORE),
             "B3 SPY/200": b3_spy_sma(R, L)}
    subs = [("1998-01-02", "2002-12-31"), ("2003-01-01", "2007-12-31"), ("2008-01-01", "2009-12-31"), ("2010-01-01", "2015-12-31")]
    for name, w in cands.items():
        hyp = name.split()[0]
        for tag, kw in [("lag3", {"lag": 3}), ("lag1", {"lag": 1}), ("cost0", {"cost_mult": 0.0}), ("cost3", {"cost_mult": 3.0})]:
            m, _ = trial("P3R", hyp, f"{name} {tag}", {"cell": name, **kw}, w, R, **kw); rows.append(row(f"{name} {tag}", m))
        for a, b in subs:
            m, _ = trial("P3R", hyp, f"{name} drop{a[:4]}-{b[:4]}", {"cell": name, "drop": f"{a[:4]}-{b[:4]}"}, w, R, drop_periods=[(a, b)])
            rows.append(row(f"{name} drop {a[:4]}-{b[:4]}", m))
        if hyp in ("H3", "H6"):
            for d in [-0.01, 0.01]:
                m, _ = trial("P3R", hyp, f"{name} drag{d:+}", {"cell": name, "sim_drag": d}, w, drag_panel(R, d)); rows.append(row(f"{name} simdrag{d:+.0%}", m))

df = pd.DataFrame(rows); df.to_csv(OUT / f"phase3b_{which}.csv", index=False)
print(df.round(3).to_string())
