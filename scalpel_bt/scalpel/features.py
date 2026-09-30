"""
Per-bar arrays used by every strategy: period opens/ids/ends for D/W/M, sigma for each
vol mode (fixed / scaled / ewma_rs), and point-in-time filters (trend, VIX regime).
Everything here uses only information available before the bar it is attached to,
except the period open itself, which is the open of the period's first bar.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from .data import load_vix, DEV_END
from .levelsets import FIXED_VOL, PERIODS, sigma_from_vol

TF_ID = {"D": "day_id", "W": "week_id", "M": "month_id"}
TF_OPEN = {"D": "DO", "W": "WO", "M": "MO"}
EWMA_LAMBDA = 0.924


@dataclass
class Frame:
    bars: pd.DataFrame
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    po: dict = field(default_factory=dict)        # tf -> period open per bar
    pid: dict = field(default_factory=dict)       # tf -> period id per bar (int64)
    pend: dict = field(default_factory=dict)      # tf -> bool, last bar of period
    pstart: dict = field(default_factory=dict)    # tf -> bool, first bar of period
    sigma: dict = field(default_factory=dict)     # (tf, mode) -> sigma per bar (points)
    vol: dict = field(default_factory=dict)       # (tf, mode) -> vol % per bar
    no_signal: dict = field(default_factory=dict) # tf -> bool, lookahead bars
    force_flat: np.ndarray = None                 # must be flat at this bar's close
    feat: pd.DataFrame = None                     # filters, per bar


def _prior_vix_mean(vix: pd.Series, dates: pd.Series, window: int = 252) -> np.ndarray:
    """Mean of the last `window` VIX closes strictly before each date."""
    m = vix.rolling(window, min_periods=window).mean()
    idx = np.searchsorted(m.index.values, dates.values.astype("datetime64[ns]"), side="left") - 1
    out = np.where(idx >= 0, m.values[np.clip(idx, 0, None)], np.nan)
    return out


def _prior_vix_close(vix: pd.Series, dates: pd.Series) -> np.ndarray:
    idx = np.searchsorted(vix.index.values, dates.values.astype("datetime64[ns]"), side="left") - 1
    return np.where(idx >= 0, vix.values[np.clip(idx, 0, None)], np.nan)


def session_days(bars: pd.DataFrame) -> pd.DataFrame:
    """Daily OHLC per D block (TradingView trading day), with its trading date."""
    g = bars.groupby("day_id")
    d = pd.DataFrame({"tday": g["tday"].last(), "open": g["open"].first(), "high": g["high"].max(),
                      "low": g["low"].min(), "close": g["close"].last(), "DO": g["DO"].first()})
    return d


def ewma_rs_vol(days: pd.DataFrame, lam: float = EWMA_LAMBDA, warm: int = 20) -> pd.Series:
    """Annualised % vol per D block from EWMA Rogers-Satchell, using blocks strictly before."""
    o, h, l, c = (days[x].values for x in ("open", "high", "low", "close"))
    rs = np.log(h / c) * np.log(h / o) + np.log(l / c) * np.log(l / o)
    var = np.full(len(rs), np.nan)
    v = np.nan
    for i in range(len(rs)):
        var[i] = v                      # value known before block i
        if i + 1 == warm:
            v = rs[:warm].mean()
        elif i + 1 > warm:
            v = lam * v + (1 - lam) * rs[i]
    return pd.Series(100 * np.sqrt(252 * var), index=days.index)


def build_frame(bars: pd.DataFrame) -> Frame:
    b = bars
    fr = Frame(bars=b, o=b["open"].values.astype(float), h=b["high"].values.astype(float),
               l=b["low"].values.astype(float), c=b["close"].values.astype(float))
    vix = load_vix("VIX")
    n = len(b)
    for tf in "DWM":
        idc = b[TF_ID[tf]].values.astype(np.int64)
        fr.pid[tf] = idc
        fr.po[tf] = b[TF_OPEN[tf]].values.astype(float)
        fr.pstart[tf] = np.r_[True, idc[1:] != idc[:-1]]
        fr.pend[tf] = np.r_[idc[1:] != idc[:-1], True]
        fr.no_signal[tf] = b[f"lookahead_{tf}"].values.astype(bool)
        # fixed
        fr.vol[(tf, "fixed")] = np.full(n, FIXED_VOL[tf])
        # scaled: 252d mean VIX as of the last VIX close before the period's first trading date
        first_tday = b.groupby(TF_ID[tf])["tday"].transform("first")
        fr.vol[(tf, "scaled")] = _prior_vix_mean(vix, first_tday)
    days = session_days(b)
    ew = ewma_rs_vol(days)
    fr.vol[("D", "ewma_rs")] = b["day_id"].map(ew).values
    for (tf, mode), v in fr.vol.items():
        fr.sigma[(tf, mode)] = sigma_from_vol(fr.po[tf], v, tf)

    # force flat: close of the bar before each contract switch, and the last bar of the data
    ff = np.zeros(n, dtype=bool)
    sw = b["roll_switch_bar"].values
    ff[:-1] |= sw[1:]
    ff[-1] = True
    fr.force_flat = ff

    # ---- filters, point in time (known at the start of each bar) ----
    f = pd.DataFrame(index=b.index)
    dcl = days["close"]
    ma20, ma50 = dcl.rolling(20).mean(), dcl.rolling(50).mean()
    # state as of the previous completed session
    prev = lambda s: b["day_id"].map(s.shift(1)).values
    f["prev_close"] = prev(dcl)
    f["ma20"] = prev(ma20)
    f["ma50"] = prev(ma50)
    f["vix_prev"] = _prior_vix_close(vix, b["tday"])
    f["vix_mean252"] = _prior_vix_mean(vix, b["tday"])
    f["dow"] = b["tday"].dt.dayofweek.values
    f["roll_week"] = b["roll_week"].values
    f["roll_month_after"] = b["roll_month_after"].values
    f["year"] = b["tday"].dt.year.values
    fr.feat = f
    return fr
