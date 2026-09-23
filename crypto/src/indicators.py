"""Indicators, written to match TradingView Pine v5/v6 built-ins where one exists.

Every function takes pandas Series and returns a Series aligned to the input index, using only data up to
and including each bar (no look-ahead). The same module is imported by the live bot, so research and
trading compute identical signals.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- Pine built-ins
def sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def stdev_pop(x: pd.Series, n: int) -> pd.Series:
    """ta.stdev (biased=true default): population standard deviation."""
    return x.rolling(n, min_periods=n).std(ddof=0)


def wma(x: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return x.rolling(n, min_periods=n).apply(lambda a: np.dot(a, w) / w.sum(), raw=True)


def rma(x: pd.Series, n: int) -> pd.Series:
    """ta.rma: Wilder smoothing seeded with the SMA of the first n non-NaN values."""
    a = x.to_numpy(dtype=float)
    out = np.full(len(a), np.nan)
    valid = np.flatnonzero(~np.isnan(a))
    if len(valid) < n:
        return pd.Series(out, index=x.index)
    start = valid[0]
    seed_end = start + n - 1
    if np.isnan(a[start:seed_end + 1]).any():
        return pd.Series(out, index=x.index)
    out[seed_end] = a[start:seed_end + 1].mean()
    for i in range(seed_end + 1, len(a)):
        v = a[i]
        out[i] = out[i - 1] if np.isnan(v) else (out[i - 1] * (n - 1) + v) / n
    return pd.Series(out, index=x.index)


def rsi(x: pd.Series, n: int) -> pd.Series:
    d = x.diff()
    up = rma(d.clip(lower=0), n)
    dn = rma((-d).clip(lower=0), n)
    u, v = up.to_numpy(), dn.to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(v == 0, 100.0, np.where(u == 0, 0.0, 100 - 100 / (1 + u / v)))
    out[np.isnan(u) | np.isnan(v)] = np.nan
    return pd.Series(out, index=x.index)


def ema(x: pd.Series, n: int) -> pd.Series:
    """ta.ema: alpha 2/(n+1), seeded with the SMA of the first n values."""
    a = x.to_numpy(dtype=float)
    out = np.full(len(a), np.nan)
    valid = np.flatnonzero(~np.isnan(a))
    if len(valid) < n:
        return pd.Series(out, index=x.index)
    s = valid[0] + n - 1
    out[s] = a[valid[0]:s + 1].mean()
    k = 2.0 / (n + 1)
    for i in range(s + 1, len(a)):
        out[i] = out[i - 1] + k * (a[i] - out[i - 1])
    return pd.Series(out, index=x.index)


def hma(x: pd.Series, n: int) -> pd.Series:
    return wma(2 * wma(x, n // 2) - wma(x, n), int(round(np.sqrt(n))))


def zscore(x: pd.Series, n: int = 20) -> pd.Series:
    """The client's Z: (src - sma) / population stdev, 0 when stdev is 0."""
    sd = stdev_pop(x, n)
    z = (x - sma(x, n)) / sd
    return z.where(sd > 0, 0.0).where(sd.notna())


# ---------------------------------------------------------------- TD Sequential
def td_setup_counts(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Consecutive-bar counts of close > close[4] (sell setup) and close < close[4] (buy setup), unbounded."""
    c = close.to_numpy(dtype=float)
    sell = np.zeros(len(c), dtype=int)
    buy = np.zeros(len(c), dtype=int)
    for i in range(4, len(c)):
        sell[i] = sell[i - 1] + 1 if c[i] > c[i - 4] else 0
        buy[i] = buy[i - 1] + 1 if c[i] < c[i - 4] else 0
    return pd.Series(sell, index=close.index), pd.Series(buy, index=close.index)


def td_countdown(close: pd.Series, high: pd.Series, low: pd.Series) -> tuple[pd.Series, pd.Series]:
    """DeMark countdown 13 flags. Buy countdown starts after a completed buy setup (count hits 9); it counts
    bars with close <= low[2] and fires on the 13th. It is cancelled when a sell setup completes, and restarts
    from zero when a new buy setup completes (recycle). No bar-8 qualifier. Mirror for sells. This reproduces the
    client's exported scr_buy13_countdown / scr_sell13_countdown columns exactly."""
    sell_cnt, buy_cnt = td_setup_counts(close)
    c, h, l = (s.to_numpy(dtype=float) for s in (close, high, low))
    n = len(c)
    buy13 = np.zeros(n, dtype=bool)
    sell13 = np.zeros(n, dtype=bool)
    b_on = s_on = False
    b_k = s_k = 0
    for i in range(n):
        if buy_cnt.iat[i] == 9:
            b_on, b_k, s_on = True, 0, False
        if sell_cnt.iat[i] == 9:
            s_on, s_k, b_on = True, 0, False
        if i >= 2:
            if b_on and c[i] <= l[i - 2]:
                b_k += 1
                if b_k == 13:
                    buy13[i], b_on = True, False
            if s_on and c[i] >= h[i - 2]:
                s_k += 1
                if s_k == 13:
                    sell13[i], s_on = True, False
    return pd.Series(sell13, index=close.index), pd.Series(buy13, index=close.index)


def tdz_signals(df: pd.DataFrame, z_len=20, z_thresh=2.5, z_lookback=4, mode="client") -> tuple[pd.Series, pd.Series]:
    """Buy and sell signal flags for the H1 variants.

    mode: client (9 or 13-consecutive + z), td (9 or 13-consecutive only), z (z crosses beyond the threshold
    this bar), countdown (DeMark countdown 13 + z), export (the client's exported scr_conf_buy/sell: 9, 13-consecutive
    or countdown 13 while the EMA stack is stretched, see ema_stack)."""
    close = df["close"]
    z = zscore(close, z_len)
    z_low = z.rolling(z_lookback, min_periods=1).min() <= -z_thresh
    z_high = z.rolling(z_lookback, min_periods=1).max() >= z_thresh
    sell_cnt, buy_cnt = td_setup_counts(close)
    td_buy = buy_cnt.isin([9, 13])
    td_sell = sell_cnt.isin([9, 13])
    if mode == "client":
        return td_buy & z_low, td_sell & z_high
    if mode == "td":
        return td_buy, td_sell
    if mode == "z":
        return (z <= -z_thresh) & (z.shift(1) > -z_thresh), (z >= z_thresh) & (z.shift(1) < z_thresh)
    if mode in ("countdown", "export"):
        s13, b13 = td_countdown(close, df["high"], df["low"])
        if mode == "countdown":
            return b13 & z_low, s13 & z_high
        up, dn = ema_stack(close)
        return (td_buy | b13) & dn, (td_sell | s13) & up
    raise ValueError(mode)


def ema_stack(close: pd.Series, lens=(50, 100, 200), dists=(0.03, 0.04, 0.05)) -> tuple[pd.Series, pd.Series]:
    """Stretched EMA stack from the client's export: close at least 3%, 4% and 5% above (up) or below (dn)
    EMA 50, 100 and 200. Reproduces scr_stack_up / scr_stack_dn exactly."""
    d = [close / ema(close, n) - 1 for n in lens]
    up = pd.concat([x >= k for x, k in zip(d, dists)], axis=1).all(axis=1)
    dn = pd.concat([x <= -k for x, k in zip(d, dists)], axis=1).all(axis=1)
    return up, dn


# ---------------------------------------------------------------- SigmaJanus RSI
def sigmajanus_fast(close: pd.Series, wma_len=7, rsi_len=8) -> pd.Series:
    return rsi(wma(close, wma_len), rsi_len)


def sigmajanus_rerisk(close: pd.Series, os_level=15.0) -> pd.Series:
    f = sigmajanus_fast(close)
    return (f < os_level) & (f > f.shift(1)) & (f.shift(1) <= f.shift(2))


# ---------------------------------------------------------------- price action / volume / CVD proxy
def clv(df: pd.DataFrame) -> pd.Series:
    """Close-location value in [-1, 1]; 0 on zero-range bars."""
    rng = df["high"] - df["low"]
    v = (2 * df["close"] - df["high"] - df["low"]) / rng
    return v.where(rng > 0, 0.0)


def cvd_proxy(df: pd.DataFrame) -> pd.Series:
    """Cumulative CLV x volume. Without taker buy/sell volume this only approximates the sign of bar delta."""
    return (clv(df) * df["volume"]).cumsum()


def return_z(close: pd.Series, n=50) -> pd.Series:
    r = close.pct_change()
    return r / r.shift(1).rolling(n, min_periods=n).std()


def rel_volume(volume: pd.Series, n=50) -> pd.Series:
    return volume / volume.shift(1).rolling(n, min_periods=n).median()


def capitulation(df: pd.DataFrame, k=3.0, vol_mult=2.0, clv_filter=True, n=50) -> pd.Series:
    sig = (return_z(df["close"], n) <= -k) & (rel_volume(df["volume"], n) >= vol_mult)
    if clv_filter:
        sig &= clv(df) >= 0
    return sig


# ---------------------------------------------------------------- trend state machines
def sma_trend(close: pd.Series, n: int) -> pd.Series:
    """1.0 while close > SMA(n), else 0.0 (NaN during warm-up)."""
    m = sma(close, n)
    return (close > m).astype(float).where(m.notna())


def donchian_trend(close: pd.Series, n: int) -> pd.Series:
    """Enter when close is the highest close of the last n bars, exit when it is the lowest of the last n//2."""
    hi = close.rolling(n, min_periods=n).max()
    lo = close.rolling(max(2, n // 2), min_periods=max(2, n // 2)).min()
    c, h, l = close.to_numpy(), hi.to_numpy(), lo.to_numpy()
    out = np.full(len(c), np.nan)
    on = 0.0
    for i in range(len(c)):
        if np.isnan(h[i]):
            continue
        if on == 0.0 and c[i] >= h[i]:
            on = 1.0
        elif on == 1.0 and c[i] <= l[i]:
            on = 0.0
        out[i] = on
    return pd.Series(out, index=close.index)
