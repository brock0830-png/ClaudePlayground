#!/usr/bin/env python3
"""Print tomorrow's target weights for the final system from data through today's close.

Usage:
  python daily_signal.py [--lever 1.0] [--holdings holdings.json] [--asof YYYY-MM-DD]

Data: reads data/proxies/returns.parquet and levels.parquet (built by src/proxies.py from the FMP pulls in
data/raw/fmp). To run live, refresh the raw pulls through today's close, rerun `python src/proxies.py`, then run
this script. Rules are in RULES.md; parameters in src/system.py (PARAMS).

The rebalance band needs your current weights: pass --holdings as JSON {"QQQ_X": 0.35, ...} (fractions of equity,
using the panel's column names) and the script prints only the trades whose |target - current| exceeds 2%.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import system as S

LIVE = {"SPY_X": "SPY", "QQQ_X": "QQQ", "IWM_X": "IWM", "TLT_X": "TLT", "IEF_X": "IEF", "GLD_X": "GLD",
        "SSO_X": "SSO", "UPRO_X": "UPRO", "QLD_X": "QLD", "TQQQ_X": "TQQQ", "UBT_X": "UBT", "TMF_X": "TMF", "UST_X": "UST", "UGL_X": "UGL"}
BAND = 0.02

ap = argparse.ArgumentParser(); ap.add_argument("--lever", type=float, default=1.0); ap.add_argument("--holdings", default=None); ap.add_argument("--asof", default=None)
a = ap.parse_args()
root = Path(__file__).resolve().parent
R = pd.read_parquet(root / "data/proxies/returns.parquet"); L = pd.read_parquet(root / "data/proxies/levels.parquet")
if a.asof:
    R = R[R.index <= a.asof]; L = L[L.index <= a.asof]
w = S.build(R, L, {**S.PARAMS, "lever": a.lever})
today = w.index[-1]; tgt = w.iloc[-1]; tgt = tgt[tgt.abs() > 1e-9]
print(f"Data through close of {today.date()}. Target weights to execute at the NEXT close (lever {a.lever}):")
for c, v in tgt.sort_values(ascending=False).items():
    print(f"  {LIVE.get(c, c):6s} {v:7.2%}")
print(f"  CASH   {1 - tgt.sum():7.2%}")
q = L["QQQ_X"]; print(f"\nQQQ close vs 200d SMA: {q.iloc[-1]:.4f} vs {q.rolling(200).mean().iloc[-1]:.4f} -> {'ABOVE (risk on)' if q.iloc[-1] > q.rolling(200).mean().iloc[-1] else 'BELOW (risk off)'}")
print(f"QQQ 20d realised vol: {R['QQQ_X'].rolling(20).std().iloc[-1] * 252 ** 0.5:.1%}")
if a.holdings:
    cur = pd.Series(json.load(open(a.holdings))).reindex(w.columns).fillna(0.0)
    d = (w.iloc[-1] - cur); d = d[d.abs() > BAND]
    print("\nTrades exceeding the 2% band:")
    for c, v in d.items():
        print(f"  {'BUY ' if v > 0 else 'SELL'} {LIVE.get(c, c):6s} {abs(v):7.2%} of equity")
    if d.empty:
        print("  none")
