"""Phase 2 EXPAND families: the confluence / context evidence discretionary users of the levels say
they stack on top of them - market regime, prior-week market profile (POC / value area), RSI
divergence, basic support / resistance, a composite evidence score - plus the market-profile levels
traded on their own (MPALONE), which tells whether any edge belongs to the profile or to the v42
levels. Same machinery and screens as families.py: full F0 grid per variant, real levels + four
placebo shifts, family screen = level specificity. Features: features.py (no look-ahead).
"""
from __future__ import annotations

import sys

import numpy as np

import families as FM
from families import _base, _is_long, run_round
from features import build
from grid import BOUNCE, BREAKOUT, D_PIERCE, D_MAX, STYLES

MPL = ["PPOC_UP", "PPOC_DN", "PVAH_UP", "PVAH_DN", "PVAL_UP", "PVAL_DN"]
MPKEY = {"PPOC": "pPOC", "PVAH": "pVAH", "PVAL": "pVAL"}


def _dist(P, arrs, sigma):
    d = np.full(len(P), np.inf)
    for a in arrs:
        d = np.fmin(d, np.abs(P - a))
    return d / sigma


# ------------------------------------------------------------------ regime
def regime(kind, mode):
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, bar_ok = _base(b)
        lg = _is_long(cell, od_nat, flip)
        if kind == "bear20":
            dd = F["dd252"]
            m = (dd <= 0.20) if lg else np.ones(len(dd), bool)
            return allow & np.isfinite(dd) & m, bar_ok, None
        r = F[{"200": "reg200", "5020": "reg5020", "strong": "regstrong"}[kind]]
        if mode == "align":
            m = (r > 0) if lg else (r < 0)
        else:                                   # avoid the opposite STRONG regime only
            m = (r != -1) if lg else (r != 1)
        return allow & np.isfinite(r) & m, bar_ok, None
    return f


# ------------------------------------------------------------------ market profile
def mp_conf(keys, tol):
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, bar_ok = _base(b)
        dist = _dist(P, [F[k] for k in keys], b.sigma)
        return allow & np.isfinite(dist) & (dist <= tol), bar_ok, None
    return f


def open_va(mode):
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, bar_ok = _base(b)
        vah, val, wo = F["pVAH"], F["pVAL"], b.wo
        lg = _is_long(cell, od_nat, flip)
        above, below = wo > vah, wo < val
        inside = ~above & ~below
        m = {"with": above if lg else below, "against": below if lg else above, "in": inside}[mode]
        return allow & np.isfinite(vah) & m, bar_ok, None
    return f


def tgt_poc():
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        return allow, bar_ok, None
    return f


def _tnext_poc(b, cell, P):
    return build(b)["pPOC"]


# ------------------------------------------------------------------ RSI divergence
def rsi_div(tf):
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, _ = _base(b)
        lg = _is_long(cell, od_nat, flip)
        key = ("div4_" if tf == "4h" else "divD_") + ("bull" if lg else "bear")
        return allow, F[key].copy(), None
    return f


# ------------------------------------------------------------------ support / resistance
def sr_pdhl(tol):
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, _ = _base(b)
        Pm = P[:, None]
        d = np.fmin(np.abs(Pm - F["pdh"]), np.abs(Pm - F["pdl"])) / b.sigma[:, None]
        return allow, np.nan_to_num(d, nan=np.inf) <= tol, None
    return f


def sr_swing(tol):
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, bar_ok = _base(b)
        piv = np.hstack([F["piv_hi"], F["piv_lo"]])
        d = np.nanmin(np.abs(piv - P[:, None]), axis=1, initial=np.inf) / b.sigma
        return allow & (d <= tol), bar_ok, None
    return f


# ------------------------------------------------------------------ composite evidence score
def score(k, tol=0.15):
    """+1 each: regime (close vs SMA200) agrees; level within tol of prior-week POC / VAH / VAL;
    level within tol of an S/R (daily swing pivot, prior-week high / low, prior-day high / low);
    RSI divergence (4h) in the trade direction at the bar before entry; WO on the trade's side of
    the prior-week POC. Entry bar allowed when the count >= k."""
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, _ = _base(b)
        lg = _is_long(cell, od_nat, flip)
        sg = b.sigma
        r = F["reg200"]
        s1 = np.where(np.isfinite(r), (r > 0) if lg else (r < 0), False)
        s2 = _dist(P, [F["pPOC"], F["pVAH"], F["pVAL"]], sg) <= tol
        piv = np.hstack([F["piv_hi"], F["piv_lo"], b.weeks[["pWH", "pWL"]].values])
        s3w = np.nanmin(np.abs(piv - P[:, None]), axis=1, initial=np.inf) / sg <= tol
        Pm = P[:, None]
        s3b = np.nan_to_num(np.fmin(np.abs(Pm - F["pdh"]), np.abs(Pm - F["pdl"])) / sg[:, None], nan=np.inf) <= tol
        s4 = F["div4_bull"] if lg else F["div4_bear"]
        s5 = (b.wo > F["pPOC"]) if lg else (b.wo < F["pPOC"])
        wk = (s1.astype(int) + s2.astype(int) + s5.astype(int))[:, None]
        tot = wk + (s3w[:, None] | s3b).astype(int) + s4.astype(int)
        return allow, tot >= k, None
    return f


# ------------------------------------------------------------------ market-profile levels alone
def mp_cells():
    out = []
    for name in MPL:
        for side in (BOUNCE, BREAKOUT):
            for unit in ("ATR", "SIG"):
                for d in D_PIERCE:
                    for style in STYLES:
                        if side == BOUNCE and style > 0:
                            for D in D_MAX:
                                if D >= d:
                                    out.append((name, side, unit, d, style, D))
                        else:
                            out.append((name, side, unit, d, style, np.inf))
    return out


def mp_od(name):
    return 1 if name.endswith("_UP") else -1


def mp_price(b, name, scale, shift):
    F = build(b)
    P = F[MPKEY[name.split("_")[0]]].copy()
    od = mp_od(name)
    P[~(od * (P - b.wo) / b.sigma >= 0.05)] = np.nan       # only weeks where it sits on that side of WO
    return P


def mp_struct(b, name, side, scale, shift):
    nan = np.full(len(b.wo), np.nan)
    return nan, nan


P2R1 = {
    "REG200_align": (regime("200", "align"), False),
    "REG5020_align": (regime("5020", "align"), False),
    "REGSTRONG_avoid": (regime("strong", "avoid"), False),
    "BEAR20_avoid": (regime("bear20", "avoid"), False),
    "MP_POC10": (mp_conf(["pPOC"], 0.10), False),
    "MP_VA10": (mp_conf(["pVAH", "pVAL"], 0.10), False),
    "MP_ANY20": (mp_conf(["pPOC", "pVAH", "pVAL"], 0.20), False),
    "OPENVA_with": (open_va("with"), False),
    "OPENVA_in": (open_va("in"), False),
    "OPENVA_against": (open_va("against"), False),
    "RSIDIV_4h": (rsi_div("4h"), False),
    "RSIDIV_D": (rsi_div("D"), False),
    "SR_PDHL10": (sr_pdhl(0.10), False),
    "SR_SWING10": (sr_swing(0.10), False),
    "SCORE2": (score(2), False),
    "SCORE3": (score(3), False),
    "TGT_POC": (tgt_poc(), False, dict(t_vals=np.array([]), t_names=[], tnext_fn=_tnext_poc)),
    "MPALONE": (tgt_poc(), False, dict(cells=mp_cells, price_fn=mp_price, od_fn=mp_od, struct_fn=mp_struct)),
}
FM.REGISTRY.update(P2R1)


# ------------------------------------------------------------------ round 2 (REFINE + EXPAND)
def open_rel(mode):
    """REFINE of OPENVA_against: how far below (longs) / above (shorts) the prior week the week opens."""
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, bar_ok = _base(b)
        lg = _is_long(cell, od_nat, flip)
        wo, sg = b.wo, b.sigma
        if mode == "poc":
            m = (wo < F["pPOC"]) if lg else (wo > F["pPOC"])
            ok = np.isfinite(F["pPOC"])
        elif mode == "far":
            m = (wo < F["pVAL"] - 0.10 * sg) if lg else (wo > F["pVAH"] + 0.10 * sg)
            ok = np.isfinite(F["pVAL"])
        else:                                   # beyond the prior week's low / high
            m = (wo < b.weeks["pWL"].values) if lg else (wo > b.weeks["pWH"].values)
            ok = np.isfinite(b.weeks["pWL"].values)
        return allow & ok & m, bar_ok, None
    return f


def _is_long_cell(cell):
    from common import UPPER
    od = 1 if cell[0] in UPPER else -1
    return (-od if cell[1] == BOUNCE else od) > 0


def _tnext_va(b, cell, P):
    F = build(b)
    return F["pVAH"] if _is_long_cell(cell) else F["pVAL"]


def poc_naked():
    """Entries only while the prior-week POC is still untouched this week (target = that POC)."""
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, _ = _base(b)
        poc = F["pPOC"][:, None]
        touch = np.nan_to_num((b.L <= poc) & (b.H >= poc), nan=False).astype(bool)
        idx = np.arange(b.O.shape[1])[None, :]
        first = np.where(touch.any(1), touch.argmax(1), 10 ** 6)[:, None]
        return allow & np.isfinite(F["pPOC"]), idx <= first, None
    return f


def mp80():
    """Weekly 80% rule: the week opens outside the prior value area and later posts two consecutive
    4h closes back inside it; only setups in the direction of the traverse, searched from then on."""
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, bar_ok = _base(b)
        lg = _is_long(cell, od_nat, flip)
        vah, val = F["pVAH"][:, None], F["pVAL"][:, None]
        inside = np.nan_to_num((b.C >= val) & (b.C <= vah), nan=False).astype(bool)
        two = inside & np.c_[np.zeros((inside.shape[0], 1), bool), inside[:, :-1]]
        fb = np.where(two.any(1), two.argmax(1), -1)
        op_ok = (b.wo < F["pVAL"]) if lg else (b.wo > F["pVAH"])
        sb = np.where((fb >= 0) & op_ok, fb + 1, -1).astype(np.int64)
        return allow, bar_ok, sb
    return f


def reg_and_mp(tol=0.20):
    rg, mp = regime("200", "align"), mp_conf(["pPOC", "pVAH", "pVAL"], tol)
    def f(b, cell, P, od_nat, flip=False):
        a1, _, _ = rg(b, cell, P, od_nat, flip)
        a2, bo, _ = mp(b, cell, P, od_nat, flip)
        return a1 & a2, bo, None
    return f


def rsi_ext(lo=35.0, hi=65.0):
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, _ = _base(b)
        r = F["rsi4_prev"]
        m = (r < lo) if _is_long(cell, od_nat, flip) else (r > hi)
        return allow, np.nan_to_num(m, nan=False).astype(bool), None
    return f


def trend20():
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, _ = _base(b)
        t = F["trend20"]
        m = (t > 0) if _is_long(cell, od_nat, flip) else (t < 0)
        return allow, np.nan_to_num(m, nan=False).astype(bool), None
    return f


P2R2 = {
    "OVA_ag_poc": (open_rel("poc"), False),
    "OVA_ag_far": (open_rel("far"), False),
    "OVA_ag_pwl": (open_rel("pwl"), False),
    "MP_ANY15": (mp_conf(["pPOC", "pVAH", "pVAL"], 0.15), False),
    "MP_ANY30": (mp_conf(["pPOC", "pVAH", "pVAL"], 0.30), False),
    "MP_POC20": (mp_conf(["pPOC"], 0.20), False),
    "MP_VA20": (mp_conf(["pVAH", "pVAL"], 0.20), False),
    "TGT_VA": (tgt_poc(), False, dict(t_vals=np.array([]), t_names=[], tnext_fn=_tnext_va)),
    "TGT_POC_naked": (poc_naked(), False, dict(t_vals=np.array([]), t_names=[], tnext_fn=_tnext_poc)),
    "MP80": (mp80(), False),
    "MP4W20": (mp_conf(["cPOC4"], 0.20), False),
    "REG200_MP20": (reg_and_mp(0.20), False),
    "RSI_EXT": (rsi_ext(), False),
    "TREND_D20": (trend20(), False),
}
FM.REGISTRY.update(P2R2)


# ------------------------------------------------------------------ round 3 (REFINE + EXPAND)
def mp_conf_tgt_va(tol):
    base = mp_conf(["pPOC", "pVAH", "pVAL"], tol)
    return base


def in_va(mode):
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, bar_ok = _base(b)
        inside = (P >= F["pVAL"]) & (P <= F["pVAH"])
        m = inside if mode == "in" else ~inside
        return allow & np.isfinite(F["pVAL"]) & m, bar_ok, None
    return f


def node(kind):
    from features import tpo_density

    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, bar_ok = _base(b)
        dens = tpo_density(F, P)
        m = (dens <= 0.30) if kind == "LVN" else (dens >= 0.70)
        return allow & np.isfinite(dens) & m, bar_ok, None
    return f


P2R3 = {
    "MP_ANY25": (mp_conf(["pPOC", "pVAH", "pVAL"], 0.25), False),
    "MP_ANY40": (mp_conf(["pPOC", "pVAH", "pVAL"], 0.40), False),
    "MP_ANY50": (mp_conf(["pPOC", "pVAH", "pVAL"], 0.50), False),
    "MP_VA30": (mp_conf(["pVAH", "pVAL"], 0.30), False),
    "MP_VA40": (mp_conf(["pVAH", "pVAL"], 0.40), False),
    "MP30_TGT_VA": (mp_conf_tgt_va(0.30), False, dict(t_vals=np.array([]), t_names=[], tnext_fn=_tnext_va)),
    "MP_IN_VA": (in_va("in"), False),
    "MP_OUT_VA": (in_va("out"), False),
    "LVN": (node("LVN"), False),
    "HVN": (node("HVN"), False),
    "MPM20": (mp_conf(["mPOC", "mVAH", "mVAL"], 0.20), False),
}
FM.REGISTRY.update(P2R3)


# ------------------------------------------------------------------ round 4 (EXPAND)
def migration(mode):
    """Value migration: prior-week POC vs the POC two weeks back (moved >= 0.10 sigma)."""
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, bar_ok = _base(b)
        lg = _is_long(cell, od_nat, flip)
        mv = (F["pPOC"] - F["ppPOC"]) / b.sigma
        up, dn = mv >= 0.10, mv <= -0.10
        m = (up if lg else dn) if mode == "with" else (dn if lg else up)
        return allow & np.isfinite(mv) & m, bar_ok, None
    return f


def balance(mode):
    """Balance = the prior two weekly value areas overlap by >= 50% of the narrower one."""
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, bar_ok = _base(b)
        o = F["va_overlap"]
        m = (o >= 0.5) if mode == "balance" else (o < 0.5)
        return allow & np.isfinite(o) & m, bar_ok, None
    return f


def dev_poc(mode):
    """Developing weekly POC at the close before entry: 'below' = long only when the last close is
    below it (short only above) - buying under developing value; 'above' = the reverse."""
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, _ = _base(b)
        lg = _is_long(cell, od_nat, flip)
        cp, dp = F["close_prev"], F["devPOC_prev"]
        below = cp < dp
        above = cp > dp
        m = (below if lg else above) if mode == "below" else (above if lg else below)
        return allow, np.nan_to_num(m, nan=False).astype(bool), None
    return f


P2R4 = {
    "VAMIG_with": (migration("with"), False),
    "VAMIG_against": (migration("against"), False),
    "BALANCE": (balance("balance"), False),
    "TRENDWK": (balance("trend"), False),
    "DEVPOC_below": (dev_poc("below"), False),
    "DEVPOC_above": (dev_poc("above"), False),
    "MPM15": (mp_conf(["mPOC", "mVAH", "mVAL"], 0.15), False),
    "MPM30": (mp_conf(["mPOC", "mVAH", "mVAL"], 0.30), False),
    "MPM_POC20": (mp_conf(["mPOC"], 0.20), False),
    "MP_VAH30": (mp_conf(["pVAH"], 0.30), False),
    "MP_VAL30": (mp_conf(["pVAL"], 0.30), False),
    "MPWM20": (None, False),
}
def mp_week_and_month(tol=0.20):
    w = mp_conf(["pPOC", "pVAH", "pVAL"], tol)
    m = mp_conf(["mPOC", "mVAH", "mVAL"], tol)
    def f(b, cell, P, od_nat, flip=False):
        a1, bo, _ = w(b, cell, P, od_nat, flip)
        a2, _, _ = m(b, cell, P, od_nat, flip)
        return a1 & a2, bo, None
    return f


P2R4["MPWM20"] = (mp_week_and_month(0.20), False)
FM.REGISTRY.update(P2R4)


# ------------------------------------------------------------------ round 5 (EXPAND)
def accept_va():
    """Acceptance: the last 4h close before entry is already beyond prior value in the trade direction."""
    def f(b, cell, P, od_nat, flip=False):
        F = build(b)
        allow, _ = _base(b)
        lg = _is_long(cell, od_nat, flip)
        cp = F["close_prev"]
        m = (cp > F["pVAH"][:, None]) if lg else (cp < F["pVAL"][:, None])
        return allow, np.nan_to_num(m, nan=False).astype(bool), None
    return f


def open_in_and_va(tol=0.30):
    a_ = open_va("in")
    m_ = mp_conf(["pVAH", "pVAL"], tol)
    def f(b, cell, P, od_nat, flip=False):
        x1, bo, _ = a_(b, cell, P, od_nat, flip)
        x2, _, _ = m_(b, cell, P, od_nat, flip)
        return x1 & x2, bo, None
    return f


def prior_close_quartile():
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        w = b.weeks
        pos = (w.pWC - w.pWL) / (w.pWH - w.pWL)
        lg = _is_long(cell, od_nat, flip)
        m = (pos >= 0.75) if lg else (pos <= 0.25)
        return allow & np.isfinite(pos.values) & m.values, bar_ok, None
    return f


def multi_poc(tol=0.25):
    return mp_conf(["pPOC", "ppPOC"], tol)


def pwhl(tol=0.30):
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        d = _dist(P, [b.weeks["pWH"].values, b.weeks["pWL"].values], b.sigma)
        return allow & np.isfinite(d) & (d <= tol), bar_ok, None
    return f


P2R5 = {
    "ACCEPT_VA": (accept_va(), False),
    "OPENIN_VA30": (open_in_and_va(0.30), False),
    "PCLOSE_Q": (prior_close_quartile(), False),
    "POC2W25": (multi_poc(0.25), False),
    "PWHL30": (pwhl(0.30), False),
    # REFINE: extent of the profile-confluence region
    "MPM25": (mp_conf(["mPOC", "mVAH", "mVAL"], 0.25), False),
    "MPM_VA30": (mp_conf(["mVAH", "mVAL"], 0.30), False),
    "MP_VAH20": (mp_conf(["pVAH"], 0.20), False),
    "MP_VAH40": (mp_conf(["pVAH"], 0.40), False),
}
FM.REGISTRY.update(P2R5)

if __name__ == "__main__":
    rnd = sys.argv[1]
    if rnd == "p2round1":
        run_round(list(P2R1), "p2round1")
    elif rnd == "p2round2":
        run_round(list(P2R2), "p2round2")
    elif rnd == "p2round3":
        run_round(list(P2R3), "p2round3")
    elif rnd == "p2round4":
        run_round(list(P2R4), "p2round4")
    elif rnd == "p2round5":
        run_round(list(P2R5), "p2round5")
