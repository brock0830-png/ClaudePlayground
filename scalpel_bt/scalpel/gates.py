"""PROTOCOL section 6 gates, computed from results/log.csv."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd

YEARS = list(range(2013, 2020))
WF_TEST = [2016, 2017, 2018, 2019]
WF_MIN_TRAIN_TRADES = 20


def twin_key(row) -> str:
    return row["key"]


def add_gates(log: pd.DataFrame) -> pd.DataFrame:
    d = log.copy()
    dirl = d[~d["modeled"].astype(bool)].copy()
    # G1: EV > 0 in this mode, and in both the fixed and scaled versions of the same spec
    ev_by = dirl.pivot_table(index="key", columns="mode", values="ev", aggfunc="first")
    fx = dirl["key"].map(ev_by.get("fixed", pd.Series(dtype=float)))
    sc = dirl["key"].map(ev_by.get("scaled", pd.Series(dtype=float)))
    dirl["ev_fixed_twin"] = fx
    dirl["ev_scaled_twin"] = sc
    dirl["G1"] = (dirl["ev"] > 0) & (fx > 0) & (sc > 0)
    dirl["G2"] = dirl["n"] >= 100
    grid_ok = dirl["grid_ev"].isna() | (dirl["ev"] > dirl["grid_ev"])
    dirl["G3"] = (dirl["jit_pct"] >= 90) & grid_ok
    dirl["G4"] = dirl["ci_lo"] > 0
    dirl["G5"] = (dirl["pos_years"] >= 5) & (dirl["total_ex_best"] > 0) & (dirl["total_ex_crisis"] > 0)
    # G6: family walk-forward
    fam_cols = ["stage", "family", "tf", "side", "mode", "roll"]
    dirl["wf_family"] = dirl[fam_cols].astype(str).agg("|".join, axis=1)
    wf = {}
    for fam, g in dirl.groupby("wf_family"):
        tot = 0.0
        picks = []
        for y in WF_TEST:
            tr = [yy for yy in YEARS if yy < y]
            n_tr = g[[f"n_{yy}" for yy in tr]].sum(axis=1)
            p_tr = g[[f"pnl_{yy}" for yy in tr]].sum(axis=1)
            ev_tr = (p_tr / n_tr).where(n_tr >= WF_MIN_TRAIN_TRADES)
            if ev_tr.notna().any():
                k = ev_tr.idxmax()
                tot += g.at[k, f"pnl_{y}"]
                picks.append(int(g.at[k, "variant_id"]))
        wf[fam] = (tot, json.dumps(picks))
    dirl["wf_pnl"] = dirl["wf_family"].map(lambda f: wf[f][0])
    dirl["wf_picks"] = dirl["wf_family"].map(lambda f: wf[f][1])
    dirl["G6"] = dirl["wf_pnl"] > 0
    dirl["ALL"] = dirl[["G1", "G2", "G3", "G4", "G5", "G6"]].all(axis=1)
    dirl["G124"] = dirl[["G1", "G2", "G4"]].all(axis=1)
    return dirl
