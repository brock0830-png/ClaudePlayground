"""Load and cache per-coin series from data.binance.vision.

klines_1m(sym)  1-minute futures klines incl. taker-buy volume (= per-minute delta), UTC index
hourly(sym)     1h bars resampled from the 1m bars, plus OI value at each bar's close
funding(sym)    funding events (time, rate)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import fetch
from .config import END, LOOKBACK_START, PQ

KCOLS = ["open_time", "o", "h", "l", "c", "v", "close_time", "qv", "n", "tbv", "tbqv", "ignore"]
TAIL_DAYS = 3          # daily files after END so trades entered on the last day can exit


def _ts_ms(x: pd.Series) -> pd.DatetimeIndex:
    x = x.astype("int64")
    unit = "us" if x.iloc[0] > 10 ** 14 else "ms"
    return pd.to_datetime(x, unit=unit, utc=True)


def _parse_klines(path) -> pd.DataFrame:
    d = fetch.read_zip_csv(path)
    d = d.iloc[:, :12]
    d.columns = KCOLS
    d.index = _ts_ms(d.open_time)
    d = d[["o", "h", "l", "c", "v", "qv", "n", "tbv", "tbqv"]].astype("float64")
    return d


def klines_1m(sym: str, refresh: bool = False) -> pd.DataFrame:
    out = PQ / "klines1m" / f"{sym}.parquet"
    if out.exists() and not refresh:
        return pd.read_parquet(out)
    last_month_end = END - pd.Timedelta("1ms")
    rels = [fetch.klines_rel(sym, "1m", m) for m in fetch.months(LOOKBACK_START, last_month_end)]
    rels += [fetch.klines_rel(sym, "1m", d, monthly=False)
             for d in fetch.days(END, END + pd.Timedelta(days=TAIL_DAYS - 1))]
    got = fetch.get_many(rels, workers=8, label=f"{sym} 1m")
    parts = [_parse_klines(p) for r, p in sorted(got.items()) if p is not None]
    if not parts:
        raise RuntimeError(f"no klines for {sym}")
    d = pd.concat(parts)
    d = d[~d.index.duplicated(keep="last")].sort_index()
    out.parent.mkdir(parents=True, exist_ok=True)
    d.to_parquet(out)
    return d


def oi_5m(sym: str, refresh: bool = False) -> pd.DataFrame:
    """sum_open_interest (coins) and sum_open_interest_value (USD) at 5-minute stamps."""
    out = PQ / "oi5m" / f"{sym}.parquet"
    if out.exists() and not refresh:
        return pd.read_parquet(out)
    rels = [fetch.metrics_rel(sym, d) for d in fetch.days(LOOKBACK_START, END + pd.Timedelta(days=TAIL_DAYS - 1))]
    got = fetch.get_many(rels, workers=16, label=f"{sym} metrics")
    parts = []
    for r, p in sorted(got.items()):
        if p is None:
            continue
        d = fetch.read_zip_csv(p)
        if len(d) == 0:
            continue
        d = d.rename(columns=str.lower)
        t = pd.to_datetime(d["create_time"], utc=True)
        parts.append(pd.DataFrame({"oi": pd.to_numeric(d["sum_open_interest"], errors="coerce").values,
                                   "oi_usd": pd.to_numeric(d["sum_open_interest_value"], errors="coerce").values,
                                   "taker_ls": pd.to_numeric(d.get("sum_taker_long_short_vol_ratio"), errors="coerce").values
                                   if "sum_taker_long_short_vol_ratio" in d else np.nan},
                                  index=t))
    d = pd.concat(parts)
    d = d[~d.index.duplicated(keep="last")].sort_index()
    out.parent.mkdir(parents=True, exist_ok=True)
    d.to_parquet(out)
    return d


def funding(sym: str, refresh: bool = False) -> pd.Series:
    out = PQ / "funding" / f"{sym}.parquet"
    if out.exists() and not refresh:
        return pd.read_parquet(out)["rate"]
    rels = [fetch.funding_rel(sym, m) for m in fetch.months(LOOKBACK_START, END + pd.Timedelta(days=31))]
    got = fetch.get_many(rels, workers=8, label=f"{sym} funding")
    parts = []
    for r, p in sorted(got.items()):
        if p is None:
            continue
        d = fetch.read_zip_csv(p)
        d = d.rename(columns=str.lower)
        tcol = "calc_time" if "calc_time" in d else d.columns[0]
        rcol = "last_funding_rate" if "last_funding_rate" in d else d.columns[-1]
        parts.append(pd.Series(pd.to_numeric(d[rcol]).values, index=_ts_ms(d[tcol]).floor("min"), name="rate"))
    s = pd.concat(parts).sort_index() if parts else pd.Series(dtype=float, name="rate")
    s = s[~s.index.duplicated(keep="last")]
    out.parent.mkdir(parents=True, exist_ok=True)
    s.to_frame().to_parquet(out)
    return s


def resample_1h(m: pd.DataFrame) -> pd.DataFrame:
    g = m.resample("1h", label="left", closed="left")
    h = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(),
                      "v": g.v.sum(), "qv": g.qv.sum(), "tbv": g.tbv.sum(), "n_min": g.c.count()})
    return h


def hourly(sym: str, refresh: bool = False) -> pd.DataFrame:
    """1h bars (index = bar open time) with oi / oi_usd at the bar's close (last 5m stamp <= close)."""
    out = PQ / "hourly" / f"{sym}.parquet"
    if out.exists() and not refresh:
        return pd.read_parquet(out)
    h = resample_1h(klines_1m(sym))
    full = pd.date_range(h.index[0], h.index[-1], freq="1h")
    h = h.reindex(full)
    oi = oi_5m(sym)
    close_t = h.index + pd.Timedelta("1h")
    # OI snapshot at the bar close: the latest 5m stamp at or before the close, no older than 15 min
    pos = oi.index.searchsorted(close_t, side="right") - 1
    ok = pos >= 0
    stamp = pd.DatetimeIndex(np.where(ok, oi.index.values[np.clip(pos, 0, None)], np.datetime64("NaT")), tz="UTC")
    fresh = ok & ((close_t - stamp) <= pd.Timedelta("15min"))
    for col in ["oi", "oi_usd"]:
        v = oi[col].values[np.clip(pos, 0, None)]
        h[col] = np.where(fresh, v, np.nan)
    out.parent.mkdir(parents=True, exist_ok=True)
    h.to_parquet(out)
    return h
