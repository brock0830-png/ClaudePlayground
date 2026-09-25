"""Single-config trade reconstruction (for trade lists, overlap clustering and validation).

Uses the same numba entry / exit functions as the grid kernel, so a config's trades here are
exactly the trades behind its grid row.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from common import COMMISSION_RT, EQUITY, LINEAGE, RISK_FRAC, SPEC, UPPER
from grid import S_VALS, STYLES, struct_prices
from sim import BOUNCE, BREAKOUT, _rnd, find_entry, trade_pnl, walk

STYLE_CODE = {v: k for k, v in STYLES.items()}


def parse(cid: str) -> dict:
    lv, side, unit, d, style, D, stop, tgt = cid.split("|")
    return dict(level=lv, side=BOUNCE if side == "bounce" else BREAKOUT, side_name=side, unit=unit,
                d=float(d[1:]), style=STYLE_CODE[style], style_name=style,
                D=float(D[1:]) if D != "Dinf" else np.inf, stop=stop, target=tgt)


def config_trades(B, cid, variant=None, shift=0.0, scale=1.0, slip=1.0):
    """Trades for one config on every ticker in B. variant = families.REGISTRY entry name or None."""
    be_R, so_t, tnext_fn = 0.0, 0.0, None
    if variant not in (None, "F0"):
        from families import REGISTRY
        kw = REGISTRY[variant][2] if len(REGISTRY[variant]) > 2 else {}
        be_R, so_t, tnext_fn = kw.get("be_R", 0.0), kw.get("so_t", 0.0), kw.get("tnext_fn")
    c = parse(cid)
    flip, mask_fn = False, None
    if variant and variant not in ("F0", None):
        from families import REGISTRY
        ent = REGISTRY[variant]
        mask_fn, flip = ent[0], ent[1]
    budget = EQUITY * RISK_FRAC
    rows = []
    for tk, b in B.items():
        sp = SPEC[tk]
        tick, pv = sp["tick"], sp["pv"]
        od_nat = 1 if c["level"] in UPPER else -1
        od = -od_nat if flip else od_nat
        lv = b.level_matrix(scale)[c["level"]]
        P = lv if shift == 0.0 else lv + od_nat * shift * b.sigma
        if shift != 0.0:
            P = np.where(od_nat * (P - b.wo) / b.sigma < 0.05, np.nan, P)
        U = b.atr if c["unit"] == "ATR" else b.sigma
        sside = (BREAKOUT if c["side"] == BOUNCE else BOUNCE) if flip else c["side"]
        S_struct, T_next = struct_prices(b, c["level"], sside, scale, shift)
        if tnext_fn is not None:
            T_next = tnext_fn(b, (c["level"], c["side"], c["unit"], c["d"], c["style"], c["D"]), P)
        allow = np.ones(len(b.wo), np.bool_)
        bar_ok = np.ones(b.O.shape, np.bool_)
        SB = None
        if mask_fn is not None:
            cell = (c["level"], c["side"], c["unit"], c["d"], c["style"], c["D"])
            allow, bar_ok, SB = (mask_fn(b, cell, P, od_nat, flip) if flip else mask_fn(b, cell, P, od_nat))
        dirn = -od if c["side"] == BOUNCE else od
        for w in range(len(b.wo)):
            if not allow[w] or not np.isfinite(P[w]):
                continue
            n = int(b.nb[w])
            sb = 0 if SB is None else int(SB[w])
            if sb < 0 or sb >= n:
                continue
            Lv, uu = P[w], U[w]
            eb, epx, etype, plan = find_entry(b.O, b.H, b.L, b.C, n, w, Lv, uu, od, c["side"], c["d"], c["style"],
                                              c["D"], tick, bar_ok, sb)
            if eb < 0:
                continue
            fill = epx + dirn * slip * tick
            plan_fill = plan + dirn * slip * tick
            tref = plan if c["style"] == 0 else epx
            if c["stop"] == "STRUCT":
                S = S_struct[w]
            else:
                s = float(c["stop"][1:])
                S = Lv + od * (c["d"] + s) * uu if c["side"] == BOUNCE else Lv + od * (c["d"] - s) * uu
            if not np.isfinite(S):
                continue
            S = _rnd(S, tick, 0)
            if dirn * (fill - S) < tick * 0.999:
                continue
            risk = dirn * (plan_fill - S)
            if risk < tick * 0.999:
                continue
            rpc = risk * pv
            ncon = math.floor(budget / rpc + 1e-9)
            if ncon < 1:
                rows.append(dict(ticker=tk, week=b.weeks.index[w], skipped="budget"))
                continue
            t = c["target"]
            if t == "NEXT":
                T = T_next[w]
            elif t == "WO":
                T = b.wo[w] if c["side"] == BOUNCE else np.nan
            elif t == "HOLD":
                T = tref + dirn * 1e6 * uu
            else:
                T = tref + dirn * float(t[1:]) * uu
            if not np.isfinite(T):
                continue
            T = _rnd(T, tick, dirn)
            if dirn * (T - epx) < tick:
                continue
            if be_R > 0 or so_t > 0:
                TA = _rnd(tref + dirn * so_t * uu, tick, dirn) if so_t > 0 else np.nan
                pnl, xb, xp, xk = trade_pnl(b.O, b.H, b.L, b.C, n, w, eb, etype, dirn, S, T, tick, slip, fill,
                                            risk, be_R, TA, ncon, pv, COMMISSION_RT)
            else:
                xp, xb, xk = walk(b.O, b.H, b.L, b.C, n, w, eb, etype, dirn, S, T, tick, slip)
                pnl = ncon * (dirn * (xp - fill) * pv - COMMISSION_RT)
            rows.append(dict(lineage=LINEAGE, ticker=tk, micro=sp["micro"], week=b.weeks.index[w],
                             year=int(b.weeks.index[w].year), entry_time=pd.Timestamp(b.TS[w, eb]),
                             exit_time=pd.Timestamp(b.TS[w, xb]), dir="long" if dirn > 0 else "short",
                             level_px=Lv, planned_px=plan, entry_px=fill, stop_px=S, target_px=T if abs(T) < 1e8 else np.nan,
                             exit_px=xp, exit_kind=["stop", "target", "time"][xk], contracts=ncon,
                             risk_usd=ncon * rpc, pnl_usd=pnl, R=pnl / (ncon * rpc), skipped=""))
    df = pd.DataFrame(rows)
    if len(df):
        df = df[df.skipped == ""].drop(columns=["skipped"]).sort_values("entry_time").reset_index(drop=True)
    return df


def summary(tr: pd.DataFrame) -> dict:
    if tr is None or len(tr) == 0:
        return dict(n=0, wr=np.nan, pf=np.nan, expR=np.nan, exp_usd=np.nan, usd=0.0, maxdd_usd=np.nan, sdR=np.nan)
    p = tr.pnl_usd.values
    gp, gl = p[p > 0].sum(), -p[p < 0].sum()
    eq = np.cumsum(tr.sort_values("exit_time").pnl_usd.values)
    dd = (np.maximum.accumulate(np.maximum(eq, 0)) - eq).max()
    return dict(n=len(tr), wr=float((tr.R > 0).mean()), pf=gp / gl if gl > 0 else np.inf, expR=float(tr.R.mean()),
                exp_usd=float(p.mean()), usd=float(p.sum()), maxdd_usd=float(dd), sdR=float(tr.R.std(ddof=1)))
