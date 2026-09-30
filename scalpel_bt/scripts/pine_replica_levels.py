"""
Logic check for pine/docs_scalpel_level_trades_es.pine (C1/C2): replays its bar-by-bar state machine in
Python with the same approximations (expiration-week roll rule, Monday 17:00 pre-roll exit, Friday 17:00 week
end, VIX of the prior session) and compares with the Phase 1 research engine on ES 2013-2026.
"""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from scalpel.data import load_bars, RESULTS
from scalpel.features import build_frame
from scalpel.strategies import level_array
from scalpel.screen import run_spec

bars = load_bars("all")
fr = build_frame(bars)
o, h, l, c = fr.o, fr.h, fr.l, fr.c
n = len(o)
t = bars.index
wk, day = bars["week_id"].values, bars["day_id"].values
newW = np.r_[True, wk[1:] != wk[:-1]]
f = fr.feat
L1 = level_array(fr, "W", "scaled", "GP_B_IN"); S1 = L1 - 0.25 * fr.sigma[("W", "scaled")]
L2 = level_array(fr, "W", "fixed", "GP_T_IN"); S2 = L2 - 0.25 * fr.sigma[("W", "fixed")]
dow = t.dayofweek.values; hr = t.hour.values
lastW = (dow == 4) & (hr == 14)                       # Friday bar closing 17:00 ET
preMon = (dow == 0) & (hr == 14)                      # Monday bar closing 17:00 ET
roll = np.zeros(n, bool)
for i in np.flatnonzero(newW):
    pdow = (dow[i] + 1) % 7 + 1                       # Pine: Sunday=1 ... Friday=6
    fri = t[i] + pd.Timedelta(days=6 - pdow)
    roll[i] = fri.month in (3, 6, 9, 12) and 15 <= fri.day <= 21
roll = pd.Series(np.where(newW, roll, np.nan)).ffill().astype(bool).values
e1 = (f["vix_prev"] < f["vix_mean252"]).values
e2 = (f["prev_close"] > f["ma20"]).values & ~roll


def run(C):
    out, inp, pend, done, below = [], False, False, False, False
    px = st = tg = ps = None; eb = None
    for i in range(n):
        if newW[i]:
            if inp and i > 0:
                out.append((eb, i - 1)); inp = False
            pend = done = below = False
        if pend:
            pend = False
            fill = o[i]
            if fill > ps:
                inp, px, st, eb = True, fill, ps, i
                tg = fill + (fill - ps) if C == 1 else np.inf
                if l[i] <= st:
                    out.append((eb, i)); inp = False
                elif h[i] >= tg:
                    out.append((eb, i)); inp = False
        elif inp:
            if l[i] <= st or h[i] >= tg:
                out.append((eb, i)); inp = False
        L, S = (L1[i], S1[i]) if C == 1 else (L2[i], S2[i])
        if C == 1:
            if not inp and not pend and not done and e1[i] and not np.isnan(L) and l[i] <= L:
                done = True
                if c[i] > S and not lastW[i] and not (roll[i] and preMon[i]):
                    pend, ps = True, S
            if inp and (lastW[i] or (roll[i] and preMon[i])):
                out.append((eb, i)); inp = False
        else:
            if not inp and not pend and not done and e2[i]:
                if c[i] <= L:
                    below = True
                elif below or o[i] < L:
                    done = True
                    if c[i] > S and not lastW[i]:
                        pend, ps = True, S
            elif c[i] <= L:
                below = True
            if inp and lastW[i]:
                out.append((eb, i)); inp = False
    return out


cands = json.loads((RESULTS / "frozen_candidates.json").read_text())
for C, cand in [(1, cands[0]), (2, cands[1])]:
    spec = dict(cand["spec"]); spec["stop"] = tuple(spec["stop"]); spec["target"] = tuple(spec["target"])
    p = run_spec(fr, spec, 0, n)[0]
    research = set(zip(p["ei"], p["xi"]))
    pine = set(run(C))
    print(f"C{C}: pine-logic {len(pine)} trades, research {len(research)}, identical {len(pine & research)}, "
          f"same entry bar {len({a for a, _ in pine} & {a for a, _ in research})}")

rows = []
for C, cand in [(1, cands[0]), (2, cands[1])]:
    spec = dict(cand["spec"]); spec["stop"] = tuple(spec["stop"]); spec["target"] = tuple(spec["target"])
    p = run_spec(fr, spec, 0, n)[0]
    for a, b, en, ex, net in zip(p["ei"], p["xi"], p["entry"], p["exit"], p["net"]):
        rows.append((f"C{C}", t[a], t[b], round(float(net), 2)))
pd.DataFrame(rows, columns=["system", "entry_bar_ET", "exit_bar_ET", "pnl_pts"]).to_csv(ROOT / "pine" / "expected_trades_levels_es.csv", index=False)
print("wrote pine/expected_trades_levels_es.csv", len(rows))
