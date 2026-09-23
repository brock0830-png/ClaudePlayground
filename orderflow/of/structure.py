"""Day / week auction structure at every hourly bar, from 1m bars (EXPLORATION_PROTOCOL.md).

For hourly bar t (index = open time, known at its close t+1h), day D = floor(t), week W = Monday of D:

  previous day   PDH PDL PDC PDPOC PDVAH PDVAL        (UTC day D-1, complete)
  previous week  PWH PWL PWPOC PWVAH PWVAL             (Mon-Sun week W-1, complete)
  developing day DO DH DL dPOC dVAH dVAL dDelta dVol   (from D 00:00 to t+1h)
  developing wk  WO WH WL wPOC wVAH wVAL wDelta wVol   (from W 00:00 to t+1h)

Profiles use profile_from_bars (each bar's volume spread over the rows its range touches), 50 rows,
70% value area. Delta = taker buy volume - taker sell volume = 2*tbv - v.
Forward outcomes: entry at the open of t+1h, exit at the open of t+1h+H; net of 0.14% and funding.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import COST_RT
from .profile import atr_wilder, profile_from_bars


def _session_table(b: pd.DataFrame, key: pd.Series) -> pd.DataFrame:
    """Completed-session stats for bars b grouped by session key."""
    rows = {}
    for k, g in b.groupby(key, sort=True):
        va = profile_from_bars(g.l.values, g.h.values, g.v.values)
        rows[k] = dict(O=g.o.iloc[0], H=g.h.max(), L=g.l.min(), C=g.c.iloc[-1], POC=va.poc, VAH=va.vah,
                       VAL=va.val, VOL=g.v.sum(), DELTA=(2 * g.tbv - g.v).sum())
    return pd.DataFrame.from_dict(rows, orient="index")


def _developing(b: pd.DataFrame, key: pd.Series, hours: pd.DatetimeIndex, prefix: str) -> pd.DataFrame:
    """Developing session profile at each hourly close. b: bars (1m or 5m) with o h l c v tbv, naive UTC index."""
    out = []
    bt = b.index.as_unit("ns").asi8                        # int64 ns: keeps searchsorted O(log n)
    o, l, hh, v = b.o.values, b.l.values, b.h.values, b.v.values
    d = (2 * b.tbv - b.v).values
    hk = key.reindex(hours).values
    one_h = pd.Timedelta("1h").value
    for k, grp in pd.Series(hours.as_unit("ns").asi8, index=hours).groupby(hk):
        s0 = np.searchsorted(bt, pd.Timestamp(k).value)
        for t, tv in zip(grp.index, grp.values):
            e = np.searchsorted(bt, tv + one_h)
            if e <= s0:
                continue
            va = profile_from_bars(l[s0:e], hh[s0:e], v[s0:e])
            out.append((t, o[s0], va.hi, va.lo, va.poc, va.vah, va.val, d[s0:e].sum(), v[s0:e].sum()))
    cols = ["O", "H", "L", "POC", "VAH", "VAL", "DELTA", "VOL"]
    D = pd.DataFrame([r[1:] for r in out], index=pd.DatetimeIndex([r[0] for r in out]), columns=cols)
    return D.add_prefix(prefix)


def build(m1: pd.DataFrame, h: pd.DataFrame, f: pd.Series, holds=(4, 12, 24)) -> pd.DataFrame:
    """Hourly structure frame for one coin."""
    m1 = m1.copy()
    m1.index = m1.index.tz_convert(None)                     # naive UTC for fast numpy searches
    day_key = pd.Series(m1.index.floor("D"), index=m1.index)
    week_key = pd.Series((m1.index.floor("D") - pd.to_timedelta(m1.index.dayofweek, unit="D")), index=m1.index)

    days = _session_table(m1, day_key)
    m5 = m1.resample("5min").agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum", "tbv": "sum"}).dropna()
    wk5 = pd.Series((m5.index.floor("D") - pd.to_timedelta(m5.index.dayofweek, unit="D")), index=m5.index)
    weeks = _session_table(m5, wk5)

    H = h.copy()
    idx = H.index.tz_convert(None)
    dkey = idx.floor("D")
    wkey = dkey - pd.to_timedelta(idx.dayofweek, unit="D")
    prev_day = days.shift(1).add_prefix("PD")                 # row k holds day k-1's stats
    prev_week = weeks.shift(1).add_prefix("PW")
    X = pd.DataFrame(index=idx)
    X = X.join(prev_day.reindex(dkey).set_axis(idx))
    X = X.join(prev_week.reindex(wkey).set_axis(idx))

    dev_d = _developing(m1, pd.Series(dkey, index=idx), idx, "d")
    dev_w = _developing(m5, pd.Series(wkey, index=idx), idx, "w")
    X = X.join(dev_d).join(dev_w)

    X["o"], X["h"], X["l"], X["c"], X["v"] = H.o.values, H.h.values, H.l.values, H.c.values, H.v.values
    X["delta"] = (2 * H.tbv - H.v).values
    X["oi_usd"] = H.oi_usd.values
    X["atr"] = atr_wilder(H).values
    X["ret24"] = X.c / X.c.shift(24) - 1
    X["ret4"] = X.c / X.c.shift(4) - 1
    X["oi24"] = X.oi_usd / X.oi_usd.shift(24) - 1
    X["dlt4"] = X.delta.rolling(4).sum() / X.v.rolling(4).sum()
    X["dlt6"] = X.delta.rolling(6).sum() / X.v.rolling(6).sum()
    X["low6"] = X.l.rolling(6).min()
    X["high6"] = X.h.rolling(6).max()
    fr = f.copy(); fr.index = fr.index.tz_convert(None)
    X["fund_last"] = fr.reindex(X.index + pd.Timedelta("1h"), method="ffill").values

    # forward outcomes (long; a short is -gross - cost + funding)
    o = X.o
    fcum = np.concatenate([[0.0], np.cumsum(fr.values)])
    fpos = lambda ts: np.searchsorted(fr.index.values, ts.values.astype("datetime64[ns]"), side="left")
    e_t = X.index + pd.Timedelta("1h")
    e_px = o.shift(-1)
    for hd in holds:
        x_px = o.shift(-(1 + hd))
        x_t = e_t + pd.Timedelta(hours=hd)
        fund = fcum[fpos(x_t)] - fcum[fpos(e_t)]
        X[f"gross{hd}"] = x_px / e_px - 1
        X[f"fund{hd}"] = fund
        X[f"L{hd}"] = X[f"gross{hd}"] - COST_RT - fund
        X[f"S{hd}"] = -X[f"gross{hd}"] - COST_RT + fund
    X["entry_px"] = e_px
    X.index = X.index.tz_localize("UTC")
    return X
