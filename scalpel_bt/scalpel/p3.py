"""
Phase 3 (PROTOCOL_P3.md): daily-bar engine with profit targets and stops, shared by ES sessions
(from the 4h export) and ETF daily bars.

Data
- `es_daily(bars)`: TradingView ES sessions, switch-adjusted OHLC, per-session roll flags,
  SPY volume of the same date (ES has no volume), VIX features.
- `etf_daily(sym)`: dividend-adjusted daily OHLCV (FMP) + VIX features. Test symbols are locked
  until the Phase 3 freeze (see `TEST_SYMBOLS`, `results/p3/TEST_UNLOCKED`).

Execution modes
- 'next_open' (ES): signal at the session close (17:00 ET), entry at the next session's open (18:00 ET).
  A time exit after N sessions fills at the open following the N-th session close.
- 'close' (ETFs): signal from the day's close, filled at that close (market-on-close); time exits at a close.
Intraday exits (both modes): stop at entry - s*ATR20, target at entry + t*ATR20 (ATR20 = mean daily
high-low of the 20 sessions up to the signal day). A day that reaches both fills the stop. A gap through
a level fills at the open.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from .data import DATA, RESULTS, load_vix

ETF_DIR = DATA / "external" / "etf"
DEV_SYMBOLS = ["SPY"]
TEST_SYMBOLS = ["QQQ", "IWM", "DIA", "EFA", "EWG", "EWJ", "EWU"]
TEST_LOCK = RESULTS / "p3" / "TEST_UNLOCKED"
ES_RT_PTS, ES_ROLL_PTS = 0.60, 0.60
ETF_RT_PCT = 0.0005          # 0.05% per round trip (about 2.5 bp per side)


# ------------------------------------------------------------------ features
def _rsi(close: pd.Series, n=2):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    tot = up + dn
    return (100 * up / tot.where(tot > 0)).fillna(50.0)


def _trailing_pct(x: np.ndarray, w=252) -> np.ndarray:
    """Share of the previous w values (incl. today) strictly below today's value; NaN until w values."""
    out = np.full(len(x), np.nan)
    for i in range(w - 1, len(x)):
        win = x[i - w + 1:i + 1]
        if np.isnan(win).any():
            continue
        out[i] = (win < x[i]).mean()
    return out


def vix_features() -> pd.DataFrame:
    v = load_vix("VIX")
    f = pd.DataFrame({"vix": v})
    f["vix_ma10"] = v.rolling(10).mean()
    f["vix_ma20"] = v.rolling(20).mean()
    f["vix_mean252"] = v.rolling(252).mean()
    f["vix_rel"] = v / f["vix_mean252"]
    f["vix_x_ma10"] = v / f["vix_ma10"]
    f["vix_pct252"] = _trailing_pct(v.values, 252)
    try:
        v3 = load_vix("VIX3M").reindex(v.index)
        f["vts"] = v / v3
    except FileNotFoundError:
        f["vts"] = np.nan
    return f


def add_features(D: pd.DataFrame, V: pd.DataFrame) -> pd.DataFrame:
    D = D.copy()
    idx = pd.DatetimeIndex(D["date"])
    for c in V.columns:
        D[c] = V[c].reindex(idx).ffill().values if c == "vix" else V[c].reindex(idx).values
    c = D["close"]
    for n in (5, 10, 20, 50, 100, 200):
        D[f"ma{n}"] = c.rolling(n).mean()
    D["rsi2"] = _rsi(c, 2)
    D["minc5"] = c.shift(1).rolling(5).min()
    D["high1"] = D["high"].shift(1)
    rng = D["high"] - D["low"]
    D["ibs"] = ((c - D["low"]) / rng.where(rng > 0)).fillna(0.5)
    D["atr20"] = rng.rolling(20).mean()
    for n in (126, 252):
        D[f"mom{n}"] = c / c.shift(n) - 1
    dn = (c < c.shift(1)).astype(int)
    D["dnstreak"] = dn.groupby((dn == 0).cumsum()).cumsum()
    D["ret3_atr"] = (c - c.shift(3)) / D["atr20"]
    D["dist5_atr"] = (c - D["ma5"]) / D["atr20"]
    if "volume" in D and D["volume"].notna().any():
        D["vol_rel50"] = D["volume"] / D["volume"].shift(1).rolling(50, min_periods=40).mean()
    D["zero"] = 0.0
    # oversold ensemble (k of 4) and continuous oversold score (mean of trailing ranks, 1 = most oversold)
    D["os_count"] = ((D["ibs"] < 0.3).astype(int) + (D["rsi2"] < 15).astype(int)
                     + (c < D["minc5"]).astype(int) + (D["dnstreak"] >= 2).astype(int))
    r1 = 1 - D["ibs"].values
    r2 = 1 - D["rsi2"].values / 100.0
    r3 = 1 - _trailing_pct(D["ret3_atr"].values, 252)
    r4 = 1 - _trailing_pct(D["dist5_atr"].values, 252)
    D["os_score"] = np.nanmean(np.vstack([r1, r2, r3, r4]), axis=0)
    D.loc[np.isnan(r3) | np.isnan(r4), "os_score"] = np.nan
    return D


# ------------------------------------------------------------------ data
def etf_daily(sym: str) -> pd.DataFrame:
    if sym in TEST_SYMBOLS and not TEST_LOCK.exists():
        raise PermissionError(f"{sym} is a Phase 3 test market; locked until the freeze commit.")
    d = pd.read_csv(ETF_DIR / f"{sym}.csv.gz", parse_dates=["date"])
    D = add_features(d, vix_features())
    D["roll"] = False
    D["sym"] = sym
    return D


def es_daily(bars: pd.DataFrame) -> pd.DataFrame:
    from .p2 import es_context
    ctx = es_context(bars)
    D = ctx["D"][["date", "open", "high", "low", "close"]].copy()
    sw_sess = pd.Series(ctx["sw"]).groupby(ctx["sess"]).any().values
    spy = pd.read_csv(ETF_DIR / "SPY.csv.gz", parse_dates=["date"]).set_index("date")["volume"]
    D["volume"] = spy.reindex(pd.DatetimeIndex(D["date"])).values
    D = add_features(D, vix_features())
    D["roll"] = sw_sess            # a contract switch happens at this session's first bar
    D["sym"] = "ES"
    return D


# ------------------------------------------------------------------ conditions
def _val(D, x):
    if x in D.columns:
        return D[x].values.astype(float)
    try:
        return float(x)
    except ValueError:
        return None


def cond(D, expr):
    for op in ("<=", ">=", "<", ">"):
        if op in expr:
            a, b = expr.split(op)
            A, B = _val(D, a), _val(D, b)
            if A is None or B is None:
                raise KeyError(expr)
            with np.errstate(invalid="ignore"):
                r = {"<=": A <= B, ">=": A >= B, "<": A < B, ">": A > B}[op]
            r = np.asarray(r, bool)
            if isinstance(A, np.ndarray):
                r &= ~np.isnan(A)
            if isinstance(B, np.ndarray):
                r &= ~np.isnan(B)
            return r
    raise ValueError(expr)


def all_of(D, exprs):
    m = np.ones(len(D), bool)
    for e in exprs:
        m &= cond(D, e)
    return m


# ------------------------------------------------------------------ engine
def _cost(D, px_in, e, last_held):
    """Round-trip cost in price units: ES points plus one roll per contract switch in sessions
    e+1..last_held (the position is carried through it); ETFs a % of the entry price."""
    if D["sym"].iat[0] == "ES":
        rolls = int(D["roll"].values[e + 1:last_held + 1].sum()) if last_held > e else 0
        return ES_RT_PTS + ES_ROLL_PTS * rolls
    return ETF_RT_PCT * px_in


def simulate(D: pd.DataFrame, spec: dict, mode: str, i0: int = 0, i1: int | None = None) -> pd.DataFrame:
    """Trades for signals at closes i0..i1-1 (exits may run to the end of D)."""
    n = len(D)
    i1 = n if i1 is None else i1
    O, H, L, C = (D[k].values.astype(float) for k in ("open", "high", "low", "close"))
    atr = D["atr20"].values
    kind = spec.get("kind", "rule")
    if kind == "target":
        return _simulate_target(D, spec, mode, i0, i1)
    ent = all_of(D, spec["entry"])
    ex = all_of(D, [spec["exit"]]) if spec.get("exit") else None
    hold_n = int(spec.get("hold", 10))
    t_atr, s_atr = float(spec.get("tgt", 0) or 0), float(spec.get("stop", 0) or 0)
    maxc = int(spec.get("max_concurrent", 1))
    rows = []
    active_exits = []
    i = i0
    while i < i1:
        if not ent[i] or np.isnan(atr[i]):
            i += 1
            continue
        if maxc > 1:
            active_exits = [x for x in active_exits if x > i]
            if len(active_exits) >= maxc:
                i += 1
                continue
        if mode == "next_open":
            e = i + 1
            if e >= n:
                break
            px_in, first = O[e], e
        else:
            e, px_in, first = i, C[i], i + 1
        stop = px_in - s_atr * atr[i] if s_atr > 0 else -np.inf
        tgt = px_in + t_atr * atr[i] if t_atr > 0 else np.inf
        k, held, px_out, xday, why, decision = first, 0, None, None, None, None
        while k < n:
            o_k = px_in if (mode == "next_open" and k == e) else O[k]
            if L[k] <= stop:
                px_out, xday, why, decision = min(stop, o_k), k, "stop", k
                break
            if H[k] >= tgt:
                px_out, xday, why, decision = max(tgt, o_k), k, "target", k
                break
            held += 1
            if held >= hold_n or (ex is not None and ex[k]):
                why = "time" if held >= hold_n else "exit_rule"
                decision = k
                if mode == "next_open":
                    xday = k + 1 if k + 1 < n else k
                    px_out = O[k + 1] if k + 1 < n else C[k]
                else:
                    xday, px_out = k, C[k]
                break
            k += 1
        if px_out is None:
            xday, px_out, why, decision = n - 1, C[n - 1], "end", n - 1
        last_held = xday - 1 if (mode == "next_open" and why in ("time", "exit_rule")) else xday
        cost = _cost(D, px_in, e, last_held)
        rows.append((i, e, xday, px_in, px_out, px_out - px_in - cost, (px_out - px_in - cost) / px_in,
                     why, max(held, 1)))
        if maxc > 1:
            active_exits.append(decision)
            i += 1
        else:
            # flat at the decision close: a new signal may come from the next close
            # (or from this same close after an intraday stop/target exit)
            i = decision if why in ("stop", "target") and decision > i else decision + 1
    return pd.DataFrame(rows, columns=["sig", "entry", "exit", "px_in", "px_out", "pnl", "ret", "why", "sessions"])


def _simulate_target(D, spec, mode, i0, i1):
    """Position series: target decided at close d (1 = long); runs of 1 become trades."""
    ent = all_of(D, spec["entry"]) if spec.get("entry") else np.zeros(len(D), bool)
    tgt = all_of(D, spec["regime"]) if spec.get("regime") else np.zeros(len(D), bool)
    dip_hold = int(spec.get("dip_hold", 0))
    if dip_hold:
        recent = pd.Series(ent.astype(float)).rolling(dip_hold, min_periods=1).max().values > 0
        tgt = tgt | recent
    O, C = D["open"].values.astype(float), D["close"].values.astype(float)
    n = len(D)
    rows = []
    d = i0
    while d < i1:
        if not tgt[d]:
            d += 1
            continue
        s = d
        while d < n and tgt[d]:
            d += 1
        last = d - 1                     # last close with target on
        if mode == "next_open":
            e, px_in = s + 1, (O[s + 1] if s + 1 < n else C[s])
            xday = last + 1 if last + 1 < n else last
            px_out = O[last + 1] if last + 1 < n else C[last]
        else:
            e, px_in, xday, px_out = s, C[s], min(last + 1, n - 1), C[min(last + 1, n - 1)]
        if e >= n:
            break
        cost = _cost(D, px_in, e, xday - 1 if mode == "next_open" else xday)
        rows.append((s, e, xday, px_in, px_out, px_out - px_in - cost, (px_out - px_in - cost) / px_in,
                     "regime", last - s + 1))
        d = last + 1
    return pd.DataFrame(rows, columns=["sig", "entry", "exit", "px_in", "px_out", "pnl", "ret", "why", "sessions"])


def random_exposure(D, trades: pd.DataFrame, mode, i0, i1, rng, n_runs=500):
    """Mean return of the same number of trades with the same session counts, random signal days."""
    if trades.empty:
        return np.full(n_runs, np.nan)
    O, C = D["open"].values.astype(float), D["close"].values.astype(float)
    L = trades["sessions"].values.astype(int)
    n = len(D)
    hi = np.maximum(i1 - L - 2, i0 + 1)
    s = (i0 + rng.random((n_runs, len(L))) * (hi - i0)[None, :]).astype(int)
    if mode == "next_open":
        pin, pout = O[np.minimum(s + 1, n - 1)], O[np.minimum(s + 1 + L[None, :], n - 1)]
        cost = ES_RT_PTS if D["sym"].iat[0] == "ES" else ETF_RT_PCT * pin
    else:
        pin, pout = C[s], C[np.minimum(s + L[None, :], n - 1)]
        cost = ETF_RT_PCT * pin
    return ((pout - pin - cost) / pin).mean(axis=1)
