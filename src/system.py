"""Candidate final system: blend of the trend-gated vol-targeted QQQ core (H3 + H9 bond-when-off)
and the cross-asset momentum rotation (H5), with optional drawdown control (H7) and an exposure multiplier.

All parameters are explicit in PARAMS so the count is auditable.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from strategies import (FUNDS, ALL_COLS, sma, realised_vol, map_exposure, h5_rotation, dd_overlay, _clip_sum)

PARAMS = dict(
    sma_len=200,      # trend length for QQQ gate and the bond gate
    vol_target=0.10,  # annualised vol target of the equity core
    vol_win=20,       # realised vol window (days)
    mom_len=126,      # rotation lookback (days)
    top_k=3,          # rotation holdings
    w_core=0.7,       # blend weight on the equity core
    dd_cut=0.10,      # drawdown control threshold (0 = off)
    lever=1.0,        # exposure multiplier (the frontier knob)
)


def core_weights(R, L, p):
    """Equity core: QQQ exposure = min(1, target/vol) while QQQ > SMA; otherwise IEF if IEF > its SMA, else cash.
    Returns exposures in underlying units (columns: QQQ, IEF)."""
    q = L["QQQ_X"]; on = q > sma(q, p["sma_len"])
    size = (p["vol_target"] / realised_vol(R["QQQ_X"], p["vol_win"])).clip(upper=1.0)
    e_q = pd.Series(np.where(on, size, 0.0), q.index)
    e_q[sma(q, p["sma_len"]).isna() | size.isna()] = 0.0
    b_on = (L["IEF_X"] > sma(L["IEF_X"], p["sma_len"]))
    e_b = pd.Series(np.where(~on & b_on, 1.0, 0.0), q.index)
    e_b[sma(q, p["sma_len"]).isna()] = 0.0
    return pd.DataFrame({"QQQ": e_q, "IEF": e_b})


def rotation_exposures(R, L, p):
    w = h5_rotation(R, L, M=p["mom_len"], k=p["top_k"]).reindex(R.index).ffill().fillna(0.0)
    return pd.DataFrame({u: w[FUNDS[u][1]] for u in ["SPY", "QQQ", "IWM", "TLT", "GLD"]})


def blend_exposures(R, L, p):
    core = core_weights(R, L, p); rot = rotation_exposures(R, L, p)
    e = rot * (1 - p["w_core"])
    for c in ["QQQ", "IEF"]:
        e[c] = e.get(c, 0.0) + p["w_core"] * core[c]
    return e.fillna(0.0)


def lever_to_funds(e: pd.DataFrame, m: float) -> pd.DataFrame:
    """Scale underlying exposures by m and map each to 1x/2x/3x funds. Uses the 3x fund where one exists."""
    out = pd.DataFrame(0.0, e.index, ALL_COLS)
    for u in e.columns:
        maxf = 3 if 3 in FUNDS[u] else (2 if 2 in FUNDS[u] else 1)
        out += map_exposure(e[u] * m, u, maxf)
    return _clip_sum(out)


def build(R, L, p=PARAMS, base_equity: pd.Series | None = None):
    """Weights for the engine. If dd_cut > 0, base_equity (equity of the same rule without DD control,
    evaluated on the same window) must be supplied; the overlay is computed from it."""
    w = lever_to_funds(blend_exposures(R, L, p), p["lever"])
    if p["dd_cut"] > 0 and base_equity is not None:
        w = dd_overlay(w, base_equity, p["dd_cut"])
    return w
