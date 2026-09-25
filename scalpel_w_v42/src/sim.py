"""Trade simulation kernel (numba) for level strategies on 4h bars, one trade per level per week.

Fill model (STEP 3 of the prompt, conservative where the 4h bar hides the path):
  * limit entry (bounce style a): fills only if price trades 1 tick through the limit; fill at the
    limit (or at the bar open if the bar opened through it). Inside the fill bar a stop is assumed
    hit if the bar's range reaches it; a target counts only if the bar CLOSES beyond it.
  * stop entry (breakout style a): triggers when the bar trades at the trigger; fill at trigger or
    the open if gapped. Inside the fill bar the stop is checked first (pessimistic).
  * reclaim / close-beyond styles: enter at the next bar's open.
  * stop and target in one bar -> stop. Gaps through a stop fill at the open.
  * 1 tick slippage on every entry, stop exit and market (time) exit; limit targets none.
  * $4.50 commission per micro contract round turn. Size = floor(budget / risk per contract);
    skip the trade if one micro exceeds the budget.
  * flat at the close of the final bar of the week.
R is net $ P&L divided by the planned $ risk (contracts x stop distance from the actual fill).
"""
import math

import numpy as np
from numba import njit

BOUNCE, BREAKOUT = 0, 1


@njit(cache=True)
def _rnd(x, tick, mode):
    # mode 1 = ceil, -1 = floor, 0 = nearest
    q = x / tick
    if mode > 0:
        return math.ceil(q - 1e-9) * tick
    if mode < 0:
        return math.floor(q + 1e-9) * tick
    return round(q) * tick


@njit(cache=True)
def find_entry(O, H, L, C, n, w, Lv, uu, od, side, d, style, D, tick, bar_ok, sb):
    """Returns (entry_bar, entry_price_before_slippage, entry_type) or (-1, nan, -1).
    entry_type: 0 = intrabar limit, 1 = at bar open, 2 = intrabar stop entry."""
    if side == BOUNCE:
        if style == 0:
            E = _rnd(Lv + od * d * uu, tick, od)            # deeper limit, rounded away from WO
            for j in range(sb, n):
                if not bar_ok[w, j]:
                    continue
                if od > 0:
                    hit = H[w, j] >= E + tick
                    gap = O[w, j] >= E
                else:
                    hit = L[w, j] <= E - tick
                    gap = O[w, j] <= E
                if hit:
                    if gap:
                        return j, O[w, j], 1
                    return j, E, 0
            return -1, np.nan, -1
        thr = Lv + od * max(d * uu, tick)
        i = -1
        for j in range(sb, n):
            if (od > 0 and H[w, j] >= thr) or (od < 0 and L[w, j] <= thr):
                i = j
                break
        if i < 0:
            return -1, np.nan, -1
        Dlim = Lv + od * D * uu
        k = style - 1          # style 1 = no time limit (k huge), 2..4 -> k = 1..3
        for j in range(i, n):
            ext = H[w, j] if od > 0 else L[w, j]
            if od * (ext - Dlim) > 0:
                return -1, np.nan, -1                      # pierced deeper than D: invalid
            if style >= 2 and j - i > k:
                return -1, np.nan, -1                      # reclaim too late
            if od * (Lv - C[w, j]) > 0:                    # closed back on the WO side
                if j + 1 < n and bar_ok[w, j + 1]:
                    return j + 1, O[w, j + 1], 1
                return -1, np.nan, -1
        return -1, np.nan, -1
    # ---------------- breakout
    if style == 0:
        E = _rnd(Lv + od * max(d * uu, tick), tick, od)
        for j in range(sb, n):
            if not bar_ok[w, j]:
                continue
            if od > 0:
                hit = H[w, j] >= E
                gap = O[w, j] >= E
            else:
                hit = L[w, j] <= E
                gap = O[w, j] <= E
            if hit:
                if gap:
                    return j, O[w, j], 1
                return j, E, 2
        return -1, np.nan, -1
    i = -1
    for j in range(sb, n):
        if (od > 0 and H[w, j] > Lv) or (od < 0 and L[w, j] < Lv):
            i = j
            break
    if i < 0:
        return -1, np.nan, -1
    thr = Lv + od * d * uu
    k = style - 1
    for j in range(i, n):
        if style >= 2 and j - i > k:
            return -1, np.nan, -1
        if od * (C[w, j] - thr) > 0:
            if j + 1 < n and bar_ok[w, j + 1]:
                return j + 1, O[w, j + 1], 1
            return -1, np.nan, -1
    return -1, np.nan, -1


@njit(cache=True)
def walk(O, H, L, C, n, w, eb, etype, dirn, S, T, tick, slip):
    """Returns (exit_price_after_slippage, exit_bar, exit_kind) kind 0=stop 1=target 2=time."""
    for j in range(eb, n):
        if dirn > 0:
            sh = L[w, j] <= S
            th = H[w, j] >= T + tick
        else:
            sh = H[w, j] >= S
            th = L[w, j] <= T - tick
        if j == eb and etype == 0:
            th = dirn * (C[w, j] - T) >= tick
        if sh:
            px = S
            if (j > eb or etype == 1) and dirn * (O[w, j] - S) <= 0:
                px = O[w, j]
            return px - dirn * slip * tick, j, 0
        if th:
            px = T
            if (j > eb or etype == 1) and dirn * (O[w, j] - T) >= 0:
                px = O[w, j]
            return px, j, 1
    return C[w, n - 1] - dirn * slip * tick, n - 1, 2


@njit(cache=True)
def simulate(O, H, L, C, nb, P, U, WO, S_struct, T_next, allow, bar_ok,
             od, side, d, style, D, s_vals, t_vals, tick, slip, pv, comm, budget, SB=None):
    """All stop x target combos for one entry definition.
    Stops: s_vals (in units U) then STRUCT. Targets: t_vals (units, from entry) then NEXT, WO.
    Returns R[w, nS, nT], PNL[w, nS, nT] (nan = no trade), entry bar, entry type, exit bar."""
    nW = O.shape[0]
    nS = s_vals.shape[0] + 1
    nT = t_vals.shape[0] + 2
    R = np.full((nW, nS, nT), np.nan)
    PNL = np.full((nW, nS, nT), np.nan)
    XB = np.full((nW, nS, nT), -1, np.int64)
    EB = np.full(nW, -1, np.int64)
    ET = np.full(nW, -1, np.int64)
    dirn = -od if side == BOUNCE else od
    for w in range(nW):
        if not allow[w]:
            continue
        Lv = P[w]
        uu = U[w]
        if not (np.isfinite(Lv) and np.isfinite(uu)) or uu <= 0:
            continue
        n = nb[w]
        sb = 0 if SB is None else SB[w]
        if sb < 0 or sb >= n:
            continue
        eb, epx, etype = find_entry(O, H, L, C, n, w, Lv, uu, od, side, d, style, D, tick, bar_ok, sb)
        if eb < 0:
            continue
        EB[w] = eb
        ET[w] = etype
        fill = epx + dirn * slip * tick
        for si in range(nS):
            if si < nS - 1:
                s = s_vals[si]
                if side == BOUNCE:
                    S = Lv + od * (d + s) * uu
                else:
                    S = Lv + od * (d - s) * uu
            else:
                S = S_struct[w]
            if not np.isfinite(S):
                continue
            S = _rnd(S, tick, 0)
            risk = dirn * (fill - S)
            if risk < tick * 0.999:
                continue                          # stop at or through the fill: no trade
            rpc = risk * pv
            ncon = math.floor(budget / rpc + 1e-9)
            if ncon < 1:
                continue
            for ti in range(nT):
                if ti < nT - 2:
                    T = epx + dirn * t_vals[ti] * uu
                elif ti == nT - 2:
                    T = T_next[w]
                else:
                    T = WO[w] if side == BOUNCE else np.nan
                if not np.isfinite(T):
                    continue
                T = _rnd(T, tick, dirn)
                if dirn * (T - epx) < tick:
                    continue                      # target already reached at entry: no trade
                xp, xb, xk = walk(O, H, L, C, n, w, eb, etype, dirn, S, T, tick, slip)
                pnl = ncon * (dirn * (xp - fill) * pv - comm)
                R[w, si, ti] = pnl / (ncon * rpc)
                PNL[w, si, ti] = pnl
                XB[w, si, ti] = xb
    return R, PNL, EB, ET, XB
