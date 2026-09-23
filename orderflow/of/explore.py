"""Exploration machinery (EXPLORATION_PROTOCOL.md): splits, trial ledger, events, screen, flush filters."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .config import COST_RT, DEV, HOLDOUT, PQ, RESULTS

VAL_END = pd.Timestamp("2025-07-01", tz="UTC")
DISC_END = pd.Timestamp("2024-01-01", tz="UTC")
LEDGER = RESULTS / "EXPLORATION_LEDGER.csv"


def split_of(sym: pd.Series, t: pd.Series) -> pd.Series:
    dev = sym.isin(DEV).values
    tt = t.values
    s = np.where(tt >= VAL_END.to_datetime64(), "vault",
                 np.where(dev & (tt < DISC_END.to_datetime64()), "discovery", "validation"))
    return pd.Series(s, index=sym.index)


def load_structure(sym: str) -> pd.DataFrame:
    return pd.read_parquet(PQ / "structure" / f"{sym}.parquet")


# ---------- statistics ----------

def day_t(x: pd.Series, t: pd.Series) -> tuple[float, int]:
    g = x.groupby(t.dt.floor("D")).mean()
    if len(g) < 3 or g.std() == 0:
        return np.nan, len(g)
    return float(g.mean() / (g.std() / np.sqrt(len(g)))), len(g)


def diff_day_t(a: pd.Series, ta: pd.Series, b: pd.Series, tb: pd.Series) -> float:
    ga, gb = a.groupby(ta.dt.floor("D")).mean(), b.groupby(tb.dt.floor("D")).mean()
    if len(ga) < 3 or len(gb) < 3:
        return np.nan
    return float((ga.mean() - gb.mean()) / np.sqrt(ga.var() / len(ga) + gb.var() / len(gb)))


def summarize(E: pd.DataFrame, col: str = "net") -> dict:
    """mean = per-trade mean (fixed notional per trade); dmean = mean of per-day means (fixed capital per
    day split across that day's trades); t = day-clustered t of the per-day means."""
    t, nd = day_t(E[col], E.t)
    dm = E[col].groupby(E.t.dt.floor("D")).mean().mean() if len(E) else np.nan
    return dict(n=len(E), days=nd, mean=E[col].mean(), dmean=dm, med=E[col].median(), win=(E[col] > 0).mean(), t=t)


def log(rows: list[dict]):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    D = pd.DataFrame(rows)
    D.insert(0, "logged", now)
    D.to_csv(LEDGER, mode="a", header=not LEDGER.exists(), index=False)


# ---------- events (family A) ----------

def _first_per(cond: pd.Series, key) -> pd.Series:
    c = cond.fillna(False).astype(bool)
    return c & (c.astype(int).groupby(key).cumsum() == 1)


def events(X: pd.DataFrame) -> dict[str, tuple[pd.Series, int, str | None]]:
    """name -> (bool trigger series, side +1/-1, target column or None)."""
    idx = X.index
    dkey = idx.floor("D")
    wkey = dkey - pd.to_timedelta(idx.dayofweek, unit="D")
    same_d = pd.Series(dkey, index=idx) == pd.Series(dkey, index=idx).shift(1)
    same_w = pd.Series(wkey, index=idx) == pd.Series(wkey, index=idx).shift(1)
    c, c1 = X.c, X.c.shift(1)
    inPD = lambda z: (z >= X.PDVAL) & (z <= X.PDVAH)
    inPW = lambda z: (z >= X.PWVAL) & (z <= X.PWVAH)
    hr = pd.Series(idx.hour, index=idx)
    newlow = (X.l <= X.dL) & (X.dL < X.dL.shift(1)) & same_d
    newhigh = (X.h >= X.dH) & (X.dH > X.dH.shift(1)) & same_d
    E = {
        "A1L_fail_below_PDL": (_first_per((X.dL < X.PDL) & (c > X.PDL), dkey), 1, None),
        "A1S_fail_above_PDH": (_first_per((X.dH > X.PDH) & (c < X.PDH), dkey), -1, None),
        "A2L_fail_below_PWL": (_first_per((X.wL < X.PWL) & (c > X.PWL), wkey), 1, None),
        "A2S_fail_above_PWH": (_first_per((X.wH > X.PWH) & (c < X.PWH), wkey), -1, None),
        "A3S_accept_below_PDL": (_first_per((c < X.PDL) & (c1 < X.PDL) & same_d, dkey), -1, None),
        "A3L_accept_above_PDH": (_first_per((c > X.PDH) & (c1 > X.PDH) & same_d, dkey), 1, None),
        "A4L_80pct_from_below": (_first_per((X.dO < X.PDVAL) & inPD(c) & inPD(c1) & same_d, dkey), 1, "PDVAH"),
        "A4S_80pct_from_above": (_first_per((X.dO > X.PDVAH) & inPD(c) & inPD(c1) & same_d, dkey), -1, "PDVAL"),
        "A5L_close_above_dayVA": ((hr == 23) & (c > X.dVAH), 1, None),
        "A5S_close_below_dayVA": ((hr == 23) & (c < X.dVAL), -1, None),
        "A6L_newlow_pos_delta": (_first_per(newlow & (X.delta > 0), dkey), 1, None),
        "A6S_newhigh_neg_delta": (_first_per(newhigh & (X.delta < 0), dkey), -1, None),
        "A7L_dPOC_above_PDVAH_12": ((hr == 11) & (X.dPOC > X.PDVAH), 1, None),
        "A7S_dPOC_below_PDVAL_12": ((hr == 11) & (X.dPOC < X.PDVAL), -1, None),
        "A8L_week80_from_below": (_first_per((X.wO < X.PWVAL) & inPW(c) & inPW(c1) & same_w, wkey), 1, "PWVAH"),
        "A8S_week80_from_above": (_first_per((X.wO > X.PWVAH) & inPW(c) & inPW(c1) & same_w, wkey), -1, "PWVAL"),
        # added in discovery round 2 (post-hoc): A3 with the side reversed = fade acceptance outside PD range
        "A9L_fade_accept_below_PDL": (_first_per((c < X.PDL) & (c1 < X.PDL) & same_d, dkey), 1, "PDL"),
        "A9S_fade_accept_above_PDH": (_first_per((c > X.PDH) & (c1 > X.PDH) & same_d, dkey), -1, "PDH"),
    }
    return E


def event_trades(sym: str, X: pd.DataFrame, trig: pd.Series, side: int, hold: int = 24,
                 target: str | None = None) -> pd.DataFrame:
    t = X.index[trig.fillna(False).values.astype(bool)]
    if len(t) == 0:
        return pd.DataFrame()
    pos = X.index.get_indexer(t)
    net = (X[f"L{hold}"] if side > 0 else X[f"S{hold}"]).values[pos]
    out = pd.DataFrame({"sym": sym, "t": t, "side": side, "net": net})
    if target is not None:
        out["net_tp"] = [_tp_exit(X, p, side, X[target].values[p], hold) for p in pos]
    return out.dropna(subset=["net"])


def _tp_exit(X, p, side, tp, hold):
    """Limit exit at tp within the hold (hourly high/low touch), else the hold exit."""
    e = X.o.values[p + 1] if p + 1 < len(X) else np.nan
    if not np.isfinite(tp) or not np.isfinite(e):
        return np.nan
    if (side > 0 and tp <= e) or (side < 0 and tp >= e):
        return -COST_RT
    hi, lo = X.h.values[p + 1: p + 1 + hold], X.l.values[p + 1: p + 1 + hold]
    hit = np.flatnonzero(hi >= tp) if side > 0 else np.flatnonzero(lo <= tp)
    if len(hit) == 0:
        return (X[f"L{hold}"] if side > 0 else X[f"S{hold}"]).values[p]
    k = hit[0]
    fund = X[f"fund{hold}"].values[p] * (k + 1) / hold      # funding pro rata to the time held (approximation)
    return side * (tp / e - 1) - COST_RT - side * fund


# ---------- screen features (family C) and flush-filter features (family B) ----------

def screen_features(X: pd.DataFrame) -> pd.DataFrame:
    a = X.atr
    F = pd.DataFrame(index=X.index)
    F["pos_pd"] = (X.c - X.PDL) / (X.PDH - X.PDL)
    F["pos_pw"] = (X.c - X.PWL) / (X.PWH - X.PWL)
    F["pos_d"] = (X.c - X.dL) / (X.dH - X.dL)
    F["pos_w"] = (X.c - X.wL) / (X.wH - X.wL)
    for k in ["PDPOC", "PDVAH", "PDVAL", "PWPOC", "PWVAH", "PWVAL", "dPOC", "dVAH", "dVAL", "wPOC", "wVAH", "wVAL"]:
        F[f"x_{k}"] = (X.c - X[k]) / a
    F["mig_d"] = (X.dPOC - X.PDPOC) / a
    F["mig_w"] = (X.wPOC - X.PWPOC) / a
    F["cvd_d"] = X.dDELTA / X.dVOL
    F["cvd_w"] = X.wDELTA / X.wVOL
    F["dlt4"] = X.dlt4
    F["dlt6"] = X.dlt6
    F["pd_delta"] = X.PDDELTA / X.PDVOL
    F["pw_delta"] = X.PWDELTA / X.PWVOL
    F["ret24"] = X.ret24
    F["ret4"] = X.ret4
    F["oi24"] = X.oi24
    F["fund_rate"] = X.fund_last
    F["swept_pdl"] = (X.low6 < X.PDL).astype(float)
    F["swept_pwl"] = (X.low6 < X.PWL).astype(float)
    F["above_pdl"] = (X.c > X.PDL).astype(float)
    F["above_pwl"] = (X.c > X.PWL).astype(float)
    F["reclaim_pdl"] = ((X.low6 < X.PDL) & (X.c > X.PDL)).astype(float)
    F["reclaim_pwl"] = ((X.low6 < X.PWL) & (X.c > X.PWL)).astype(float)
    F["in_pdva"] = ((X.c >= X.PDVAL) & (X.c <= X.PDVAH)).astype(float)
    F["below_pdval"] = (X.c < X.PDVAL).astype(float)
    F["below_pwval"] = (X.c < X.PWVAL).astype(float)
    return F


BINARY = {"swept_pdl", "swept_pwl", "above_pdl", "above_pwl", "reclaim_pdl", "reclaim_pwl", "in_pdva",
          "below_pdval", "below_pwval"}


def tercile_spread(D: pd.DataFrame, feat: str, ret: str, cut_src: pd.DataFrame) -> dict:
    """Top-third minus bottom-third (or 1 minus 0 for binaries) of `ret`, cutoffs from cut_src."""
    x = D[feat]
    if feat in BINARY:
        g, b = D[x == 1], D[x == 0]
        desc = "1 - 0"
    else:
        q1, q2 = cut_src[feat].quantile([1 / 3, 2 / 3])
        g, b = D[x > q2], D[x <= q1]
        desc = f"top(>{q2:.3g}) - bottom(<={q1:.3g})"
    return dict(feature=feat, compare=desc, n_top=len(g), n_bot=len(b), top=g[ret].mean(), bot=b[ret].mean(),
                spread=g[ret].mean() - b[ret].mean(), t=diff_day_t(g[ret], g.t, b[ret], b.t))
