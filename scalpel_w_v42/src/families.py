"""EXPAND hypothesis families. Each variant = the full F0 pierce grid run under a filter (week
mask, bar mask and/or a per-week start bar), on the real levels and on the four placebo shifts.

A family variant passes the IN-SAMPLE screen when
  (a) at least one config passes the config screen (screen.py: n, PF, breadth, plateau), AND
  (b) level specificity: the real-level search beats at least 3 of its 4 placebo-level searches on
      BOTH the number of screen passers and the mean expectancy of its top-10 configs.
(b) is needed because selection makes any single config beat its own placebo in-sample.
"""
from __future__ import annotations

import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

from common import LINEAGE, OUT
from data import load_all
from grid import BOUNCE, cells, run_grid
from screen import screen

SHIFTS = [0.0, -0.30, -0.15, 0.15, 0.30]
_B = None


def _book():
    global _B
    if _B is None:
        _B = load_all()
    return _B


def _is_long(cell, od_nat, flip):
    side = cell[1]
    od = -od_nat if flip else od_nat
    dirn = -od if side == BOUNCE else od
    return dirn > 0


def _base(b):
    return np.ones(len(b.wo), np.bool_), np.ones(b.O.shape, np.bool_)


def first_bar(cond):
    """cond [nW, MAXB] bool -> first True index per week or -1."""
    has = cond.any(1)
    return np.where(has, cond.argmax(1), -1)


# ------------------------------------------------------------------ variant builders
def trend(n, mode):
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        sma = b.weeks["WC"].shift(1).rolling(n).mean().values
        up = b.wo > sma
        ok = np.isfinite(sma)
        lg = _is_long(cell, od_nat, flip)
        want = up if (lg == (mode == "with")) else ~up
        return allow & ok & want, bar_ok, None
    return f


def prior_dm(th, mode):
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        dm = np.abs(b.weeks["pWC"].values - b.weeks["pWO"].values) / b.sigma
        m = dm < th if mode == "lt" else dm >= th
        return allow & np.isfinite(dm) & m, bar_ok, None
    return f


def session(hours):
    def f(b, cell, P, od_nat, flip=False):
        allow, _ = _base(b)
        return allow, np.isin(b.HR, hours), None
    return f


def dow(days):
    def f(b, cell, P, od_nat, flip=False):
        allow, _ = _base(b)
        return allow, np.isin(b.DOW, days), None
    return f


def vol(mode):
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        r = pd.Series(b.atr / b.sigma)
        med = r.shift(1).rolling(52, min_periods=20).median().values
        m = (r.values < med) if mode == "low" else (r.values >= med)
        return allow & np.isfinite(med) & m, bar_ok, None
    return f


def gap(mode, th=0.10):
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        g = (b.wo - b.weeks["pWC"].values) / b.sigma
        lg = _is_long(cell, od_nat, flip)
        against = (g < -th) if lg else (g > th)
        withg = (g > th) if lg else (g < -th)
        return allow & (against if mode == "against" else withg), bar_ok, None
    return f


def wo_crossed(th=0.10):
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        x = th * b.sigma[:, None]
        cond = (b.H >= b.wo[:, None] + x) if od_nat < 0 else (b.L <= b.wo[:, None] - x)
        fb = first_bar(np.nan_to_num(cond, nan=False).astype(bool))
        sb = np.where(fb >= 0, fb + 1, -1)
        return allow, bar_ok, sb.astype(np.int64)
    return f


def second_touch(reset=0.25):
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        Pm = P[:, None]
        touch = (b.H > Pm) if od_nat > 0 else (b.L < Pm)
        touch = np.nan_to_num(touch, nan=False).astype(bool)
        i = first_bar(touch)
        x = reset * b.sigma[:, None]
        away = (b.L <= Pm - x) if od_nat > 0 else (b.H >= Pm + x)
        away = np.nan_to_num(away, nan=False).astype(bool)
        idx = np.arange(b.O.shape[1])[None, :]
        away &= idx > i[:, None]
        r = first_bar(away)
        sb = np.where((i >= 0) & (r >= 0), r + 1, -1)
        return allow, bar_ok, sb.astype(np.int64)
    return f


def monthly(mode, tol=0.25):
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        M = np.vstack([v for v in b.mlev.values()])        # [nM, nW]
        dist = np.nanmin(np.abs(M - P[None, :]), 0) / b.sigma
        m = dist < tol if mode == "conf" else dist >= tol
        return allow & np.isfinite(dist) & m, bar_ok, None
    return f


def retest(ext=0.25):
    def f(b, cell, P, od_nat, flip=True):
        allow, bar_ok = _base(b)
        Pm = P[:, None]
        x = ext * b.sigma[:, None]
        cond = (b.H >= Pm + x) if od_nat > 0 else (b.L <= Pm - x)
        fb = first_bar(np.nan_to_num(cond, nan=False).astype(bool))
        sb = np.where(fb >= 0, fb + 1, -1)
        return allow, bar_ok, sb.astype(np.int64)
    return f


def hold():
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        return allow, bar_ok, None
    return f


def first_bar_dir(mode):
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        up = b.C[:, 0] > b.wo
        dn = b.C[:, 0] < b.wo
        lg = _is_long(cell, od_nat, flip)
        withd = up if lg else dn
        agst = dn if lg else up
        m = withd if mode == "with" else agst
        return allow & m, bar_ok, np.ones(len(b.wo), np.int64)
    return f


def prior_box(mode):
    from data import weekly_levels
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        pw = b.weeks["pWO"].values
        pl = weekly_levels(b.tk, pw)
        pwc = b.weeks["pWC"].values
        strong = pwc >= pl["GB_BOT"]
        weak = pwc <= pl["RB_TOP"]
        lg = _is_long(cell, od_nat, flip)
        if mode == "with":
            m = strong if lg else weak
        elif mode == "against":
            m = weak if lg else strong
        else:
            m = ~strong & ~weak
        return allow & np.isfinite(pw) & m, bar_ok, None
    return f


def week_half(mode):
    def f(b, cell, P, od_nat, flip=False):
        allow, _ = _base(b)
        idx = np.arange(b.O.shape[1])[None, :].repeat(len(b.wo), 0)
        return allow, (idx < 15) if mode == "early" else (idx >= 15), None
    return f


def prior_hl(mode, tol=0.15):
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        d1 = np.abs(P - b.weeks["pWH"].values) / b.sigma
        d2 = np.abs(P - b.weeks["pWL"].values) / b.sigma
        dist = np.fmin(d1, d2)
        m = dist < tol if mode == "conf" else dist >= tol
        return allow & np.isfinite(dist) & m, bar_ok, None
    return f


def month_week(mode):
    def f(b, cell, P, od_nat, flip=False):
        allow, bar_ok = _base(b)
        mth = b.weeks["month"].values
        first = np.r_[True, mth[1:] != mth[:-1]]
        return allow & (first if mode == "first" else ~first), bar_ok, None
    return f


ROUND2 = {
    "HOLD": (hold(), False, dict(t_vals=[1e6], t_names=["HOLD"])),
    "FIRSTBAR_with": (first_bar_dir("with"), False),
    "FIRSTBAR_against": (first_bar_dir("against"), False),
    "PRIORBOX_with": (prior_box("with"), False),
    "PRIORBOX_against": (prior_box("against"), False),
    "PRIORBOX_in": (prior_box("in"), False),
    "EARLY_WEEK": (week_half("early"), False),
    "LATE_WEEK": (week_half("late"), False),
    "PWHL_CONF": (prior_hl("conf"), False),
    "PWHL_NONE": (prior_hl("none"), False),
    "MONTH_FIRSTWEEK": (month_week("first"), False),
    "MONTH_REST": (month_week("rest"), False),
}

ROUND1 = {
    "TREND10_with": (trend(10, "with"), False),
    "TREND10_counter": (trend(10, "counter"), False),
    "DM40_lt": (prior_dm(0.40, "lt"), False),
    "DM40_ge": (prior_dm(0.40, "ge"), False),
    "RTH": (session([6, 10, 14]), False),
    "ON": (session([18, 22, 2]), False),
    "DOW_MonTue": (dow([0, 1]), False),
    "DOW_WedThu": (dow([2, 3]), False),
    "DOW_Fri": (dow([4]), False),
    "VOL_low": (vol("low"), False),
    "VOL_high": (vol("high"), False),
    "GAP_against": (gap("against"), False),
    "GAP_with": (gap("with"), False),
    "WO_crossed_first": (wo_crossed(0.10), False),
    "TOUCH2": (second_touch(0.25), False),
    "MCONF": (monthly("conf"), False),
    "MNONE": (monthly("none"), False),
    "RETEST": (retest(0.25), True),
}
REGISTRY = dict(ROUND1)
REGISTRY.update(ROUND2)


def _job(args):
    name, sh = args
    ent = REGISTRY[name]
    fn, flip = ent[0], ent[1]
    kw = ent[2] if len(ent) > 2 else {}
    B = _book()
    t0 = time.time()
    masks = (lambda b, cell, P, od: fn(b, cell, P, od, flip)) if flip else (lambda b, cell, P, od: fn(b, cell, P, od))
    res, _, cov = run_grid(B, family=f"X_{name}", cell_list=cells(), shift=sh, masks=masks,
                           keep_bits=False, verbose=False, flip=flip, **kw)
    s = screen(res)
    tag = f"{name}{'' if sh == 0 else f'_shift{sh:+.2f}'}"
    keep = ["config", "family", "level", "side", "unit", "d", "style", "D", "stop", "target", "n", "wr", "pf",
            "expR", "sdR", "exp_usd", "maxdd_usd", "tk_elig", "tk_pos", "expR_ES", "expR_NQ", "expR_CL", "expR_6J",
            "n_ES", "n_NQ", "n_CL", "n_6J", "nb_med_pf", "base_ok", "breadth_ok", "plateau_ok", "screen_pass"]
    s[keep].to_parquet(OUT / "families" / f"screen_{tag}.parquet")
    if sh == 0:
        cov.to_csv(OUT / "families" / f"coverage_{name}.csv", index=False)
    q = s[s.n >= 100].sort_values("expR", ascending=False)
    return dict(variant=name, shift=sh, configs=len(s), configs_n100=len(q), screen_pass=int(s.screen_pass.sum()),
                top10=q.expR.head(10).mean() if len(q) else np.nan, secs=time.time() - t0)


def summarize(names, rows):
    df = pd.DataFrame(rows)
    out = []
    for n in names:
        r = df[(df.variant == n) & (df["shift"] == 0)].iloc[0]
        p = df[(df.variant == n) & (df["shift"] != 0)]
        beat_pass = int((r.screen_pass > p.screen_pass).sum())
        beat_top = int((r.top10 > p.top10).sum())
        a = r.screen_pass >= 1
        b_ = (beat_pass >= 3) and (beat_top >= 3)
        out.append(dict(lineage=LINEAGE, variant=n, real_pass=int(r.screen_pass), plc_pass_mean=p.screen_pass.mean(),
                        plc_pass_max=int(p.screen_pass.max()), real_top10=r.top10, plc_top10_mean=p.top10.mean(),
                        plc_top10_max=p.top10.max(), beats_plc_pass=beat_pass, beats_plc_top10=beat_top,
                        screen_a=bool(a), level_specific_b=bool(b_), family_pass=bool(a and b_)))
    return pd.DataFrame(out)


def run_round(names, tag, procs=4):
    (OUT / "families").mkdir(parents=True, exist_ok=True)
    jobs = [(n, sh) for n in names for sh in SHIFTS]
    t0 = time.time()
    with Pool(procs) as pool:
        rows = []
        for i, r in enumerate(pool.imap_unordered(_job, jobs)):
            rows.append(r)
            print(f"  [{tag}] {i + 1}/{len(jobs)} {r['variant']} {r['shift']:+.2f} pass={r['screen_pass']} "
                  f"top10={r['top10']:.3f} ({time.time() - t0:.0f}s)", flush=True)
    raw = pd.DataFrame(rows)
    raw.to_csv(OUT / "families" / f"{tag}_raw.csv", index=False)
    summ = summarize(names, rows)
    summ.to_csv(OUT / "families" / f"{tag}_summary.csv", index=False)
    print(summ.round(3).to_string())
    return summ


if __name__ == "__main__":
    rnd = sys.argv[1]
    if rnd == "round1":
        run_round(list(ROUND1), "round1")
    elif rnd == "round2":
        run_round(list(ROUND2), "round2")
