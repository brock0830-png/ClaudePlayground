"""Hand-built sessions for the unit tests. Prices are in ticks (1 tick = 0.25 ES points)."""
from __future__ import annotations

import numpy as np
import pandas as pd

RTH0 = 9 * 60 + 30
FULL = 405                      # 09:30-16:15


def path_prices(waypoints: list[tuple[int, int]], n_min: int = FULL) -> np.ndarray:
    """Price at each minute boundary 0..n_min, linear between (minute, price) waypoints, rounded
    to whole ticks. The last waypoint's price is held to the end."""
    xs = [w[0] for w in waypoints]
    ys = [w[1] for w in waypoints]
    t = np.arange(n_min + 1)
    return np.rint(np.interp(t, xs, ys)).astype(np.int64)


def bars_from_path(waypoints, n_min: int = FULL, vol: int = 10) -> pd.DataFrame:
    """One bar per minute: open = price at the minute's start, close = price at its end."""
    p = path_prices(waypoints, n_min)
    o, c = p[:-1], p[1:]
    return pd.DataFrame({"o": o, "h": np.maximum(o, c), "l": np.minimum(o, c), "c": c,
                         "v": np.full(n_min, vol), "minute": RTH0 + np.arange(n_min)})


def bars_from_periods(periods: list[tuple[int, int, int, int]]) -> pd.DataFrame:
    """Periods given as (open, low, high, close); each 30-minute period (the 14th is 15 minutes)
    goes open -> low -> high -> close, or open -> high -> low -> close if close < open. Each
    period must open where the previous one closed, so period ranges are exactly as given."""
    wps, m = [], 0
    for j, (o, lo, hi, c) in enumerate(periods):
        n = 15 if j == 13 else 30
        if j:
            assert o == periods[j - 1][3], "periods must be continuous"
        a, b = (lo, hi) if c >= o else (hi, lo)
        wps += ([(m, o)] if j == 0 else []) + [(m + n // 3, a), (m + 2 * n // 3, b), (m + n, c)]
        m += n
    return bars_from_path(wps, n_min=m)


def feats(bars: pd.DataFrame, offset: int = 0) -> dict:
    from mp.features import session_features
    return session_features(bars.o, bars.h, bars.l, bars.c, bars.v, bars.minute, raw_offset=offset)
