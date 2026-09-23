"""A9L diagnostics on DISCOVERY + VALIDATION only (vault untouched). No parameter is chosen here."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np, pandas as pd
from of import explore as ex
from of.config import DEV, HOLDOUT, RESULTS
import run_explore as rx

E = rx.all_events(DEV + HOLDOUT)
A = E[(E.event == "A9L_fade_accept_below_PDL") & (E.split != "vault")].copy()
T = pd.read_csv(RESULTS / "flush_signals.csv"); T["t"] = pd.to_datetime(T.t, utc=True)
# overlap: a flush signal on the same coin within the previous 24h or the next 24h
ov = []
for s, g in A.groupby("sym"):
    ft = T[T.sym == s].t.values
    for t in g.t.values:
        ov.append(bool(len(ft) and (np.abs((ft - t).astype("timedelta64[h]").astype(int)) <= 24).any()))
A["near_flush"] = pd.Series(ov, index=A.sort_values("sym").index).reindex(A.index)

def line(tag, x):
    r = ex.summarize(x)
    print(f"{tag:44s} n={r['n']:6d} days={r['days']:5d} trade={r['mean']*100:+.3f}% day={r['dmean']*100:+.3f}% win={r['win']:.3f} t={r['t']:+.2f}")

for sp in ["discovery", "validation"]:
    x = A[A.split == sp]
    print(f"\n== {sp}")
    line("all", x)
    line("no flush signal within 24h", x[~x.near_flush])
    line("flush signal within 24h", x[x.near_flush])
    for y in sorted(x.t.dt.year.unique()):
        line(f"year {y}", x[x.t.dt.year == y])
x = A[A.split == "validation"]
per = x.groupby("sym").net.agg(["count", "mean"]).sort_values("mean")
print("\nvalidation per coin: coins with mean > 0:", (per["mean"] > 0).sum(), "of", len(per))
print((per.assign(mean=lambda d: (d["mean"] * 100).round(3))).T.to_string())
# daily P&L (fixed notional per trade, booked on the entry day) -> Sharpe, maxDD
for sp in ["discovery", "validation"]:
    x = A[A.split == sp]
    d = x.groupby(x.t.dt.floor("D")).net.sum()
    d = d.reindex(pd.date_range(d.index.min(), d.index.max(), freq="D"), fill_value=0)
    eq = d.cumsum()
    print(f"{sp}: daily-sum Sharpe {d.mean()/d.std()*np.sqrt(365):.2f}, total {d.sum()*100:.0f}% (sum of trade %), "
          f"max drawdown of cumulative sum {(eq - eq.cummax()).min()*100:.0f}%, worst day {d.min()*100:.0f}%")
