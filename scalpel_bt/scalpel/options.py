"""
MODELED option screens. Nothing here can become an OOS candidate (PROTOCOL 1, 5).

Pricing: Black-76 on the ES price (r = 0), European exercise (SPX/XSP-style, cash settled),
so no early assignment is modeled. Implied vol:
    atm_iv = ATM_RATIO * VIX9D(prior close) / 100        (VIX9D is the ~1-week index)
    iv(K)  = atm_iv * (1 + SKEW_SLOPE * z + SKEW_CURV * z^2),  z = ln(K/F) / (atm_iv * sqrt(T))
floored at 0.5 * atm_iv, with z clipped to +/-3.5 (flat wings). ATM_RATIO and the skew are ASSUMPTIONS (no real quotes exist here
to calibrate them); "flat" variants set the skew to zero.
Fills: sells at mid - 25% of spread, buys at mid + 25%; spread = max(0.25, 5% of mid) pt;
commission $0.65 per contract per leg (= 0.013 ES pt). Strikes rounded to 5 points.
Settlement: close of the last bar of the expiry session (17:00 ET; SPX settles 16:00 -> proxy).
Contract switches inside a trade: prices after the switch bar are shifted back by the
measured calendar spread (data/roll_dates.csv) so the index path has no roll gap.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.special import ndtr
from scipy.stats import norm
from .data import DATA, load_vix
from .levelsets import coefficients

ATM_RATIO = 0.92
SKEW_SLOPE = -0.15
SKEW_CURV = 0.03
COMM_PTS = 0.65 / 50.0
Z_CAP = 3.5          # skew is flat beyond +/-3.5 standard deviations
YEAR_H = 365.0 * 24.0


def iv_of(K, F, T, atm, slope=SKEW_SLOPE, curv=SKEW_CURV):
    z = np.clip(np.log(K / F) / (atm * np.sqrt(T)), -Z_CAP, Z_CAP)
    return np.maximum(atm * (1 + slope * z + curv * z * z), 0.5 * atm)


def b76(F, K, T, vol, cp):
    """cp = +1 call, -1 put. Returns price, delta."""
    T = np.maximum(T, 1e-8)
    sd = vol * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    if cp > 0:
        return F * ndtr(d1) - K * ndtr(d2), ndtr(d1)
    return K * ndtr(-d2) - F * ndtr(-d1), ndtr(d1) - 1.0


def price(F, K, T, atm, cp, flat=False):
    v = np.full_like(np.asarray(K, float), atm) if flat else iv_of(K, F, T, atm)
    return b76(F, K, T, v, cp)


def spread_cost(mid):
    return 0.25 * np.maximum(0.25, 0.05 * mid)


def strike_for_delta(F, T, atm, cp, delta, flat=False):
    """Strike with |model delta| = delta (skew-aware), rounded to 5."""
    lo, hi = F * 0.5, F * 1.5
    target = delta if cp > 0 else -delta
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        _, d = price(F, np.array([mid]), T, atm, cp, flat)
        d = d[0]
        # call delta falls with K; put delta (negative) falls toward -1 as K rises
        if (d > target):
            lo = mid
        else:
            hi = mid
    return round5(0.5 * (lo + hi))


def round5(x):
    return np.round(np.asarray(x) / 5.0) * 5.0


def roll_adjusted_close(bars: pd.DataFrame) -> np.ndarray:
    """Close series with each contract switch gap removed (back-adjusted within history)."""
    rt = pd.read_csv(DATA / "roll_dates.csv", parse_dates=["switch_tday"])
    adj = np.zeros(len(bars))
    sw = bars["roll_switch_bar"].values
    jumps = dict(zip(rt["switch_tday"].dt.normalize(), rt["jump"]))
    idx = np.flatnonzero(sw)
    for i in idx:
        j = jumps.get(bars["tday"].iloc[i], 0.0)
        adj[i:] += j
    # price_on_old_contract_basis = price - cumulative jumps since
    return adj


def vix9d_prior(bars: pd.DataFrame) -> np.ndarray:
    v = load_vix("VIX9D")
    d = bars["tday"].values.astype("datetime64[ns]")
    i = np.searchsorted(v.index.values, d, side="left") - 1
    return np.where(i >= 0, v.values[np.clip(i, 0, None)], np.nan)
