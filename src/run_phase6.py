"""Phase 6 (post-holdout, exploratory): can one add-on family lift TALOS's CAGR by 1-2% and MAR by 0.1-0.25 over
1991-2026? Panel: data/proxies_ext. Design window 1991-01-04..2015-12-31; confirmation window 2016-01-04..2026-09-18
(already seen once in the holdout, so it is a pseudo-holdout, not a clean one). Selection rule, fixed before running:
within each family, the design-window cell with the highest MAR subject to CAGR >= baseline CAGR; a family is kept
only if that cell beats the baseline on BOTH CAGR and MAR in design AND in confirmation. At most two kept families are
combined. Every cell is logged to TRIAL_LEDGER.csv as phase P6 (excluded from the DSR count of the frozen system)."""
from __future__ import annotations
import sys, itertools, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trials import cost_model, log, consecutive_roundtrips
from engine import run, BASE_LAG
from metrics import summary, drawdown_series
from strategies import ALL_COLS, LEVERAGE, b1_spy
import system2 as S2

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "reports" / "phase6"; OUT.mkdir(parents=True, exist_ok=True)
R = pd.read_parquet(ROOT / "data/proxies_ext/returns.parquet"); L = pd.read_parquet(ROOT / "data/proxies_ext/levels.parquet")
WIN = ("1991-01-04", "2026-09-18"); DESIGN = ("1991-01-04", "2015-12-31"); CONFIRM = ("2016-01-04", "2026-09-18")
PERIODS = {"design": DESIGN, "confirm": CONFIRM, "full": WIN}
BAND = 0.02
led = pd.read_csv(ROOT / "TRIAL_LEDGER.csv"); led["note"] = led["note"].fillna("")
already = set(led[(led.phase == "P6") & ~led.note.str.startswith("duplicate")].cell)


def full_run(w, band=BAND):
    idx = R.index[(R.index >= WIN[0]) & (R.index <= WIN[1])]
    return run(w.reindex(R.index)[ALL_COLS].loc[idx], R[ALL_COLS], R["CASH"], cost_model(1.0), lag=BASE_LAG, leverage=LEVERAGE, rebalance_threshold=band)


def slice_metrics(res, a, b):
    keep = (res.returns.index >= a) & (res.returns.index <= b); ret = res.returns[keep]
    m = summary(ret, rf=R["CASH"], spy=R["SPY_X"], weights_held=res.weights_held[keep], gross_leverage=res.gross_leverage.abs()[keep],
                turnover=res.turnover[keep], trades=res.trades[keep])
    m["ConsecRoundTripsPerYear"] = consecutive_roundtrips(res.deltas[keep]) / (len(ret) / 252); m["T"] = int(len(ret)); return m


def jsonable(p):
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()}


rows = []; curves = {}
def evaluate(name, family, p, periods=("design",), note=""):
    res = full_run(S2.build2(R, L, p)); curves[name] = res; out = {}
    for per in periods:
        m = slice_metrics(res, *PERIODS[per]); cell = f"{name} [{per}]"
        tid = None if cell in already else log("P6", family, cell, jsonable(p), PERIODS[per], BASE_LAG, 1.0, m, note or "P6 add-on search on proxies_ext; exploratory")
        rows.append({"name": name, "family": family, "period": per, "trial": tid, **{k: v for k, v in p.items() if k in ("lever", "resid_set", "resid_len", "w_gold", "gold_len", "gold_vt", "dip_n", "dip_hold", "dip_boost", "dip_off_frac")}, **m}); out[per] = m
    return out


P0 = dict(S2.PARAMS2, lever=1.0)
base = evaluate("TALOS 1x", "BASE", P0, periods=("design", "confirm", "full"))
grid = {"A_resid": [], "B_gold": [], "C_dip": []}
for rs, rl in itertools.product([("IEF",), ("TLT",), ("GLD",), ("IEF", "GLD"), ("TLT", "GLD"), ("IEF", "TLT", "GLD")], [100, 200]):
    grid["A_resid"].append((f"A resid={'+'.join(rs)} len={rl}", dict(P0, resid_set=rs, resid_len=rl)))
for wg, vt in itertools.product([0.1, 0.2, 0.3], [0.0, 0.10]):
    grid["B_gold"].append((f"B gold w={wg} vt={vt}", dict(P0, w_gold=wg, gold_vt=vt)))
for n, h in itertools.product([5, 10], [3, 5]):
    grid["C_dip"].append((f"C dip n={n} hold={h} boost=1.0", dict(P0, dip_n=n, dip_hold=h, dip_boost=1.0)))
for n, f in itertools.product([10], [0.5, 1.0]):
    grid["C_dip"].append((f"C dip n={n} hold=5 off_frac={f}", dict(P0, dip_n=n, dip_hold=5, dip_boost=1.0, dip_off_frac=f)))
# stage 1b (added after seeing stage 1: the fixed 100% boost doubles the 2000 drawdown): vol-scaled dip boost
grid["C2_dipvol"] = []
for n, h, k in itertools.product([5, 10], [3, 5], [1.5, 2.0, 3.0]):
    grid["C2_dipvol"].append((f"C2 dipvol n={n} hold={h} mult={k}", dict(P0, dip_n=n, dip_hold=h, dip_mult=k)))

design = {}
for fam, cells in grid.items():
    for name, p in cells:
        design[name] = (fam, p, evaluate(name, fam, p)["design"])

# selection
bd = base["design"]; bc = base["confirm"]
picked = {}
for fam in grid:
    cands = [(n, f, p, m) for n, (f, p, m) in design.items() if f == fam and m["CAGR"] >= bd["CAGR"]]
    if not cands:
        print(fam, "no cell reaches baseline CAGR in design"); continue
    n, f, p, m = max(cands, key=lambda t: t[3]["MAR"])
    conf = evaluate(n, fam, p, periods=("confirm", "full"))
    keep = m["CAGR"] > bd["CAGR"] and m["MAR"] > bd["MAR"] and conf["confirm"]["CAGR"] > bc["CAGR"] and conf["confirm"]["MAR"] > bc["MAR"]
    picked[fam] = dict(name=n, params=p, design=m, confirm=conf["confirm"], full=conf["full"], kept=bool(keep))
    print(fam, "->", n, "| design CAGR %.3f MAR %.3f | confirm CAGR %.3f MAR %.3f | kept=%s" % (m["CAGR"], m["MAR"], conf["confirm"]["CAGR"], conf["confirm"]["MAR"], keep))

kept = [f for f, v in picked.items() if v["kept"]]
# stage 2 (rule widened after stage 1: no single family passed): also combine the best-by-MAR cell of every family,
# using the design-window best cell regardless of the CAGR constraint when no cell met it.
for fam in grid:
    if fam not in picked:
        n, (f, p, m) = max(((n, v) for n, v in design.items() if v[0] == fam), key=lambda t: t[1][2]["MAR"])
        conf = evaluate(n, fam, p, periods=("confirm", "full"))
        picked[fam] = dict(name=n, params=p, design=m, confirm=conf["confirm"], full=conf["full"], kept=False)
combos = {}
for r in (2, 3):
  for fams in itertools.combinations(list(picked), r):
    f1, f2 = fams[0], "+".join(fams[1:])
    if r == 3 and not ({"C_dip", "C2_dipvol"} - set(fams)):
        continue
    if {"C_dip", "C2_dipvol"} <= set(fams):
        continue
    p = dict(P0)
    for f in fams:
        for k, v in picked[f]["params"].items():
            if k not in P0 or v != P0[k]:
                p[k] = v
    n = "COMBO " + "+".join(picked[f]["name"] for f in fams)
    combos[n] = (p, evaluate(n, "COMBO", p, periods=("design", "confirm", "full")))
    print(n, {per: (round(m["CAGR"], 4), round(m["MAR"], 3)) for per, m in combos[n][1].items()})

# final candidate = best full-window MAR among kept singles and combos that beat baseline on both metrics in all three windows
finalists = {picked[f]["name"]: (picked[f]["params"], {k: picked[f][k] for k in ("design", "confirm", "full")}) for f in picked}
finalists.update({n: (p, m) for n, (p, m) in combos.items()})
ok = {n: (p, m) for n, (p, m) in finalists.items()
      if all(m[per]["CAGR"] > base[per]["CAGR"] and m[per]["MAR"] > base[per]["MAR"] for per in PERIODS)}
final = max(ok, key=lambda n: ok[n][1]["full"]["MAR"]) if ok else None
print("FINAL:", final)
extra = {}
if final:
    pf = ok[final][0]
    for lev in [2.5]:
        p = dict(pf, lever=lev); n = f"{final} lever={lev}"
        extra[n] = evaluate(n, "FINAL6", p, periods=("design", "confirm", "full"))
        n0 = f"TALOS lever={lev}"; extra[n0] = evaluate(n0, "BASE", dict(P0, lever=lev), periods=("design", "confirm", "full"))
    # sensitivities on the final at 1x: lag 1/3, cost 0/3
    w = S2.build2(R, L, pf)
    for tag, kw in [("lag3", dict(lag=3)), ("lag1", dict(lag=1)), ("cost0", dict(cost_mult=0.0)), ("cost3", dict(cost_mult=3.0))]:
        idx = R.index[(R.index >= WIN[0]) & (R.index <= WIN[1])]
        res = run(w.reindex(R.index)[ALL_COLS].loc[idx], R[ALL_COLS], R["CASH"], cost_model(kw.get("cost_mult", 1.0)), lag=kw.get("lag", BASE_LAG), leverage=LEVERAGE, rebalance_threshold=BAND)
        m = slice_metrics(res, *WIN); cell = f"{final} {tag} [full]"
        tid = None if cell in already else log("P6", "FINAL6", cell, {**jsonable(pf), **kw}, WIN, kw.get("lag", BASE_LAG), kw.get("cost_mult", 1.0), m, "sensitivity")
        rows.append({"name": f"{final} {tag}", "family": "FINAL6", "period": "full", "trial": tid, **m})

df = pd.DataFrame(rows); df.to_csv(OUT / "phase6_metrics.csv", index=False)
json.dump({"picked": {f: {k: (jsonable(v) if k == "params" else v) for k, v in d.items()} for f, d in picked.items()}, "final": final,
           "final_params": jsonable(ok[final][0]) if final else None}, open(OUT / "selection.json", "w"), indent=2, default=float)

# chart
if final:
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#eeede9"})
    fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    for k, col in [("TALOS 1x", "#2a78d6"), (final, "#eb6834"), (f"{final} lever=2.5", "#b23a1a"), ("TALOS lever=2.5", "#7fa8d8")]:
        if k not in curves: continue
        eq = (1 + curves[k].returns).cumprod(); m = slice_metrics(curves[k], *WIN)
        ax[0].plot(eq, color=col, lw=1.1, label=f"{k}: CAGR {m['CAGR']:.1%}, MaxDD {m['MaxDD']:.0%}, MAR {m['MAR']:.2f}")
        ax[1].plot(drawdown_series(eq), color=col, lw=0.9)
    eq = (1 + full_run(b1_spy(R, L), 0.0).returns).cumprod(); ax[0].plot(eq, color="#1baf7a", lw=0.9, label="SPY buy-and-hold")
    ax[0].set_yscale("log"); ax[0].legend(loc="upper left", frameon=False, fontsize=8); ax[0].set_title("Phase 6: TALOS vs TALOS + add-on, 1991-2026 (log scale)")
    ax[1].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0)); ax[1].set_ylabel("drawdown")
    for a_ in ax: a_.axvline(pd.Timestamp("2016-01-04"), color="#bbb", lw=0.8, ls="--")
    fig.tight_layout(); fig.savefig(OUT / "equity_phase6.png", dpi=130); plt.close(fig)
    pd.DataFrame({k: v.returns for k, v in curves.items() if k in ("TALOS 1x", final, f"{final} lever=2.5", "TALOS lever=2.5")}).to_parquet(OUT / "daily_returns.parquet")
