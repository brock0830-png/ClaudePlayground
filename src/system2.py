"""Phase 6 candidates: TALOS (system.py) plus one add-on family at a time.

Add-on families (each switched off by default so p == PARAMS2 defaults reproduces TALOS exactly):
  A. Residual deployment ("bonds"/"gold" angle): the part of the 70% core sleeve that the vol target leaves in
     cash is put into the trend-passing members of `resid_set` (equal split, close > SMA(resid_len)); cash otherwise.
  B. Gold sleeve: a third sleeve of weight w_gold in GLD when GLD > SMA(gold_len), optionally vol-targeted
     (gold_vt = 0 means full sleeve), funded pro rata from the core and rotation sleeves.
  C. Buy-the-dip: when QQQ is above its SMA and today's close is the lowest of the last dip_n closes, the core holds
     QQQ at dip_boost x sleeve (or, if dip_mult > 0, at min(1, dip_mult x vol-target size)) for dip_hold days. dip_off_frac > 0 additionally
     buys QQQ at that fraction of the sleeve for dip_hold days on an dip_n-day low while QQQ is BELOW its SMA.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from strategies import FUNDS, ALL_COLS, sma, realised_vol, map_exposure, _clip_sum
import system as S

PARAMS2 = dict(S.PARAMS, dd_cut=0.0,
               resid_set=(), resid_len=200,
               w_gold=0.0, gold_len=200, gold_vt=0.0, gold_assets=("GLD",),
               dip_n=0, dip_hold=5, dip_boost=1.0, dip_off_frac=0.0, dip_mult=0.0)


def _nday_low(x: pd.Series, n: int) -> pd.Series:
    return x <= x.rolling(n, min_periods=n).min()


def _hold_flag(trigger: pd.Series, h: int) -> pd.Series:
    """True for h days starting at each trigger (inclusive)."""
    t = trigger.fillna(False).astype(float)
    return t.rolling(h, min_periods=1).max().astype(bool)


def core_weights2(R, L, p):
    q = L["QQQ_X"]; s = sma(q, p["sma_len"]); on = q > s
    size = (p["vol_target"] / realised_vol(R["QQQ_X"], p["vol_win"])).clip(upper=1.0)
    e_q = pd.Series(np.where(on, size, 0.0), q.index)
    warm = s.isna() | size.isna()
    if p["dip_n"] > 0:
        low = _nday_low(q, p["dip_n"])
        boost = _hold_flag(low & on, p["dip_hold"]) & on
        target = (size * p["dip_mult"]).clip(upper=1.0) if p["dip_mult"] > 0 else p["dip_boost"]   # vol-scaled or fixed boost
        e_q = pd.Series(np.where(boost, np.maximum(e_q, target), e_q), q.index)
        if p["dip_off_frac"] > 0:
            off_buy = _hold_flag(low & ~on, p["dip_hold"]) & ~on
            e_q = pd.Series(np.where(off_buy, p["dip_off_frac"], e_q), q.index)
    e_q[warm] = 0.0
    b_on = L["IEF_X"] > sma(L["IEF_X"], p["sma_len"])
    e_b = pd.Series(np.where(~on & b_on, 1.0, 0.0), q.index); e_b[s.isna()] = 0.0
    out = pd.DataFrame({"QQQ": e_q, "IEF": e_b})
    # A. residual deployment
    if p["resid_set"]:
        resid = (1.0 - e_q - e_b).clip(lower=0.0); resid[warm] = 0.0
        gates = pd.DataFrame({u: (L[FUNDS[u][1]] > sma(L[FUNDS[u][1]], p["resid_len"])) for u in p["resid_set"]}).fillna(False)
        n_on = gates.sum(axis=1).replace(0, np.nan)
        for u in p["resid_set"]:
            out[u] = out.get(u, 0.0) + (resid * gates[u] / n_on).fillna(0.0)
    return out


def blend_exposures2(R, L, p):
    core = core_weights2(R, L, p); rot = S.rotation_exposures(R, L, p)
    wg = p["w_gold"]
    e = rot * (1 - p["w_core"]) * (1 - wg)
    for c in core.columns:
        e[c] = e.get(c, 0.0) + p["w_core"] * (1 - wg) * core[c]
    if wg > 0:
        assets = tuple(p["gold_assets"])   # each metal gets an equal share of the sleeve, gated and sized on its own
        for u in assets:
            g = L[f"{u}_X"]; g_on = g > sma(g, p["gold_len"])
            size = 1.0 if p["gold_vt"] <= 0 else (p["gold_vt"] / realised_vol(R[f"{u}_X"], p["vol_win"])).clip(upper=1.0)
            e_g = pd.Series(np.where(g_on, size, 0.0), g.index).fillna(0.0)
            e[u] = e.get(u, 0.0) + wg * e_g / len(assets)
    return e.fillna(0.0)


def build2(R, L, p=PARAMS2):
    e = blend_exposures2(R, L, p)
    extra = [c for c in e.columns if c not in FUNDS]          # e.g. SLV: 1x fund only, no leveraged expression
    w = S.lever_to_funds(e.drop(columns=extra), p["lever"])
    for u in extra:
        w[f"{u}_X"] = (e[u] * p["lever"]).clip(upper=1.0)
    return _clip_sum(w)
