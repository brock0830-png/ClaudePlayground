"""
Phase 4 (PROTOCOL_P4.md): stress tests of the frozen P2A and P3B. Rules come from
results/p3/frozen_candidates.json and are executed by the unchanged Phase 3 engine (scalpel/p3.py).

This module adds: the P4 lock, loaders for the fresh ETFs / SPX / SPY top-up, random-entry benchmarks
(1,000 draws, optional eligible-day mask), month-clustered bootstrap CIs, deflated Sharpe with the
cumulative trial count, daily mark-to-market P&L, and the append-only results/p4/log.csv.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from . import p3
from .data import DATA, RESULTS, ROOT
from .stats import deflated_sharpe

OUT = RESULTS / "p4"
LOCK = OUT / "TEST_UNLOCKED"
LOG = OUT / "log.csv"
FRESH = ["XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "EWZ", "EWA", "EWC", "EWY", "EWT", "FXI", "INDA", "EWW"]
P3_TEST = list(p3.TEST_SYMBOLS)
LAST_SIGNAL = pd.Timestamp("2026-09-29")          # last VIX date
N_PRIOR_TRIALS = 12514 + 640 + 258                # Phases 1-3 (results/log.csv, p2/log.csv, p3/log.csv)
TRIAL_VAR = 0.0043                                 # Phase 3 per-trade Sharpe variance (n >= 60), as in Phase 3
N_DRAWS = 1000
HV_VIX = 25.0
HV_TICKS_USD = 0.04                               # 2 ticks x $0.01 per side, round trip, per share
HV_ES_PTS = 1.0                                   # 2 ticks x 0.25 pt per side, round trip
FROZEN = {c["name"]: c["spec"] for c in json.loads((RESULTS / "p3" / "frozen_candidates.json").read_text())}
P2A = FROZEN["P2A_reference"]
P3B = FROZEN["P3B_oversold_score90"]


# ------------------------------------------------------------------ lock
def check_lock():
    if not LOCK.exists():
        raise SystemExit("Phase 4 tests are locked: results/p4/TEST_UNLOCKED missing")
    h = LOCK.read_text().split()[0]
    proto = subprocess.run(["git", "log", "--format=%H", "--", "PROTOCOL_P4.md"], cwd=ROOT,
                           capture_output=True, text=True).stdout.split()
    if not proto or proto[-1] != h:
        raise SystemExit(f"TEST_UNLOCKED {h} is not the commit that created PROTOCOL_P4.md ({proto[-1:]})")
    if proto[0] != h:
        raise SystemExit("PROTOCOL_P4.md changed after the unlock commit")
    frozen_dirty = subprocess.run(["git", "status", "--porcelain", "--", "results/p3/frozen_candidates.json",
                                   "scalpel/p3.py"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if frozen_dirty:
        raise SystemExit(f"frozen rules or engine modified:\n{frozen_dirty}")


# ------------------------------------------------------------------ data
def load_etf(sym: str) -> pd.DataFrame:
    """Dividend-adjusted daily bars + Phase 3 features. Seen ETFs get the top-up rows after their file."""
    d = pd.read_csv(p3.ETF_DIR / f"{sym}.csv.gz", parse_dates=["date"])
    up = DATA / "external" / "etf_update" / f"{sym}.csv"
    if up.exists():
        u = pd.read_csv(up, parse_dates=["date"])
        d = pd.concat([d, u[u["date"] > d["date"].max()]], ignore_index=True)
    D = p3.add_features(d, p3.vix_features())
    D["roll"] = False
    D["sym"] = sym
    return D


def load_gspc() -> pd.DataFrame:
    d = pd.read_csv(DATA / "external" / "GSPC.csv.gz", parse_dates=["date"])
    D = p3.add_features(d, p3.vix_features())
    D["roll"] = False
    D["sym"] = "SPX"
    return D


def load_es(split="all") -> pd.DataFrame:
    from .data import load_bars
    return p3.es_daily(load_bars(split))


def window(D: pd.DataFrame, start=None, end=LAST_SIGNAL, warm=252) -> tuple[int, int]:
    """Signal index range: from the 253rd bar (or `start`, whichever is later) to the last date <= end."""
    dates = D["date"].values
    i0 = warm
    if start is not None:
        i0 = max(i0, int(np.searchsorted(dates, np.datetime64(pd.Timestamp(start)))))
    i1 = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(end)), side="right"))
    return i0, i1


# ------------------------------------------------------------------ trades and costs
def trades(D, spec, mode, i0, i1) -> pd.DataFrame:
    t = p3.simulate(D, spec, mode, i0, i1)
    if len(t) == 0:
        return t.assign(sym=[], date=[], vix=[])
    return t.assign(sym=D["sym"].iat[0], date=D["date"].values[t["sig"].values],
                    vix=D["vix"].values[t["sig"].values], trend=(D["ma50"] > D["ma200"]).values[t["sig"].values])


def highvix_ret(D, sig_idx, px_in, ret, unadj_px=None):
    """High-VIX slippage case: extra 2 ticks per side when VIX at the signal > 25."""
    v = D["vix"].values[sig_idx]
    hv = np.nan_to_num(v) > HV_VIX
    if D["sym"].iat[0] == "ES":
        return ret - hv * HV_ES_PTS / px_in
    den = px_in if unadj_px is None else unadj_px
    return ret - hv * HV_TICKS_USD / den


# ------------------------------------------------------------------ random entries
def random_entries(D, t: pd.DataFrame, mode, i0, i1, rng, n_draws=N_DRAWS, eligible=None, highvix=False,
                   unadj=None, raw_open=None):
    """Mean return of each of n_draws sets of random entries (same count, same holding sessions, same
    execution mode and costs). Entry (signal) days uniform over [i0, i1) restricted to `eligible`
    (bool array) and to days whose exit fits in the data."""
    if len(t) == 0:
        return np.full(n_draws, np.nan)
    O, C = D["open"].values.astype(float), D["close"].values.astype(float)
    n = len(D)
    ok = np.zeros(n, bool)
    ok[i0:i1] = True
    if eligible is not None:
        ok &= np.asarray(eligible, bool)
    cand = np.flatnonzero(ok)
    is_es = D["sym"].iat[0] == "ES"
    rollcum = np.r_[0, np.cumsum(D["roll"].values.astype(int))]
    vix = np.nan_to_num(D["vix"].values.astype(float))
    total = np.zeros(n_draws)
    L = t["sessions"].values.astype(int)
    for l in np.unique(L):
        k = int((L == l).sum())
        pool = cand[cand + l + (1 if mode == "next_open" else 0) < n]
        if len(pool) == 0:
            return np.full(n_draws, np.nan)
        s = pool[rng.integers(0, len(pool), size=(n_draws, k))]
        if mode == "next_open":
            e, x = s + 1, s + 1 + l
            pin, pout = O[e], O[x]
            last_held = x - 1
        else:
            e, x = s, s + l
            pin, pout = C[e], C[x]
            last_held = x
        if is_es:
            rolls = np.where(last_held > e, rollcum[last_held + 1] - rollcum[e + 1], 0)
            cost = p3.ES_RT_PTS + p3.ES_ROLL_PTS * rolls
        else:
            cost = p3.ETF_RT_PCT * pin
        den = pin if raw_open is None else raw_open[e]          # ES: % of the raw traded price
        r = (pout - pin - cost) / den
        if highvix:
            hv = vix[s] > HV_VIX
            extra = (HV_ES_PTS / pin) if is_es else HV_TICKS_USD / (pin if unadj is None else unadj[s])
            r = r - hv * extra
        total += r.sum(axis=1)
    return total / len(L)


def add_excess(D, t, mode, i0, i1, rng, eligible=None, col="ret", highvix=False, unadj=None):
    """Adds 'bench' (market benchmark mean) and 'excess' = t[col] - bench; returns (t, draws)."""
    draws = random_entries(D, t, mode, i0, i1, rng, eligible=eligible, highvix=highvix, unadj=unadj)
    bench = float(np.nanmean(draws))
    t = t.assign(bench=bench, excess=t[col] - bench)
    return t, draws


# ------------------------------------------------------------------ statistics
def month_ci(x: pd.Series, dates: pd.Series, n_boot=10000, seed=17):
    """Pooled mean with a month-clustered bootstrap 95% CI (all trades signalled in a month move together)."""
    m = pd.DataFrame({"x": np.asarray(x, float), "m": pd.to_datetime(dates).dt.to_period("M")}).groupby("m")["x"]
    S, N = m.sum().values, m.size().values
    if len(S) < 2:
        return float(S.sum() / max(N.sum(), 1)), np.nan, np.nan
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(S), size=(n_boot, len(S)))
    b = S[idx].sum(1) / N[idx].sum(1)
    return float(S.sum() / N.sum()), float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))


def paired_month_ci(a: pd.DataFrame, b: pd.DataFrame, col="excess", n_boot=10000, seed=19):
    """CI of mean(a[col]) - mean(b[col]) resampling the same calendar months for both arms."""
    ma = a.groupby(pd.to_datetime(a["date"]).dt.to_period("M"))[col].agg(["sum", "size"])
    mb = b.groupby(pd.to_datetime(b["date"]).dt.to_period("M"))[col].agg(["sum", "size"])
    M = ma.join(mb, how="outer", lsuffix="_a", rsuffix="_b").fillna(0.0)
    Sa, Na, Sb, Nb = (M[c].values for c in ("sum_a", "size_a", "sum_b", "size_b"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(M), size=(n_boot, len(M)))
    d = Sa[idx].sum(1) / np.maximum(Na[idx].sum(1), 1) - Sb[idx].sum(1) / np.maximum(Nb[idx].sum(1), 1)
    point = Sa.sum() / Na.sum() - Sb.sum() / Nb.sum()
    return float(point), float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))


def basic(r) -> dict:
    r = np.asarray(r, float)
    if len(r) == 0:
        return dict(n=0)
    return dict(n=int(len(r)), mean_pct=float(r.mean() * 100), win=float((r > 0).mean()),
                pf=float(r[r > 0].sum() / -r[r < 0].sum()) if (r < 0).any() else float("inf"),
                worst_pct=float(r.min() * 100))


def n_trials_now() -> int:
    n4 = len(pd.read_csv(LOG)) if LOG.exists() else 0
    return N_PRIOR_TRIALS + n4


def dsr(r) -> dict:
    r = np.asarray(r, float)
    if len(r) < 3 or r.std() == 0:
        return {}
    N = n_trials_now()
    d = deflated_sharpe(float(r.mean() / r.std(ddof=1)), len(r), float(pd.Series(r).skew()),
                        float(pd.Series(r).kurt() + 3), TRIAL_VAR, N)
    d["n_trials"] = N
    return d


# ------------------------------------------------------------------ daily mark-to-market
def daily_mtm(D: pd.DataFrame, t: pd.DataFrame, mode: str, unit="pct", denom: str = "px_in") -> pd.Series:
    """Daily P&L by bar date. unit='pct': fraction of the entry notional; 'pts': price points.
    close mode: entry at C[e], marked at closes e+1..x, cost at exit. next_open (ES): entry at O[e],
    marked at closes e..x-1, the exit at O[x] is booked on bar x's date; cost at exit."""
    O, C = D["open"].values.astype(float), D["close"].values.astype(float)
    dates = pd.DatetimeIndex(D["date"])
    pnl = np.zeros(len(D))
    for r in t.itertuples():
        e, x, pin = int(r.entry), int(r.exit), float(r.px_in)
        cost = (r.px_out - pin) - r.pnl                     # total cost of this trade in points
        if mode == "next_open":
            path = np.r_[pin, C[e:x], O[x]] if x > e else np.r_[pin, O[x]]
            days = np.r_[np.arange(e, x), x]
        else:
            path = C[e:x + 1]
            days = np.arange(e + 1, x + 1)
        step = np.diff(path)
        step[-1] -= cost
        scale = (1.0 / float(getattr(r, denom))) if unit == "pct" else 1.0
        np.add.at(pnl, days, step * scale)
    return pd.Series(pnl, index=dates)


# ------------------------------------------------------------------ log
LOG_COLS = ["logged", "test", "variant", "system", "universe", "mode", "cost_case", "n", "markets", "mean_ret_pct",
            "excess_pct", "ci_lo_pct", "ci_hi_pct", "share_markets_pos", "dsr", "n_trials", "verdict", "note"]


def log(rows: list[dict]):
    OUT.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    D = pd.DataFrame(rows).assign(logged=now).reindex(columns=LOG_COLS)
    D.to_csv(LOG, mode="a", header=not LOG.exists(), index=False)


# ------------------------------------------------------------------ universe runner (A3, B1, B2)
def run_universe(syms, spec, mode, seed, loader=None, start=None, end=LAST_SIGNAL, highvix=True):
    """Per market: trades, 1,000-draw random benchmark, excess (base and high-VIX cost cases).
    Returns (pooled trades with columns ret, excess, ret_hv, excess_hv; per-market dict)."""
    loader = loader or load_etf
    rng = np.random.default_rng(seed)
    pooled, per = [], {}
    for sym in syms:
        D = loader(sym)
        i0, i1 = window(D, start, end)
        t = trades(D, spec, mode, i0, i1)
        if len(t) == 0:
            per[sym] = {"n": 0, "start": str(pd.Timestamp(D["date"].iat[i0]).date())}
            continue
        t, draws = add_excess(D, t, mode, i0, i1, rng)
        s = basic(t["ret"].values)
        s.update(start=str(pd.Timestamp(D["date"].iat[i0]).date()), bench_pct=float(t["bench"].iat[0] * 100),
                 excess_pct=float(t["excess"].mean() * 100),
                 rand_pctile=float((draws < t["ret"].mean()).mean() * 100))
        if highvix:
            t["ret_hv"] = highvix_ret(D, t["sig"].values, t["px_in"].values, t["ret"].values)
            hv_draws = random_entries(D, t, mode, i0, i1, rng, highvix=True)
            t["excess_hv"] = t["ret_hv"] - float(np.nanmean(hv_draws))
            s["excess_hv_pct"] = float(t["excess_hv"].mean() * 100)
        per[sym] = s
        pooled.append(t)
    P = pd.concat(pooled, ignore_index=True) if pooled else pd.DataFrame()
    return P, per


def pooled_summary(P, per, col="excess", raw="ret") -> dict:
    m, lo, hi = month_ci(P[col], P["date"])
    pos = [k for k, v in per.items() if v.get("n", 0) and v.get("excess_pct", -1) > 0]
    traded = [k for k, v in per.items() if v.get("n", 0)]
    out = dict(basic(P[raw].values), excess_pct=m * 100, ci_lo_pct=lo * 100, ci_hi_pct=hi * 100,
               markets=len(traded), markets_pos=len(pos), share_markets_pos=len(pos) / max(len(per), 1))
    rm, rlo, rhi = month_ci(P[raw], P["date"])
    out.update(raw_ci_lo_pct=rlo * 100, raw_ci_hi_pct=rhi * 100)
    return out


# ------------------------------------------------------------------ ES raw (traded) prices
def es_raw_prices(split="all") -> pd.DataFrame:
    """Raw front-month session open/close aligned row-for-row with p3.es_daily(load_bars(split)).
    The engine's ES prices are roll-adjusted forward (anchored to the 2013 contract), so point P&L is
    correct but % returns must be divided by the RAW traded price."""
    from .data import load_bars
    from .p2 import es_context
    bars = load_bars(split)
    ctx = es_context(bars)
    sess = ctx["sess"]
    raw = pd.DataFrame({"open": bars["open"].values, "close": bars["close"].values, "sess": sess})
    g = raw.groupby("sess")
    out = pd.DataFrame({"raw_open": g["open"].first().values, "raw_close": g["close"].last().values})
    out["date"] = ctx["D"]["date"].values
    return out


def with_raw_denominator(t: pd.DataFrame, raw: pd.DataFrame, mode="next_open") -> pd.DataFrame:
    """ES trades: replace ret with pnl / raw entry price (entry at the raw session open in next_open mode)."""
    col = "raw_open" if mode == "next_open" else "raw_close"
    px_raw = raw[col].values[t["entry"].values]
    return t.assign(px_raw=px_raw, ret=t["pnl"] / px_raw)
