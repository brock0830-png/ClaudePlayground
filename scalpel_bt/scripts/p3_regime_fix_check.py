"""
Correction check (after the Phase 3 test): scalpel/p3.py::_simulate_target exited regime trades one session
early in next-open mode (ES). Close-mode results (all SPY development data and the 7-ETF test verdicts) were
unaffected. This re-runs the 7 affected development variants (T1/T2) with the fixed engine, applies the same
gates, and recomputes P3C's ES 2020-2026 and next-open ETF figures. Writes results/p3/regime_fix_check.json.
"""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np
import pandas as pd
from scalpel.data import load_bars, RESULTS, OOS_START
from scalpel import p3
from scalpel.stats import boot_ci_mean
from scalpel.p3_gates import add_gates
from p3_screen import grids, dataset_stats

OUT = RESULTS / "p3"
log = pd.read_csv(OUT / "log.csv")
spy = p3.etf_daily("SPY")
s0 = int(np.searchsorted(spy["date"].values, np.datetime64("1994-01-03")))
s1 = int(np.searchsorted(spy["date"].values, np.datetime64("2013-01-01")))
es = p3.es_daily(load_bars("dev"))
rng = np.random.default_rng(3)
fixed = log.copy()
G = grids()
for k, v in enumerate(G):
    if v["family"] not in ("T1_trend", "T2_trend_dip"):
        continue
    a, ta, ra = dataset_stats(spy, v["spec"], "close", s0, s1, rng, "spy")
    b, tb, rb = dataset_stats(es, v["spec"], "next_open", 0, len(es), rng, "es")
    P = pd.concat([ta, tb], ignore_index=True)
    r = P["ret"].values
    upd = {**a, **b, "n": len(r), "ev": r.mean(), "t": r.mean() / r.std(ddof=1) * np.sqrt(len(r)),
           "pf": r[r > 0].sum() / -r[r < 0].sum()}
    upd["ci_lo"], upd["ci_hi"] = boot_ci_mean(r)
    na, nb = len(ta), len(tb)
    rnd = (np.nan_to_num(ra) * na + np.nan_to_num(rb) * nb) / max(na + nb, 1)
    upd["rand_pct"] = float((rnd < upd["ev"]).mean() * 100)
    yr = P.groupby("year")["ret"].sum()
    upd["pos_year_share"] = float((yr > 0).mean())
    for c, val in upd.items():
        fixed.loc[fixed["variant_id"] == k + 1, c] = val
g0, g1 = add_gates(log), add_gates(fixed)
cols = ["variant_id", "family", "params", "es_n", "es_ev", "ev", "t", "rand_pct", "ALL"]
T = g0[g0.family.isin(["T1_trend", "T2_trend_dip"])][cols].merge(
    g1[g1.family.isin(["T1_trend", "T2_trend_dip"])][cols], on=["variant_id", "family", "params"], suffixes=("_logged", "_fixed"))
print(T.round(4).to_string(index=False))
grpC = g1[(g1.group == "C") & g1["ALL"]].sort_values("t", ascending=False)
pick = int(grpC["variant_id"].iat[0]) if len(grpC) else None
print("group C pick with the fixed engine:", pick, "(frozen pick was 255)")

# P3C figures that used next-open mode
spec = dict(kind="target", regime=["mom126>zero"])
Dall = p3.es_daily(load_bars("all"))
i0 = int(np.searchsorted(pd.DatetimeIndex(Dall["date"]), OOS_START.tz_localize(None)))
t = p3.simulate(Dall, spec, "next_open", i0, len(Dall))
es_fix = dict(n=len(t), ev_pts=float(t.pnl.mean()), total_pts=float(t.pnl.sum()),
              pf_pts=float(t.loc[t.pnl > 0, "pnl"].sum() / -t.loc[t.pnl < 0, "pnl"].sum()))
p3.TEST_LOCK.exists() or sys.exit("test markets locked")
R = []
for sym in p3.TEST_SYMBOLS:
    D = p3.etf_daily(sym)
    R.append(p3.simulate(D, spec, "next_open", 252, len(D))["ret"].values)
r = np.concatenate(R)
no_fix = dict(n=len(r), ev_pct=float(r.mean() * 100), pf=float(r[r > 0].sum() / -r[r < 0].sum()),
              markets_positive=int(sum(x.mean() > 0 for x in R)))
print("P3C ES 2020-2026 (fixed):", es_fix)
print("P3C next-open ETFs (fixed):", no_fix)
(OUT / "regime_fix_check.json").write_text(json.dumps({"dev_T_rows": T.to_dict("records"), "group_C_pick_fixed": pick,
                                                     "p3c_es_2020_2026_fixed": es_fix, "p3c_next_open_etf_fixed": no_fix},
                                                    indent=1, default=str))
