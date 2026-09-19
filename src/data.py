"""Load raw FMP pulls into clean daily series.

All price series are dividend-adjusted closes (total return) except the
index symbols (GSPC, NDX, RUT, VIX, GCUSD), which are price only.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "fmp"


def load_close(sym: str) -> pd.Series:
    df = pd.read_parquet(RAW / f"{sym}.parquet")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    col = "adjClose" if "adjClose" in df.columns else ("close" if "close" in df.columns else "price")
    s = df[col].astype(float)
    s = s[s > 0]
    s.name = sym
    return s


def load_volume(sym: str) -> pd.Series:
    df = pd.read_parquet(RAW / f"{sym}.parquet")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    return df["volume"].astype(float)


def load_treasury() -> pd.DataFrame:
    """Constant-maturity Treasury yields in decimal, weekdays only, forward-filled gaps."""
    t = pd.read_parquet(RAW / "TREASURY.parquet")
    t["date"] = pd.to_datetime(t["date"])
    t = t.set_index("date").sort_index()
    t = t[t.index.dayofweek < 5]
    t = t.rename(columns={"month1": "m1", "month2": "m2", "month3": "m3", "month6": "m6",
                          "year1": "y1", "year2": "y2", "year3": "y3", "year5": "y5",
                          "year7": "y7", "year10": "y10", "year20": "y20", "year30": "y30"})
    return t.astype(float) / 100.0


def trading_calendar(start="1993-01-29", end=None) -> pd.DatetimeIndex:
    """SPY trading dates. For starts before SPY's first print (1993-01-29) the S&P 500 index (GSPC)
    dates are used for the pre-SPY segment so the post-1993 calendar is unchanged."""
    spy = load_close("SPY")
    idx = spy.index[spy.index >= pd.Timestamp(start)]
    if pd.Timestamp(start) < spy.index[0]:
        g = load_close("GSPC").index
        idx = g[(g >= pd.Timestamp(start)) & (g < spy.index[0])].append(idx)
    if end is not None:
        idx = idx[idx <= pd.Timestamp(end)]
    return idx
