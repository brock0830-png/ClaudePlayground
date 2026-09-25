"""Overfitting guard: honest N, effective N by trade-overlap clustering, Deflated Sharpe floor.

Trade overlap is measured on entry sets: the (ticker, week) pairs in which a configuration
trades. All stop / target variants of one entry definition share (almost) the same entry set, so
they fall in one cluster, as the prompt's "trade-overlap > 0.7 means same cluster" rule implies.
Clustering is greedy: sets are visited from the highest score down; each unassigned set becomes a
representative and absorbs every unassigned set with Jaccard > 0.7.
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit
from scipy.stats import norm

from common import UPPER
from grid import BOUNCE, BREAKOUT, cells, global_weeks, struct_prices  # noqa: F401
from sim import find_entry

EULER = 0.5772156649015329


@njit(cache=True)
def entries_only(O, H, L, C, nb, P, U, allow, bar_ok, od, side, d, style, D, tick, SB):
    nW = O.shape[0]
    out = np.zeros(nW, np.bool_)
    for w in range(nW):
        if not allow[w]:
            continue
        if not (np.isfinite(P[w]) and np.isfinite(U[w])):
            continue
        n = nb[w]
        sb = SB[w]
        if sb < 0 or sb >= n:
            continue
        eb, epx, et, pl = find_entry(O, H, L, C, n, w, P[w], U[w], od, side, d, style, D, tick, bar_ok, sb)
        out[w] = eb >= 0
    return out


def cell_entry_sets(B, variant=None):
    """Boolean matrix [n_cells, n_tickers * n_global_weeks] of entries, plus cell keys."""
    from common import SPEC
    mask_fn, flip = None, False
    if variant not in (None, "F0"):
        from families import REGISTRY
        mask_fn, flip = REGISTRY[variant][0], REGISTRY[variant][1]
    allw, gmap = global_weeks(B)
    nG = len(allw)
    cl = cells()
    M = np.zeros((len(cl), len(B) * nG), np.bool_)
    for ci, cell in enumerate(cl):
        name, side, unit, d, style, D = cell
        od_nat = 1 if name in UPPER else -1
        od = -od_nat if flip else od_nat
        for k, (tk, b) in enumerate(B.items()):
            P = b.levels[name]
            U = b.atr if unit == "ATR" else b.sigma
            allow = np.ones(len(b.wo), np.bool_)
            bar_ok = np.ones(b.O.shape, np.bool_)
            SB = np.zeros(len(b.wo), np.int64)
            if mask_fn is not None:
                allow, bar_ok, sb = (mask_fn(b, cell, P, od_nat, flip) if flip else mask_fn(b, cell, P, od_nat))
                if sb is not None:
                    SB = sb
            e = entries_only(b.O, b.H, b.L, b.C, b.nb, P, U, allow, bar_ok, od, side, d, style, D,
                             SPEC[tk]["tick"], SB)
            M[ci, k * nG + gmap[tk]] = e
    keys = [f"{c[0]}|{'bounce' if c[1] == BOUNCE else 'breakout'}|{c[2]}|d{c[3]:.2f}|{['a_limit','b_reclaim','c1','c2','c3'][c[4]]}|D{c[5]:.1f}"
            for c in cl]
    return M, keys


def greedy_cluster(M, score, thr=0.7, min_size=1):
    """M bool [n, m]; score [n]. Returns cluster id per row (-1 for rows with < min_size entries)."""
    n = M.shape[0]
    sizes = M.sum(1)
    cid = np.full(n, -1, np.int64)
    ok = sizes >= min_size
    order = np.argsort(-np.where(ok, score, -np.inf), kind="stable")
    Mf = M.astype(np.float32)
    unassigned = ok.copy()
    c = 0
    for i in order:
        if not unassigned[i]:
            continue
        inter = Mf @ Mf[i]
        union = sizes + sizes[i] - inter
        jac = np.where(union > 0, inter / np.maximum(union, 1), 0)
        take = unassigned & (jac > thr)
        take[i] = True
        cid[take] = c
        unassigned[take] = False
        c += 1
    return cid


def sr0_floor(var_sr, N):
    N = max(float(N), 2.0)
    return math.sqrt(var_sr) * ((1 - EULER) * norm.ppf(1 - 1.0 / N) + EULER * norm.ppf(1 - 1.0 / (N * math.e)))


def dsr(sr, T, skew, kurt, sr0):
    den = math.sqrt(max(1 - skew * sr + (kurt - 1) / 4.0 * sr ** 2, 1e-12))
    return float(norm.cdf((sr - sr0) * math.sqrt(max(T - 1, 1)) / den))
