"""USD-mode OI-flush signal and its 24h trade (SPEC background section).

Signal bar t (1h bar, index = open time) fires when
    close[t] / close[t-24h] - 1 <= -4.6%   and   oi_usd[t] / oi_usd[t-24h] - 1 <= -1.8%
where oi_usd[t] is the OI value snapshot at bar t's close. Entry at the open of bar t+1h,
exit at the open of bar t+25h. net = exit/entry - 1 - 0.14% - sum(funding rates in [entry, exit)).

Dedup: PRIMARY = one position per coin at a time (a new signal needs t >= previous signal t + 24h,
i.e. entry at or after the previous exit). The other counts are printed for the replication check.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import COST_RT, END, HOLD_H, OI_CHG, PRICE_CHG, START


def flush_condition(h: pd.DataFrame, oi_col: str = "oi_usd") -> pd.Series:
    r24 = h.c / h.c.shift(24) - 1
    o24 = h[oi_col] / h[oi_col].shift(24) - 1
    return (r24 <= PRICE_CHG) & (o24 <= OI_CHG)


def dedup(times: pd.DatetimeIndex, mode: str) -> pd.DatetimeIndex:
    if mode == "all":
        return times
    if mode == "episode":          # first bar of each run of consecutive signal bars
        prev = times.to_series().diff()
        return times[(prev != pd.Timedelta("1h")).values]
    if mode == "nonoverlap":
        keep, nxt = [], None
        for t in times:
            if nxt is None or t >= nxt:
                keep.append(t)
                nxt = t + pd.Timedelta(hours=HOLD_H)
        return pd.DatetimeIndex(keep)
    raise ValueError(mode)


def funding_between(f: pd.Series, a, b) -> float:
    """Sum of funding rates with a <= stamp < b (a long pays positive rates)."""
    i, j = f.index.searchsorted(a, side="left"), f.index.searchsorted(b, side="left")
    return float(f.values[i:j].sum())


def trades(sym: str, h: pd.DataFrame, f: pd.Series, mode: str = "nonoverlap", oi_col: str = "oi_usd",
           hold_h: int = HOLD_H, side: int = 1) -> pd.DataFrame:
    cond = flush_condition(h, oi_col)
    t = cond.index[cond.values & (cond.index >= START) & (cond.index < END)]
    t = dedup(t, mode)
    rows = []
    for ts in t:
        e_t, x_t = ts + pd.Timedelta("1h"), ts + pd.Timedelta(hours=1 + hold_h)
        if e_t not in h.index or x_t not in h.index:
            continue
        e, x = h.at[e_t, "o"], h.at[x_t, "o"]
        if not (np.isfinite(e) and np.isfinite(x)):
            continue
        gross = side * (x / e - 1)
        fund = side * funding_between(f, e_t, x_t)
        rows.append(dict(sym=sym, t=ts, entry_t=e_t, exit_t=x_t, entry=e, exit=x, close=h.at[ts, "c"],
                         gross=gross, fund=fund, net=gross - COST_RT - fund))
    return pd.DataFrame(rows)
