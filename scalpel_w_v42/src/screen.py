"""In-sample screen + PLATEAU RULE for grid results.

A config passes the IS screen when (pooled over tickers, 2013-2020):
  * n >= 100 pooled trades; expectancy > 0 net and PF >= 1.3
  * ticker breadth: among tickers with >= 30 trades (at least 2 of them), all but at most one are
    net positive
  * plateau: every existing neighbour (+-1 step on each grid dimension) is net positive and the
    median neighbour PF is >= 1.3
Grid dimensions for neighbours: d, stop s (STRUCT has none), target t (NEXT / WO have none),
max pierce D, and reclaim time limit (c1 < c2 < c3 < b). Units ATR / SIG are separate runs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

D_ORDER = [0.0, 0.10, 0.25, 0.40, 0.50, 0.75, 1.00]
S_ORDER = ["s0.10", "s0.25", "s0.40", "s0.50", "s0.75", "s1.00"]
T_ORDER = ["t0.25", "t0.50", "t0.75", "t1.00", "t1.50", "t2.00"]
DM_ORDER = [0.5, 1.0, 1.5]
ST_ORDER = ["c1", "c2", "c3", "b_reclaim"]
MIN_TK, MIN_POOLED, PF_MIN = 30, 100, 1.3


def _step(order, v, k):
    if v not in order:
        return None
    i = order.index(v) + k
    return order[i] if 0 <= i < len(order) else None


def neighbours(row):
    """Yield neighbour keys (level, side, unit, d, style, D, stop, target)."""
    base = dict(level=row.level, side=row.side, unit=row.unit, d=row.d, style=row["style"],
                D=row.D, stop=row.stop, target=row.target)
    out = []
    for k in (-1, 1):
        dd = _step(D_ORDER, round(row.d, 2), k)
        if dd is not None:
            out.append(dict(base, d=dd))
        ss = _step(S_ORDER, row.stop, k)
        if ss is not None:
            out.append(dict(base, stop=ss))
        tt = _step(T_ORDER, row.target, k)
        if tt is not None:
            out.append(dict(base, target=tt))
        if np.isfinite(row.D):
            DD = _step(DM_ORDER, row.D, k)
            if DD is not None:
                out.append(dict(base, D=DD))
        st = _step(ST_ORDER, row["style"], k)
        if st is not None:
            out.append(dict(base, style=st))
    return out


def keyof(d):
    D = d["D"]
    return (d["level"], d["side"], d["unit"], round(float(d["d"]), 2), d["style"],
            -1.0 if not np.isfinite(D) else float(D), d["stop"], d["target"])


def screen(df: pd.DataFrame, family_col="family"):
    """df: rows for all scopes (tickers + POOLED). Returns pooled frame with screen columns."""
    tick = df[df.scope != "POOLED"]
    pooled = df[df.scope == "POOLED"].copy()
    piv_n = tick.pivot_table(index="config", columns="scope", values="n", aggfunc="first")
    piv_e = tick.pivot_table(index="config", columns="scope", values="expR", aggfunc="first")
    elig = piv_n >= MIN_TK
    pos = (piv_e > 0) & elig
    n_elig = elig.sum(1)
    n_pos = pos.sum(1)
    pooled = pooled.set_index("config")
    pooled["tk_elig"] = n_elig.reindex(pooled.index).fillna(0).astype(int)
    pooled["tk_pos"] = n_pos.reindex(pooled.index).fillna(0).astype(int)
    for tk in piv_e.columns:
        pooled[f"expR_{tk}"] = piv_e[tk].reindex(pooled.index)
        pooled[f"n_{tk}"] = piv_n[tk].reindex(pooled.index)
    pooled["breadth_ok"] = (pooled.tk_elig >= 2) & (pooled.tk_pos >= pooled.tk_elig - 1) & (pooled.tk_pos >= 2)
    pooled["base_ok"] = (pooled.n >= MIN_POOLED) & (pooled.expR > 0) & (pooled.pf >= PF_MIN)
    pooled = pooled.reset_index()
    # neighbour lookup
    pooled["_key"] = [keyof(r) for r in pooled[["level", "side", "unit", "d", "style", "D", "stop", "target"]].to_dict("records")]
    lut = dict(zip(pooled["_key"], zip(pooled.expR.values, pooled.pf.values, pooled.n.values)))
    nb_all_pos, nb_med_pf, nb_cnt = [], [], []
    for _, r in pooled.iterrows():
        if not r.base_ok:
            nb_all_pos.append(False); nb_med_pf.append(np.nan); nb_cnt.append(0)
            continue
        vals = [lut.get(keyof(nb)) for nb in neighbours(r)]
        vals = [v for v in vals if v is not None]
        if not vals:
            nb_all_pos.append(False); nb_med_pf.append(np.nan); nb_cnt.append(0)
            continue
        e = np.array([v[0] for v in vals], float)
        pf = np.array([v[1] for v in vals], float)
        nb_all_pos.append(bool(np.all(np.nan_to_num(e, nan=-1) > 0)))
        nb_med_pf.append(float(np.nanmedian(pf)))
        nb_cnt.append(len(vals))
    pooled["nb_all_pos"] = nb_all_pos
    pooled["nb_med_pf"] = nb_med_pf
    pooled["nb_cnt"] = nb_cnt
    pooled["plateau_ok"] = pooled.nb_all_pos & (pooled.nb_med_pf >= PF_MIN)
    pooled["screen_pass"] = pooled.base_ok & pooled.breadth_ok & pooled.plateau_ok
    return pooled.drop(columns=["_key"])
