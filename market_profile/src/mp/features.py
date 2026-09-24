"""Session and multi-session Market Profile features (spec section 3).

`session_features` works on one RTH session's bars (adjusted ticks). `cross_session` adds
everything that needs prior sessions: IB ratio, open location, opening type, day type,
initiative/responsive, 3-to-I, P/b shapes, balance areas, value placement and overnight inventory.
Features that are only known at the close carry the session's own date and are consumed by
next-day tests only (spec section 7).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .path import Path, bar_points
from .profile import build_profile, rotation_factor, volume_va, value_area

RTH0 = 9 * 60 + 30
OR_MIN = 5
NPER = 14          # A..N for a full 09:30-16:15 session
IB_NARROW, IB_WIDE = 0.7, 1.3


def period_index(minute: np.ndarray) -> np.ndarray:
    return (np.asarray(minute) - RTH0) // 30


def session_features(o, h, l, c, v, minute, raw_offset: int = 0) -> dict:
    """Features of one RTH session. Prices are adjusted ticks; `raw_offset` is subtracted before
    binning TPO rows so that 2-tick rows line up with the traded contract's own prices."""
    o, h, l, c, v, minute = (np.asarray(x) for x in (o, h, l, c, v, minute))
    per = period_index(minute)
    n_per = int(per.max()) + 1
    p_hi = np.array([h[per == j].max() for j in range(n_per)])
    p_lo = np.array([l[per == j].min() for j in range(n_per)])
    p_op = np.array([o[per == j][0] for j in range(n_per)])
    p_cl = np.array([c[per == j][-1] for j in range(n_per)])
    f: dict = dict(n_per=n_per, O=int(o[0]), H=int(h.max()), L=int(l.min()), C=int(c[-1]),
                   p_hi=p_hi, p_lo=p_lo, p_op=p_op, p_cl=p_cl)
    orm = minute < RTH0 + OR_MIN
    f["or_hi"], f["or_lo"] = int(h[orm].max()), int(l[orm].min())
    f["a_hi"], f["a_lo"] = int(p_hi[0]), int(p_lo[0])
    f["ib_hi"], f["ib_lo"] = int(p_hi[:2].max()), int(p_lo[:2].min())
    f["ib_w"] = f["ib_hi"] - f["ib_lo"]
    f["range"] = f["H"] - f["L"]
    # range extension: any trade beyond the IB after the IB (periods C onward)
    post = per >= 2
    up_bars = np.flatnonzero(post & (h > f["ib_hi"]))
    dn_bars = np.flatnonzero(post & (l < f["ib_lo"]))
    f["re_up"], f["re_dn"] = bool(len(up_bars)), bool(len(dn_bars))
    f["re_up_per"] = int(per[up_bars[0]]) if len(up_bars) else -1
    f["re_dn_per"] = int(per[dn_bars[0]]) if len(dn_bars) else -1
    f["re_first"] = (0 if not (len(up_bars) or len(dn_bars)) else
                     (1 if (len(up_bars) and (not len(dn_bars) or up_bars[0] < dn_bars[0])) else -1))
    # profile on raw ticks, then shifted back to adjusted
    off = raw_offset
    pr = build_profile(p_lo - off, p_hi - off)
    f["prof"] = pr
    f["rs"] = pr.rs
    f["poc"], f["vah"], f["val"] = pr.poc_t + off, pr.vah_t + off, pr.val_t + off
    f["tail_hi_len"], f["tail_lo_len"] = pr.tail_hi_len, pr.tail_lo_len
    f["tail_hi_inner"] = pr.tail_hi_inner_t() + off if pr.tail_hi_len else np.nan
    f["tail_lo_inner"] = pr.tail_lo_inner_t() + off if pr.tail_lo_len else np.nan
    f["poor_high"], f["poor_low"] = pr.poor_high, pr.poor_low
    f["single_runs"] = [(a + off, b + off) for a, b in pr.single_runs_t()]
    f["tpo_above"], f["tpo_below"], f["tpo_dir"] = pr.tpo_above, pr.tpo_below, pr.tpo_dir
    f["rf"] = rotation_factor(p_lo, p_hi)
    f["max_width"] = pr.max_width
    f["total_tpo"] = pr.total
    vp, vl, vh = volume_va(pr, l - off, h - off, v)
    f["vpoc"], f["vval"], f["vvah"] = vp + off, vl + off, vh + off
    # P / b shape ingredients
    R = f["range"]
    mids = pr.row_mid(np.arange(pr.n_rows)) + off
    f["poc_mid"] = float(pr.row_mid(pr.poc) + off)
    f["frac_low3"] = float(pr.counts[mids < f["L"] + R / 3].sum() / pr.total) if R else np.nan
    f["frac_up3"] = float(pr.counts[mids > f["H"] - R / 3].sum() / pr.total) if R else np.nan
    f["low_per"] = int(np.flatnonzero(p_lo == f["L"])[0])
    f["high_per"] = int(np.flatnonzero(p_hi == f["H"])[0])
    f["hi_thru_C"] = int(p_hi[:3].max())
    f["lo_thru_C"] = int(p_lo[:3].min())
    f.update(spike(p_lo, p_hi, p_op, f["H"], f["L"], off))
    return f


def spike(p_lo, p_hi, p_op, H, L, off=0) -> dict:
    """Spike (p.247-252): the last 2 periods both trade beyond the VA of the earlier periods, the
    spike side's day extreme is made in them, and together they cover >= 25% of the day's range.
    Spike range: breakout period (the first of the two) open -> day extreme [C9]."""
    out = dict(spike_dir=0, spike_lo=np.nan, spike_hi=np.nan)
    n = len(p_lo)
    if n < 4 or H == L:
        return out
    early = build_profile(p_lo[:-2] - off, p_hi[:-2] - off)
    e_vah, e_val = early.vah_t + off, early.val_t + off
    l2_hi, l2_lo = p_hi[-2:], p_lo[-2:]
    cover = (l2_hi.max() - l2_lo.min()) >= 0.25 * (H - L)
    up = (l2_hi > e_vah).all() and l2_hi.max() == H and cover
    dn = (l2_lo < e_val).all() and l2_lo.min() == L and cover
    if up and not dn:
        out.update(spike_dir=1, spike_lo=int(p_op[-2]), spike_hi=int(H))
    elif dn and not up:
        out.update(spike_dir=-1, spike_lo=int(L), spike_hi=int(p_op[-2]))
    return out


# ------------------------------------------------------------------------------------------------
def opening_type(P: np.ndarray, jump, minute: np.ndarray, f: dict, prior_hi, prior_lo,
                 bal_hi, bal_lo, med_arange) -> dict:
    """Opening type from the first 30 minutes (p.63-73), precedence OD > OTD > ORR > OA [C10].

    P holds the session's path points (4 per bar). Returns the label known at 10:00 (`open_A`),
    the final label that also needs period B for Open-Drive (`open_type`), and the direction and
    reference fields the trades use."""
    out = dict(open_A="", open_type="", od_dir=0, otd_dir=0, orr_dir=0, orr_ext=np.nan,
               od_full=False)
    O, or_hi, or_lo = f["O"], f["or_hi"], f["or_lo"]
    nA = int((minute < RTH0 + 30).sum())
    nOR = int((minute < RTH0 + OR_MIN).sum())
    nAB = int((minute < RTH0 + 60).sum())
    PA = P[:4 * nA]
    post_A = P[4 * nOR:4 * nA]
    post_AB = P[4 * nOR:4 * nAB]
    a_close = P[4 * nA - 1]
    # Open-Drive
    up_brk, dn_brk = (post_A > or_hi).any(), (post_A < or_lo).any()
    if up_brk and not dn_brk:
        out["od_dir"] = 1
        out["od_full"] = not (post_AB < or_lo).any()
    elif dn_brk and not up_brk:
        out["od_dir"] = -1
        out["od_full"] = not (post_AB > or_hi).any()
    # Open-Test-Drive
    refs_up = [r for r in (prior_hi, bal_hi) if r == r and O < r + 2]
    refs_dn = [r for r in (prior_lo, bal_lo) if r == r and O > r - 2]
    otd = []
    if refs_up:
        lvl = min(refs_up) + 2
        kt = _first(PA >= lvl)
        if kt >= 0 and not (PA[4 * nOR:kt] < or_lo).any():
            kr = _first(PA[kt:] < or_lo)
            if kr >= 0 and a_close < or_lo:
                otd.append((kt, -1))
    if refs_dn:
        lvl = max(refs_dn) - 2
        kt = _first(PA <= lvl)
        if kt >= 0 and not (PA[4 * nOR:kt] > or_hi).any():
            kr = _first(PA[kt:] > or_hi)
            if kr >= 0 and a_close > or_hi:
                otd.append((kt, 1))
    if otd:
        out["otd_dir"] = min(otd)[1]
    # Open-Rejection-Reverse
    if med_arange == med_arange and med_arange > 0:
        thr = 0.25 * med_arange
        ku, kd = _first(PA - O >= thr), _first(O - PA >= thr)
        first_up = ku >= 0 and (kd < 0 or ku < kd)
        first_dn = kd >= 0 and (ku < 0 or kd < ku)
        if first_up:
            kr = _first(PA[ku:] < or_lo)
            if kr >= 0:
                out["orr_dir"], out["orr_ext"] = -1, int(PA[:ku + kr + 1].max())
        elif first_dn:
            kr = _first(PA[kd:] > or_hi)
            if kr >= 0:
                out["orr_dir"], out["orr_ext"] = 1, int(PA[:kd + kr + 1].min())
    oa = "OA-in" if (prior_lo == prior_lo and prior_lo <= O <= prior_hi) else "OA-out"
    if out["od_dir"]:
        out["open_A"] = "OD"
    elif out["otd_dir"]:
        out["open_A"] = "OTD"
    elif out["orr_dir"]:
        out["open_A"] = "ORR"
    else:
        out["open_A"] = oa
    out["open_type"] = out["open_A"] if (out["open_A"] != "OD" or out["od_full"]) else oa
    if out["open_type"] == "OD":
        out["open_type"] = "OD"
    return out


def _first(mask: np.ndarray) -> int:
    return int(mask.argmax()) if mask.any() else -1


def day_type(f: dict, ib_narrow: bool, ib_wide: bool) -> str:
    """Day type at the close (p.19-31), with precedence where the spec's types overlap [C11]."""
    R = f["range"]
    if f["re_up"] and f["re_dn"]:
        ext = f["C"] >= f["H"] - 0.15 * R or f["C"] <= f["L"] + 0.15 * R
        return "Neutral-Extreme" if ext else "Neutral-Center"
    if f["re_up"] or f["re_dn"]:
        up = f["re_up"]
        dd_sp = any((b > f["ib_hi"]) if up else (a < f["ib_lo"]) for a, b in f["single_runs"])
        if ib_narrow and dd_sp:
            return "DD-Trend"
        near_ext = (f["O"] - f["L"] <= 0.1 * R) or (f["H"] - f["O"] <= 0.1 * R)
        if near_ext and f["max_width"] <= 5:
            return "Trend"
        if R <= 2 * f["ib_w"]:
            return "Normal-Variation"
        return "Other-RE1"
    if ib_narrow:
        return "Nontrend"
    if ib_wide:
        return "Normal"
    return "Other-noRE"


def balance_run(val: np.ndarray, vah: np.ndarray, t: int) -> int:
    """Length of the longest run of sessions ending at t whose VAs share a common overlap."""
    lo, hi, k = -np.inf, np.inf, 0
    for i in range(t, -1, -1):
        lo, hi = max(lo, val[i]), min(hi, vah[i])
        if lo > hi:
            break
        k += 1
    return k


def value_rel(val, vah) -> np.ndarray:
    """+1 higher value, -1 lower value, 0 otherwise, vs the prior session [C12]."""
    out = np.zeros(len(val), dtype=int)
    dv, dh = np.diff(val), np.diff(vah)
    hi = (dv >= 0) & (dh >= 0) & ((dv > 0) | (dh > 0))
    lo = (dv <= 0) & (dh <= 0) & ((dv < 0) | (dh < 0))
    out[1:] = np.where(hi, 1, np.where(lo, -1, 0))
    return out


def cross_session(S: pd.DataFrame, bars: pd.DataFrame, feats: list[dict]) -> pd.DataFrame:
    """Add multi-session features. S: sessions table (b0, b1, on_hi_t, on_lo_t ...)."""
    n = len(feats)
    col = lambda k: np.array([f[k] for f in feats], dtype=float)
    D = pd.DataFrame({k: col(k) for k in (
        "O", "H", "L", "C", "or_hi", "or_lo", "a_hi", "a_lo", "ib_hi", "ib_lo", "ib_w", "range",
        "poc", "vah", "val", "vpoc", "vval", "vvah", "rs", "tail_hi_len", "tail_lo_len",
        "tail_hi_inner", "tail_lo_inner", "tpo_above", "tpo_below", "tpo_dir", "rf", "max_width",
        "total_tpo", "poc_mid", "frac_low3", "frac_up3", "low_per", "high_per", "hi_thru_C",
        "lo_thru_C", "spike_dir", "spike_lo", "spike_hi", "n_per", "re_up_per", "re_dn_per",
        "re_first")})
    for k in ("re_up", "re_dn", "poor_high", "poor_low"):
        D[k] = [bool(f[k]) for f in feats]
    D["single_runs"] = [f["single_runs"] for f in feats]
    D["date"] = S["date"].to_numpy()
    D["early_close"] = S["early_close"].to_numpy()
    D["on_hi"], D["on_lo"] = S["on_hi_t"].to_numpy(), S["on_lo_t"].to_numpy()
    D["a_range"] = D["a_hi"] - D["a_lo"]
    D["va_w"] = D["vah"] - D["val"]
    D["va_mid"] = (D["vah"] + D["val"]) / 2
    prev = D.shift(1)
    for k in ("H", "L", "C", "poc", "vah", "val", "vpoc", "vval", "vvah", "ib_w"):
        D["p_" + k] = prev[k]
    med20 = lambda s: s.shift(1).rolling(20, min_periods=20).median()
    D["med20_ib"] = med20(D["ib_w"])
    D["med20_arange"] = med20(D["a_range"])
    D["med20_range"] = med20(D["range"])
    D["ib_ratio"] = D["ib_w"] / D["med20_ib"]
    D["ib_narrow"] = D["ib_ratio"] < IB_NARROW
    D["ib_wide"] = D["ib_ratio"] > IB_WIDE
    tr = np.maximum(D["H"], D["C"].shift(1)) - np.minimum(D["L"], D["C"].shift(1))
    tr.iloc[0] = D["range"].iloc[0]
    D["atr20"] = tr.rolling(20, min_periods=20).mean()
    D["va_w_q33"] = D["va_w"].rolling(20, min_periods=20).quantile(1 / 3)
    D["va_narrow"] = D["va_w"] <= D["va_w_q33"]
    D["mig10"] = np.sign(D["va_mid"] - D["va_mid"].shift(10))
    # open location vs prior VA / range: 0 inside VA, 1 outside VA inside range, 2 outside range
    O = D["O"]
    inside_va = (O >= D["p_val"]) & (O <= D["p_vah"])
    inside_rng = (O >= D["p_L"]) & (O <= D["p_H"])
    D["open_loc"] = np.where(D["p_val"].isna(), np.nan, np.where(inside_va, 0, np.where(inside_rng, 1, 2)))
    D["open_side"] = np.where(O > D["p_vah"], 1, np.where(O < D["p_val"], -1, 0))
    D["vrel"] = value_rel(D["val"].to_numpy(), D["vah"].to_numpy())
    D["vvrel"] = value_rel(D["vval"].to_numpy(), D["vvah"].to_numpy())
    # balance areas as of the close
    val, vah = D["val"].to_numpy(), D["vah"].to_numpy()
    runs = np.array([balance_run(val, vah, t) for t in range(n)])
    D["bal_run"] = runs
    for m in (3, 5):
        hi = np.full(n, np.nan); lo = np.full(n, np.nan)
        for t in range(n):
            if runs[t] >= m:
                hi[t] = D["H"].iloc[t - runs[t] + 1:t + 1].max()
                lo[t] = D["L"].iloc[t - runs[t] + 1:t + 1].min()
        D[f"bal{m}_hi"], D[f"bal{m}_lo"] = hi, lo
    # opening types
    Pall = bar_points(bars["o"], bars["h"], bars["l"], bars["c"])
    minute = bars["minute"].to_numpy()
    rows = []
    for t in range(n):
        b0, b1 = int(S["b0"].iloc[t]), int(S["b1"].iloc[t])
        if t == 0:
            rows.append(dict(open_A="", open_type="", od_dir=0, otd_dir=0, orr_dir=0, orr_ext=np.nan, od_full=False))
            continue
        rows.append(opening_type(Pall[4 * b0:4 * b1], None, minute[b0:b1], feats[t],
                                 D["H"].iloc[t - 1], D["L"].iloc[t - 1],
                                 D["bal3_hi"].iloc[t - 1], D["bal3_lo"].iloc[t - 1],
                                 D["med20_arange"].iloc[t]))
    OT = pd.DataFrame(rows)
    for k in OT.columns:
        D[k] = OT[k].to_numpy()
    D["day_type"] = [day_type(feats[t], bool(D["ib_narrow"].iloc[t]), bool(D["ib_wide"].iloc[t])) for t in range(n)]
    # initiative / responsive vs prior VA [C13]
    pval, pvah = D["p_val"], D["p_vah"]
    tail_lo_mid = (D["L"] + D["tail_lo_inner"]) / 2
    tail_hi_mid = (D["H"] + D["tail_hi_inner"]) / 2
    has_lo, has_hi = D["tail_lo_len"] > 0, D["tail_hi_len"] > 0
    D["tail_dir"] = np.where(has_lo & ~has_hi, 1, np.where(has_hi & ~has_lo, -1, 0))
    D["tail_init"] = np.where(D["tail_dir"] == 1, tail_lo_mid >= pval,
                              np.where(D["tail_dir"] == -1, tail_hi_mid <= pvah, False))
    D["re_dir"] = np.where(D["re_up"] & ~D["re_dn"], 1, np.where(D["re_dn"] & ~D["re_up"], -1, 0))
    re_up_mid, re_dn_mid = (D["ib_hi"] + D["H"]) / 2, (D["ib_lo"] + D["L"]) / 2
    D["re_init"] = np.where(D["re_dir"] == 1, re_up_mid >= pval,
                            np.where(D["re_dir"] == -1, re_dn_mid <= pvah, False))
    D["tpo_init"] = np.where(D["tpo_dir"] == 1, D["poc"] >= pval,
                             np.where(D["tpo_dir"] == -1, D["poc"] <= pvah, False))
    same = (D["tail_dir"] != 0) & (D["tail_dir"] == D["re_dir"]) & (D["re_dir"] == D["tpo_dir"]) & pval.notna()
    D["three_i"] = np.where(same & D["tail_init"] & D["re_init"] & D["tpo_init"], D["re_dir"], 0)
    D["two_i_one_r"] = np.where(same & ~D["tail_init"].astype(bool) & D["re_init"] & D["tpo_init"], D["re_dir"], 0)
    # P / b shapes (p.123-128) [C14]
    R = D["range"]
    lower2 = (pd.Series(D["vrel"]).shift(1) == -1) & (pd.Series(D["vrel"]).shift(2) == -1)
    higher2 = (pd.Series(D["vrel"]).shift(1) == 1) & (pd.Series(D["vrel"]).shift(2) == 1)
    p_shape = ((D["poc_mid"] >= D["L"] + 2 * R / 3) & (D["frac_low3"] <= 0.20) & (D["low_per"] <= 2)
               & (D["hi_thru_C"] - D["L"] > 0.5 * R))
    b_shape = ((D["poc_mid"] <= D["H"] - 2 * R / 3) & (D["frac_up3"] <= 0.20) & (D["high_per"] <= 2)
               & (D["H"] - D["lo_thru_C"] > 0.5 * R))
    D["p_shape"] = p_shape & lower2.to_numpy()
    D["b_shape"] = b_shape & higher2.to_numpy()
    # overnight inventory
    onr = D["on_hi"] - D["on_lo"]
    inv_long = (O >= D["on_hi"] - 0.2 * onr) & (O > D["p_C"])
    inv_short = (O <= D["on_lo"] + 0.2 * onr) & (O < D["p_C"])
    D["inventory"] = np.where((onr > 0) & inv_long, 1, np.where((onr > 0) & inv_short, -1, 0))
    return D


def acceptance_period(p_lo, p_hi, lo: float, hi: float, start: int = 0, n: int = 2) -> int:
    """Acceptance (p.75, 244): the area [lo, hi] is traded in >= n consecutive periods. Returns the
    period at whose end acceptance is confirmed (first such), or -1 (rejection)."""
    p_lo, p_hi = np.asarray(p_lo), np.asarray(p_hi)
    inside = (p_hi >= lo) & (p_lo <= hi)
    run = 0
    for j in range(start, len(p_lo)):
        run = run + 1 if inside[j] else 0
        if run >= n:
            return j
    return -1
