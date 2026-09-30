"""
Every Scalpel level is linear in (period open, sigma):  level = PO + sigma * k[name].
This module derives k from params_es (so it is exactly levels.level_frame), builds the
per-bar open/sigma arrays for each vol mode, and produces jittered and round-grid
variants for the baselines.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .params_es import ES, GP_OUTER, GP_INNER

NAMES = ["OPEN", "GB_TOP", "TH2", "TH1", "GB_BOT", "RH", "RL", "RB_TOP", "TL1", "TL2", "RB_BOT",
         "GP_T_OUT", "GP_T_IN", "GP_B_OUT", "GP_B_IN", "RNG_T_HI", "RNG_T_LO", "RNG_B_HI", "RNG_B_LO"]
PERIODS = {"D": 252, "W": 52, "M": 12}
FIXED_VOL = {tf: ES[tf]["vol"] for tf in "DWM"}
# round-grid baseline step = half the fixed-mode sigma, in % of the open (PROTOCOL 5.2)
GRID_STEP_PCT = {tf: 0.5 * FIXED_VOL[tf] / np.sqrt(PERIODS[tf]) for tf in "DWM"}


def coefficients(tf: str, params: dict = ES) -> dict[str, float]:
    p = params[tf]
    up, dn = p["bias"] / 0.5, (1.0 - p["bias"]) / 0.5
    k = {"OPEN": 0.0,
         "GB_TOP": up * p["gbtop"], "TH2": up * p["wth2"], "TH1": up * p["wth1"],
         "GB_BOT": up * p["inner_top"], "RH": up * p["wrh"],
         "RL": -dn * p["wrl"], "RB_TOP": -dn * p["inner_bot"], "TL1": -dn * p["tl1"],
         "TL2": -dn * p["tl2"], "RB_BOT": -dn * p["rbbot"]}
    inner = k["GB_BOT"] - k["RB_TOP"]
    k["GP_T_OUT"] = k["RB_TOP"] + inner * GP_OUTER
    k["GP_T_IN"] = k["RB_TOP"] + inner * GP_INNER
    k["GP_B_OUT"] = k["RB_TOP"] + inner * (1 - GP_OUTER)
    k["GP_B_IN"] = k["RB_TOP"] + inner * (1 - GP_INNER)
    k["RNG_T_HI"] = k["RH"] + p["rng_top"]
    k["RNG_T_LO"] = k["RH"] - p["rng_top"]
    k["RNG_B_HI"] = k["RL"] + p["rng_bot"]
    k["RNG_B_LO"] = k["RL"] - p["rng_bot"]
    return k


def sigma_from_vol(po: np.ndarray, vol: np.ndarray | float, tf: str) -> np.ndarray:
    return po * (np.asarray(vol) / 100.0) / np.sqrt(PERIODS[tf])


def jitter_factors(rng: np.random.Generator, names=NAMES) -> dict[str, float]:
    """1 + s*u, s=+/-1, u~U[0.10,0.40], independent per level name; OPEN untouched."""
    f = {}
    for n in names:
        if n == "OPEN":
            f[n] = 1.0
            continue
        s = 1.0 if rng.random() < 0.5 else -1.0
        f[n] = 1.0 + s * rng.uniform(0.10, 0.40)
    return f


def grid_coefficients(tf: str) -> dict[str, float]:
    """
    Round-grid baseline: each level role moves to the nearest multiple of the grid step
    (half fixed-mode sigma, a fixed %) on the same side of the open. Returned as a
    *percent-of-open* multiplier m, i.e. level = PO * (1 + m/100).
    """
    k = coefficients(tf)
    sig_pct = FIXED_VOL[tf] / np.sqrt(PERIODS[tf])
    step = GRID_STEP_PCT[tf]
    out = {}
    for n, kv in k.items():
        if n == "OPEN":
            out[n] = 0.0
            continue
        pct = kv * sig_pct
        m = max(1, int(round(abs(pct) / step)))
        out[n] = np.sign(pct) * m * step
    return out
