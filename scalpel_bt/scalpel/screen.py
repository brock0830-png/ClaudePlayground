"""
Variant evaluation with the three directional baselines, and the log writer.
A spec may have "legs": a list of sub-specs traded together (trades concatenated),
all legs sharing one jitter draw per baseline run.
"""
from __future__ import annotations
import json
import os
import numpy as np
import pandas as pd
from .strategies import run, build
from .levelsets import jitter_factors
from .stats import trade_frame, summarize
from .data import COST_RT_PTS, RESULTS

N_JIT = 500
N_RAND = 500
LOG = RESULTS / "log.csv"
_FR = None   # Frame, set per process


def set_frame(fr):
    global _FR
    _FR = fr


def legs(spec):
    return spec["legs"] if "legs" in spec else [spec]


def spec_key(spec: dict, drop=("mode",)) -> str:
    def clean(s):
        return {k: v for k, v in s.items() if k not in drop and k not in ("stage", "note")}
    if "legs" in spec:
        d = {k: v for k, v in spec.items() if k not in ("legs",) + tuple(drop) + ("stage", "note")}
        d["legs"] = [clean(x) for x in spec["legs"]]
        return json.dumps(d, sort_keys=True, default=str)
    return json.dumps(clean(spec), sort_keys=True, default=str)


def run_spec(fr, spec, start, end, jit=None, grid=False):
    parts = [run(fr, {**s, "mode": spec.get("mode", s.get("mode"))} if "legs" in spec else s,
                 start, end, jit=jit, grid=grid) for s in legs(spec)]
    return parts


def ev_of(parts):
    net = np.concatenate([p["net"] for p in parts]) if parts else np.array([])
    return (float(net.mean()) if len(net) else np.nan), len(net)


def random_entry_ev(fr, spec, parts, start, end, rng, n_runs=N_RAND):
    """Same count, direction and holding time; random eligible entry bars; open->close P&L."""
    evs = np.full(n_runs, np.nan)
    tot = sum(len(p["net"]) for p in parts)
    if tot == 0:
        return evs
    draws = []
    for s, p in zip(legs(spec), parts):
        if len(p["net"]) == 0:
            continue
        s2 = {**s, "mode": spec.get("mode", s.get("mode"))} if "legs" in spec else s
        _, _, _, _, elig, _, _ = build(fr, s2)
        pool = np.flatnonzero(elig[start:end] & ~fr.force_flat[start:end]) + start
        hold = (p["xi"] - p["ei"] + 1)
        sgn = 1.0 if s2["side"] == "long" else -1.0
        draws.append((pool, hold, sgn))
    c, o = fr.c, fr.o
    tot_pnl = np.zeros(n_runs); cnt = 0
    for pool, hold, sgn in draws:
        if len(pool) == 0:
            continue
        ent = rng.choice(pool, size=(n_runs, len(hold)))
        ex = np.minimum(ent + hold[None, :] - 1, end - 1)
        tot_pnl += (sgn * (c[ex] - o[ent]) - COST_RT_PTS).sum(axis=1)
        cnt += len(hold)
    if cnt:
        evs = tot_pnl / cnt
    return evs


def evaluate(spec: dict, start: int, end: int, n_jit=N_JIT, n_rand=N_RAND, seed=12345,
             years=range(2013, 2020)) -> dict:
    fr = _FR
    parts = run_spec(fr, spec, start, end)
    tf_ = pd.concat([trade_frame(fr, p) for p in parts], ignore_index=True) if parts else pd.DataFrame()
    if len(tf_):
        tf_ = tf_.sort_values("entry_time").reset_index(drop=True)
    row = {"spec": json.dumps(spec, default=str), "key": spec_key(spec), "stage": spec.get("stage", ""),
           "family": spec.get("family", ""), "tf": spec.get("tf", legs(spec)[0].get("tf")),
           "mode": spec.get("mode", legs(spec)[0].get("mode")), "roll": spec.get("roll", legs(spec)[0].get("roll", "incl")),
           "side": spec.get("side", "+".join(sorted({l["side"] for l in legs(spec)}))),
           "level": spec.get("level", "+".join(l["level"] for l in legs(spec))),
           "trig": spec.get("trig", legs(spec)[0].get("trig")),
           "stop": str(spec.get("stop", legs(spec)[0].get("stop"))),
           "target": str(spec.get("target", legs(spec)[0].get("target"))),
           "filters": json.dumps(spec.get("filters", legs(spec)[0].get("filters", {})), default=str),
           "modeled": False}
    row.update(summarize(tf_, years=years) if len(tf_) else summarize(pd.DataFrame(columns=["net"]), years=years))
    rng = np.random.default_rng(seed)
    # jitter baseline
    if n_jit and row["n"] > 0:
        jev = np.empty(n_jit)
        for j in range(n_jit):
            jev[j], _ = ev_of(run_spec(fr, spec, start, end, jit=jitter_factors(rng)))
        jv = jev[~np.isnan(jev)]
        row["jit_mean"] = float(jv.mean()) if len(jv) else np.nan
        row["jit_p90"] = float(np.quantile(jv, 0.9)) if len(jv) else np.nan
        row["jit_pct"] = float((jv < row["ev"]).mean() * 100) if len(jv) else np.nan
    # round-grid baseline
    gev, gn = ev_of(run_spec(fr, spec, start, end, grid=True))
    row["grid_ev"], row["grid_n"] = gev, gn
    # random entry (informational)
    if n_rand and row["n"] > 0:
        rev = random_entry_ev(fr, spec, parts, start, end, rng, n_rand)
        rv = rev[~np.isnan(rev)]
        row["rand_mean"] = float(rv.mean()) if len(rv) else np.nan
        row["rand_pct"] = float((rv < row["ev"]).mean() * 100) if len(rv) else np.nan
    return row


def append_log(rows: list[dict], path=None):
    LOGP = LOG if path is None else path
    df = pd.DataFrame(rows)
    if LOGP.exists():
        old = pd.read_csv(LOGP)
        start_id = int(old["variant_id"].max()) + 1
        df.insert(0, "variant_id", range(start_id, start_id + len(df)))
        df = pd.concat([old, df], ignore_index=True)
    else:
        df.insert(0, "variant_id", range(1, len(df) + 1))
    df.to_csv(LOGP, index=False)
    return df
