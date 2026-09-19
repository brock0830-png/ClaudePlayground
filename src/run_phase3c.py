"""Phase 3c: candidate system variants (logged as H12 variants) and the leverage frontier on the design window."""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trials import load_panel, trial, evaluate
from engine import run, BASE_LAG
import system as S
from strategies import ALL_COLS, LEVERAGE
from trials import cost_model

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "reports" / "phase3"
R, L, VIX = load_panel()
pd.set_option("display.width", 250)
COLS = ["CAGR", "Vol", "Sharpe", "MaxDD", "MAR", "Turnover_ann", "TradesPerYear", "ConsecRoundTripsPerYear", "AvgLeverage"]
rows = []


def run_variant(tag, p, band=0.0, hyp="H12", note="", lag=BASE_LAG, cost_mult=1.0, drop=None, Rx=None):
    Rx = R if Rx is None else Rx
    p0 = {**p, "dd_cut": 0.0}
    w0 = S.build(Rx, L, p0)
    if band > 0:
        # engine-level rebalance band: run manually so we can pass the threshold
        from trials import DESIGN
        idx = Rx.index[(Rx.index >= DESIGN[0]) & (Rx.index <= DESIGN[1])]
        res0 = run(w0.loc[idx], Rx[ALL_COLS], Rx["CASH"], cost_model(cost_mult), lag=lag, leverage=LEVERAGE, rebalance_threshold=band)
        base_eq = res0.equity.reindex(Rx.index).ffill()
        w = S.build(Rx, L, p, base_eq) if p["dd_cut"] > 0 else w0
        from trials import summary, consecutive_roundtrips, log
        res = run(w.loc[idx], Rx[ALL_COLS], Rx["CASH"], cost_model(cost_mult), lag=lag, leverage=LEVERAGE, rebalance_threshold=band)
        ret = res.returns; keep = pd.Series(True, ret.index)
        if drop:
            for a, b in drop: keep[(ret.index >= a) & (ret.index <= b)] = False
        ret = ret[keep]
        m = summary(ret, rf=Rx["CASH"], spy=Rx["SPY_X"], weights_held=res.weights_held[keep], gross_leverage=res.gross_leverage.abs()[keep],
                    turnover=res.turnover[keep], trades=res.trades[keep])
        m["ConsecRoundTripsPerYear"] = consecutive_roundtrips(res.deltas[keep]) / (len(ret) / 252)
        m["trial_id"] = log("P3C", hyp, tag, {**p, "band": band}, DESIGN, lag, cost_mult, m, note)
    else:
        m0, res0 = evaluate(w0, R if Rx is R else Rx, lag=lag, cost_mult=cost_mult)
        base_eq = res0.equity.reindex(Rx.index).ffill()
        w = S.build(Rx, L, p, base_eq) if p["dd_cut"] > 0 else w0
        m, res = trial("P3C", hyp, tag, {**p, "band": band}, w, Rx, lag=lag, cost_mult=cost_mult, note=note, drop_periods=drop)
    rows.append({"cell": tag, **{k: m[k] for k in COLS}, "trial": m["trial_id"]})
    return m


which = sys.argv[1] if len(sys.argv) > 1 else "variants"
P = dict(S.PARAMS)
if which == "variants":
    run_variant("V1 core only (H3+H9 IEF)", {**P, "w_core": 1.0, "dd_cut": 0.0}, note="deviation: H9 inside core")
    run_variant("V2 0.7core+0.3rot k3", {**P, "dd_cut": 0.0})
    run_variant("V3 V2 + DD10", {**P})
    run_variant("V4 V2 + band2%", {**P, "dd_cut": 0.0}, band=0.02, note="deviation: rebalance band added (T+1 hygiene)")
    run_variant("V5 V3 + band2%", {**P}, band=0.02, note="deviation: rebalance band added")
    run_variant("V6 0.5core+0.5rot + band2%", {**P, "w_core": 0.5, "dd_cut": 0.0}, band=0.02)
    run_variant("V7 0.5core+0.5rot + DD10 + band2%", {**P, "w_core": 0.5}, band=0.02)
    run_variant("V8 V4 rot k2", {**P, "top_k": 2, "dd_cut": 0.0}, band=0.02)
elif which == "frontier":
    p = json.loads(sys.argv[2]) if len(sys.argv) > 2 else P
    band = float(sys.argv[3]) if len(sys.argv) > 3 else 0.02
    for m in [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]:
        run_variant(f"frontier lever={m}", {**p, "lever": m}, band=band, hyp="FRONTIER")
elif which == "robust":
    p = json.loads(sys.argv[2]); band = float(sys.argv[3])
    for tag, kw in [("lag3", {"lag": 3}), ("lag1", {"lag": 1}), ("cost0", {"cost_mult": 0.0}), ("cost3", {"cost_mult": 3.0})]:
        run_variant(f"final {tag}", p, band=band, hyp="FINAL", **kw)
    for a, b in [("1998-01-02", "2002-12-31"), ("2003-01-01", "2007-12-31"), ("2008-01-01", "2009-12-31"), ("2010-01-01", "2015-12-31")]:
        run_variant(f"final drop {a[:4]}-{b[:4]}", p, band=band, hyp="FINAL", drop=[(a, b)])
    from trials import drag_panel
    for d in [-0.01, 0.01]:
        run_variant(f"final simdrag{d:+.0%}", p, band=band, hyp="FINAL", Rx=drag_panel(R, d))

df = pd.DataFrame(rows); df.to_csv(OUT / f"phase3c_{which}.csv", index=False, mode="a")
print(df.round(3).to_string())
