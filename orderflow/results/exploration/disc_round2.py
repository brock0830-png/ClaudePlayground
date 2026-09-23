"""Discovery round 2 (post-hoc, DISCOVERY split only; every row logged to the ledger)."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
import numpy as np, pandas as pd
from of import explore as ex
from of.config import DEV
import run_explore as rx
pd.set_option("display.width", 250)

led = []
def rep(tag, x, col):
    r = ex.summarize(x, col); led.append(dict(family="R2", split="discovery", id=tag, **r))
    print(f"{tag:60s} n={r['n']:5d} days={r['days']:4d} mean={r['mean']*100:+.3f}% win={r['win']:.3f} t={r['t']:+.2f}")

rows = []
for s in DEV:
    X = ex.load_structure(s); F = ex.screen_features(X)
    D = F.copy(); D["L24"] = X.L24; D["S24"] = X.S24; D["gross24"] = X.gross24; D["sym"] = s; D["t"] = D.index; D["hour"] = D.index.hour
    rows.append(D.reset_index(drop=True))
P = pd.concat(rows, ignore_index=True).dropna(subset=["L24"])
P["split"] = ex.split_of(P.sym, P.t)
Dd = P[P.split == "discovery"]

for hr in [0, 12, 4, 8, 16, 20]:
    x = Dd[Dd.hour == hr]
    q1, q2 = x.pos_d.quantile([1/3, 2/3])
    rep(f"R2:posd_bottom_long@{hr:02d}", x[x.pos_d <= q1], "L24")
    rep(f"R2:posd_top_short@{hr:02d}", x[x.pos_d > q2], "S24")
for hr in [0, 12]:
    x = Dd[Dd.hour == hr]
    q1, q2 = x.pos_pd.quantile([1/3, 2/3])
    rep(f"R2:pospd_bottom_long@{hr:02d}", x[x.pos_pd <= q1], "L24")
    rep(f"R2:pospd_top_short@{hr:02d}", x[x.pos_pd > q2], "S24")

print("\n-- double sort at 12:00: mean GROSS 24h return, rows = ret24 tercile, cols = pos_d tercile")
x = Dd[Dd.hour == 12].copy()
x["r_t"] = pd.qcut(x.ret24, 3, labels=["r_lo", "r_mid", "r_hi"]); x["p_t"] = pd.qcut(x.pos_d, 3, labels=["p_lo", "p_mid", "p_hi"])
print((x.pivot_table(index="r_t", columns="p_t", values="gross24", aggfunc="mean", observed=False) * 100).round(3))
print(x.pivot_table(index="r_t", columns="p_t", values="gross24", aggfunc="count", observed=False))

print("\n-- reversed event trades")
E = rx.all_events(DEV); E = E[E.split == "discovery"]
# reverse side: net_rev = -net - 2*cost  (funding sign flips too, already inside net)
for name in ["A3L_accept_above_PDH", "A3S_accept_below_PDL", "A4L_80pct_from_below", "A4S_80pct_from_above"]:
    g = E[E.event == name].copy(); g["rev"] = -g.net - 2 * 0.0014
    rep(f"R2:reverse_{name}", g, "rev")
ex.log(led)
