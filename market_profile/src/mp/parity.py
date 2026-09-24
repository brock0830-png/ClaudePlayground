"""Print IB, POC, VAH, VAL and opening type for the most recent RTH sessions, in the traded
contract's own prices, for a side-by-side check against a TradingView TPO chart.

TradingView settings to match: symbol = the contract printed below (or ES1! unadjusted), session
09:30-16:15 America/New_York, TPO period 30 minutes, row size = 1 tick (0.25) or 2 ticks where
`rows` says 2, value area 70%.
"""
from __future__ import annotations

import sys

import pandas as pd

from .data import build_market
from .features import session_features, cross_session

WARMUP = 60


def parity(sym: str = "ES", last: int = 3) -> pd.DataFrame:
    m = build_market(sym)
    S = m.sessions.iloc[-(WARMUP + last):].reset_index(drop=True)
    b0 = int(S["b0"].iloc[0])
    bars = m.bars.iloc[b0:int(S["b1"].iloc[-1])].reset_index(drop=True)
    S["b0"] -= b0; S["b1"] -= b0
    feats = []
    for i in range(len(S)):
        b = bars.iloc[S["b0"].iloc[i]:S["b1"].iloc[i]]
        feats.append(session_features(b.o, b.h, b.l, b.c, b.v, b.minute, raw_offset=int(S["offset_t"].iloc[i])))
    D = cross_session(S, bars, feats)
    t = m.tick
    rows = []
    for i in range(len(S) - last, len(S)):
        off = int(S["offset_t"].iloc[i])
        px = lambda x: (x - off) * t
        r = D.iloc[i]
        rows.append({"date": S["date"].iloc[i].date(), "contract": S["contract"].iloc[i], "rows": f"{int(r.rs)} tick",
                     "open": px(r.O), "high": px(r.H), "low": px(r.L), "close": px(r.C),
                     "IB high": px(r.ib_hi), "IB low": px(r.ib_lo), "POC": px(r.poc), "VAH": px(r.vah),
                     "VAL": px(r.val), "opening type": r.open_type, "day type": r.day_type,
                     "vol POC": px(r.vpoc), "vol VAH": px(r.vvah), "vol VAL": px(r.vval)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    print(parity(sys.argv[1] if len(sys.argv) > 1 else "ES").to_string(index=False))
