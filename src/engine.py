"""Vectorised daily backtester with explicit signal-to-execution lag.

Timing convention (base case): a target weight decided from data through the
close of day t is executed at the close of day t+1 and therefore first earns
the return from close t+1 to close t+2. In return-space that is a lag of 2.
lag=1 is "same-close" execution (sensitivity only); lag=3 is one extra day of
delay (robustness check).

Weights are fractions of equity in each instrument; the remainder (1 - sum)
is held in CASH and earns the CASH return column. Weights must be >= 0 and
sum to <= 1 (long-only, no borrowing). Leverage comes only from the
instruments themselves (leveraged ETFs), tracked via the `leverage` map.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

BASE_LAG = 2


@dataclass
class CostModel:
    commission_bp: float = 2.0                     # per trade, both sides
    half_spread_bp: dict = field(default_factory=dict)  # per instrument
    default_half_spread_bp: float = 1.0
    leveraged: set = field(default_factory=set)    # instruments whose cost is doubled
    multiplier: float = 1.0                        # 0, 1, 3 sensitivity

    def per_unit(self, cols) -> np.ndarray:
        out = []
        for c in cols:
            hs = self.half_spread_bp.get(c, self.default_half_spread_bp)
            bp = self.commission_bp + hs
            if c in self.leveraged:
                bp *= 2
            out.append(bp / 1e4 * self.multiplier)
        return np.array(out)


@dataclass
class Result:
    returns: pd.Series          # daily portfolio net returns
    equity: pd.Series
    weights_held: pd.DataFrame  # weights in force during each day (after lag)
    turnover: pd.Series         # one-way turnover per day (sum |trade|)
    costs: pd.Series
    trades: pd.Series           # number of instruments traded per day
    gross_leverage: pd.Series   # sum(w_i * L_i)
    lag: int


def run(target: pd.DataFrame, rets: pd.DataFrame, cash: pd.Series, cost: CostModel | None = None,
        lag: int = BASE_LAG, leverage: dict | None = None, rebalance_threshold: float = 0.0) -> Result:
    """Run the backtest.

    target: dates x instruments, weight decided using data through that date's close.
    rets:   dates x instruments, simple daily returns (close-to-close).
    cash:   daily return of the cash sleeve.
    rebalance_threshold: skip trading an instrument when |target - drifted| < threshold.
    """
    cost = cost or CostModel()
    leverage = leverage or {}
    cols = list(target.columns)
    rets = rets[cols].reindex(target.index)
    cash = cash.reindex(target.index)
    T = target.to_numpy(dtype=float)
    Rm = rets.to_numpy(dtype=float)
    C = cash.to_numpy(dtype=float)
    n, k = T.shape
    if np.nanmin(T) < -1e-12:
        raise ValueError("long-only: negative target weight")
    if np.nanmax(T.sum(axis=1)) > 1 + 1e-9:
        raise ValueError("weights sum above 1: no borrowing allowed")
    unit_cost = cost.per_unit(cols)
    L = np.array([leverage.get(c, 1.0) for c in cols])

    held = np.zeros((n, k))      # weights in force during day i (earn Rm[i])
    port = np.zeros(n)
    turnover = np.zeros(n)
    costs = np.zeros(n)
    trades = np.zeros(n)
    w_prev = np.zeros(k)         # weights at close of previous day, after drift
    for i in range(n):
        # weights in force during day i are those set at the close of day i-1
        held[i] = w_prev
        r = np.nan_to_num(Rm[i], nan=0.0)   # instrument unavailable -> treated as flat (should not be held)
        cash_w = 1.0 - w_prev.sum()
        gross = float(w_prev @ r + cash_w * (C[i] if not np.isnan(C[i]) else 0.0))
        # drift weights through day i
        w_drift = w_prev * (1 + r) / (1 + gross) if (1 + gross) != 0 else w_prev
        # execute at the close of day i the target decided at close of day i - (lag - 1)
        j = i - (lag - 1)
        if j >= 0 and not np.isnan(T[j]).any():
            w_new = T[j].copy()
            delta = w_new - w_drift
            if rebalance_threshold > 0:
                small = np.abs(delta) < rebalance_threshold
                w_new[small] = w_drift[small]
                delta = w_new - w_drift
            trade_cost = float(np.abs(delta) @ unit_cost)
            turnover[i] = float(np.abs(delta).sum())
            trades[i] = int((np.abs(delta) > 1e-12).sum())
            costs[i] = trade_cost
            port[i] = gross - trade_cost
            w_prev = w_new
        else:
            port[i] = gross
            w_prev = w_drift
    idx = target.index
    ret = pd.Series(port, idx, name="ret")
    return Result(returns=ret, equity=(1 + ret).cumprod(),
                  weights_held=pd.DataFrame(held, idx, cols), turnover=pd.Series(turnover, idx),
                  costs=pd.Series(costs, idx), trades=pd.Series(trades, idx),
                  gross_leverage=pd.Series(held @ L, idx), lag=lag)
