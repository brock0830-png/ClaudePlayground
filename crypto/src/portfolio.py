"""Daily long/flat spot portfolio engine.

W (dates x coins) holds target weights decided at the close of day d. They are executed at the open of day
d+1+delay. On a rebalance day (R true) every holding is reset to its target. On other days only coins whose target
switches between zero and non-zero are traded, and the rest drift. Costs are |trade| x cost per side, paid from cash.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def simulate(W: pd.DataFrame, R: pd.Series, opens: pd.DataFrame, closes: pd.DataFrame, cost: pd.Series,
             delay: int = 0, cost_mult: float = 1.0):
    cols = list(W.columns)
    O = opens[cols].to_numpy(float)
    C = closes[cols].to_numpy(float)
    Wv = W.fillna(0.0).to_numpy(float)
    Rv = R.reindex(W.index).fillna(False).to_numpy(bool)
    cv = cost.reindex(cols).to_numpy(float) * cost_mult
    T, K = Wv.shape
    h = np.zeros(K)
    cash = 1.0
    eq = np.full(T, np.nan)
    eq[0] = 1.0
    expo = np.zeros(T)
    turn = np.zeros(T)
    ntr = np.zeros(T)
    held = np.zeros((T, K))
    for d in range(1, T):
        f = O[d] / C[d - 1]
        h = h * np.where(np.isfinite(f), f, 1.0)
        e_now = cash + h.sum()
        dd = d - 1 - delay
        if dd >= 0:
            w = Wv[dd]
            if Rv[dd]:
                reset = np.ones(K, dtype=bool)
            else:
                prev = Wv[dd - 1] if dd >= 1 else np.zeros(K)
                reset = ((w > 0) != (prev > 0)) | ((w == 0) & (h != 0))

            def target(e):
                return np.where(reset, w * e, h)

            # size new targets on equity net of this rebalance's cost, so cash never goes negative
            c0 = float(np.abs(target(e_now) - h) @ cv)
            tgt = target(e_now - c0)
            tr = tgt - h
            moved = np.abs(tr) > 1e-12 * max(e_now, 1e-12)
            c = float(np.abs(tr[moved]) @ cv[moved]) if moved.any() else 0.0
            turn[d] = np.abs(tr).sum() / e_now if e_now > 0 else 0.0
            ntr[d] = int(moved.sum())
            cash = e_now - tgt.sum() - c
            h = tgt
        g = C[d] / O[d]
        h = h * np.where(np.isfinite(g), g, 1.0)
        eq[d] = cash + h.sum()
        expo[d] = h.sum() / eq[d] if eq[d] > 0 else 0.0
        held[d] = h
    idx = W.index
    return {"equity": pd.Series(eq, idx), "exposure": pd.Series(expo, idx), "turnover": pd.Series(turn, idx),
            "trades": pd.Series(ntr, idx), "held": pd.DataFrame(held, idx, cols)}


def metrics(ret: pd.Series, exposure=None, turnover=None, trades=None) -> dict:
    ret = ret.dropna()
    n = len(ret)
    if n < 2:
        return {}
    yrs = n / 365.0
    eq = (1 + ret).cumprod()
    cagr = float(eq.iloc[-1] ** (1 / yrs) - 1) if eq.iloc[-1] > 0 else -1.0
    vol = float(ret.std(ddof=1) * np.sqrt(365))
    sharpe = float(ret.mean() / ret.std(ddof=1) * np.sqrt(365)) if ret.std(ddof=1) > 0 else np.nan
    dn = ret[ret < 0]
    sortino = float(ret.mean() / np.sqrt((dn ** 2).sum() / n) * np.sqrt(365)) if len(dn) else np.nan
    peak = eq.cummax()
    mdd = float((eq / peak - 1).min())
    out = {"cagr": cagr, "vol": vol, "sharpe": sharpe, "sortino": sortino, "maxdd": mdd,
           "mar": cagr / abs(mdd) if mdd < 0 else np.nan, "skew": float(ret.skew()), "kurt": float(ret.kurt() + 3),
           "days": n}
    if exposure is not None:
        out["exposure"] = float(exposure.reindex(ret.index).mean())
    if turnover is not None:
        out["turnover_ann"] = float(turnover.reindex(ret.index).sum() / yrs)
    if trades is not None:
        out["trades_per_year"] = float(trades.reindex(ret.index).sum() / yrs)
    return out


def sharpe_excluding(ret: pd.Series, a: str, b: str) -> float:
    r = ret.dropna()
    keep = ~((r.index >= pd.Timestamp(a, tz="UTC")) & (r.index < pd.Timestamp(b, tz="UTC") + pd.Timedelta(days=1)))
    r = r[keep]
    return float(r.mean() / r.std(ddof=1) * np.sqrt(365))


def deflated_sharpe(sr_ann: float, n_trials: int, T: int, skew: float, kurt: float, sr_std_ann: float) -> float:
    """Bailey & Lopez de Prado DSR with 365-day annualisation. sr_std_ann: cross-trial std of annual Sharpe."""
    from scipy.stats import norm
    sr = sr_ann / np.sqrt(365)
    v = (sr_std_ann / np.sqrt(365)) ** 2
    g = 0.5772156649
    n = max(n_trials, 2)
    sr0 = np.sqrt(v) * ((1 - g) * norm.ppf(1 - 1 / n) + g * norm.ppf(1 - 1 / (n * np.e)))
    den = np.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr ** 2, 1e-12))
    return float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / den))
