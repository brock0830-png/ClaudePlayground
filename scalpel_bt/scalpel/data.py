"""
Bar data, period ids, roll flags, VIX, and the DEV/OOS split with the OOS lock.

Everything that runs a strategy must get its bars from `load_bars(split)`.
"""
from __future__ import annotations
import os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
EXPORT = DATA / "es_levels_CME_MINI_ES1_240.csv.gz"

DEV_START = pd.Timestamp("2010-01-01", tz="America/New_York")
DEV_END = pd.Timestamp("2019-12-31 23:59:59", tz="America/New_York")
OOS_START = pd.Timestamp("2020-01-01", tz="America/New_York")
OOS_LOCK = RESULTS / "OOS_UNLOCKED"

TICK = 0.25
PT_USD = 50.0            # ES $ per point
COST_RT_PTS = 2 * TICK + 2 * 2.50 / PT_USD   # 1 tick slip per side + $2.50/side = 0.60 pt


def read_export(path: Path | str = EXPORT) -> pd.DataFrame:
    """Raw export, tz-aware America/New_York index. Duplicate v37 weekly columns get '.1'."""
    df = pd.read_csv(path)
    df.index = pd.DatetimeIndex(pd.to_datetime(df["time"], utc=True).dt.tz_convert("America/New_York"))
    df.index.name = "time"
    return df


def _period_ids(idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Session day (18:00 ET start), month of that session, and ISO-like week id."""
    t = idx.to_series()
    # bars at 18,22,02,06,10,14 ET; +6h puts every bar of a session on its trading date
    tday = (t.dt.tz_localize(None) + pd.Timedelta(hours=6)).dt.normalize()
    out = pd.DataFrame(index=idx)
    out["tday"] = tday.values
    out["month"] = tday.dt.to_period("M").astype(str).values
    return out


def _blocks(b: pd.DataFrame, col: str, derived_new: pd.Series) -> tuple[pd.Series, pd.Series]:
    """
    Period blocks from changes in the exported open `col`; a derived boundary with the
    bar opening exactly at the (unchanged) value also starts a block (coincidence case).
    Returns (block id, lookahead flag). A bar is flagged when its block's open is the
    open of a LATER bar of the same block (TradingView orphan bars, e.g. Thursday-evening
    sessions before a July-4 Friday), i.e. the level was not yet knowable.
    """
    v = b[col]
    new = (v != v.shift()) | (derived_new & ((b["open"] - v).abs() < 1e-9))
    bid = new.cumsum()
    hit = (b["open"] - v).abs() < 1e-9
    pos = pd.Series(np.arange(len(b)), index=b.index)
    first_hit = pos.where(hit).groupby((v != v.shift()).cumsum()).transform("min")
    look = first_hit.notna() & (pos < first_hit)
    return bid, look


def build_bars(raw: pd.DataFrame) -> pd.DataFrame:
    """OHLC + exported period opens + period blocks + lookahead and roll flags."""
    from .levels import weekly_id
    b = raw[["open", "high", "low", "close", "DO", "WO", "MO"]].copy()
    b = b.join(_period_ids(b.index))
    t = b.index.to_series()
    gap_h = t.diff().dt.total_seconds().div(3600).fillna(1e9)
    b["day_id"], la_d = _blocks(b, "DO", b["tday"] != b["tday"].shift())
    b["week_id"], la_w = _blocks(b, "WO", gap_h >= 40)
    b["month_id"], la_m = _blocks(b, "MO", b["month"] != b["month"].shift())
    b["lookahead_D"], b["lookahead_W"], b["lookahead_M"] = la_d, la_w, la_m
    b["wk_derived"] = weekly_id(b).values
    # roll flags: switch bar = first bar of the switch trading day (18:00 ET session start)
    rt = roll_table()
    b["roll_switch_bar"] = False
    if len(rt):
        sw = set(pd.to_datetime(rt["switch_tday"]).dt.normalize())
        first_of_day = b["tday"] != b["tday"].shift()
        b["roll_switch_bar"] = first_of_day & b["tday"].isin(sw)
    sw_week = b.groupby("week_id")["roll_switch_bar"].transform("any")
    b["roll_week"] = sw_week
    # monthly levels are stale from the switch to month end
    after = b.groupby("month_id")["roll_switch_bar"].cumsum() > 0
    b["roll_month_after"] = after
    return b


def load_bars(split: str = "dev") -> pd.DataFrame:
    """split in {'dev','oos','all'}; 'oos'/'all' need results/OOS_UNLOCKED."""
    if split in ("oos", "all") and not OOS_LOCK.exists():
        raise PermissionError("OOS is locked. Freeze rules and commit first (see PROTOCOL.md).")
    b = build_bars(read_export())
    if split == "dev":
        b = b[b.index <= DEV_END]
    elif split == "oos":
        # keep the DEV tail for warm-up of rolling features; callers trade only >= OOS_START
        pass
    return b


def load_vix(name: str = "VIX") -> pd.Series:
    v = pd.read_csv(DATA / "external" / f"{name}_History.csv")
    v.index = pd.to_datetime(v["DATE"], format="%m/%d/%Y")
    return v["CLOSE"].astype(float).rename(name)


def load_spx_daily() -> pd.Series:
    v = pd.read_csv(DATA / "external" / "SPX_History.csv")
    v.index = pd.to_datetime(v["DATE"], format="%m/%d/%Y")
    return v["SPX"].astype(float)


def daily_ohlc(bars: pd.DataFrame) -> pd.DataFrame:
    """Session-day OHLC (18:00 ET start) from 4h bars."""
    g = bars.groupby("tday")
    d = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(),
                      "low": g["low"].min(), "close": g["close"].last()})
    return d


def roll_table() -> pd.DataFrame:
    """Detected TradingView contract switches (see scripts/detect_rolls.py)."""
    p = DATA / "roll_dates.csv"
    return pd.read_csv(p, parse_dates=["switch_tday"]) if p.exists() else pd.DataFrame()
