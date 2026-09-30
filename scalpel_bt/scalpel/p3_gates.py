"""PROTOCOL_P3 development gates D1-D6 from results/p3/log.csv."""
import json
import numpy as np
import pandas as pd


def neighbours(log: pd.DataFrame) -> dict:
    """variant_id -> list of one-step neighbour variant_ids (numeric parameters only)."""
    out = {}
    P = {vid: json.loads(p) for vid, p in zip(log["variant_id"], log["params"])}
    fam = dict(zip(log["variant_id"], log["family"]))
    by_fam = {}
    for vid, f in fam.items():
        by_fam.setdefault(f, []).append(vid)
    for f, vids in by_fam.items():
        keys = sorted({k for v in vids for k in P[v]})
        num = {k: sorted({P[v][k] for v in vids if isinstance(P[v].get(k), (int, float))}) for k in keys}
        for v in vids:
            nb = []
            for k, vals in num.items():
                if not isinstance(P[v].get(k), (int, float)) or len(vals) < 2:
                    continue
                j = vals.index(P[v][k])
                for jj in (j - 1, j + 1):
                    if 0 <= jj < len(vals):
                        for w in vids:
                            if w != v and P[w].get(k) == vals[jj] and all(P[w].get(q) == P[v].get(q) for q in P[v] if q != k):
                                nb.append(w)
            out[v] = nb
    return out


def add_gates(log: pd.DataFrame) -> pd.DataFrame:
    g = log.copy()
    g["D1"] = (g["spy_ev"] > 0) & (g["es_ev"] > 0)
    g["D2"] = (g["spy_n"] >= 20) & (g["es_n"] >= 20) & (g["n"] >= 60)
    g["D3"] = g["rand_pct"] >= 90
    g["D4"] = g["ci_lo"] > 0
    nb = neighbours(g)
    ev = dict(zip(g["variant_id"], g["ev"]))
    nb_mean = {v: (np.nanmean([ev[w] for w in ws]) if ws else np.nan) for v, ws in nb.items()}
    g["nb_n"] = g["variant_id"].map(lambda v: len(nb[v]))
    g["nb_ev"] = g["variant_id"].map(nb_mean)
    g["D5"] = g["nb_ev"].isna() | ((g["nb_ev"] > 0) & (g["nb_ev"] >= 0.5 * g["ev"]))
    g["D6"] = g["pos_year_share"] >= 0.6
    g["ALL"] = g[["D1", "D2", "D3", "D4", "D5", "D6"]].all(axis=1)
    return g
