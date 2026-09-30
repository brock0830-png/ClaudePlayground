"""
Phase 2: directional ES rules from price and VIX (see PROTOCOL_P2.md).

- `es_context(bars)`: switch-adjusted ES 4h prices, session table with features, bar -> session map.
- `spx_context()`: SPX daily closes + VIX for the pre-DEV robustness check (1990-2012).
- `daily_target(D, spec)`: target position decided at each daily close (+1/0/-1); works on ES sessions
  and SPX days (returns None when the rule needs a column the table lacks, e.g. IBS on SPX closes).
- `session_target(ctx, spec)`: bar-level target for F1 session-window rules.
- `run_bars(ctx, tgt, i0, i1)`: position P&L on ES bars (next-open execution, costs, rolls).
- `run_daily_close(S, tgt, i0, i1)`: % P&L on SPX closes (executed at the signal close).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .data import load_vix, load_spx_daily
from .options import roll_adjusted_close

SIDE_COST = 0.30          # pt per contract per side (1 tick + $2.50)
ROLL_COST = 0.60          # pt per contract per roll held through a switch
SPX_RT_COST = 0.0003      # 0.03% per round trip on the SPX proxy


# ----------------------------------------------------------------------------- features
def rsi(close: pd.Series, n: int = 2) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    tot = up + dn
    return (100 * up / tot.where(tot > 0)).fillna(50.0)


def add_daily_features(D: pd.DataFrame) -> pd.DataFrame:
    c = D["close"]
    for n in (5, 10, 20, 50, 100, 200):
        D[f"ma{n}"] = c.rolling(n).mean()
    D["rsi2"] = rsi(c, 2)
    for n in (5, 10, 20, 55):
        D[f"minc{n}"] = c.shift(1).rolling(n).min()     # lowest close of the PRIOR n days
        D[f"maxc{n}"] = c.shift(1).rolling(n).max()
    for n in (63, 126, 252):
        D[f"mom{n}"] = c / c.shift(n) - 1
    dn = (c < c.shift(1)).astype(int)
    up = (c > c.shift(1)).astype(int)
    D["dnstreak"] = dn.groupby((dn == 0).cumsum()).cumsum()
    D["upstreak"] = up.groupby((up == 0).cumsum()).cumsum()
    D["zero"] = 0.0
    if "high" in D:
        rng = (D["high"] - D["low"]).where(lambda x: x > 0)
        D["ibs"] = ((c - D["low"]) / rng).fillna(0.5)
    v = D["vix"]
    D["vix_ma10"] = v.rolling(10).mean()
    D["vix_ma20"] = v.rolling(20).mean()
    D["vix_mean252"] = v.rolling(252).mean()
    D["vix_x_ma10"] = v / D["vix_ma10"]
    D["vix_rsi2"] = rsi(v, 2)
    if "vix3m" in D:
        D["vts"] = v / D["vix3m"]
    dates = pd.DatetimeIndex(D["date"])
    m = pd.Series(dates.to_period("M").astype(str), index=D.index)
    D["tdm"] = m.groupby(m).cumcount().values + 1                           # 1 = first trading day of month
    D["tdm_rev"] = m.groupby(m).cumcount(ascending=False).values + 1        # 1 = last trading day of month
    D["dow"] = dates.dayofweek
    return D


def _vix_on(dates, name: str) -> np.ndarray:
    v = load_vix(name)
    return v.reindex(pd.DatetimeIndex(dates)).ffill().values   # same-date close, known by 17:00 ET


def es_context(bars: pd.DataFrame) -> dict:
    off = roll_adjusted_close(bars)
    o = bars["open"].values - off
    h = bars["high"].values - off
    l = bars["low"].values - off
    c = bars["close"].values - off
    day = bars["day_id"].values
    last_of_day = np.r_[day[1:] != day[:-1], True]
    first_of_day = np.r_[True, day[1:] != day[:-1]]
    sess = np.cumsum(first_of_day) - 1
    D = pd.DataFrame({"date": pd.Series(bars["tday"].values).groupby(sess).last().values,
                      "open": pd.Series(o).groupby(sess).first().values,
                      "high": pd.Series(h).groupby(sess).max().values,
                      "low": pd.Series(l).groupby(sess).min().values,
                      "close": pd.Series(c).groupby(sess).last().values})
    D["vix"] = _vix_on(D["date"], "VIX")
    D["vix3m"] = _vix_on(D["date"], "VIX3M")
    D = add_daily_features(D)
    return dict(bars=bars, o=o, c=c, sw=bars["roll_switch_bar"].values.astype(bool),
                last_of_day=last_of_day, D=D, sess=sess, hour=bars.index.hour.values,
                year=pd.DatetimeIndex(bars["tday"]).year.values, tday=bars["tday"].values,
                week=pd.DatetimeIndex(bars["tday"]).to_period("W").astype(str).values,
                vix_prev=None)


def spx_context(start="1989-01-01", end="2012-12-31") -> pd.DataFrame:
    s = load_spx_daily()
    s = s[(s.index >= start) & (s.index <= end)]
    D = pd.DataFrame({"date": s.index, "close": s.values})
    D["vix"] = _vix_on(D["date"], "VIX")
    return add_daily_features(D.reset_index(drop=True))


# ----------------------------------------------------------------------------- rules
def _val(D, x):
    if x in D.columns:
        return D[x].values.astype(float)
    try:
        return float(x)
    except ValueError:
        return None


def _cond(D: pd.DataFrame, expr: str):
    """'rsi2<10', 'close>ma200', 'vts<1.0', 'close<minc5', 'dnstreak>=3'. None if a column is missing."""
    for op in ("<=", ">=", "<", ">"):
        if op in expr:
            a, b = expr.split(op)
            A, B = _val(D, a), _val(D, b)
            if A is None or B is None:
                return None
            with np.errstate(invalid="ignore"):
                r = {"<=": A <= B, ">=": A >= B, "<": A < B, ">": A > B}[op]
            return np.asarray(r & ~np.isnan(A) & ~np.isnan(B), bool) if isinstance(A, np.ndarray) or isinstance(B, np.ndarray) else r
    raise ValueError(expr)


def _all(D, exprs):
    m = np.ones(len(D), bool)
    for e in exprs:
        r = _cond(D, e)
        if r is None:
            return None
        m &= r
    return m


def daily_target(D: pd.DataFrame, spec: dict):
    """Target decided at each daily close; it applies to the NEXT session."""
    n = len(D)
    side = 1.0 if spec.get("side", "long") == "long" else -1.0
    kind = spec["kind"]
    if kind == "regime":
        on = _all(D, spec["on"])
        if on is None:
            return None
        return np.where(on, 1.0, -1.0) if spec.get("longshort") else np.where(on, side, 0.0)
    if kind == "entry_exit":
        ent = _all(D, spec["entry"] + spec.get("filters", []))
        if ent is None:
            return None
        ex = spec["exit"]
        if ex.startswith("hold"):
            exit_c, hold_n = None, int(ex[4:])
        else:
            exit_c, hold_n = _cond(D, ex), int(spec.get("max_hold", 10))
            if exit_c is None:
                return None
        t = np.zeros(n)
        pos, held = 0.0, 0
        for i in range(n):
            was = pos
            if pos != 0:
                held += 1
                if (exit_c is not None and exit_c[i]) or held >= hold_n:
                    pos = 0.0
            if pos == 0 and was == 0 and ent[i]:
                pos, held = side, 0
            t[i] = pos
        return t
    if kind == "calendar":
        cal = spec["cal"]
        if cal[0] == "tom":        # from the close of the k-th last trading day to the close of the j-th day
            _, k, j = cal
            on = (D["tdm_rev"].values <= k) | (D["tdm"].values < j)
            return np.where(on, side, 0.0)
        if cal[0] == "preholiday":  # hold the last session before an exchange holiday
            dates = pd.DatetimeIndex(D["date"]).to_series().reset_index(drop=True)
            gap = (dates.shift(-1) - dates).dt.days.values
            pre = (gap > 1) & ~((D["dow"].values == 4) & (gap == 3))
            return np.where(np.r_[pre[1:], False], side, 0.0)
        if cal[0] == "weekday":     # hold sessions whose trading date is weekday w
            nd = np.r_[D["dow"].values[1:], -1]
            return np.where(nd == cal[1], side, 0.0)
    raise ValueError(spec)


def bar_target_from_daily(ctx, t_daily: np.ndarray) -> np.ndarray:
    """A session's daily target is decided at its last bar and held until the next session's last bar."""
    tb = np.full(len(ctx["o"]), np.nan)
    lod = ctx["last_of_day"]
    tb[lod] = t_daily[ctx["sess"][lod]]
    return pd.Series(tb).ffill().fillna(0.0).values


def session_target(ctx, spec: dict) -> np.ndarray:
    """F1: in position during bars whose hour is in spec['hours']; filters use the last completed session."""
    side = 1.0 if spec["side"] == "long" else -1.0
    nxt_h = np.r_[ctx["hour"][1:], -1]
    on = np.isin(nxt_h, list(spec["hours"]))
    flt = spec.get("filters", [])
    if flt:
        m = _all(ctx["D"], flt)
        if m is None:
            return None
        sess_next = np.r_[ctx["sess"][1:], ctx["sess"][-1]]
        on &= (sess_next > 0) & m[np.clip(sess_next - 1, 0, None)]
    return np.where(on, side, 0.0)


# ----------------------------------------------------------------------------- engines
def _runs(hold: np.ndarray):
    """(start, end, dir) of maximal runs of constant non-zero position."""
    n = len(hold)
    edges = np.flatnonzero(np.diff(np.r_[0.0, hold, 0.0]) != 0)
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        if a < n and hold[a] != 0:
            out.append((a, b - 1, hold[a]))
    return out


def run_bars(ctx, tgt: np.ndarray, i0: int, i1: int) -> dict:
    """Bars i0..i1-1. hold[t] = tgt[t-1] (flat at i0); anything open is closed at the last bar's close."""
    o, c, sw = ctx["o"][i0:i1], ctx["c"][i0:i1], ctx["sw"][i0:i1]
    n = len(o)
    tg = tgt[i0:i1].astype(float).copy()
    tg[-1] = 0.0
    hold = np.r_[0.0, tg[:-1]]
    prev_hold = np.r_[0.0, hold[:-1]]
    prev_c = np.r_[o[0], c[:-1]]
    rolled = sw & (prev_hold == hold) & (hold != 0)
    pnl = prev_hold * (o - prev_c) + hold * (c - o) - SIDE_COST * np.abs(hold - prev_hold) - ROLL_COST * np.abs(hold) * rolled
    pnl[-1] -= SIDE_COST * abs(hold[-1])
    rows = []
    for s, e, d in _runs(hold):
        x = o[e + 1] if e + 1 < n else c[e]
        nrolls = int(sw[s + 1:e + 1].sum())
        rows.append((s + i0, e + i0, d, d * (x - o[s]) - 2 * SIDE_COST * abs(d) - ROLL_COST * abs(d) * nrolls, e - s + 1))
    trades = pd.DataFrame(rows, columns=["s", "e", "dir", "net", "bars"])
    return dict(pnl=pnl, hold=hold, trades=trades, i0=i0, i1=i1)


def run_daily_close(S: pd.DataFrame, tgt: np.ndarray, i0: int, i1: int) -> dict:
    """SPX proxy: position decided at close d is held from close d to close d+1. P&L in % of price."""
    c = S["close"].values[i0:i1]
    r = np.r_[c[1:] / c[:-1] - 1, 0.0]
    pos = tgt[i0:i1].astype(float).copy()
    pos[-1] = 0.0
    prev = np.r_[0.0, pos[:-1]]
    pnl = pos * r - SPX_RT_COST / 2 * np.abs(pos - prev)
    rows = []
    for s, e, d in _runs(pos):
        rows.append((s + i0, e + i0, d, float(d * r[s:e + 1].sum()) - SPX_RT_COST * abs(d), e - s + 1))
    return dict(pnl=pnl, hold=pos, r=r, trades=pd.DataFrame(rows, columns=["s", "e", "dir", "net", "days"]))
