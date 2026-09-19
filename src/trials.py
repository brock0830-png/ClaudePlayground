"""Trial harness: run a weight rule through the engine on a window, compute metrics, log to TRIAL_LEDGER.csv."""
from __future__ import annotations

import csv, json, time
from pathlib import Path

import numpy as np
import pandas as pd

from engine import run, CostModel, BASE_LAG
from metrics import summary
from strategies import ALL_COLS, LEVERAGE, LEVERAGED_COLS

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "TRIAL_LEDGER.csv"
DESIGN = ("1998-01-02", "2015-12-31")
HOLDOUT = ("2016-01-04", "2026-09-18")
UNLOCK = ROOT / "HOLDOUT_UNLOCKED"   # created only at the freeze

HALF_SPREAD = {"SPY_X": 0.5, "QQQ_X": 0.5, "IWM_X": 1.0, "TLT_X": 1.0, "IEF_X": 1.0, "SHY_X": 0.5, "GLD_X": 1.0}
_counter = {"n": 0}


def load_panel():
    R = pd.read_parquet(ROOT / "data/proxies/returns.parquet")
    Lv = pd.read_parquet(ROOT / "data/proxies/levels.parquet")
    vix = pd.read_parquet(ROOT / "data/proxies/vix.parquet")["VIX"]
    return R, Lv, vix


def cost_model(mult=1.0):
    return CostModel(commission_bp=2.0, half_spread_bp=HALF_SPREAD, default_half_spread_bp=1.0,
                     leveraged=set(LEVERAGED_COLS), multiplier=mult)


def consecutive_roundtrips(deltas: pd.DataFrame) -> float:
    """Count (instrument, day) pairs with an executed buy on day i and an executed sell on day i+1."""
    up = deltas > 1e-9; down = deltas < -1e-9
    return float((up.shift(1, fill_value=False) & down).sum().sum())


def evaluate(target: pd.DataFrame, R: pd.DataFrame, window=DESIGN, lag=BASE_LAG, cost_mult=1.0,
             drop_periods: list[tuple[str, str]] | None = None):
    start, end = window
    if pd.Timestamp(end) > pd.Timestamp(DESIGN[1]) and not UNLOCK.exists():
        raise RuntimeError("holdout locked: evaluation past 2015-12-31 refused until freeze")
    idx = R.index[(R.index >= start) & (R.index <= end)]
    tgt = target.reindex(R.index)[ALL_COLS].loc[idx]
    res = run(tgt, R[ALL_COLS], R["CASH"], cost_model(cost_mult), lag=lag, leverage=LEVERAGE)
    ret = res.returns; keep = pd.Series(True, ret.index)
    if drop_periods:
        for a, b in drop_periods:
            keep[(ret.index >= a) & (ret.index <= b)] = False
    ret = ret[keep]
    yrs = len(ret) / 252
    m = summary(ret, rf=R["CASH"], spy=R["SPY_X"], weights_held=res.weights_held[keep],
                gross_leverage=res.gross_leverage.abs()[keep], turnover=res.turnover[keep], trades=res.trades[keep])
    m["ConsecRoundTripsPerYear"] = consecutive_roundtrips(res.deltas[keep]) / yrs
    return m, res


def log(phase, hyp, cell, params, window, lag, cost_mult, m, note=""):
    _counter["n"] += 1
    new = not LEDGER.exists() or LEDGER.stat().st_size == 0
    with open(LEDGER, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow("trial_id,timestamp,phase,hypothesis,cell,params,window_start,window_end,lag,cost_mult,cagr,vol,sharpe,sortino,maxdd,mar,turnover_ann,trades_per_year,consec_day_roundtrips_per_year,avg_leverage,note".split(","))
        tid = sum(1 for _ in open(LEDGER)) - 1 + 1
        w.writerow([tid, time.strftime("%Y-%m-%dT%H:%M:%S"), phase, hyp, cell, json.dumps(params, sort_keys=True),
                    window[0], window[1], lag, cost_mult,
                    round(m["CAGR"], 5), round(m["Vol"], 5), round(m["Sharpe"], 4), round(m["Sortino"], 4),
                    round(m["MaxDD"], 5), round(m["MAR"], 4), round(m["Turnover_ann"], 3), round(m["TradesPerYear"], 2),
                    round(m["ConsecRoundTripsPerYear"], 2), round(m["AvgLeverage"], 4), note])
    return tid


def trial(phase, hyp, cell, params, target, R, window=DESIGN, lag=BASE_LAG, cost_mult=1.0, note="", drop_periods=None):
    m, res = evaluate(target, R, window, lag, cost_mult, drop_periods)
    tid = log(phase, hyp, cell, params, window, lag, cost_mult, m, note)
    m["trial_id"] = tid
    return m, res
