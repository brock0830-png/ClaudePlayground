"""Data layer: 4h bars -> CME weeks, weekly opens, daily ATR(14), v42 weekly levels.

Week bucket = CME week opening Sunday 18:00 ET (prompt). A bar belongs to the week whose
Sunday-18:00 start is the latest one at or before the bar's open time. WO = open of the first
4h bar in the bucket. Timestamps in the CSVs carry their own UTC offset (TradingView exports in
America/Anchorage, UTC-9 winter / UTC-8 summer) and are converted exactly.

The 2021+ period is sealed: load(..., oos=True) refuses to run unless OOS_UNSEALED exists, and
that file is written only by validate_oos.py after rules are frozen.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import (DATA, IS_END, LK_BIAS, LK_VOL, M_BIAS, M_MULT, M_VOL, SEAL_FILE, W_MULT,
                    W_RNG_HALF, GP_INNER, GP_OUTER, LEVELS)

MAXB = 32  # max 4h bars per week (30 in practice)


GC_SEAL = DATA.parent / "GC_UNSEALED"
HOLDOUT = {"GC": DATA / "sealed" / "GC_240_tv_mcp.csv"}   # never read before GC_UNSEALED exists


def read_bars(tk: str) -> pd.DataFrame:
    if tk in HOLDOUT:
        if not GC_SEAL.exists():
            raise PermissionError(f"{tk} is a sealed holdout ticker (GC_UNSEALED absent)")
        path = HOLDOUT[tk]
    else:
        path = DATA / f"{tk}_240.csv"
    df = pd.read_csv(path, usecols=["time", "open", "high", "low", "close"])
    ts = pd.to_datetime(df["time"], utc=True)
    et = ts.dt.tz_convert("America/New_York")
    shifted = (et + pd.Timedelta(hours=6)).dt.tz_localize(None)   # Sun 18:00 ET -> Mon 00:00
    df["ts"] = ts
    df["et"] = et
    df["tdate"] = shifted.dt.normalize()                            # CME trading date
    df["week"] = (shifted - pd.to_timedelta(shifted.dt.weekday, unit="D")).dt.normalize()
    df["month"] = df["tdate"].dt.to_period("M")
    df["hour_et"] = et.dt.hour
    return df.drop(columns=["time"]).reset_index(drop=True)


def wilder_atr(h, l, c, n=14):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    atr = np.full_like(tr, np.nan)
    if len(tr) > n:
        atr[n - 1] = tr[:n].mean()
        for i in range(n, len(tr)):
            atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    return atr


def weekly_levels(tk: str, wo, scale: float = 1.0) -> dict:
    """v42 WEEKLY engine. Returns dict name -> price array. scale multiplies every SD multiplier
    (including the 1.0 inner edge and the 0.078 range half-width) for the x0.95/x1.05 test."""
    wo = np.asarray(wo, dtype=float)
    vol, bias, m = LK_VOL[tk], LK_BIAS[tk], W_MULT[tk]
    sigma = wo * (vol / 100.0) / np.sqrt(52.0)
    ts = sigma * (bias / 0.5)
    bs = sigma * ((1.0 - bias) / 0.5)
    k = scale
    L = {}
    L["GB_TOP"] = wo + ts * m["gbtop"] * k
    L["WTH2"] = wo + ts * m["wth2"] * k
    L["WTH1"] = wo + ts * m["wth1"] * k
    L["GB_BOT"] = wo + ts * 1.0 * k
    L["WRH"] = wo + ts * m["wrh"] * k
    L["WRL"] = wo - bs * m["wrl"] * k
    L["RB_TOP"] = wo - bs * 1.0 * k
    L["WTL1"] = wo - bs * m["wtl1"] * k
    L["WTL2"] = wo - bs * m["wtl2"] * k
    L["RB_BOT"] = wo - bs * m["rbbot"] * k
    inner = L["GB_BOT"] - L["RB_TOP"]
    L["GP_T_OUT"] = L["RB_TOP"] + inner * GP_OUTER
    L["GP_T_IN"] = L["RB_TOP"] + inner * GP_INNER
    L["GP_B_OUT"] = L["RB_TOP"] + inner * (1.0 - GP_OUTER)
    L["GP_B_IN"] = L["RB_TOP"] + inner * (1.0 - GP_INNER)
    rh = sigma * W_RNG_HALF * k
    L["RNG_T_HI"] = L["WRH"] + rh
    L["RNG_T_LO"] = L["WRH"] - rh
    L["RNG_B_HI"] = L["WRL"] + rh
    L["RNG_B_LO"] = L["WRL"] - rh
    L["_sigma"] = sigma
    L["_ts"] = ts
    L["_bs"] = bs
    return L


def monthly_levels(tk: str, mo) -> dict:
    """v42 MONTHLY engine (confluence family only). CL/6J fall back to lk_vol/lk_bias and the
    weekly multipliers, as the pine does for uncalibrated monthly assets."""
    mo = np.asarray(mo, dtype=float)
    vol = M_VOL.get(tk, LK_VOL[tk])
    bias = M_BIAS.get(tk, LK_BIAS[tk])
    m = M_MULT.get(tk, W_MULT[tk])
    sigma = mo * (vol / 100.0) / np.sqrt(12.0)
    ts = sigma * (bias / 0.5)
    bs = sigma * ((1.0 - bias) / 0.5)
    return {
        "M_GB_TOP": mo + ts * m["gbtop"], "M_WTH2": mo + ts * m["wth2"], "M_WTH1": mo + ts * m["wth1"],
        "M_GB_BOT": mo + ts, "M_WRH": mo + ts * m["wrh"], "M_WRL": mo - bs * m["wrl"],
        "M_RB_TOP": mo - bs, "M_WTL1": mo - bs * m["wtl1"], "M_WTL2": mo - bs * m["wtl2"],
        "M_RB_BOT": mo - bs * m["rbbot"], "M_MO": mo,
    }


class Book:
    """Per-ticker weekly panel: padded bar arrays [n_weeks, MAXB] plus a week table."""

    def __init__(self, tk: str, oos: bool = False, full: bool = False):
        if tk in HOLDOUT:
            full = True                       # holdout ticker: every week is out-of-sample
        elif (oos or full) and not SEAL_FILE.exists():
            raise PermissionError("2021+ data is sealed until rules are frozen (OOS_UNSEALED absent)")
        self.tk = tk
        bars = read_bars(tk)
        # ---- daily bars (CME trading date) for ATR(14)
        d = bars.groupby("tdate").agg(o=("open", "first"), h=("high", "max"), l=("low", "min"),
                                      c=("close", "last"))
        d["atr"] = wilder_atr(d.h.values, d.l.values, d.c.values, 14)
        # ---- roll / session-gap flag: any in-week (not first bar) 18:00 ET bar whose open gaps
        # more than 1.0x the rolling median 4h range from the prior close
        gap = (bars["open"] - bars["close"].shift()).abs()
        medr = (bars["high"] - bars["low"]).rolling(60, min_periods=20).median()
        bars["biggap"] = (gap > medr) & (bars["hour_et"] == 18)
        # ---- week table
        g = bars.groupby("week", sort=True)
        wk = pd.DataFrame({
            "start": g.apply(lambda x: x.index[0], include_groups=False),
            "n": g.size(),
            "WO": g["open"].first(),
            "WC": g["close"].last(),
            "WH": g["high"].max(),
            "WL": g["low"].min(),
            "first_tdate": g["tdate"].first(),
            "month": g["month"].first(),
        })
        first_bar_flag = pd.Series(False, index=bars.index)
        first_bar_flag.loc[wk["start"].values] = True
        bars.loc[first_bar_flag, "biggap"] = False
        wk["roll_flag"] = bars.groupby("week")["biggap"].any()
        wk["nonpos"] = g["low"].min() <= 0
        # ATR at week open = last completed trading day's ATR before the week's first trading date
        d_idx = d.index.values
        pos = np.searchsorted(d_idx, wk["first_tdate"].values, side="left") - 1
        wk["atr"] = np.where(pos >= 0, d["atr"].values[np.clip(pos, 0, None)], np.nan)
        # prior week stats (for filters)
        wk["pWO"] = wk["WO"].shift()
        wk["pWC"] = wk["WC"].shift()
        wk["pWH"] = wk["WH"].shift()
        wk["pWL"] = wk["WL"].shift()
        # monthly open: first bar open of the CME month (trading-date month)
        mo = bars.groupby("month")["open"].first()
        wk["MO"] = wk["month"].map(mo)
        # ---- seal
        if full:
            pass
        elif oos:
            wk = wk[wk.index >= pd.Timestamp(IS_END)]
        else:
            wk = wk[wk.index < pd.Timestamp(IS_END)]
        # drop the first (partial) week of each file and weeks without ATR
        wk = wk.iloc[1:] if wk.index[0] == bars["week"].iloc[0] else wk
        wk = wk[wk["atr"].notna()]
        self.weeks = wk
        self.bars = bars
        self.daily = d
        # ---- padded arrays
        nW = len(wk)
        O = np.full((nW, MAXB), np.nan); H = O.copy(); Lo = O.copy(); C = O.copy()
        HR = np.full((nW, MAXB), -1, dtype=np.int64)
        DOW = np.full((nW, MAXB), -1, dtype=np.int64)
        TS = np.zeros((nW, MAXB), dtype="datetime64[s]")
        nb = np.zeros(nW, dtype=np.int64)
        bo, bh, bl, bc = (bars[c].values for c in ["open", "high", "low", "close"])
        hr = bars["hour_et"].values
        dow = bars["tdate"].dt.weekday.values
        tsv = bars["ts"].dt.tz_localize(None).values.astype("datetime64[s]")
        for i, (s, n) in enumerate(zip(wk["start"].values, wk["n"].values)):
            n = min(n, MAXB)
            sl = slice(s, s + n)
            O[i, :n], H[i, :n], Lo[i, :n], C[i, :n] = bo[sl], bh[sl], bl[sl], bc[sl]
            HR[i, :n] = hr[sl]; DOW[i, :n] = dow[sl]; TS[i, :n] = tsv[sl]
            nb[i] = n
        self.O, self.H, self.L, self.C, self.HR, self.DOW, self.TS, self.nb = O, H, Lo, C, HR, DOW, TS, nb
        self.wo = wk["WO"].values.astype(float)
        self.atr = wk["atr"].values.astype(float)
        self.year = wk.index.year.values
        self.levels = weekly_levels(tk, self.wo)
        self.sigma = self.levels["_sigma"]
        self.mlev = monthly_levels(tk, wk["MO"].values.astype(float))

    def level_matrix(self, scale: float = 1.0) -> dict:
        return weekly_levels(self.tk, self.wo, scale)


def load_all(oos=False, full=False, tickers=None):
    from common import TICKERS
    return {tk: Book(tk, oos=oos, full=full) for tk in (tickers or TICKERS)}
