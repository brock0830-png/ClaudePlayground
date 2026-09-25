"""Phase 2 validation (context / confluence families).

    python validate_p2.py freeze      # IS-only selection -> finalists_p2.csv, FREEZE_P2.md
    python validate_p2.py loto        # leave-one-ticker-out, in-sample
    python validate_p2.py evaluate    # ONE shot: 2021+ second look (ES NQ CL 6J) + sealed GC holdout

Holdouts. 2021+ on the four design tickers was opened once in phase 1, so here it is a SECOND
LOOK: the phase 2 rules were chosen on 2013-2020 only, but the period is no longer unseen and is
reported as weaker evidence. The clean test is GC (COMEX:GC1!, 4h, 2023-07 to 2026-09, from the
TradingView connector), sealed on disk before phase 2 started and first read by `evaluate`.

Selection (fixed before `evaluate`):
  pool = configs passing the config screen in any phase 2 variant (real levels); score = IS t-stat;
  clusters by entry overlap (Jaccard > 0.7).
  A: best member of each of the 6 best clusters from the phase 2 variants that passed the family
     screen (level specificity); if fewer than 6 such clusters exist, the rest come from the whole
     phase 2 pool (tagged A*).
  B: one representative per idea the users of the levels named - generalized uptrend (REG200_align),
     avoid bullish setups in strong bear markets (REGSTRONG_avoid), prior-week POC / value confluence
     (MP_ANY20), RSI divergence (RSIDIV_4h), basic S/R (SR_PDHL10), stacked evidence (SCORE3), and the
     market-profile levels on their own (MPALONE): the best-scoring screen passer, else the best
     config with >= 100 IS trades (flagged).
Gates: G1-G7 as phase 1 on the 2021+ second look, plus
  G8 (clean holdout): GC expectancy > 0 in R and $ with >= 20 trades, and above the mean of the four
     placebo level sets on GC.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from common import LINEAGE, OOS_START, OUT, ROOT, TICKERS
from screen import keyof, neighbours

FAM = OUT / "families"
GC_SEAL = ROOT / "GC_UNSEALED"
SECOND_LOOK = ROOT / "OOS_SECOND_LOOK_P2"
K_A = 6
USER_IDEAS = [
    ("REG200_align", "generalized uptrend: longs only above the 200-day SMA, shorts only below"),
    ("REGSTRONG_avoid", "no bullish setups in a strong bear market (and no bearish ones in a strong bull)"),
    ("MP_ANY20", "level within 0.20 sigma of the prior-week POC / VAH / VAL"),
    ("RSIDIV_4h", "RSI(14) divergence on 4h in the trade direction"),
    ("SR_PDHL10", "level within 0.10 sigma of the prior-day high / low"),
    ("SCORE3", "at least 3 of 5 supporting signals (regime, profile, S/R, divergence, open vs POC)"),
    ("MPALONE", "prior-week POC / VAH / VAL traded as levels, no v42 level"),
]


def p2_variants():
    names = []
    for p in sorted(FAM.glob("p2round*_summary.csv")):
        names += list(pd.read_csv(p).variant)
    return names


def p2_summaries():
    rows = [pd.read_csv(p) for p in sorted(FAM.glob("p2round*_summary.csv"))]
    return pd.concat(rows) if rows else pd.DataFrame()


def screen_of(v):
    s = pd.read_parquet(FAM / f"screen_{v}.parquet")
    s["variant"] = v
    s["score"] = s.expR / s.sdR * np.sqrt(s.n)
    return s


def cell_of(cid):
    return "|".join(cid.split("|")[:6])


def freeze():
    if GC_SEAL.exists():
        raise SystemExit("GC holdout already opened; phase 2 finalists cannot be re-selected")
    import families_p2  # noqa: F401  (registers phase 2 variants)
    from data import load_all
    from deflate import greedy_cluster
    B = load_all()
    variants = p2_variants()
    pool = pd.concat([screen_of(v) for v in variants], ignore_index=True)
    pool = pool[pool.screen_pass].copy()
    print("phase 2 pool:", len(pool), "configs across", pool.variant.nunique(), "variants")
    mats, keys = [], []
    for v in pool.variant.unique():
        M, ck = _entry_sets(B, v)
        need = set(pool.loc[pool.variant == v, "config"].map(cell_of))
        idx = [i for i, k in enumerate(ck) if k in need]
        mats.append(M[idx])
        keys += [(v, ck[i]) for i in idx]
    M = np.vstack(mats) if mats else np.zeros((0, 1), bool)
    kidx = {k: i for i, k in enumerate(keys)}
    pool["set_idx"] = [kidx[(v, cell_of(c))] for v, c in zip(pool.variant, pool.config)]
    pool["cluster"] = greedy_cluster(M[pool.set_idx.values], pool.score.values, 0.7) if len(pool) else []
    fs = p2_summaries()
    passing = set(fs.loc[fs.family_pass, "variant"]) if len(fs) else set()
    repsA = pool[pool.variant.isin(passing)].sort_values("score", ascending=False).groupby("cluster").head(1)
    finA = repsA.sort_values("score", ascending=False).head(K_A).copy()
    finA["tier"] = "A"
    finA["why"] = [f"A: level-specific phase 2 family ({r.variant}), cluster rank {i + 1}" for i, r in enumerate(finA.itertuples())]
    if len(finA) < K_A:
        rest = pool[~pool.cluster.isin(finA.cluster)].sort_values("score", ascending=False).groupby("cluster").head(1)
        extra = rest.sort_values("score", ascending=False).head(K_A - len(finA)).copy()
        extra["tier"] = "A*"
        extra["why"] = [f"A*: no level-specific family left; whole phase 2 pool, cluster rank {i + 1}" for i in range(len(extra))]
        finA = pd.concat([finA, extra])
    finB = []
    for v, why in USER_IDEAS:
        if v not in variants:
            continue
        s = screen_of(v)
        best = s[s.screen_pass].sort_values("score", ascending=False).head(1)
        flag = ""
        if len(best) == 0:
            best = s[s.n >= 100].sort_values("score", ascending=False).head(1)
            flag = " [no config passes the IS screen; best with >= 100 IS trades carried]"
        if len(best) == 0:
            continue
        best = best.copy()
        best["tier"] = "B"
        best["why"] = f"B: user idea - {why}" + flag
        finB.append(best)
    fin = pd.concat([finA] + finB, ignore_index=True).drop_duplicates(subset=["variant", "config"])
    fin["finalist"] = [f"P{i + 1:02d}" for i in range(len(fin))]
    cols = ["finalist", "tier", "variant", "config", "why", "n", "wr", "pf", "expR", "sdR", "score", "exp_usd",
            "maxdd_usd", "expR_ES", "expR_NQ", "expR_CL", "expR_6J", "n_ES", "n_NQ", "n_CL", "n_6J", "screen_pass"]
    fin = fin[[c for c in cols if c in fin.columns]]
    fin.insert(0, "lineage", LINEAGE)
    fin.to_csv(ROOT / "finalists_p2.csv", index=False)
    pool[["variant", "config", "n", "expR", "sdR", "pf", "score", "cluster"]].to_csv(OUT / "finalist_pool_p2.csv", index=False)
    h = hashlib.sha256((ROOT / "finalists_p2.csv").read_bytes()).hexdigest()
    txt = [f"# FREEZE_P2 - {LINEAGE} phase 2 (context / confluence)", "",
           f"Frozen {datetime.now(timezone.utc).isoformat()} from 2013-2020 data only. GC holdout still sealed.",
           f"finalists_p2.csv sha256 `{h}`", "",
           f"Pool: {len(pool)} screen-passing configs across {pool.variant.nunique()} phase 2 variants. "
           f"Family-screen passes: {', '.join(sorted(passing)) or 'none'}.", "",
           "| id | tier | variant | config | why | IS n | IS PF | IS expR | t-stat |", "|---|---|---|---|---|---|---|---|---|"]
    for r in fin.itertuples():
        txt.append(f"| {r.finalist} | {r.tier} | {r.variant} | `{r.config}` | {r.why} | {r.n} | {r.pf:.2f} | {r.expR:.3f} | {r.score:.2f} |")
    (ROOT / "FREEZE_P2.md").write_text("\n".join(txt) + "\n")
    print("\n".join(txt))


def _entry_sets(B, v):
    from deflate import cell_entry_sets
    import families as FM
    ent = FM.REGISTRY[v]
    kw = ent[2] if len(ent) > 2 else {}
    if "cells" in kw:          # MPALONE: entry sets over its own cells
        return _entry_sets_custom(B, v, kw)
    return cell_entry_sets(B, v)


def _entry_sets_custom(B, v, kw):
    from common import SPEC
    from deflate import entries_only
    from grid import global_weeks, BOUNCE
    allw, gmap = global_weeks(B)
    nG = len(allw)
    cl = kw["cells"]()
    M = np.zeros((len(cl), len(B) * nG), np.bool_)
    for ci, (name, side, unit, d, style, D) in enumerate(cl):
        od = kw["od_fn"](name)
        for k, (tk, b) in enumerate(B.items()):
            P = kw["price_fn"](b, name, 1.0, 0.0)
            U = b.atr if unit == "ATR" else b.sigma
            e = entries_only(b.O, b.H, b.L, b.C, b.nb, P, U, np.ones(len(b.wo), np.bool_), np.ones(b.O.shape, np.bool_),
                             od, side, d, style, D, SPEC[tk]["tick"], np.zeros(len(b.wo), np.int64))
            M[ci, k * nG + gmap[tk]] = e
    keys = [f"{c[0]}|{'bounce' if c[1] == BOUNCE else 'breakout'}|{c[2]}|d{c[3]:.2f}|{['a_limit','b_reclaim','c1','c2','c3'][c[4]]}|D{c[5]:.1f}"
            for c in cl]
    return M, keys


# ------------------------------------------------------------------ trades for a phase 2 config
def p2_trades(B, cid, variant, **kw):
    import families_p2 as P2
    from trades import config_trades
    if variant == "MPALONE":
        return mp_trades(B, cid, **kw)
    return config_trades(B, cid, variant=variant, **kw)


def mp_trades(B, cid, shift=0.0, scale=1.0, slip=1.0):
    """Trade reconstruction for MPALONE configs (profile levels as levels)."""
    import math
    from common import COMMISSION_RT, EQUITY, RISK_FRAC, SPEC
    from families_p2 import mp_od, mp_price
    from sim import BOUNCE, _rnd, find_entry, walk
    from trades import parse
    c = parse(cid)
    rows = []
    budget = EQUITY * RISK_FRAC
    for tk, b in B.items():
        sp = SPEC[tk]
        tick, pv = sp["tick"], sp["pv"]
        od = mp_od(c["level"])
        P = mp_price(b, c["level"], scale, 0.0)
        if shift:
            P = P + od * shift * b.sigma
            P = np.where(od * (P - b.wo) / b.sigma < 0.05, np.nan, P)
        U = b.atr if c["unit"] == "ATR" else b.sigma
        dirn = -od if c["side"] == BOUNCE else od
        bar_ok = np.ones(b.O.shape, np.bool_)
        for w in range(len(b.wo)):
            if not np.isfinite(P[w]) or not np.isfinite(U[w]):
                continue
            n = int(b.nb[w])
            eb, epx, et, plan = find_entry(b.O, b.H, b.L, b.C, n, w, P[w], U[w], od, c["side"], c["d"], c["style"],
                                           c["D"], tick, bar_ok, 0)
            if eb < 0 or c["stop"] == "STRUCT":
                continue
            s = float(c["stop"][1:])
            S = P[w] + od * (c["d"] + s) * U[w] if c["side"] == BOUNCE else P[w] + od * (c["d"] - s) * U[w]
            S = _rnd(S, tick, 0)
            fill = epx + dirn * slip * tick
            pf_ = plan + dirn * slip * tick
            if dirn * (fill - S) < tick * 0.999 or dirn * (pf_ - S) < tick * 0.999:
                continue
            rpc = dirn * (pf_ - S) * pv
            ncon = math.floor(budget / rpc + 1e-9)
            if ncon < 1:
                continue
            tref = plan if c["style"] == 0 else epx
            if c["target"] == "WO":
                T = b.wo[w] if c["side"] == BOUNCE else np.nan
            elif c["target"] == "NEXT":
                continue
            else:
                T = tref + dirn * float(c["target"][1:]) * U[w]
            if not np.isfinite(T):
                continue
            T = _rnd(T, tick, dirn)
            if dirn * (T - epx) < tick:
                continue
            xp, xb, xk = walk(b.O, b.H, b.L, b.C, n, w, eb, et, dirn, S, T, tick, slip)
            pnl = ncon * (dirn * (xp - fill) * pv - COMMISSION_RT)
            rows.append(dict(lineage=LINEAGE, ticker=tk, week=b.weeks.index[w], year=int(b.weeks.index[w].year),
                             entry_time=pd.Timestamp(b.TS[w, eb]), exit_time=pd.Timestamp(b.TS[w, xb]),
                             dir="long" if dirn > 0 else "short", level_px=P[w], planned_px=plan, entry_px=fill,
                             stop_px=S, target_px=T, exit_px=xp, exit_kind=["stop", "target", "time"][xk],
                             contracts=ncon, risk_usd=ncon * rpc, pnl_usd=pnl, R=pnl / (ncon * rpc)))
    df = pd.DataFrame(rows)
    return df.sort_values("entry_time").reset_index(drop=True) if len(df) else df


# ------------------------------------------------------------------ LOTO
def loto():
    import families_p2  # noqa: F401
    from data import load_all
    from trades import summary
    B = load_all()
    fin = pd.read_csv(ROOT / "finalists_p2.csv")
    rows = []
    for f in fin.itertuples():
        s = pd.read_parquet(FAM / f"screen_{f.variant}.parquet")
        lv, side, unit = f.config.split("|")[:3]
        loc = s[(s.level == lv) & (s.side == side) & (s.unit == unit)].copy()
        for k in TICKERS:
            others = [t for t in TICKERS if t != k]
            n3 = sum(loc[f"n_{t}"].fillna(0) for t in others)
            e3 = sum(loc[f"n_{t}"].fillna(0) * loc[f"expR_{t}"].fillna(0) for t in others) / n3.replace(0, np.nan)
            loc["n3"], loc["e3"] = n3, e3
            lut = {keyof(r): (r["e3"], r["n3"]) for r in loc[["level", "side", "unit", "d", "style", "D", "stop", "target", "e3", "n3"]].to_dict("records")}
            cand = loc[(loc.n3 >= 75) & (loc.e3 > 0)].copy()
            ok = []
            for _, r in cand.iterrows():
                nb = [lut.get(keyof(x)) for x in neighbours(r)]
                nb = [x for x in nb if x is not None]
                ok.append(bool(nb) and all(np.isfinite(x[0]) and x[0] > 0 for x in nb))
            cand = cand[np.array(ok, bool)] if len(cand) else cand
            if len(cand) == 0:
                rows.append(dict(lineage=LINEAGE, finalist=f.finalist, held_out=k, chosen="(none passes on 3 tickers)",
                                 n_k=0, expR_k=np.nan, positive=False))
                continue
            cand["t3"] = cand.e3 * np.sqrt(cand.n3)
            ch = cand.sort_values("t3", ascending=False).iloc[0]
            tr = p2_trades({k: B[k]}, ch.config, f.variant)
            sm = summary(tr)
            rows.append(dict(lineage=LINEAGE, finalist=f.finalist, held_out=k, chosen=ch.config, n_k=sm["n"],
                             expR_k=sm["expR"], pf_k=sm["pf"], positive=bool(sm["n"] > 0 and sm["expR"] > 0)))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "validation_p2_loto.csv", index=False)
    print(df.to_string())


# ------------------------------------------------------------------ one-shot evaluation
def evaluate():
    if GC_SEAL.exists():
        raise SystemExit("phase 2 holdouts already evaluated once")
    import families_p2  # noqa: F401
    from data import Book, load_all
    from trades import summary
    fin = pd.read_csv(ROOT / "finalists_p2.csv")
    h = hashlib.sha256((ROOT / "finalists_p2.csv").read_bytes()).hexdigest()
    stamp = json.dumps(dict(opened_utc=datetime.now(timezone.utc).isoformat(), finalists_p2_sha256=h)) + "\n"
    SECOND_LOOK.write_text(stamp)
    GC_SEAL.write_text(stamp)
    B = load_all(full=True)
    G = {"GC": Book("GC")}
    oos0 = pd.Timestamp(OOS_START)
    runs = {"base": {}, "slip2": dict(slip=2.0), "x0.95": dict(scale=0.95), "x1.05": dict(scale=1.05),
            "plc-0.30": dict(shift=-0.30), "plc-0.15": dict(shift=-0.15), "plc+0.15": dict(shift=0.15),
            "plc+0.30": dict(shift=0.30)}
    rows, tl = [], []
    for f in fin.itertuples():
        for rn, kw in runs.items():
            if f.variant == "MPALONE" and rn.startswith("x"):
                continue                                  # no v42 multipliers involved
            for book, label in ((B, "4tk"), (G, "GC")):
                tr = p2_trades(book, f.config, f.variant, **kw)
                if len(tr) == 0:
                    tr = pd.DataFrame(columns=["week", "ticker", "R", "pnl_usd", "exit_time", "year"])
                if label == "GC":
                    tr["period"] = "GC_HOLDOUT"
                else:
                    tr["period"] = np.where(pd.to_datetime(tr.week) >= oos0, "OOS2", "IS")
                for per in (["GC_HOLDOUT"] if label == "GC" else ["IS", "OOS2"]):
                    sub = tr[tr.period == per]
                    scopes = ["GC"] if label == "GC" else TICKERS + ["POOLED"]
                    for sc in scopes:
                        x = sub if sc in ("POOLED", "GC") else sub[sub.ticker == sc]
                        rows.append(dict(lineage=LINEAGE, finalist=f.finalist, run=rn, period=per, scope=sc, **summary(x)))
                if rn == "base":
                    t2 = tr.copy()
                    t2.insert(0, "finalist", f.finalist)
                    tl.append(t2)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "validation_p2_holdouts.csv", index=False)
    pd.concat(tl).to_csv(OUT / "finalist_p2_trades_all.csv", index=False)
    print("phase 2 holdouts evaluated once -> outputs/validation_p2_holdouts.csv")


if __name__ == "__main__":
    {"freeze": freeze, "loto": loto, "evaluate": evaluate}[sys.argv[1]]()
