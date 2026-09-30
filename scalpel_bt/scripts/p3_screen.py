"""
Phase 3 development screen (PROTOCOL_P3.md). Grids below are fixed before running.
Development data: SPY 1993-2012 (market-on-close) + ES sessions 2013-2019 (next open).
Output: results/p3/log.csv (one row per variant, pooled and per-dataset stats).
Usage: python scripts/p3_screen.py
"""
import sys, json, itertools, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from scalpel.data import load_bars, RESULTS
from scalpel import p3
from scalpel.stats import boot_ci_mean

OUT = RESULTS / "p3"
E0 = ["ibs<0.3", "vix>20"]
N_RAND = 500


def grids():
    V = []

    def add(group, family, params, spec):
        V.append(dict(group=group, family=family, params=params, spec=spec))
    for h in [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20]:
        add("A", "V1_hold", {"hold": h}, dict(entry=E0, hold=h))
    for ex in ["close>high1", "ibs>0.7", "rsi2>70", "close>ma5", "close>ma10"]:
        add("A", "V2_exit", {"exit": ex}, dict(entry=E0, exit=ex, hold=10))
    for t, s, mh in itertools.product([0, 0.5, 1.0, 1.5, 2.0, 3.0], [0, 1.0, 1.5, 2.0, 3.0], [5, 10]):
        add("A", "V3_tgtstop", {"tgt": t, "stop": s, "hold": mh}, dict(entry=E0, tgt=t, stop=s, hold=mh))
    gates = {"none": [], "vix15": ["vix>15"], "vix20": ["vix>20"], "vix25": ["vix>25"], "vix30": ["vix>30"]}
    for ib, (gn, g), h in itertools.product([0.1, 0.2, 0.3, 0.4, 0.5], gates.items(), [3, 5]):
        add("A", "V4_thresh", {"ibs": ib, "vixgate": list(gates).index(gn), "hold": h},
            dict(entry=[f"ibs<{ib}"] + g, hold=h))
    rel = {"above_mean": ["vix>vix_mean252"], "pct70": ["vix_pct252>0.7"], "rel12": ["vix_rel>1.2"]}
    for ib, (rn, g), h in itertools.product([0.1, 0.2, 0.3, 0.4, 0.5], rel.items(), [3, 5]):
        add("A", "V4b_relvix", {"ibs": ib, "gate": rn, "hold": h}, dict(entry=[f"ibs<{ib}"] + g, hold=h))
    trend = {"above_ma200": ["close>ma200"], "below_ma200": ["close<ma200"], "above_ma50": ["close>ma50"],
             "below_ma50": ["close<ma50"], "golden": ["ma50>ma200"], "mom126_up": ["mom126>zero"],
             "mom126_dn": ["mom126<zero"]}
    for base_name, base in [("E0", E0), ("ibs_only", ["ibs<0.3"])]:
        for tn, tf in trend.items():
            add("A", "V5_trend", {"base": base_name, "trend": tn}, dict(entry=base + tf, hold=5))
        for vr in [1.2, 1.5, 2.0]:
            add("A", "V6_volume", {"base": base_name, "volrel": vr}, dict(entry=base + [f"vol_rel50>{vr}"], hold=5))
    for mc in [2, 3]:
        add("A", "V7_stack", {"max_concurrent": mc}, dict(entry=E0, hold=5, max_concurrent=mc))
    cg = {"vix20": ["vix>20"], "pct70": ["vix_pct252>0.7"], "rel11": ["vix_rel>1.1"], "none": []}
    cx = {"hold3": dict(hold=3), "hold5": dict(hold=5), "strength": dict(exit="close>high1", hold=10)}
    for k, (gn, g), (xn, x) in itertools.product([2, 3, 4], cg.items(), cx.items()):
        add("B", "C1_kof4", {"k": k, "gate": gn, "exit": xn}, dict(entry=[f"os_count>={k}"] + g, **x))
    for th, (gn, g), (xn, x) in itertools.product([0.75, 0.85, 0.90], cg.items(), cx.items()):
        add("B", "C2_score", {"thr": th, "gate": gn, "exit": xn}, dict(entry=[f"os_score>{th}"] + g, **x))
    for rn, r in {"ma50": ["close>ma50"], "ma100": ["close>ma100"], "ma200": ["close>ma200"],
                  "mom126": ["mom126>zero"], "mom252": ["mom252>zero"]}.items():
        add("C", "T1_trend", {"regime": rn}, dict(kind="target", regime=r))
    for rn, r in {"ma200": ["close>ma200"], "ma50": ["close>ma50"]}.items():
        add("C", "T2_trend_dip", {"regime": rn}, dict(kind="target", regime=r, entry=E0, dip_hold=5))
    return V


def dataset_stats(D, spec, mode, i0, i1, rng, prefix):
    t = p3.simulate(D, spec, mode, i0, i1)
    out = {f"{prefix}_n": len(t)}
    if len(t) == 0:
        return out, t, np.full(N_RAND, np.nan)
    r = t["ret"].values
    out.update({f"{prefix}_ev": float(r.mean()), f"{prefix}_win": float((r > 0).mean()),
                f"{prefix}_pf": float(r[r > 0].sum() / -r[r < 0].sum()) if (r < 0).any() else np.inf,
                f"{prefix}_sessions": float(t["sessions"].mean())})
    if D["sym"].iat[0] == "ES":
        out[f"{prefix}_ev_pts"] = float(t["pnl"].mean())
    rnd = p3.random_exposure(D, t, mode, i0, i1, rng, N_RAND)
    out[f"{prefix}_rand_mean"] = float(np.nanmean(rnd))
    t = t.assign(year=pd.DatetimeIndex(D["date"].values[t["sig"].values]).year)
    return out, t, rnd


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    spy = p3.etf_daily("SPY")
    s0 = int(np.searchsorted(spy["date"].values, np.datetime64("1994-01-03")))   # one year of feature warm-up
    s1 = int(np.searchsorted(spy["date"].values, np.datetime64("2013-01-01")))
    es = p3.es_daily(load_bars("dev"))
    rng = np.random.default_rng(3)
    rows = []
    t0 = time.time()
    for k, v in enumerate(grids()):
        spec = v["spec"]
        a, ta, ra = dataset_stats(spy, spec, "close", s0, s1, rng, "spy")
        b, tb, rb = dataset_stats(es, spec, "next_open", 0, len(es), rng, "es")
        row = {"variant_id": k + 1, "group": v["group"], "family": v["family"], "params": json.dumps(v["params"]),
               "spec": json.dumps(spec)}
        row.update(a); row.update(b)
        pooled = pd.concat([ta, tb], ignore_index=True) if len(ta) or len(tb) else pd.DataFrame()
        if len(pooled):
            r = pooled["ret"].values
            row["n"] = len(r)
            row["ev"] = float(r.mean())
            row["t"] = float(r.mean() / r.std(ddof=1) * np.sqrt(len(r))) if len(r) > 1 and r.std() > 0 else 0.0
            row["ci_lo"], row["ci_hi"] = boot_ci_mean(r)
            row["pf"] = float(r[r > 0].sum() / -r[r < 0].sum()) if (r < 0).any() else np.inf
            na, nb = len(ta), len(tb)
            rnd = (np.nan_to_num(ra) * na + np.nan_to_num(rb) * nb) / max(na + nb, 1)
            row["rand_pct"] = float((rnd < row["ev"]).mean() * 100)
            yr = pooled.groupby("year")["ret"].sum()
            row["years"] = int(len(yr)); row["pos_year_share"] = float((yr > 0).mean())
            row["sharpe_trade"] = float(r.mean() / r.std(ddof=1)) if len(r) > 1 else np.nan
        rows.append(row)
        if (k + 1) % 50 == 0:
            print(k + 1, round(time.time() - t0), "s", flush=True)
    pd.DataFrame(rows).to_csv(OUT / "log.csv", index=False)
    print("done", len(rows))


if __name__ == "__main__":
    main()
