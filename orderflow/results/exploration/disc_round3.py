"""Discovery round 3 (post-hoc, DISCOVERY split only; logged)."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
import pandas as pd
from of import explore as ex, load, signals
from of.config import DEV
import run_explore as rx

led = []
def rep(tag, x, col):
    r = ex.summarize(x, col); led.append(dict(family="R3", split="discovery", id=tag, **r))
    print(f"{tag:48s} n={r['n']:5d} days={r['days']:4d} trade-mean={r['mean']*100:+.3f}% day-mean={r['dmean']*100:+.3f}% win={r['win']:.3f} t={r['t']:+.2f}")

E = rx.all_events(DEV); E = E[E.split == "discovery"]
for name in ["A9L_fade_accept_below_PDL", "A9S_fade_accept_above_PDH", "A6L_newlow_pos_delta", "A6S_newhigh_neg_delta",
             "A1L_fail_below_PDL", "A1S_fail_above_PDH"]:
    g = E[E.event == name]
    rep(f"A:{name}", g, "net")
    if g.net_tp.notna().any():
        rep(f"A:{name}:tp(back to level)", g, "net_tp")

print("\n-- flush signal, hold-period variants (DISCOVERY)")
for hold in [4, 12, 24, 48]:
    T = pd.concat([signals.trades(s, load.hourly(s), load.funding(s), mode="nonoverlap", oi_col="oi", hold_h=hold) for s in DEV])
    T = T[T.t < pd.Timestamp("2024-01-01", tz="UTC")]
    rep(f"flush_hold{hold}h", T, "net")
ex.log(led)
