"""
Logic check for pine/docs_buyfear_systems_es.pine: re-implements its per-session state machines in Python
(same timing: signals from the session that just closed and that date's VIX close, entries/exits at the next
session's first-bar open) and compares the resulting trades with the research engines on ES 2013-2026.
Also writes pine/expected_trades_es.csv so trades drawn by the Pine script can be checked against the research.
Usage: python scripts/pine_replica.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from scalpel.data import load_bars
from scalpel import p2, p3

bars = load_bars("all")
ctx = p2.es_context(bars)
D = p3.es_daily(bars)                     # same sessions as ctx["D"], plus Phase 3 features
S = len(D)
first_bar = np.flatnonzero(np.r_[True, ctx["sess"][1:] != ctx["sess"][:-1]])   # first bar of each session
times = bars.index
ibs, vix, score = D["ibs"].values, D["vix"].values, D["os_score"].values
vx10 = D["vix"].rolling(10).mean().values
close, sma50 = D["close"].values, D["close"].rolling(50).mean().values
mom = (D["close"] > D["close"].shift(126)).values


def machine(sig, hold):
    """Pine P2A/P3B/P2C logic at each session start s: age, exit at open after `hold` sessions, then enter."""
    out, inpos, held, e = [], False, 0, None
    for s in range(1, S):
        exited = False
        if inpos:
            held += 1
            if held >= hold:
                out.append((e, s)); inpos = False; exited = True
        if not inpos and not exited and sig[s]:
            inpos, held, e = True, 0, s
    return out


def stacked(sig, hold, maxu):
    out, units = [], []                       # units: [entry_session, held]
    for s in range(1, S):
        keep = []
        for e, h in units:
            h += 1
            if h >= hold:
                out.append((e, s))
            else:
                keep.append([e, h])
        units = keep
        if sig[s] and len(units) < maxu:
            units.append([s, 0])
    return out


def regime(on):
    out, inpos, e = [], False, None
    for s in range(1, S):
        if inpos and not on[s]:
            out.append((e, s)); inpos = False
        elif not inpos and on[s]:
            inpos, e = True, s
    return out


def prev(x):
    return np.r_[False, x[:-1]]


with np.errstate(invalid="ignore"):
    sigA = prev((ibs < 0.3) & (vix > 20))
    sigB = prev(score > 0.9)
    sigC = prev(vix > 1.2 * vx10)
    onM = prev(mom)
pine = {"P2A": machine(sigA, 5), "P3B": machine(sigB, 5), "P3A": stacked(sigA, 5, 3),
        "P2C": machine(sigC, 10), "P3C": regime(onM)}

# research engines, converted to (entry session, exit session)
res = {}
t = p3.simulate(D, dict(entry=["ibs<0.3", "vix>20"], hold=5), "next_open"); res["P2A"] = list(zip(t.entry, t.exit))
t = p3.simulate(D, dict(entry=["os_score>0.9"], hold=5), "next_open"); res["P3B"] = list(zip(t.entry, t.exit))
t = p3.simulate(D, dict(entry=["ibs<0.3", "vix>20"], hold=5, max_concurrent=3), "next_open"); res["P3A"] = list(zip(t.entry, t.exit))
t = p3.simulate(D, dict(kind="target", regime=["mom126>zero"]), "next_open"); res["P3C"] = list(zip(t.entry, t.exit))
td = p2.daily_target(ctx["D"], dict(kind="entry_exit", entry=["vix_x_ma10>1.2"], exit="hold10", filters=[], side="long"))
r = p2.run_bars(ctx, p2.bar_target_from_daily(ctx, td), 0, len(bars))
sess_of = ctx["sess"]
res["P2C"] = [(int(sess_of[a]), int(sess_of[min(b + 1, len(bars) - 1)])) for a, b in zip(r["trades"].s, r["trades"].e)]

rows = []
for k in ["P2A", "P3B", "P3A", "P2C", "P3C"]:
    a, b = sorted(pine[k]), sorted(res[k])
    last = S - 1
    a = [x for x in a if x[1] < last]; b = [x for x in b if x[1] < last]     # ignore trades still open at the end
    match = len(set(a) & set(b))
    print(f"{k}: pine-logic {len(a)} trades, research {len(b)}, identical {match}")
    for e, x in pine[k]:
        eb, xb = first_bar[e], first_bar[x] if x < S else len(bars) - 1
        pnl = ctx["o"][xb] - ctx["o"][eb] - 0.60
        rows.append((k, times[eb], times[xb], round(pnl, 2)))

# P2B overnight: Pine enters at the session's first bar if the previous session closed below its 50-day SMA
# and exits at the open of the first bar from 10:00 ET; research = Phase 2 session engine.
hour = ctx["hour"]
pb = []
inpos, eb = False, None
for i in range(len(bars)):
    if inpos and 10 <= hour[i] < 17:
        pb.append((eb, i)); inpos = False
    s = sess_of[i]
    if hour[i] == 18 and s >= 1 and not inpos and close[s - 1] < sma50[s - 1]:
        inpos, eb = True, i
tgt = p2.session_target(ctx, dict(hours=[18, 22, 2, 6], side="long", filters=["close<ma50"]))
rb = p2.run_bars(ctx, tgt, 0, len(bars))["trades"]
rset = set(zip(rb.s, rb.e + 1))
print(f"P2B: pine-logic {len(pb)} trades, research {len(rb)}, identical {len(set(pb) & rset)}")
for e, x in pb:
    rows.append(("P2B", times[e], times[x], round(ctx["o"][x] - ctx["o"][e] - 0.60, 2)))

out = pd.DataFrame(rows, columns=["system", "entry_time_ET", "exit_time_ET", "pnl_pts_switch_adjusted"])
out.to_csv(ROOT / "pine" / "expected_trades_es.csv", index=False)
print("wrote pine/expected_trades_es.csv", len(out))
