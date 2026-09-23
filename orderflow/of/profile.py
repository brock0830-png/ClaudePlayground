"""Volume profile, POC and 70% value area (SPEC "Profiles" section), and Wilder ATR.

Rows: `nrows` equal price rows spanning [L, H] of the profile; a trade at price p goes to
row min(floor((p - L) / (H - L) * nrows), nrows - 1).
POC: the row with the most volume; ties -> the row nearest the middle of the range, then the lower row.
Value area: start at the POC row and add ONE row at a time, whichever of the next row above /
next row below has more volume (tie -> above), until >= 70% of the volume is inside.
VAL = lower edge of the lowest VA row, VAH = upper edge of the highest, POC price = POC row midpoint.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class VA:
    lo: float
    hi: float
    poc: float
    val: float
    vah: float
    hist: np.ndarray


def rows_of(p: np.ndarray, lo: float, hi: float, nrows: int) -> np.ndarray:
    if hi <= lo:
        return np.zeros(len(p), dtype=int)
    return np.minimum(((p - lo) / (hi - lo) * nrows).astype(int), nrows - 1)


def value_area(hist: np.ndarray, lo: float, hi: float, share: float = 0.70) -> VA:
    n = len(hist)
    w = (hi - lo) / n if hi > lo else 0.0
    mx = hist.max()
    cand = np.flatnonzero(hist == mx)
    mid = (n - 1) / 2
    poc = int(cand[np.lexsort((cand, np.abs(cand - mid)))][0])
    target = share * hist.sum()
    a = b = poc
    acc = hist[poc]
    while acc < target:
        up = hist[b + 1] if b + 1 < n else -1.0
        dn = hist[a - 1] if a - 1 >= 0 else -1.0
        if up < 0 and dn < 0:
            break
        if up >= dn:
            b += 1; acc += up
        else:
            a -= 1; acc += dn
    return VA(lo, hi, lo + (poc + 0.5) * w, lo + a * w, lo + (b + 1) * w, hist)


def profile_from_trades(p: np.ndarray, q: np.ndarray, nrows: int = 50) -> VA:
    lo, hi = float(p.min()), float(p.max())
    r = rows_of(p, lo, hi, nrows)
    hist = np.bincount(r, weights=q, minlength=nrows).astype(float)
    return value_area(hist, lo, hi)


def profile_from_bars(l: np.ndarray, h: np.ndarray, v: np.ndarray, nrows: int = 50,
                      lo: float | None = None, hi: float | None = None) -> VA:
    """Approximate profile from OHLC bars: each bar's volume spread evenly over the rows its
    [low, high] touches (the standard bar-based approximation when trades are not used)."""
    lo = float(np.nanmin(l)) if lo is None else lo
    hi = float(np.nanmax(h)) if hi is None else hi
    hist = np.zeros(nrows)
    if hi <= lo:
        hist[0] = np.nansum(v)
        return value_area(hist, lo, hi)
    ra = rows_of(l, lo, hi, nrows)
    rb = rows_of(h, lo, hi, nrows)
    cnt = rb - ra + 1
    per = np.where(cnt > 0, v / cnt, 0.0)
    # difference-array trick: add per[i] to rows ra[i]..rb[i]
    diff = np.zeros(nrows + 1)
    np.add.at(diff, ra, per)
    np.add.at(diff, rb + 1, -per)
    hist = np.cumsum(diff[:-1])
    return value_area(hist, lo, hi)


def atr_wilder(h: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = h.c.shift(1)
    tr = pd.concat([h.h - h.l, (h.h - pc).abs(), (h.l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
