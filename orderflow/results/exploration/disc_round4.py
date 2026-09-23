"""Discovery round 4 (post-hoc, DISCOVERY only; logged): idiosyncratic vs market-wide (BTC as the market)."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
import numpy as np, pandas as pd
from of import explore as ex
from of.config import DEV
import run_explore as rx

led = []
def rep(tag, x, col="net"):
    r = ex.summarize(x, col); led.append(dict(family="R4", split="discovery", id=tag, **r))
    print(f"{tag:58s} n={r['n']:5d} days={r['days']:4d} trade-mean={r['mean']*100:+.3f}% day-mean={r['dmean']*100:+.3f}% win={r['win']:.3f} t={r['t']:+.2f}")

B = ex.load_structure("BTCUSDT")
btc = pd.DataFrame({"btc_below_pdl": (B.c < B.PDL).astype(float), "btc_above_pdh": (B.c > B.PDH).astype(float),
                    "btc_ret24": B.ret24, "btc_pos_d": (B.c - B.dL) / (B.dH - B.dL)}, index=B.index)

E = rx.all_events(DEV); E = E[(E.split == "discovery")].merge(btc, left_on="t", right_index=True, how="left")
S = [s for s in DEV if s != "BTCUSDT"]
g = E[(E.event == "A9L_fade_accept_below_PDL") & E.sym.isin(S)]
rep("A9L alts | BTC also below its PDL", g[g.btc_below_pdl == 1])
rep("A9L alts | BTC NOT below its PDL", g[g.btc_below_pdl == 0])
g = E[(E.event == "A9S_fade_accept_above_PDH") & E.sym.isin(S)]
rep("A9S alts | BTC also above its PDH", g[g.btc_above_pdh == 1])
rep("A9S alts | BTC NOT above its PDH", g[g.btc_above_pdh == 0])

# causal breadth: how many of the 9 dev coins have had the same event earlier today (incl. this bar)
for name in ["A9L_fade_accept_below_PDL", "A9S_fade_accept_above_PDH", "A6L_newlow_pos_delta", "A6S_newhigh_neg_delta"]:
    g = E[E.event == name].sort_values("t").copy()
    g["day"] = g.t.dt.floor("D")
    g["breadth"] = [((g.day == d) & (g.t <= t)).sum() for d, t in zip(g.day, g.t)]
    rep(f"{name} | breadth so far <= 2", g[g.breadth <= 2])
    rep(f"{name} | breadth so far >= 3", g[g.breadth >= 3])

T = pd.read_csv(rx.SIG); T["t"] = pd.to_datetime(T.t, utc=True)
T = T[T.sym.isin(DEV) & (T.t < pd.Timestamp("2024-01-01", tz="UTC"))].merge(btc, left_on="t", right_index=True, how="left")
Ta = T[T.sym != "BTCUSDT"].copy()
Ta["excess"] = Ta.merge(pd.DataFrame(index=[0]), how="cross").index * 0 if False else np.nan
X = {s: ex.load_structure(s) for s in S}
Ta["ret24"] = [X[s].ret24.get(t, np.nan) for s, t in zip(Ta.sym, Ta.t)]
Ta["excess"] = Ta.ret24 - Ta.btc_ret24
q1, q2 = Ta.excess.quantile([1/3, 2/3])
print(f"\nflush alts: excess 24h drop vs BTC terciles (cutoffs {q1:.4f} / {q2:.4f})")
rep("flush alts | excess drop bottom third (most idiosyncratic)", Ta[Ta.excess <= q1])
rep("flush alts | excess drop middle third", Ta[(Ta.excess > q1) & (Ta.excess <= q2)])
rep("flush alts | excess drop top third (moved with BTC)", Ta[Ta.excess > q2])
rep("flush alts | BTC 24h ret > -2%", Ta[Ta.btc_ret24 > -0.02])
rep("flush alts | BTC 24h ret <= -2%", Ta[Ta.btc_ret24 <= -0.02])
ex.log(led)
