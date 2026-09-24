"""Phase 1 hypotheses MP1-MP28 (spec sections 4 and 4b) as trade generators.

Each generator takes the context and a variant dict and returns candidate Trades. Only
information available at the entry time is used: prior sessions' features, the current
session's path up to the entry point, and labels that the spec says are known at that point
(opening type at 10:00, IB at 10:30). Day-type labels feed next-session trades only.
"""
from __future__ import annotations

import math

import numpy as np

from .engine import Ctx, Trade, simulate
from .features import acceptance_period
from .profile import build_profile

M_OPEN, M_1000, M_1030, M_1100 = 570, 600, 630, 660


def _f(x) -> bool:
    return x == x and x is not None


def _tgt(level: float, side: int) -> float:
    """Round a target to a whole tick on the conservative side."""
    return math.floor(level) if side > 0 else math.ceil(level)


def _ok(tr: Trade) -> bool:
    """Drop trades whose entry is already at/through the stop or the target."""
    if _f(tr.stop) and (tr.px - tr.stop) * tr.side <= 0:
        return False
    if _f(tr.target) and (tr.target - tr.px) * tr.side <= 0:
        return False
    return True


def _at(ctx: Ctx, d: int, minute: int, side: int, **kw) -> Trade | None:
    k = ctx.k_open(d, minute)
    if k < 0:
        return None
    tr = Trade(d=d, k=k, px=int(ctx.P[k]), side=side, tau=minute, exit=kw.pop("exit", ("close", 0)), **kw)
    return tr if _ok(tr) else None


def _touch_trade(ctx: Ctx, d: int, k: int, level: float, side: int, **kw) -> Trade | None:
    if k < 0:
        return None
    px = ctx.path.fill(k, int(level))
    tr = Trade(d=d, k=k, px=px, side=side, tau=int(ctx.minute[k // 4]), exit=kw.pop("exit", ("close", 0)),
               check_from=k, **kw)
    return tr if _ok(tr) else None


def _ses_of_k(ctx: Ctx, k: int) -> int:
    return int(np.searchsorted(ctx.b1, k // 4, side="right"))


def _collect(xs):
    return [x for x in xs if x is not None]


def _prior(ctx, d, col):
    return ctx.D[col].iloc[d - 1]


# ------------------------------------------------------------------------------------------------ MP1
def _va_cols(v):
    return ("p_val", "p_vah", "p_poc") if v.get("va", "tpo") == "tpo" else ("p_vval", "p_vvah", "p_vpoc")


def mp1(ctx: Ctx, v: dict, strict: bool = False) -> list:
    """Value-Area Rule (p.244-246): open outside prior VA, accepted back inside for 2 periods ->
    enter at the end of the 2nd period toward the far edge; target far edge; stop a 30-minute close
    back outside. MP1c (strict) adds: open inside prior range, prior VA narrow (bottom third of 20
    VA widths), trade in the direction of the 10-day value migration."""
    cv, ch, _ = _va_cols(v)
    D, out = ctx.D, []
    for d in range(1, ctx.n):
        val, vah, O = D[cv].iloc[d], D[ch].iloc[d], D["O"].iloc[d]
        if not (_f(val) and _f(vah)) or val <= O <= vah:
            continue
        side = -1 if O > vah else 1
        if strict:
            if not (D["p_L"].iloc[d] <= O <= D["p_H"].iloc[d]):
                continue
            if not bool(D["va_narrow"].iloc[d - 1]) or D["mig10"].iloc[d - 1] != side:
                continue
        F = ctx.F[d]
        j = acceptance_period(F["p_lo"], F["p_hi"], val, vah, 0, 2)
        if j < 0 or j >= F["n_per"] - 1:
            continue
        out.append(_at(ctx, d, M_OPEN + 30 * (j + 1), side, target=val if side < 0 else vah,
                       pc_stop=vah if side < 0 else val))
    return _collect(out)


def mp1c(ctx, v):
    return mp1(ctx, v, strict=True)


# ------------------------------------------------------------------------------------------------ opening types
def _drive_ok(D, d, col, v) -> bool:
    """Explore variant "drive05" (addendum 1): the drive also reached at least drive_min x the
    20-day median A-period range beyond the OR by 10:00."""
    k = v.get("drive_min")
    if k is None:
        return True
    med = D["med20_arange"].iloc[d]
    return bool(med == med and D[col].iloc[d] >= k * med)


def mp2(ctx, v):
    """Open-Drive: enter 10:00 in drive direction, stop = trade back through the OR."""
    D, out = ctx.D, []
    for d in np.flatnonzero(D["open_A"].to_numpy() == "OD"):
        if not _drive_ok(D, d, "od_dist", v):
            continue
        s = int(D["od_dir"].iloc[d])
        stop = D["or_lo"].iloc[d] - 1 if s > 0 else D["or_hi"].iloc[d] + 1
        out.append(_at(ctx, d, M_1000, s, stop=stop))
    return _collect(out)


def mp3(ctx, v):
    """Open-Rejection-Reverse: first retest of the OR from 10:00 in the reversal direction; stop =
    beyond the initial extreme [C16]."""
    D, out = ctx.D, []
    for d in np.flatnonzero(D["open_A"].to_numpy() == "ORR"):
        s = int(D["orr_dir"].iloc[d])
        lvl = D["or_lo"].iloc[d] if s < 0 else D["or_hi"].iloc[d]
        k0 = ctx.k_open(d, M_1000)
        if k0 < 0:
            continue
        k = ctx.path.touch(k0, ctx.k_end(d), int(lvl), from_below=(s < 0), armed_at_start=True)
        ext = D["orr_ext"].iloc[d]
        out.append(_touch_trade(ctx, d, k, lvl, s, stop=ext + 1 if s < 0 else ext - 1))
    return _collect(out)


def mp4(ctx, v):
    """Open-Test-Drive: enter 10:00 in drive direction, stop = back through the OR."""
    D, out = ctx.D, []
    for d in np.flatnonzero(D["open_A"].to_numpy() == "OTD"):
        if not _drive_ok(D, d, "otd_dist", v):
            continue
        s = int(D["otd_dir"].iloc[d])
        stop = D["or_lo"].iloc[d] - 1 if s > 0 else D["or_hi"].iloc[d] + 1
        out.append(_at(ctx, d, M_1000, s, stop=stop))
    return _collect(out)


def mp5(ctx, v):
    """Open-Auction in range: from 11:00 fade the first touch of the developing VAH/VAL toward the
    developing POC; stop 4 ticks beyond the day's extreme. Developing profile = completed periods [C22]."""
    D, out = ctx.D, []
    for d in np.flatnonzero(D["open_A"].to_numpy() == "OA-in"):
        F, off = ctx.F[d], int(ctx.offset[d])
        for j in range(3, F["n_per"]):
            pr = build_profile(F["p_lo"][:j] - off, F["p_hi"][:j] - off)
            vah, val, poc = pr.vah_t + off, pr.val_t + off, pr.poc_t + off
            k0, k1 = ctx.period_k(d, j)
            ref = k0 - 1                      # previous close, for arming
            kh = ctx.path.touch(ref, k1, vah, from_below=True)
            kl = ctx.path.touch(ref, k1, val, from_below=False)
            if kh < 0 and kl < 0:
                continue
            if kh >= 0 and (kl < 0 or kh <= kl):
                hi = max(int(ctx.P[ctx.k_start(d):kh].max()), vah)       # extreme up to the touch
                out.append(_touch_trade(ctx, d, kh, vah, -1, stop=hi + 4, target=_tgt(poc, -1)))
            else:
                lo = min(int(ctx.P[ctx.k_start(d):kl].min()), val)
                out.append(_touch_trade(ctx, d, kl, val, 1, stop=lo - 4, target=_tgt(poc, 1)))
            break
    return _collect(out)


def _ib_break(ctx, d, **kw):
    """First 30-minute close beyond the IB (period C onward), enter at the next bar open, stop back
    inside the IB (strictly inside) [C15, C17]."""
    F = ctx.F[d]
    ib_hi, ib_lo = ctx.D["ib_hi"].iloc[d], ctx.D["ib_lo"].iloc[d]
    for j in range(2, F["n_per"] - 1):
        c = F["p_cl"][j]
        if c > ib_hi or c < ib_lo:
            s = 1 if c > ib_hi else -1
            return _at(ctx, d, M_OPEN + 30 * (j + 1), s, stop=ib_hi - 1 if s > 0 else ib_lo + 1, **kw)
    return None


def mp6(ctx, v):
    D = ctx.D
    return _collect(_ib_break(ctx, d) for d in np.flatnonzero(D["open_A"].to_numpy() == "OA-out"))


def mp7(ctx, v):
    D = ctx.D
    return _collect(_ib_break(ctx, d) for d in np.flatnonzero(D["ib_narrow"].to_numpy()))


def mp8(ctx, v):
    """Wide IB: fade the first touch of IB high/low after 10:30, target IB midpoint (no stop in spec)."""
    D, out = ctx.D, []
    for d in np.flatnonzero(D["ib_wide"].to_numpy()):
        hi, lo = int(D["ib_hi"].iloc[d]), int(D["ib_lo"].iloc[d])
        k0 = ctx.k_open(d, M_1030)
        if k0 < 0:
            continue
        kh = ctx.path.first_at_or_above(k0, ctx.k_end(d), hi)
        kl = ctx.path.first_at_or_below(k0, ctx.k_end(d), lo)
        mid = (hi + lo) / 2
        if kh >= 0 and (kl < 0 or kh <= kl):
            out.append(_touch_trade(ctx, d, kh, hi, -1, target=_tgt(mid, -1)))
        elif kl >= 0:
            out.append(_touch_trade(ctx, d, kl, lo, 1, target=_tgt(mid, 1)))
    return _collect(out)


def mp9(ctx, v):
    """Range estimation: open inside prior VA, accepted (A and B inside), an A or B tail at one IB
    extreme -> enter at 10:30 toward the other side, target tail extreme -/+ 0.9 x prior range."""
    D, out = ctx.D, []
    for d in np.flatnonzero(D["open_loc"].to_numpy() == 0):
        F, off = ctx.F[d], int(ctx.offset[d])
        if acceptance_period(F["p_lo"][:2], F["p_hi"][:2], D["p_val"].iloc[d], D["p_vah"].iloc[d], 0, 2) != 1:
            continue
        pr = build_profile(F["p_lo"][:2] - off, F["p_hi"][:2] - off, last_period=-1)
        th, tl = pr.tail_hi_len > 0, pr.tail_lo_len > 0
        if th == tl:
            continue
        prng = D["p_H"].iloc[d] - D["p_L"].iloc[d]
        if th:
            out.append(_at(ctx, d, M_1030, -1, target=_tgt(pr.hi_t + off - 0.9 * prng, -1)))
        else:
            out.append(_at(ctx, d, M_1030, 1, target=_tgt(pr.lo_t + off + 0.9 * prng, 1)))
    return _collect(out)


def mp10(ctx, v):
    """Open above/below prior VA. Accepted outside in the first hour (A and B both trade beyond the
    VA): 10:30 with it. Otherwise, if price traded back into the VA: 10:30 toward prior POC."""
    cv, ch, cp = _va_cols(v)
    leg = v.get("leg", "both")
    D, out = ctx.D, []
    for d in range(1, ctx.n):
        val, vah, poc, O = D[cv].iloc[d], D[ch].iloc[d], D[cp].iloc[d], D["O"].iloc[d]
        if not _f(val) or val <= O <= vah:
            continue
        s = 1 if O > vah else -1
        F = ctx.F[d]
        beyond = [(F["p_hi"][j] > vah) if s > 0 else (F["p_lo"][j] < val) for j in (0, 1)]
        inside = [(F["p_lo"][j] <= vah and F["p_hi"][j] >= val) for j in (0, 1)]
        if all(beyond):
            if leg in ("both", "acc"):
                out.append(_at(ctx, d, M_1030, s, tag="acc"))
        elif any(inside) and leg in ("both", "rej"):
            k = ctx.k_open(d, M_1030)
            if k >= 0 and (ctx.P[k] - poc) * s > 0:
                out.append(_at(ctx, d, M_1030, -s, tag="rej"))
    return _collect(out)


def mp11(ctx, v):
    """Overnight inventory: against it at the open, exit 10:30."""
    D = ctx.D
    return _collect(_at(ctx, d, M_OPEN, -int(D["inventory"].iloc[d]), exit=("time", 0, M_1030))
                    for d in np.flatnonzero(D["inventory"].to_numpy() != 0))


# ------------------------------------------------------------------------------------------------ balance
def _bal_break(ctx, d, bh, bl, k0, exit_rule, only=0):
    """First trade 2+ ticks beyond a balance extreme from point k0; stop 4 ticks back inside."""
    k1 = ctx.k_end(d)
    ku = ctx.path.first_at_or_above(k0, k1, bh + 2) if only >= 0 else -1
    kd = ctx.path.first_at_or_below(k0, k1, bl - 2) if only <= 0 else -1
    if ku >= 0 and (kd < 0 or ku <= kd):
        return _touch_trade(ctx, d, ku, bh + 2, 1, stop=bh - 4, exit=exit_rule)
    if kd >= 0:
        return _touch_trade(ctx, d, kd, bl - 2, -1, stop=bl + 4, exit=exit_rule)
    return None


def mp12(ctx, v, failed: bool = False):
    m = v.get("bal", 3)
    ex = ("close", 2) if v.get("hold3") else ("close", 0)
    D, out = ctx.D, []
    for d in range(1, ctx.n):
        bh, bl = D[f"bal{m}_hi"].iloc[d - 1], D[f"bal{m}_lo"].iloc[d - 1]
        if not _f(bh):
            continue
        tr = _bal_break(ctx, d, int(bh), int(bl), ctx.k_start(d), ex)
        if tr is None:
            continue
        if not failed:
            out.append(tr)
            continue
        r = simulate(ctx, tr)
        if r is None or r["why"] != "stop" or r["k_exit"] >= ctx.k_end(d):
            continue
        out.append(_bal_break(ctx, d, int(bh), int(bl), r["k_exit"], ex, only=-tr.side))
    return _collect(out)


def mp12b(ctx, v):
    return mp12(ctx, v, failed=True)


# ------------------------------------------------------------------------------------------------ close-to-next-day
def _close_trades(ctx, v, col_side):
    ex = ("close", 1) if v.get("next_close") else ("time", 1, M_1100)
    out = []
    for d in np.flatnonzero(col_side != 0):
        k = ctx.k_close(d)
        out.append(Trade(d=int(d), k=k, px=int(ctx.P[k]), side=int(col_side[d]), tau="close", exit=ex))
    return out


def mp13(ctx, v):
    D = ctx.D
    ne = D["day_type"].to_numpy() == "Neutral-Extreme"
    side = np.where(ne, np.where(D["C"] >= D["H"] - 0.15 * D["range"], 1, -1), 0)
    return _close_trades(ctx, v, side)


def mp14(ctx, v):
    return _close_trades(ctx, v, ctx.D["three_i"].to_numpy())


def mp14b(ctx, v):
    return _close_trades(ctx, v, ctx.D["two_i_one_r"].to_numpy())


# ------------------------------------------------------------------------------------------------ spikes
def _spike_days(ctx):
    D = ctx.D
    for d in range(1, ctx.n):
        sd = int(D["spike_dir"].iloc[d - 1])
        if sd:
            yield d, sd, int(D["spike_lo"].iloc[d - 1]), int(D["spike_hi"].iloc[d - 1]), D["O"].iloc[d]


def mp15(ctx, v):
    """Open beyond the spike in its direction: trade the first test of the spike edge with the
    spike, stop 4 ticks inside the spike."""
    out = []
    for d, sd, lo, hi, O in _spike_days(ctx):
        if sd > 0 and O > hi:
            k = ctx.path.touch(ctx.k_start(d), ctx.k_end(d), hi, from_below=False, armed_at_start=True)
            out.append(_touch_trade(ctx, d, k, hi, 1, stop=hi - 4))
        elif sd < 0 and O < lo:
            k = ctx.path.touch(ctx.k_start(d), ctx.k_end(d), lo, from_below=True, armed_at_start=True)
            out.append(_touch_trade(ctx, d, k, lo, -1, stop=lo + 4))
    return _collect(out)


def mp15b(ctx, v):
    """Open inside the spike: fade the first touch of a spike extreme, target the spike midpoint."""
    out = []
    for d, sd, lo, hi, O in _spike_days(ctx):
        if not (lo <= O <= hi):
            continue
        k0, k1 = ctx.k_start(d), ctx.k_end(d)
        kh = ctx.path.touch(k0, k1, hi, from_below=True)
        kl = ctx.path.touch(k0, k1, lo, from_below=False)
        mid = (hi + lo) / 2
        if kh >= 0 and (kl < 0 or kh <= kl):
            out.append(_touch_trade(ctx, d, kh, hi, -1, target=_tgt(mid, -1)))
        elif kl >= 0:
            out.append(_touch_trade(ctx, d, kl, lo, 1, target=_tgt(mid, 1)))
    return _collect(out)


def mp15c(ctx, v):
    """Open against the spike: enter at 10:00 against the spike direction."""
    return _collect(_at(ctx, d, M_1000, -sd) for d, sd, lo, hi, O in _spike_days(ctx)
                    if (sd > 0 and O < lo) or (sd < 0 and O > hi))


# ------------------------------------------------------------------------------------------------ prior-day structure
def mp16(ctx, v):
    """Prior-day poor high/low within one prior-day IB width of the open: trade toward it at the
    open, target the level [C23]."""
    D, out = ctx.D, []
    for d in range(1, ctx.n):
        O, w = D["O"].iloc[d], D["p_ib_w"].iloc[d]
        c = []
        if bool(D["poor_high"].iloc[d - 1]):
            dist = D["p_H"].iloc[d] - O
            if 0 < dist <= w:
                c.append((dist, 1, D["p_H"].iloc[d]))
        if bool(D["poor_low"].iloc[d - 1]):
            dist = O - D["p_L"].iloc[d]
            if 0 < dist <= w:
                c.append((dist, -1, D["p_L"].iloc[d]))
        if not c or (len(c) == 2 and c[0][0] == c[1][0]):
            continue
        _, s, lvl = min(c)
        out.append(_at(ctx, d, M_OPEN, s, target=lvl))
    return _collect(out)


def mp17(ctx, v):
    """Prior-day tail: fade the first test of the tail's inner edge, stop beyond the tail extreme."""
    D, out = ctx.D, []
    for d in range(1, ctx.n):
        O, k0, k1 = D["O"].iloc[d], ctx.k_start(d), ctx.k_end(d)
        cands = []
        if D["tail_hi_len"].iloc[d - 1] > 0:
            e = int(D["tail_hi_inner"].iloc[d - 1])
            if O < e:
                k = ctx.path.touch(k0, k1, e, from_below=True, armed_at_start=True)
                if k >= 0:
                    cands.append((k, e, -1, D["p_H"].iloc[d] + 1))
        if D["tail_lo_len"].iloc[d - 1] > 0:
            e = int(D["tail_lo_inner"].iloc[d - 1])
            if O > e:
                k = ctx.path.touch(k0, k1, e, from_below=False, armed_at_start=True)
                if k >= 0:
                    cands.append((k, e, 1, D["p_L"].iloc[d] - 1))
        if cands:
            k, e, s, stop = min(cands)
            out.append(_touch_trade(ctx, d, k, e, s, stop=stop))
    return _collect(out)


def mp18(ctx, v):
    """Prior-day mid-profile single prints: fade the first test of the near edge, stop 4 ticks
    through the far side."""
    D, out = ctx.D, []
    for d in range(1, ctx.n):
        O, k0, k1 = D["O"].iloc[d], ctx.k_start(d), ctx.k_end(d)
        cands = []
        for lo, hi in D["single_runs"].iloc[d - 1]:
            if O > hi:
                k = ctx.path.touch(k0, k1, hi, from_below=False, armed_at_start=True)
                if k >= 0:
                    cands.append((k, hi, 1, lo - 4))
            elif O < lo:
                k = ctx.path.touch(k0, k1, lo, from_below=True, armed_at_start=True)
                if k >= 0:
                    cands.append((k, lo, -1, hi + 4))
        if cands:
            k, e, s, stop = min(cands)
            out.append(_touch_trade(ctx, d, k, e, s, stop=stop))
    return _collect(out)


def mp19(ctx, v):
    """Value placement: 2+ sessions of higher (lower) value and the open inside/above (below) the
    prior VA -> enter at the open in the trend direction."""
    rel = "vrel" if v.get("va", "tpo") == "tpo" else "vvrel"
    cv, ch, _ = _va_cols(v)
    D, out = ctx.D, []
    for d in range(2, ctx.n):
        r1, r2, O = D[rel].iloc[d - 1], D[rel].iloc[d - 2], D["O"].iloc[d]
        if r1 == 1 and r2 == 1 and O >= D[cv].iloc[d]:
            out.append(_at(ctx, d, M_OPEN, 1))
        elif r1 == -1 and r2 == -1 and O <= D[ch].iloc[d]:
            out.append(_at(ctx, d, M_OPEN, -1))
    return _collect(out)


def mp20(ctx, v):
    """P-shape after lower value: short next open; b-shape after higher value: long next open."""
    D, out = ctx.D, []
    for d in range(1, ctx.n):
        if bool(D["p_shape"].iloc[d - 1]):
            out.append(_at(ctx, d, M_OPEN, -1))
        elif bool(D["b_shape"].iloc[d - 1]):
            out.append(_at(ctx, d, M_OPEN, 1))
    return _collect(out)


def mp21(ctx, v):
    """Gap: open outside prior range, not filled in the first hour -> 10:30 in gap direction."""
    D, out = ctx.D, []
    for d in np.flatnonzero(D["open_loc"].to_numpy() == 2):
        O, F = D["O"].iloc[d], ctx.F[d]
        if O > D["p_H"].iloc[d] and min(F["p_lo"][:2]) > D["p_H"].iloc[d]:
            out.append(_at(ctx, d, M_1030, 1))
        elif O < D["p_L"].iloc[d] and max(F["p_hi"][:2]) < D["p_L"].iloc[d]:
            out.append(_at(ctx, d, M_1030, -1))
    return _collect(out)


def mp22(ctx, v):
    """Prior-week composite VAH/VAL (1-tick rows) [C18]: fade the first touch of each in the week,
    stop 8 ticks beyond, exit at that session's close. Approach side decides the fade direction."""
    D = ctx.D
    wk = D["date"].dt.to_period("W-FRI").to_numpy()
    weeks = list(dict.fromkeys(wk))
    out = []
    for w_prev, w in zip(weeks[:-1], weeks[1:]):
        prev = np.flatnonzero(wk == w_prev)
        cur = np.flatnonzero(wk == w)
        lo = np.concatenate([ctx.F[i]["p_lo"] for i in prev])
        hi = np.concatenate([ctx.F[i]["p_hi"] for i in prev])
        pr = build_profile(lo, hi, rs=1)
        k0, k1 = ctx.k_start(cur[0]), ctx.k_end(cur[-1])
        start = ctx.P[k0]
        for lvl in (pr.vah_t, pr.val_t):
            if start == lvl:
                continue
            below = start < lvl
            k = ctx.path.touch(k0, k1, lvl, from_below=below, armed_at_start=True)
            if k < 0:
                continue
            d = _ses_of_k(ctx, k)
            s = -1 if below else 1
            out.append(_touch_trade(ctx, d, k, lvl, s, stop=lvl + 8 if s < 0 else lvl - 8))
    return _collect(out)


# ------------------------------------------------------------------------------------------------ 4b
def _ap_trades(ctx, confirmed: bool):
    D, out = ctx.D, []
    for e in range(ctx.n - 1):
        ib_hi, ib_lo, C = D["ib_hi"].iloc[e], D["ib_lo"].iloc[e], D["C"].iloc[e]
        levels = []
        if D["re_up"].iloc[e]:
            ap = int(ib_hi) + 1
            if confirmed and C > ap:
                levels.append((ap, 1))            # support: buy the retest from above
            if not confirmed and C <= ib_hi:
                levels.append((ap, -1))           # failed: sell the return from below
        if D["re_dn"].iloc[e]:
            ap = int(ib_lo) - 1
            if confirmed and C < ap:
                levels.append((ap, -1))
            if not confirmed and C >= ib_lo:
                levels.append((ap, 1))
        last = min(e + 5, ctx.n - 1)
        k0, k1 = ctx.k_start(e + 1), ctx.k_end(last)
        for ap, s in levels:
            # confirmed: retest from the extension side; failed: first return from inside
            from_below = (s < 0)
            k = ctx.path.touch(k0, k1, ap, from_below=from_below)
            if k < 0:
                continue
            d = _ses_of_k(ctx, k)
            out.append(_touch_trade(ctx, d, k, ap, s, stop=ap - 4 if s > 0 else ap + 4))
    return _collect(out)


def mp23(ctx, v):
    """Confirmed auction point (SoM ch.11): next 5 sessions, first retest from the extension side,
    go with it; stop 4 ticks through; exit at close [C19]."""
    return _ap_trades(ctx, True)


def mp24(ctx, v):
    """Failed range extension (SoM ch.11): next 5 sessions, fade the first return to the auction
    point; stop 4 ticks beyond; exit at close."""
    return _ap_trades(ctx, False)


def mp25(ctx, v):
    """Narrow-range day (RTH range <= 0.6 x 20-day median): next day, MP6 entry."""
    D = ctx.D
    nr = (D["range"] <= 0.6 * D["med20_range"]).to_numpy()
    return _collect(_ib_break(ctx, d) for d in range(1, ctx.n) if nr[d - 1])


def composite_count(ctx, d: int) -> tuple[int, int]:
    """(count, direction) for MP26 at the close of d, or (-1, 0) if no composite [C24]."""
    D = ctx.D
    rng, med = D["range"].to_numpy(), D["med20_range"].to_numpy()
    exp = np.flatnonzero(rng[:d + 1] >= 1.5 * med[:d + 1])
    if not len(exp) or exp[-1] == d:
        return -1, 0
    e = int(exp[-1])
    sess = list(range(max(e + 1, d - 9), d + 1))
    lo = np.concatenate([ctx.F[i]["p_lo"] for i in sess])
    hi = np.concatenate([ctx.F[i]["p_hi"] for i in sess])
    cnt = build_profile(lo, hi, rs=1).max_width
    return cnt, int(np.sign(D["C"].iloc[e] - D["O"].iloc[e]))


def mp26(ctx, v):
    """Timeslots-used (SoM ch.6): count >= 43 -> next open against the composite's starting move;
    count <= 18 -> with it; hold 3 sessions."""
    out = []
    for d in range(ctx.n - 1):
        cnt, dr = composite_count(ctx, d)
        if cnt < 0 or dr == 0:
            continue
        if cnt >= 43:
            out.append(_at(ctx, d + 1, M_OPEN, -dr, exit=("close", 2), tag="over"))
        elif cnt <= 18:
            out.append(_at(ctx, d + 1, M_OPEN, dr, exit=("close", 2), tag="under"))
    return _collect(out)


def mp27(ctx, v):
    """Repeated lows (highs) without excess over the last 5 sessions: long (short) next open, hold 3
    sessions. The repeated level must be the window's extreme [C25]."""
    D, out = ctx.D, []
    L, H, atr = D["L"].to_numpy(), D["H"].to_numpy(), D["atr20"].to_numpy()
    tlo, thi = D["tail_lo_len"].to_numpy(), D["tail_hi_len"].to_numpy()
    for d in range(4, ctx.n - 1):
        if not _f(atr[d]):
            continue
        w = slice(d - 4, d + 1)
        tol = 0.25 * atr[d]
        lows = np.flatnonzero(L[w] <= L[w].min() + tol)
        highs = np.flatnonzero(H[w] >= H[w].max() - tol)
        rl = len(lows) >= 2 and not (tlo[w][lows] > 0).any()
        rh = len(highs) >= 2 and not (thi[w][highs] > 0).any()
        if rl and not rh:
            out.append(_at(ctx, d + 1, M_OPEN, 1, exit=("close", 2)))
        elif rh and not rl:
            out.append(_at(ctx, d + 1, M_OPEN, -1, exit=("close", 2)))
    return _collect(out)


def mp28(ctx, v):
    """Bracket-extreme fade: inside a balance area, the first probe beyond a balance extreme that is
    back inside within the same or next period -> fade toward the balance midpoint, stop 4 ticks
    beyond the probe's extreme, exit at close [C17]."""
    m = v.get("bal", 3)
    D, out = ctx.D, []
    for d in range(1, ctx.n):
        bh, bl = D[f"bal{m}_hi"].iloc[d - 1], D[f"bal{m}_lo"].iloc[d - 1]
        if not _f(bh):
            continue
        bh, bl = int(bh), int(bl)
        k0, k1 = ctx.k_start(d), ctx.k_end(d)
        ku = ctx.path.first_at_or_above(k0, k1, bh + 1)
        kd = ctx.path.first_at_or_below(k0, k1, bl - 1)
        if ku < 0 and kd < 0:
            continue
        up = ku >= 0 and (kd < 0 or ku <= kd)
        kp = ku if up else kd
        j = int((ctx.minute[kp // 4] - 570) // 30)
        _, kend = ctx.period_k(d, j + 1) if j + 1 < ctx.F[d]["n_per"] else (0, k1)
        if up:
            kb = ctx.path.first_at_or_below(kp, kend, bh - 1)
            if kb >= 0:
                ext = int(ctx.P[kp:kb + 1].max())
                out.append(_touch_trade(ctx, d, kb, bh - 1, -1, stop=ext + 4))
        else:
            kb = ctx.path.first_at_or_above(kp, kend, bl + 1)
            if kb >= 0:
                ext = int(ctx.P[kp:kb + 1].min())
                out.append(_touch_trade(ctx, d, kb, bl + 1, 1, stop=ext - 4))
    return _collect(out)


# ------------------------------------------------------------------------------------------------ registry
P = dict(id="P", desc="spec definition", eligible=True)
VOL = dict(id="volVA", desc="volume value area (robustness only)", va="vol", eligible=False)
# Addendum 1 (requested after the first explore freeze, run on the explore period only):
DRIVE05 = dict(id="drive05", desc="drive >= 0.5x 20-day median A-range beyond the OR by 10:00",
               drive_min=0.5, eligible=True, addendum=1)

FAMILIES = [
    # (family, generator, primary baseline, variants)
    ("MP1", mp1, "loc", [P, VOL]),
    ("MP1c", mp1c, "loc", [P, VOL]),
    ("MP2", mp2, "all", [P, DRIVE05]),
    ("MP3", mp3, "all", [P]),
    ("MP4", mp4, "all", [P, DRIVE05]),
    ("MP5", mp5, "loc", [P]),
    ("MP6", mp6, "loc", [P]),
    ("MP7", mp7, "all", [P]),
    ("MP8", mp8, "all", [P]),
    ("MP9", mp9, "loc", [P]),
    ("MP10", mp10, "loc", [P, dict(id="acc", desc="accepted-outside leg only", leg="acc", eligible=True),
                           dict(id="rej", desc="rejected-into-VA leg only", leg="rej", eligible=True),
                           dict(VOL, leg="both")]),
    ("MP11", mp11, "all", [P]),
    ("MP12", mp12, "all", [dict(P, bal=3), dict(id="bal5", desc="5-session balance", bal=5, eligible=True),
                           dict(id="hold3", desc="secondary exit: 3 sessions", bal=3, hold3=True, eligible=True),
                           dict(id="bal5_hold3", desc="5-session balance, 3-session exit", bal=5, hold3=True, eligible=True)]),
    ("MP12b", mp12b, "all", [dict(P, bal=3), dict(id="bal5", desc="5-session balance", bal=5, eligible=True),
                             dict(id="hold3", desc="secondary exit: 3 sessions", bal=3, hold3=True, eligible=True),
                             dict(id="bal5_hold3", desc="5-session balance, 3-session exit", bal=5, hold3=True, eligible=True)]),
    ("MP13", mp13, "all", [P, dict(id="nextclose", desc="secondary exit: next close", next_close=True, eligible=True)]),
    ("MP14", mp14, "all", [P, dict(id="nextclose", desc="secondary exit: next close", next_close=True, eligible=True)]),
    ("MP14b", mp14b, "all", [P, dict(id="nextclose", desc="secondary exit: next close", next_close=True, eligible=True)]),
    ("MP15", mp15, "all", [P]),
    ("MP15b", mp15b, "all", [P]),
    ("MP15c", mp15c, "all", [P]),
    ("MP16", mp16, "all", [P]),
    ("MP17", mp17, "all", [P]),
    ("MP18", mp18, "all", [P]),
    ("MP19", mp19, "loc", [P, VOL]),
    ("MP20", mp20, "all", [P]),
    ("MP21", mp21, "loc", [P]),
    ("MP22", mp22, "all", [P]),
    ("MP23", mp23, "all", [P]),
    ("MP24", mp24, "all", [P]),
    ("MP25", mp25, "all", [P]),
    ("MP26", mp26, "all", [P]),
    ("MP27", mp27, "all", [P]),
    ("MP28", mp28, "all", [dict(P, bal=3), dict(id="bal5", desc="5-session balance", bal=5, eligible=True)]),
]
