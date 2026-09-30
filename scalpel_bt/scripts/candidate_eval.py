"""
Evaluate one frozen candidate over a date window: trades, full metrics, by-year, by-VIX,
jitter and round-grid baselines, DSR/PSR, equity plot. Used for the DEV candidate pages
and (unchanged) for the one-shot OOS run.

The simulator always runs over all loaded bars from the first bar, so period state
(first touch, open positions) carries across the window start exactly as in live
trading; only trades whose ENTRY falls inside [start, end] are kept.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from scalpel.screen import run_spec
from scalpel.levelsets import jitter_factors
from scalpel.stats import trade_frame, deflated_sharpe, psr
from scalpel import report

N_JIT = 500


def load_spec(s) -> dict:
    d = json.loads(s) if isinstance(s, str) else dict(s)
    for k in ("stop", "target"):
        if k in d:
            d[k] = tuple(d[k])
    return d


def trades_in_window(fr, spec, start, end, jit=None, grid=False) -> pd.DataFrame:
    parts = run_spec(fr, spec, 0, len(fr.o), jit=jit, grid=grid)
    t = pd.concat([trade_frame(fr, p) for p in parts], ignore_index=True)
    if t.empty:
        return t
    et = pd.to_datetime(t["entry_time"])
    t = t[(et >= start) & (et <= end)].sort_values("entry_time").reset_index(drop=True)
    return t


def evaluate_candidate(fr, spec, start, end, trial_var, n_trials, n_jit=N_JIT, seed=2020, plot_path=None, title=""):
    t = trades_in_window(fr, spec, start, end)
    out = {"spec": spec, "window": [str(start), str(end)]}
    out["metrics"] = report.full_metrics(t) if len(t) else {"trades": 0}
    if len(t) == 0:
        return out, t
    out["by_year"] = report.by_year(t).round(4).reset_index().to_dict("records")
    out["by_vix"] = report.by_vix(t).round(4).reset_index().astype({"vix_prev": str}).to_dict("records")
    rw = t["roll_week"].astype(bool)
    out["ex_roll_week_trades"] = {"trades": int((~rw).sum()), "ev_pts": float(t.loc[~rw, "net"].mean()) if (~rw).any() else None}
    rng = np.random.default_rng(seed)
    jev, curves = [], []
    for j in range(n_jit):
        tj = trades_in_window(fr, spec, start, end, jit=jitter_factors(rng))
        jev.append(tj["net"].mean() if len(tj) else np.nan)
        if plot_path is not None and j < 60 and len(tj):
            tj = tj.sort_values("exit_time")
            curves.append((pd.to_datetime(tj["exit_time"]).dt.tz_localize(None), tj["net"].cumsum().values))
    jev = np.array(jev)
    jv = jev[~np.isnan(jev)]
    out["jitter"] = {"runs": int(len(jv)), "mean_ev": float(jv.mean()), "p90_ev": float(np.quantile(jv, 0.9)),
                     "pct_rank_of_actual": float((jv < t["net"].mean()).mean() * 100)}
    tg = trades_in_window(fr, spec, start, end, grid=True)
    out["grid"] = {"trades": int(len(tg)), "ev_pts": float(tg["net"].mean()) if len(tg) else None}
    x = t["net"]
    sr = float(x.mean() / x.std(ddof=1))
    sk, ku = float(x.skew()), float(x.kurt() + 3.0)
    out["dsr"] = deflated_sharpe(sr, len(x), sk, ku, trial_var, n_trials)
    out["psr_vs_0"] = psr(sr, len(x), sk, ku)
    if plot_path is not None:
        report.plot_equity(t, plot_path, title, jitter_curves=curves)
    return out, t
