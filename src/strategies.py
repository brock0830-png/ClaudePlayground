"""Pre-registered rule families (PREREG.md H1-H12) and baselines.

Every function returns a DataFrame of target weights (dates x instruments) on
the full calendar. Weights are decided from data through each row's close and
are executed by the engine one day later. Only backward-looking pandas ops
(rolling, shift, cummax) are used.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANN = np.sqrt(252)

# fund families: underlying -> {leverage: column}
FUNDS = {
    "SPY": {1: "SPY_X", 2: "SSO_X", 3: "UPRO_X", -1: "SH_X", -2: "SDS_X", -3: "SPXU_X"},
    "QQQ": {1: "QQQ_X", 2: "QLD_X", 3: "TQQQ_X", -1: "PSQ_X", -2: "QID_X", -3: "SQQQ_X"},
    "TLT": {1: "TLT_X", 2: "UBT_X", 3: "TMF_X", -2: "TBT_X", -3: "TMV_X"},
    "IEF": {1: "IEF_X", 2: "UST_X"},
    "GLD": {1: "GLD_X", 2: "UGL_X"},
    "IWM": {1: "IWM_X"},
}
ALL_COLS = sorted({c for f in FUNDS.values() for c in f.values()})
LEVERAGE = {c: L for f in FUNDS.values() for L, c in f.items()}
LEVERAGED_COLS = {c for c, L in LEVERAGE.items() if abs(L) > 1 or L < 0}


def sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def realised_vol(r: pd.Series, n: int) -> pd.Series:
    return r.rolling(n, min_periods=n).std() * ANN


def map_exposure(e: pd.Series, under: str, max_fund: int = 2) -> pd.DataFrame:
    """Turn a signed exposure series (multiple of the underlying) into fund weights.

    Long: e in [0,1] -> e in 1x. e in (1, max_fund] -> mix of 1x and max_fund-x with
    weights summing to 1. Short: |e| <= 1 -> |e| in the -1x fund (or -2x at half weight
    if no -1x exists); |e| in (1,2] -> mix of -1x and -2x.
    """
    f = FUNDS[under]
    out = pd.DataFrame(0.0, index=e.index, columns=ALL_COLS)
    e = e.fillna(0.0)
    pos = e.clip(lower=0); neg = (-e).clip(lower=0)
    # long side
    one = pos.clip(upper=1.0)
    extra = (pos - 1).clip(lower=0)
    if max_fund > 1 and max_fund in f:
        b = extra / (max_fund - 1)            # weight in the L-x fund
        out[f[max_fund]] += b
        out[f[1]] += (one - b).clip(lower=0)
    else:
        out[f[1]] += one
    # short side (inverse funds held long)
    if -1 in f:
        out[f[-1]] += neg.clip(upper=1.0)
        if -2 in f:
            extra_s = (neg - 1).clip(lower=0)
            out[f[-2]] += extra_s              # 1 unit of -2x adds 2 units of short; rebalance below
            out[f[-1]] -= extra_s
            out[f[-1]] = out[f[-1]].clip(lower=0)
    elif -2 in f:
        out[f[-2]] += (neg / 2).clip(upper=1.0)
    return out


def _clip_sum(w: pd.DataFrame) -> pd.DataFrame:
    s = w.sum(axis=1)
    over = s > 1
    w.loc[over] = w.loc[over].div(s[over], axis=0)
    return w.clip(lower=0)


# ------------------------------------------------------------------ baselines
def b1_spy(R, L):
    w = pd.DataFrame(0.0, R.index, ALL_COLS); w["SPY_X"] = 1.0; return w


def b2_6040(R, L):
    w = pd.DataFrame(np.nan, R.index, ALL_COLS)
    me = R.index.to_series().groupby([R.index.year, R.index.month]).tail(1).index
    w.loc[me, :] = 0.0; w.loc[me, "SPY_X"] = 0.6; w.loc[me, "IEF_X"] = 0.4
    return w  # NaN rows = no trade (engine lets weights drift)


def b3_spy_sma(R, L, n=200):
    on = (L["SPY_X"] > sma(L["SPY_X"], n)).astype(float)
    return map_exposure(on, "SPY")


def b4_voltarget(R, L, target=0.10, n=20, cap=1.0):
    e = (target / realised_vol(R["SPY_X"], n)).clip(upper=cap)
    return map_exposure(e, "SPY", 2)


# ------------------------------------------------------------------ hypotheses
def h1_trend(R, L, E="SPY", n=200, bear=0):
    p = L[FUNDS[E][1]]
    on = p > sma(p, n)
    e = pd.Series(np.where(on, 1.0, -float(bear)), p.index)
    e[sma(p, n).isna()] = 0.0
    return map_exposure(e, E, 2)


def h2_vol(R, L, E="SPY", target=0.10, n=20, cap=1.0):
    e = (target / realised_vol(R[FUNDS[E][1]], n)).clip(upper=cap)
    return map_exposure(e, E, 2)


def h3_trend_vol(R, L, E="SPY", n_trend=200, target=0.10, cap=2.0, bear=0, n_vol=20):
    p = L[FUNDS[E][1]]
    on = p > sma(p, n_trend)
    size = (target / realised_vol(R[FUNDS[E][1]], n_vol))
    e = pd.Series(np.where(on, size.clip(upper=cap), -bear * size.clip(upper=1.0)), p.index)
    e[sma(p, n_trend).isna() | size.isna()] = 0.0
    return map_exposure(e, E, 2)


def h4_dip(R, L, E="SPY", D=0.05, lev=3, n_trend=200):
    p = L[FUNDS[E][1]]
    trend = p > sma(p, n_trend)
    hi20 = p.rolling(20, min_periods=20).max()
    dip = p <= hi20 * (1 - D)
    newhigh = p >= hi20
    # state machine: add-on active from dip until new 20d high or trend off
    active = np.zeros(len(p), dtype=bool)
    a = False
    tr = trend.to_numpy(); dp = dip.to_numpy(); nh = newhigh.to_numpy()
    for i in range(len(p)):
        if not tr[i]:
            a = False
        elif dp[i]:
            a = True
        elif nh[i]:
            a = False
        active[i] = a
    e = pd.Series(np.where(trend, np.where(active, float(lev), 1.0), 0.0), p.index)
    e[sma(p, n_trend).isna()] = 0.0
    return map_exposure(e, E, lev)


def h5_rotation(R, L, M=126, k=2, universe=("SPY", "QQQ", "IWM", "TLT", "GLD")):
    cols = [FUNDS[u][1] for u in universe]
    mom = L[cols] / L[cols].shift(M) - 1
    cash_mom = L["CASH"] / L["CASH"].shift(M) - 1
    w = pd.DataFrame(np.nan, R.index, ALL_COLS)
    me = R.index.to_series().groupby([R.index.year, R.index.month]).tail(1).index
    for d in me:
        m = mom.loc[d].dropna()
        if len(m) < len(cols):
            continue
        top = m.sort_values(ascending=False).index[:k]
        w.loc[d, :] = 0.0
        for c in top:
            if m[c] > cash_mom.loc[d]:
                w.loc[d, c] = 1.0 / k
    return w


def h6_multi(R, L, n_trend=200, target=0.09, cap=2.0, bear=0, n_vol=60):
    assets = {"SPY": "SPY_X", "TLT": "TLT_X", "GLD": "GLD_X"}
    raw = {}
    for u, c in assets.items():
        v = realised_vol(R[c], n_vol)
        on = L[c] > sma(L[c], n_trend)
        sign = np.where(on, 1.0, (-1.0 * bear) if u != "GLD" else 0.0)
        raw[u] = pd.Series(sign / v, R.index)
    raw = pd.DataFrame(raw)
    gross = raw.abs().sum(axis=1)
    wn = raw.div(gross.replace(0, np.nan), axis=0).fillna(0.0)      # signed weights summing to 1 in abs
    port_r = (wn.shift(1) * pd.DataFrame({u: R[c] for u, c in assets.items()})).sum(axis=1)
    pv = realised_vol(port_r, n_vol)
    scale = (target / pv).clip(upper=cap).fillna(0.0)
    out = pd.DataFrame(0.0, R.index, ALL_COLS)
    for u in assets:
        out += map_exposure(wn[u] * scale, u, 2)
    out[gross.isna() | pv.isna()] = 0.0
    return _clip_sum(out)


def dd_overlay(w: pd.DataFrame, base_equity: pd.Series, D=0.10) -> pd.DataFrame:
    """Halve exposure when the un-overlaid rule's own equity is more than D below its peak; restore within D/2."""
    dd = base_equity / base_equity.cummax() - 1
    state = np.zeros(len(dd)); s = 1.0
    for i, x in enumerate(dd.to_numpy()):
        if s == 1.0 and x < -D:
            s = 0.5
        elif s == 0.5 and x > -D / 2:
            s = 1.0
        state[i] = s
    return w.mul(pd.Series(state, dd.index).reindex(w.index).ffill().fillna(1.0), axis=0)


def vix_overlay(w: pd.DataFrame, vix: pd.Series, V=25) -> pd.DataFrame:
    stress = (vix > sma(vix, 50)) & (vix > V)
    return w.mul(np.where(stress.reindex(w.index).fillna(False), 0.5, 1.0), axis=0)


def bonds_instead_of_cash(w: pd.DataFrame, L, bond="TLT_X", n=200) -> pd.DataFrame:
    on = (L[bond] > sma(L[bond], n)).reindex(w.index).fillna(False)
    free = (1 - w.sum(axis=1)).clip(lower=0)
    w = w.copy(); w[bond] = w[bond] + np.where(on, free, 0.0)
    return w


def h10_reversal(R, L, E="SPY", c=3, fund=1, n_trend=200):
    p = L[FUNDS[E][1]]; r = R[FUNDS[E][1]]
    trend = p > sma(p, n_trend)
    down = (r < 0).astype(int)
    streak = down * (down.groupby((down != down.shift()).cumsum()).cumcount() + 1)
    hold = np.zeros(len(p)); h = 0; days = 0
    st = streak.to_numpy(); tr = trend.to_numpy(); rr = r.to_numpy()
    for i in range(len(p)):
        if h:
            days += 1
            if rr[i] > 0 or days >= 5 or not tr[i]:
                h = 0; days = 0
        if not h and tr[i] and st[i] >= c:
            h = 1; days = 0
        hold[i] = h
    e = pd.Series(hold * float(fund), p.index)
    return map_exposure(e, E, 2)


def gold_sleeve(w: pd.DataFrame, L, n=200, frac=0.2) -> pd.DataFrame:
    on = (L["GLD_X"] > sma(L["GLD_X"], n)).reindex(w.index).fillna(False)
    w = w * (1 - frac)
    w["GLD_X"] = w["GLD_X"] + np.where(on, frac, 0.0)
    return w
