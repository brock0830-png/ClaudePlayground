"""Apply the pass rules of SPEC_value_area_tests.md to the per-signal feature table.

Cells: dev 22-23, dev 24-26 (the 9 Kraken coins) and holdout (the 26 coins, all dates).
Tercile cutoffs come from dev 22-23 only and are frozen for every other cell.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DEV, HOLDOUT, SPLIT

FEATURES = [  # id, kind, good side, judged on dev too?
    ("V1", "bin", 1, True),
    ("V2", "cont", "high", True),
    ("V3", "cont", "low", True),
    ("F1r", "cont", "low", False),
]


def cells(F: pd.DataFrame) -> dict[str, pd.DataFrame]:
    d = F[F.sym.isin(DEV)]
    return {"dev 22-23": d[d.t < SPLIT], "dev 24-26": d[d.t >= SPLIT], "holdout": F[F.sym.isin(HOLDOUT)]}


def day_means(x: pd.DataFrame, col: str = "net") -> pd.Series:
    return x.groupby(x.t.dt.floor("D"))[col].mean()


def diff_t(G: pd.DataFrame, B: pd.DataFrame, col: str = "net") -> float:
    """Welch t of good-minus-bad on day-clustered means (same-day signals averaged into one obs)."""
    g, b = day_means(G, col), day_means(B, col)
    if len(g) < 2 or len(b) < 2:
        return np.nan
    return (g.mean() - b.mean()) / np.sqrt(g.var() / len(g) + b.var() / len(b))


def mean_t(x: pd.DataFrame, col: str = "net") -> float:
    g = day_means(x, col)
    return g.mean() / (g.std() / np.sqrt(len(g))) if len(g) > 1 else np.nan


def splitters(F: pd.DataFrame, k: str, kind: str, good):
    if kind == "bin":
        return (lambda x: x[x[k] == 1]), (lambda x: x[x[k] == 0]), "1 vs 0"
    A = cells(F)["dev 22-23"]
    q1, q2 = A[k].quantile([1 / 3, 2 / 3])
    if good == "high":
        g = lambda x: x[x[k] > q2]; b = lambda x: x[x[k] <= q1]
        return g, b, f"top third (> {q2:.4g}) vs bottom third (<= {q1:.4g})"
    g = lambda x: x[x[k] <= q1]; b = lambda x: x[x[k] > q2]
    return g, b, f"bottom third (<= {q1:.4g}) vs top third (> {q2:.4g})"


def feature_table(F: pd.DataFrame) -> pd.DataFrame:
    F = F[F.missing == 0]
    C = cells(F)
    rows = []
    for k, kind, good, dev_judged in FEATURES:
        g, b, desc = splitters(F, k, kind, good)
        r = {"feature": k, "good vs bad": desc}
        for name, x in C.items():
            G, Bd = g(x), b(x)
            r[f"{name} good"] = f"{100 * G.net.mean():+.2f}% (n={len(G)})"
            r[f"{name} bad"] = f"{100 * Bd.net.mean():+.2f}% (n={len(Bd)})"
            r[f"{name} diff"] = round(100 * (G.net.mean() - Bd.net.mean()), 3)
            r[f"{name} day-t"] = round(diff_t(G, Bd), 2)
        dev_ok = (r["dev 22-23 diff"] > 0 and r["dev 24-26 diff"] > 0) if dev_judged else True
        hold_ok = r["holdout diff"] > 0 and r["holdout day-t"] >= 2.5
        r["dev rule"] = ("pass" if dev_ok else "fail") if dev_judged else "n/a (holdout only)"
        r["holdout rule"] = "pass" if hold_ok else "fail"
        r["PASS"] = bool(dev_ok and hold_ok)
        rows.append(r)
    return pd.DataFrame(rows)


def daily_pnl(x: pd.DataFrame, net_col: str, t_col: str, start, end) -> pd.Series:
    """Fixed notional per trade; P&L booked on the UTC exit day; days without exits = 0."""
    s = x.groupby(pd.to_datetime(x[t_col], utc=True).dt.floor("D"))[net_col].sum()
    last = max(pd.Timestamp(end) - pd.Timedelta("1D"), s.index.max()) if len(s) else pd.Timestamp(end)
    idx = pd.date_range(pd.Timestamp(start), last, freq="D")
    return s.reindex(idx, fill_value=0.0)


def sharpe(d: pd.Series) -> float:
    return d.mean() / d.std() * np.sqrt(365) if d.std() > 0 else np.nan


def x1_table(F: pd.DataFrame) -> pd.DataFrame:
    F = F[F.missing == 0]
    C = cells(F)
    bounds = {"dev 22-23": ("2022-01-01", "2024-01-01"), "dev 24-26": ("2024-01-01", "2026-09-01"),
              "holdout": ("2022-01-01", "2026-09-01")}
    rows = []
    for name, x in C.items():
        a, b = (pd.Timestamp(v, tz="UTC") for v in bounds[name])
        base = daily_pnl(x, "net", "exit_t", a, b)
        x1 = daily_pnl(x, "x1_net", "x1_t", a, b)
        rows.append({"cell": name, "n": len(x), "TP hit rate": round(x.x1_hit.mean(), 3),
                     "TP at/below entry": int((x.POC0 <= x.entry).sum()),
                     "24h: mean net": f"{100 * x.net.mean():+.3f}%", "24h: total": f"{100 * x.net.sum():+.1f}%",
                     "24h: daily Sharpe": round(sharpe(base), 2),
                     "X1: mean net": f"{100 * x.x1_net.mean():+.3f}%", "X1: total": f"{100 * x.x1_net.sum():+.1f}%",
                     "X1: daily Sharpe": round(sharpe(x1), 2),
                     "X1 better": bool(sharpe(x1) > sharpe(base))})
    T = pd.DataFrame(rows)
    T.attrs["PASS"] = bool(T["X1 better"].all())
    return T


def base_table(T: pd.DataFrame) -> pd.DataFrame:
    """Base-signal replication: count and net per trade per cell."""
    rows = []
    for name, x in cells(T).items():
        rows.append({"cell": name, "signals": len(x), "coins": x.sym.nunique(),
                     "mean net": f"{100 * x.net.mean():+.3f}%", "median net": f"{100 * x.net.median():+.3f}%",
                     "win rate": round((x.net > 0).mean(), 3), "day-clustered t": round(mean_t(x), 2),
                     "signal days": x.t.dt.floor("D").nunique()})
    return pd.DataFrame(rows)
