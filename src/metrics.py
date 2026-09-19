"""Performance metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd


def drawdown_series(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1


def max_drawdown(equity: pd.Series) -> tuple[float, pd.Timestamp, pd.Timestamp, pd.Timestamp | None, int]:
    """Return (mdd, peak_date, trough_date, recovery_date, longest_underwater_days)."""
    dd = drawdown_series(equity)
    trough = dd.idxmin()
    peak = equity.loc[:trough].idxmax()
    after = equity.loc[trough:]
    rec = after[after >= equity.loc[peak]]
    recovery = rec.index[0] if len(rec) else None
    # longest underwater in calendar days
    under = dd < 0
    longest = 0; cur_start = None
    for d, u in under.items():
        if u and cur_start is None:
            cur_start = d
        elif not u and cur_start is not None:
            longest = max(longest, (d - cur_start).days); cur_start = None
    if cur_start is not None:
        longest = max(longest, (under.index[-1] - cur_start).days)
    return float(dd.min()), peak, trough, recovery, longest


def summary(ret: pd.Series, rf: pd.Series | None = None, spy: pd.Series | None = None,
            weights_held: pd.DataFrame | None = None, gross_leverage: pd.Series | None = None,
            turnover: pd.Series | None = None, trades: pd.Series | None = None) -> dict:
    ret = ret.dropna()
    if len(ret) == 0:
        return {}
    eq = (1 + ret).cumprod()
    yrs = len(ret) / 252
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan
    vol = ret.std() * np.sqrt(252)
    ex = ret - (rf.reindex(ret.index).fillna(0) if rf is not None else 0)
    sharpe = ex.mean() / ex.std() * np.sqrt(252) if ex.std() > 0 else np.nan
    downside = ex[ex < 0].std() * np.sqrt(252)
    sortino = ex.mean() * 252 / downside if downside > 0 else np.nan
    mdd, peak, trough, rec, longest = max_drawdown(eq)
    monthly = eq.resample("ME").last().pct_change().dropna()
    r12 = (eq / eq.shift(252) - 1).dropna()
    out = {
        "CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino, "MaxDD": mdd,
        "MAR": (cagr / abs(mdd)) if mdd < 0 else np.nan,
        "MaxDD_peak": str(peak.date()), "MaxDD_trough": str(trough.date()),
        "MaxDD_recovery": str(rec.date()) if rec is not None else "not recovered",
        "LongestUnderwater_days": longest,
        "WorstDay": ret.min(), "WorstMonth": monthly.min() if len(monthly) else np.nan,
        "Worst12m": r12.min() if len(r12) else np.nan,
        "Years": yrs,
    }
    if weights_held is not None:
        wh = weights_held.reindex(ret.index)
        out["TimeInMarket"] = float((wh.sum(axis=1) > 1e-9).mean())
    if gross_leverage is not None:
        out["AvgLeverage"] = float(gross_leverage.reindex(ret.index).mean())
    if turnover is not None:
        out["Turnover_ann"] = float(turnover.reindex(ret.index).sum() / yrs)
    if trades is not None:
        out["TradesPerYear"] = float(trades.reindex(ret.index).sum() / yrs)
    if spy is not None:
        out["CorrSPY"] = float(ret.corr(spy.reindex(ret.index)))
    return out


def deflated_sharpe(sr: float, n_trials: int, T: int, skew: float = 0.0, kurt: float = 3.0,
                    sr_var_trials: float | None = None) -> float:
    """Bailey & Lopez de Prado deflated Sharpe ratio probability (daily SR inputs annualised outside).

    sr: annualised Sharpe of the candidate; T: number of daily observations.
    sr_var_trials: variance of annualised Sharpe across trials; if None use 0.5^2 as a conservative guess.
    Returns probability that the true Sharpe exceeds the expected max of n_trials null Sharpes.
    """
    from scipy.stats import norm
    sr_d = sr / np.sqrt(252)
    v = (sr_var_trials if sr_var_trials is not None else 0.25) / 252
    euler = 0.5772156649
    n = max(n_trials, 2)
    sr0 = np.sqrt(v) * ((1 - euler) * norm.ppf(1 - 1 / n) + euler * norm.ppf(1 - 1 / (n * np.e)))
    denom = np.sqrt(max(1 - skew * sr_d + (kurt - 1) / 4 * sr_d ** 2, 1e-12))
    z = (sr_d - sr0) * np.sqrt(T - 1) / denom
    return float(norm.cdf(z))
