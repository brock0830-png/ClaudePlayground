#!/usr/bin/env python3
"""Print tomorrow's target weights for TALOS v2 (configuration T7) from data through today's close.

Usage:
  python daily_signal.py [--lever 1.25] [--holdings holdings.json] [--asof YYYY-MM-DD] [--v1]

Data: reads data/proxies/returns.parquet and levels.parquet (built by src/proxies.py from the FMP pulls in
data/raw/fmp). To run live, refresh the raw pulls through today's close, rerun `python src/proxies.py`, then run
this script. Rules are in RULES.md; parameters in src/system2.py (PARAMS_T7). --v1 prints the pre-registered
TALOS v1 instead (src/system.py PARAMS).

The rebalance band needs your current weights: pass --holdings as JSON {"QQQ_X": 0.35, ...} (fractions of equity,
using the panel's column names) and the script prints only the trades whose |target - current| exceeds 2%.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import system as S
import system2 as S2

LIVE = {"SPY_X": "SPY", "QQQ_X": "QQQ", "IWM_X": "IWM", "TLT_X": "TLT", "IEF_X": "IEF", "GLD_X": "GLD",
        "SSO_X": "SSO", "UPRO_X": "UPRO", "QLD_X": "QLD", "TQQQ_X": "TQQQ", "UBT_X": "UBT", "TMF_X": "TMF", "UST_X": "UST", "UGL_X": "UGL"}
BAND = 0.02

ap = argparse.ArgumentParser(); ap.add_argument("--lever", type=float, default=None); ap.add_argument("--holdings", default=None)
ap.add_argument("--asof", default=None); ap.add_argument("--v1", action="store_true", help="pre-registered TALOS v1 instead of T7")
a = ap.parse_args()
root = Path(__file__).resolve().parent
R = pd.read_parquet(root / "data/proxies/returns.parquet"); L = pd.read_parquet(root / "data/proxies/levels.parquet")
if a.asof:
    R = R[R.index <= a.asof]; L = L[L.index <= a.asof]
if a.v1:
    p = {**S.PARAMS, "lever": a.lever if a.lever is not None else 1.0}; w = S.build(R, L, p); label = "TALOS v1"
else:
    p = {**S2.PARAMS_T7, "lever": a.lever if a.lever is not None else S2.PARAMS_T7["lever"]}; w = S2.build2(R, L, p); label = "TALOS v2 (T7)"
today = w.index[-1]; tgt = w.iloc[-1]; tgt = tgt[tgt.abs() > 1e-9]
print(f"{label}. Data through close of {today.date()}. Target weights to execute at the NEXT close (lever {p['lever']}):")
for c, v in tgt.sort_values(ascending=False).items():
    print(f"  {LIVE.get(c, c):6s} {v:7.2%}")
print(f"  CASH   {1 - tgt.sum():7.2%}")
n = p["sma_len"]; q = L["QQQ_X"]; s = q.rolling(n).mean().iloc[-1]
if a.v1:
    state = "ABOVE (risk on)" if q.iloc[-1] > s else "BELOW (risk off)"
else:
    on = S2._gate(q, q.rolling(n).mean(), p["gate_band"]).iloc[-1]
    state = f"{'ON' if on else 'OFF'} (band: on above {s * (1 + p['gate_band']):.2f}, off below {s * (1 - p['gate_band']):.2f})"
print(f"\nQQQ close {q.iloc[-1]:.4f} vs {n}d SMA {s:.4f} -> gate {state}")
print(f"QQQ 20d realised vol: {R['QQQ_X'].rolling(20).std().iloc[-1] * 252 ** 0.5:.1%}")
if not a.v1:
    on_s = S2._gate(q, q.rolling(n).mean(), p["gate_band"]); low_s = S2._nday_low(q, p["dip_n"]) & on_s
    boost = bool((S2._hold_flag(low_s, p["dip_hold"]) & on_s).iloc[-1]); low = bool(low_s.iloc[-1])
    print(f"Dip trigger today (lowest close of last {p['dip_n']} while gate on): {'YES' if low else 'no'}; boost {'ACTIVE' if boost else 'inactive'} (a trigger within the last {p['dip_hold']} days doubles the vol-target size, capped at 100% of the sleeve)")
    g = L["GLD_X"]; gs = g.rolling(n).mean().iloc[-1]
    print(f"GLD close {g.iloc[-1]:.4f} vs {n}d SMA {gs:.4f} -> gold sleeve {'ON' if g.iloc[-1] > gs else 'OFF'}; GLD 20d vol {R['GLD_X'].rolling(20).std().iloc[-1] * 252 ** 0.5:.1%}")
if a.holdings:
    cur = pd.Series(json.load(open(a.holdings))).reindex(w.columns).fillna(0.0)
    d = (w.iloc[-1] - cur); d = d[d.abs() > BAND]
    print("\nTrades exceeding the 2% band:")
    for c, v in d.items():
        print(f"  {'BUY ' if v > 0 else 'SELL'} {LIVE.get(c, c):6s} {abs(v):7.2%} of equity")
    if d.empty:
        print("  none")
