"""Phase 2 context features, computed from the 4h bars only, with no look-ahead.

Everything a filter uses is known before the entry it gates:
  * week-level values use data up to the close of the last trading day before the week opens;
  * bar-level signals gate an entry bar with information available at the close of the bar before
    it (for next-open entries that is the signal bar itself).

Features
  regime      daily closes: SMA50, SMA200, SMA200 twenty days earlier, drawdown from the 252-day
              high of closes. reg200 = sign(close - SMA200); reg5020 = sign(SMA50 - SMA200);
              regstrong = +1 if close > SMA200 and SMA200 rising, -1 if close < SMA200 and falling.
  profile     prior-week market profile, TPO proxy: every 4h bar spreads its time (1.0, or 0.75
              for the 3-hour 14:00 ET bar) evenly over the price bins inside its high-low range;
              bin = 0.02 weekly sigma. POC = fullest bin (ties -> nearest the range midpoint);
              value area = POC plus the fuller neighbouring bin, repeatedly, until 70% of time.
              No volume is used - the exports have none.
  rsi div     Wilder RSI(14). A pivot low is a bar whose low is below the 2 bars before it and
              not above the 2 bars after it (so it is confirmed 2 bars later). Bullish divergence
              at bar j: the latest pivot low confirmed by j lies within the lookback, bar j's low
              is below it and RSI(j) is above RSI at the pivot. Bearish mirrors it on highs.
              4h: lookback 30 bars, signal counts for 3 bars. Daily: lookback 20 days, 3 days.
  s/r         prior trading day high / low (per bar); daily swing pivots (k = 2) confirmed before
              the week, from the last 20 trading days; prior-week high / low.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

from data import MAXB

BIN_SIG = 0.02
VA_FRAC = 0.70


# ------------------------------------------------------------------ primitives
def wilder_rsi(c, n=14):
    """Wilder RSI (RMA seeded with the simple mean, as TradingView's ta.rsi)."""
    c = np.asarray(c, float)
    rsi = np.full(len(c), np.nan)
    if len(c) <= n:
        return rsi
    d = np.diff(c)
    up = np.clip(d, 0, None)
    dn = np.clip(-d, 0, None)
    au, ad = up[:n].mean(), dn[:n].mean()
    rsi[n] = 100.0 if ad == 0 else 100.0 - 100.0 / (1.0 + au / ad)
    for i in range(n, len(d)):
        au = (au * (n - 1) + up[i]) / n
        ad = (ad * (n - 1) + dn[i]) / n
        rsi[i + 1] = 100.0 if ad == 0 else 100.0 - 100.0 / (1.0 + au / ad)
    return rsi


@njit(cache=True)
def divergence(L, H, rsi, k, lookback):
    """bull[j], bear[j] per the module docstring (pivot confirmed k bars after it)."""
    n = len(L)
    bull = np.zeros(n, np.bool_)
    bear = np.zeros(n, np.bool_)
    last_lo = -1
    last_hi = -1
    for j in range(n):
        p = j - k                      # the newest bar that can be confirmed as a pivot at j
        if p - k >= 0:
            is_lo = True
            is_hi = True
            for q in range(p - k, p):
                if not (L[p] < L[q]):
                    is_lo = False
                if not (H[p] > H[q]):
                    is_hi = False
            for q in range(p + 1, p + k + 1):
                if L[p] > L[q]:
                    is_lo = False
                if H[p] < H[q]:
                    is_hi = False
            if is_lo:
                last_lo = p
            if is_hi:
                last_hi = p
        if last_lo >= 0 and j - last_lo <= lookback and j > last_lo + k - 1:
            if L[j] < L[last_lo] and np.isfinite(rsi[j]) and np.isfinite(rsi[last_lo]) and rsi[j] > rsi[last_lo]:
                bull[j] = True
        if last_hi >= 0 and j - last_hi <= lookback and j > last_hi + k - 1:
            if H[j] > H[last_hi] and np.isfinite(rsi[j]) and np.isfinite(rsi[last_hi]) and rsi[j] < rsi[last_hi]:
                bear[j] = True
    return bull, bear


def recent(x, w):
    """True if x was True in any of the last w elements (inclusive)."""
    s = pd.Series(x.astype(float)).rolling(w, min_periods=1).max().values
    return s > 0


def tpo_profile(H, L, wt, bin_size):
    """POC, VAH, VAL of one period from its bars (TPO proxy)."""
    lo = np.floor(np.nanmin(L) / bin_size)
    hi = np.ceil(np.nanmax(H) / bin_size)
    nb = int(hi - lo) + 1
    if nb <= 0 or nb > 100000:
        return np.nan, np.nan, np.nan
    hist = np.zeros(nb)
    centers = (lo + np.arange(nb) + 0.5) * bin_size
    for h, l, w in zip(H, L, wt):
        m = (centers >= l) & (centers <= h)
        if not m.any():
            k = int(np.clip(np.floor((0.5 * (h + l)) / bin_size) - lo, 0, nb - 1))
            hist[k] += w
        else:
            hist[m] += w / m.sum()
    mx = hist.max()
    cand = np.flatnonzero(np.isclose(hist, mx))
    mid = 0.5 * (np.nanmax(H) + np.nanmin(L))
    poc = cand[np.argmin(np.abs(centers[cand] - mid))]
    tot = hist.sum()
    a = b = poc
    acc = hist[poc]
    while acc < VA_FRAC * tot - 1e-12:
        up = hist[b + 1] if b + 1 < nb else -1.0
        dn = hist[a - 1] if a - 1 >= 0 else -1.0
        if up < 0 and dn < 0:
            break
        if up >= dn:
            b += 1
            acc += up
        else:
            a -= 1
            acc += dn
    return centers[poc], (lo + b + 1) * bin_size, (lo + a) * bin_size


# ------------------------------------------------------------------ build per ticker
def build(b):
    """Attach b.F (dict of arrays aligned to b.weeks / padded bars). Idempotent."""
    if getattr(b, "F", None) is not None:
        return b.F
    from common import LK_VOL
    bars, d, wk = b.bars, b.daily.copy(), b.weeks
    nW = len(wk)
    starts = wk["start"].values
    F = {}
    # ---------------- daily regime (value of the previous trading day, per trading date)
    c = d["c"]
    d["sma50"] = c.rolling(50).mean()
    d["sma200"] = c.rolling(200).mean()
    d["sma200_20"] = d["sma200"].shift(20)
    d["hi252"] = c.rolling(252, min_periods=200).max()
    d["dd"] = 1.0 - c / d["hi252"]
    d["rsi"] = wilder_rsi(c.values, 14)
    bd, sd_ = divergence(d["l"].values, d["h"].values, d["rsi"].values, 2, 20)
    d["divb"] = recent(bd, 3)
    d["divs"] = recent(sd_, 3)
    prev = d.shift(1)                              # row t holds values known at the open of day t
    tdi = {t: i for i, t in enumerate(d.index)}
    wpos = np.array([tdi[t] for t in wk["first_tdate"].values])
    pv = prev.iloc[wpos]
    close_prev = pv["c"].values
    s200 = pv["sma200"].values
    F["reg200"] = np.where(np.isfinite(s200), np.sign(close_prev - s200), np.nan)
    F["reg5020"] = np.where(np.isfinite(s200), np.sign(pv["sma50"].values - s200), np.nan)
    rising = pv["sma200"].values > pv["sma200_20"].values
    F["regstrong"] = np.where(~np.isfinite(pv["sma200_20"].values), np.nan,
                              np.where((close_prev > s200) & rising, 1.0,
                                       np.where((close_prev < s200) & ~rising, -1.0, 0.0)))
    F["dd252"] = pv["dd"].values
    # ---------------- per-bar daily values (prior trading day)
    bpos = np.array([tdi[t] for t in bars["tdate"].values])
    pdh = prev["h"].values[bpos]
    pdl = prev["l"].values[bpos]
    divb_d = prev["divb"].values[bpos].astype(float)
    divs_d = prev["divs"].values[bpos].astype(float)
    # ---------------- 4h RSI divergence, known at the close of the bar before the entry bar
    rsi4 = wilder_rsi(bars["close"].values, 14)
    b4, s4 = divergence(bars["low"].values, bars["high"].values, rsi4, 2, 30)
    b4 = recent(b4, 3)
    s4 = recent(s4, 3)
    b4_prev = np.r_[False, b4[:-1]]
    s4_prev = np.r_[False, s4[:-1]]

    def pad(x, fill=np.nan, dtype=float):
        out = np.full((nW, MAXB), fill, dtype=dtype)
        for i, (s, n) in enumerate(zip(starts, b.nb)):
            out[i, :n] = x[s:s + n]
        return out

    F["pdh"] = pad(pdh)
    F["pdl"] = pad(pdl)
    F["div4_bull"] = pad(b4_prev, False, np.bool_)
    F["div4_bear"] = pad(s4_prev, False, np.bool_)
    F["divD_bull"] = pad(divb_d > 0, False, np.bool_)
    F["divD_bear"] = pad(divs_d > 0, False, np.bool_)
    # ---------------- prior-week TPO profile (computed on every week of the file, then shifted)
    wt_all = np.where(bars["hour_et"].values == 14, 0.75, 1.0)
    prof = {}
    vol = LK_VOL[b.tk] / 100.0 / np.sqrt(52.0)
    for wlab, g in bars.groupby("week", sort=True):
        wo = g["open"].iloc[0]
        prof[wlab] = tpo_profile(g["high"].values, g["low"].values, wt_all[g.index.values], BIN_SIG * wo * vol)
    labels = sorted(prof)
    pidx = {w: i for i, w in enumerate(labels)}
    ppoc = np.full(nW, np.nan); pvah = ppoc.copy(); pval = ppoc.copy()
    for i, w in enumerate(wk.index):
        j = pidx[w] - 1
        if j >= 0:
            ppoc[i], pvah[i], pval[i] = prof[labels[j]]
    F["pPOC"], F["pVAH"], F["pVAL"] = ppoc, pvah, pval
    # ---------------- daily swing pivots confirmed before the week (last 20 trading days)
    dh, dl = d["h"].values, d["l"].values
    nd = len(d)
    ph = np.zeros(nd, bool); pl = np.zeros(nd, bool)
    for i in range(2, nd - 2):
        ph[i] = dh[i] > dh[i - 2:i].max() and dh[i] >= dh[i + 1:i + 3].max()
        pl[i] = dl[i] < dl[i - 2:i].min() and dl[i] <= dl[i + 1:i + 3].min()
    K = 10
    piv_hi = np.full((nW, K), np.nan); piv_lo = np.full((nW, K), np.nan)
    for i, p0 in enumerate(wpos):
        # pivot at day q is confirmed after day q+2 closes -> usable if q + 2 <= p0 - 1
        qs = np.arange(max(0, p0 - 20), max(0, p0 - 2))
        hq = qs[ph[qs]][-K:]
        lq = qs[pl[qs]][-K:]
        piv_hi[i, :len(hq)] = dh[hq]
        piv_lo[i, :len(lq)] = dl[lq]
    F["piv_hi"], F["piv_lo"] = piv_hi, piv_lo
    # ---------------- round 2 additions
    # 4-week composite profile POC (bars of the four weeks before this one)
    cpoc = np.full(nW, np.nan)
    wl = bars["week"].values
    for i, w in enumerate(wk.index):
        j = pidx[w]
        if j >= 4:
            m = (wl >= labels[j - 4]) & (wl < w)
            g = bars.loc[m]
            wo = g["open"].iloc[0]
            cpoc[i] = tpo_profile(g["high"].values, g["low"].values, wt_all[g.index.values], BIN_SIG * wo * vol)[0]
    F["cPOC4"] = cpoc
    # 4h RSI at the close of the bar before each bar
    F["rsi4_prev"] = pad(np.r_[np.nan, rsi4[:-1]])
    # short-term daily trend: prior-day close vs its 20-day SMA, per bar
    sma20 = d["c"].rolling(20).mean()
    t20 = np.sign(d["c"] - sma20).shift(1).values[bpos]
    F["trend20"] = pad(t20)
    b.F = F
    return F
