"""The frozen H4 finalist as a pure function: daily closes in, target weights out.

Rule (crypto/PREREG.md H4, selected at design, passed the one-shot holdout):
  * a coin is eligible once it has 200 days of daily history before today's bar;
  * each eligible coin gets an equal slot: 1 / (number of eligible coins);
  * a coin's slot is held while its daily close > SMA(50) of daily closes, else it sits in the quote currency;
  * BTC gate: an alt may be held only while BTC's close > BTC's SMA(100). BTC itself is not gated;
  * every slot is reset to its target on the 1st of each month (UTC) and whenever the eligible set changes; on other
    days only coins that switch on or off trade, and the rest drift.
Decisions use closed daily bars (UTC midnight to midnight) and are executed right after the close.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import indicators as ind  # noqa: E402  (the same code the research used)


@dataclass(frozen=True)
class Params:
    sma_len: int = 50
    gate_len: int = 100
    gate_coin: str = "BTC"
    eligibility_days: int = 200


@dataclass
class Decision:
    asof: pd.Timestamp
    eligible: dict[str, bool]
    on: dict[str, bool]
    weights: dict[str, float]
    rebalance: bool
    gate_open: bool
    notes: list[str]


def _eligible(close: pd.Series, asof: pd.Timestamp, p: Params) -> bool:
    c = close.dropna()
    return len(c) > 0 and asof in c.index and c.index[0] <= asof - pd.Timedelta(days=p.eligibility_days)


def decide(closes: dict[str, pd.Series], asof: pd.Timestamp, p: Params = Params()) -> Decision:
    """closes: coin -> daily close series indexed by bar-open time (UTC midnight), closed bars only, up to asof."""
    notes = []
    gate_open = False
    g = closes.get(p.gate_coin)
    if g is not None and asof in g.index:
        gt = ind.sma_trend(g.loc[:asof].dropna(), p.gate_len)
        gate_open = bool(gt.iloc[-1] == 1.0) if len(gt) and pd.notna(gt.iloc[-1]) else False
    else:
        notes.append(f"gate coin {p.gate_coin} missing at {asof.date()}: all alts treated as off")
    elig, on = {}, {}
    for coin, c in closes.items():
        c = c.loc[:asof]
        elig[coin] = _eligible(c, asof, p)
        if not elig[coin]:
            on[coin] = False
            continue
        t = ind.sma_trend(c.dropna(), p.sma_len)
        trend_up = bool(t.iloc[-1] == 1.0) if pd.notna(t.iloc[-1]) else False
        on[coin] = trend_up and (coin == p.gate_coin or gate_open)
    n = sum(elig.values())
    weights = {c: (1.0 / n if (elig[c] and on[c]) else 0.0) for c in closes} if n else {c: 0.0 for c in closes}
    prev = asof - pd.Timedelta(days=1)
    elig_prev = {c: _eligible(s.loc[:prev], prev, p) for c, s in closes.items()}
    rebalance = asof.day == 1 or elig_prev != elig
    return Decision(asof, elig, on, weights, rebalance, gate_open, notes)


def decide_history(closes: dict[str, pd.Series], p: Params = Params()) -> tuple[pd.DataFrame, pd.Series]:
    """Vectorised weights and rebalance flags over every date (used by the parity tests)."""
    C = pd.DataFrame(closes).sort_index()
    idx = C.index
    first = {c: C[c].first_valid_index() for c in C.columns}
    E = pd.DataFrame({c: (idx >= first[c] + pd.Timedelta(days=p.eligibility_days)) for c in C.columns}, index=idx)
    E &= C.notna()
    on = pd.DataFrame({c: ind.sma_trend(C[c].dropna(), p.sma_len) for c in C.columns}).reindex(idx).fillna(0.0)
    gate = ind.sma_trend(C[p.gate_coin].dropna(), p.gate_len).reindex(idx).fillna(0.0)
    for c in C.columns:
        if c != p.gate_coin:
            on[c] = on[c] * gate
    n = E.sum(axis=1).replace(0, float("nan"))
    W = (on * E).div(n, axis=0).fillna(0.0)
    R = pd.Series(idx.day == 1, index=idx) | (E != E.shift(1)).any(axis=1)
    return W, R
