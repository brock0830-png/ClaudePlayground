"""Event engine: a signal at the close of bar t opens one trade at the open of bar t+1+delay and closes it H bars later.

No pyramiding: a signal is skipped while a trade from the same family is open on that symbol. A trade counts in a
window only if its signal bar and its exit bar both fall inside the window, so a design-window trade never touches
holdout prices.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def trades(df: pd.DataFrame, signal: pd.Series, H, side: str, window, cost_side: float, fund_bar: float = 0.0,
           delay: int = 0, z: pd.Series | None = None, cap: int = 32, sym: str = "") -> pd.DataFrame:
    o = df["open"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    hi = df["high"].to_numpy(float)
    idx = df.index
    n = len(o)
    zz = z.to_numpy(float) if z is not None else None
    start, end = window
    sig = np.flatnonzero(signal.reindex(idx).fillna(False).to_numpy(bool))
    rows = []
    free = 0
    for t in sig:
        if idx[t] < start or idx[t] > end:
            continue
        e = t + 1 + delay
        if e < free or e >= n:
            continue
        if H == "zexit":
            x = None
            for s in range(e, min(e + cap, n - 1 - delay)):
                if (side == "long" and zz[s] >= 0) or (side == "short" and zz[s] <= 0):
                    x = s + 1 + delay
                    break
            if x is None:
                x = e + cap
        else:
            x = e + H
        if x >= n or idx[x] > end:
            continue
        ratio = o[x] / o[e]
        gross = ratio - 1 if side == "long" else 1 - ratio
        net = gross - 2 * cost_side - fund_bar * (x - e)
        adverse = (lo[e:x].min() / o[e] - 1) if side == "long" else (1 - hi[e:x].max() / o[e])
        rows.append((sym, idx[t], idx[e], idx[x], x - e, gross, net, adverse))
        free = x
    return pd.DataFrame(rows, columns=["sym", "signal_time", "entry_time", "exit_time", "bars", "gross", "net", "adverse"])


def unconditional(df: pd.DataFrame, H: int, side: str, window, delay: int = 0) -> tuple[float, float]:
    """Mean H-bar open-to-open return and mean worst excursion over every bar of the window (the drift baseline)."""
    o = df["open"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    hi = df["high"].to_numpy(float)
    idx = df.index
    n = len(o)
    t = np.flatnonzero((idx >= window[0]) & (idx <= window[1]))
    e = t + 1 + delay
    x = e + H
    ok = x < n
    e, x = e[ok], x[ok]
    ok = idx[x] <= window[1]
    e, x = e[ok], x[ok]
    if len(e) == 0:
        return np.nan, np.nan
    r = o[x] / o[e] - 1
    # worst excursion over [e, x) via a rolling window on lows/highs
    if side == "long":
        wmin = pd.Series(lo).rolling(H, min_periods=H).min().shift(-(H - 1)).to_numpy()
        adv = wmin[e] / o[e] - 1
        return float(np.nanmean(r)), float(np.nanmean(adv))
    wmax = pd.Series(hi).rolling(H, min_periods=H).max().shift(-(H - 1)).to_numpy()
    adv = 1 - wmax[e] / o[e]
    return float(np.nanmean(-r)), float(np.nanmean(adv))


def clustered_t(tr: pd.DataFrame, col: str = "net") -> float:
    if len(tr) < 3:
        return np.nan
    g = tr.groupby(tr["entry_time"].dt.floor("D"))[col].mean()
    if len(g) < 3 or g.std(ddof=1) == 0:
        return np.nan
    return float(g.mean() / (g.std(ddof=1) / np.sqrt(len(g))))


def summarize(tr: pd.DataFrame, uncond: dict[str, float], uncond_adv: dict[str, float] | None = None) -> dict:
    """Pooled stats. uncond maps sym -> unconditional mean H-bar return for this side (drift baseline)."""
    if len(tr) == 0:
        return {"n": 0}
    base = tr["sym"].map(uncond)
    pos = tr.loc[tr.net > 0, "net"].sum()
    neg = -tr.loc[tr.net < 0, "net"].sum()
    per = tr.groupby("sym")["net"].agg(["count", "mean"])
    q = per[per["count"] >= 5]
    out = {
        "n": int(len(tr)),
        "n_syms": int(tr["sym"].nunique()),
        "mean_gross": float(tr.gross.mean()),
        "mean_net": float(tr.net.mean()),
        "median_net": float(tr.net.median()),
        "win_rate": float((tr.net > 0).mean()),
        "profit_factor": float(pos / neg) if neg > 0 else np.inf,
        "t_clust": clustered_t(tr),
        "excess": float((tr.gross - base).mean()),
        "breadth": float((q["mean"] > 0).mean()) if len(q) else np.nan,
        "breadth_syms": int(len(q)),
        "avg_bars": float(tr.bars.mean()),
        "adverse": float(tr.adverse.mean()),
    }
    if uncond_adv is not None:
        out["adverse_uncond"] = float(tr["sym"].map(uncond_adv).mean())
    return out
