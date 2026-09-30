"""
Variant spec -> arrays for the simulator, for the real levels, jittered levels and the
round-grid baseline.  A spec is a plain dict:

  family      'bounce' | 'break' | 'reclaim' | ...
  tf          'D' | 'W' | 'M'           (timeframe of the entry level)
  mode        'fixed' | 'scaled' | 'ewma_rs'
  side        'long' | 'short'
  level       entry level name (e.g. 'RL' long, 'RH' short)
  trig        'touch' | 'reject' | 'limit' | 'break' | 'stopin' | 'reclaim'
  stop        ('sig', x)  -> x sigma beyond the entry level   | ('lvl', NAME)
  target      ('lvl', NAME) | ('R', r) | ('none',)
  pend        True -> flat at the end of the level period
  max_bars    0 = no bar limit
  roll        'incl' | 'excl'  (excl: no signals in roll weeks (W) / after the switch (M))
  filters     dict, see `filter_mask`
"""
from __future__ import annotations
import numpy as np
from .levelsets import coefficients, grid_coefficients
from .engine import TRIG, TGT_LEVEL, TGT_R, TGT_NONE, simulate
from .features import Frame
from .data import COST_RT_PTS


def level_array(fr: Frame, tf: str, mode: str, name: str, jit: dict | None = None,
                grid: bool = False) -> np.ndarray:
    po = fr.po[tf]
    if grid:
        m = grid_coefficients(tf)[name]
        return po * (1.0 + m / 100.0)
    k = coefficients(tf)[name] * (1.0 if jit is None else jit[name])
    return po + fr.sigma[(tf, mode)] * k


def filter_mask(fr: Frame, spec: dict, E_orig: np.ndarray | None = None) -> np.ndarray:
    f = fr.feat
    n = len(fr.o)
    m = ~fr.no_signal[spec["tf"]]
    m &= ~np.isnan(fr.sigma[(spec["tf"], spec["mode"])])
    if spec.get("roll", "incl") == "excl":
        if spec["tf"] == "W":
            m &= ~f["roll_week"].values
        elif spec["tf"] == "M":
            m &= ~f["roll_month_after"].values
        else:
            m &= ~f["roll_week"].values
    flt = spec.get("filters", {}) or {}
    pc = f["prev_close"].values
    for key, val in flt.items():
        if key == "trend":            # 'up20','dn20','up50','dn50'
            ma = f["ma20"].values if val.endswith("20") else f["ma50"].values
            ok = (pc > ma) if val.startswith("up") else (pc < ma)
            m &= ok & ~np.isnan(ma)
        elif key == "vix":            # 'lt15','15_20','20_30','gt30','lt20','gt20','below_mean','above_mean'
            v = f["vix_prev"].values
            vm = f["vix_mean252"].values
            ok = {"lt15": v < 15, "15_20": (v >= 15) & (v < 20), "20_30": (v >= 20) & (v < 30),
                  "gt30": v >= 30, "lt20": v < 20, "gt20": v >= 20,
                  "below_mean": v < vm, "above_mean": v >= vm}[val]
            m &= ok
        elif key == "dow":            # int 0..4 (trading-day weekday)
            m &= f["dow"].values == val
        elif key == "htf":            # ('W','above') : prev close vs the higher-TF period open
            tf2, where = val
            ref = fr.po[tf2]
            m &= (pc > ref) if where == "above" else (pc < ref)
        elif key == "conf":           # (pct, ('W','M')) any level of those TFs within pct% of E
            pct, tfs = val
            assert E_orig is not None
            near = np.zeros(n, dtype=bool)
            for tf2 in tfs:
                for nm in coefficients(tf2):
                    L = level_array(fr, tf2, "fixed" if spec["mode"] == "ewma_rs" else spec["mode"], nm)
                    near |= np.abs(L - E_orig) <= pct / 100.0 * E_orig
            m &= near
        else:
            raise KeyError(key)
    return m


def build(fr: Frame, spec: dict, jit: dict | None = None, grid: bool = False):
    tf, mode = spec["tf"], spec["mode"]
    E = level_array(fr, tf, mode, spec["level"], jit, grid)
    sig = fr.sigma[(tf, mode)] if not grid else fr.po[tf] * 2.0 * _grid_step(tf) / 100.0
    sgn = 1.0 if spec["side"] == "long" else -1.0
    st = spec["stop"]
    if st[0] == "sig":
        S = E - sgn * st[1] * sig
    else:
        S = level_array(fr, tf, mode, st[1], jit, grid)
    tg = spec["target"]
    if tg[0] == "lvl":
        T = level_array(fr, tf, mode, tg[1], jit, grid)
        tmode, r = TGT_LEVEL, 0.0
    elif tg[0] == "R":
        T = np.full_like(E, np.nan); tmode, r = TGT_R, float(tg[1])
    else:
        T = np.full_like(E, np.nan); tmode, r = TGT_NONE, 0.0
    elig = filter_mask(fr, spec, E_orig=E)
    if sgn > 0:
        px = (fr.o, fr.h, fr.l, fr.c)
    else:
        px = (-fr.o, -fr.l, -fr.h, -fr.c)
        E, S, T = -E, -S, -T
    return px, E, S, T, elig, tmode, r


def _grid_step(tf):
    from .levelsets import GRID_STEP_PCT
    return GRID_STEP_PCT[tf]


def run(fr: Frame, spec: dict, start: int, end: int, jit: dict | None = None, grid: bool = False):
    """Returns a dict of trade arrays (net points after costs)."""
    (o, h, l, c), E, S, T, elig, tmode, r = build(fr, spec, jit, grid)
    ei, xi, ep, xp, sp, rsn = simulate(o, h, l, c, E, S, T, elig, fr.pid[spec["tf"]],
                                       fr.pend[spec["tf"]], fr.force_flat, TRIG[spec["trig"]],
                                       tmode, r, int(spec.get("max_bars", 0)),
                                       bool(spec.get("pend", True)), start, end)
    gross = xp - ep
    risk = ep - sp
    return dict(ei=ei, xi=xi, entry=ep, exit=xp, stop=sp, reason=rsn, gross=gross,
                net=gross - COST_RT_PTS, risk=risk, side=spec["side"])
