"""Phase 7 (post-holdout, exploratory): (1) every phase-6 add-on at the 2.5x multiplier; (2) free-rein simplification /
improvement ideas applied to the phase-6 candidate (TALOS + vol-scaled dip + gold sleeve): trend-gate hysteresis,
sizing on the higher of two vol windows, momentum fallback instead of trend-gated IEF, dropping the rotation sleeve,
levered gold sleeve (UGL). Same protocol as P6: design 1991-2015, confirmation 2016-2026, kept only if it beats its
base on CAGR and MAR in both windows. Logged as phase P7."""
from __future__ import annotations
import sys, itertools
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trials import cost_model, log, consecutive_roundtrips
from engine import run, BASE_LAG
from metrics import summary, drawdown_series
from strategies import ALL_COLS, LEVERAGE, b1_spy
import system2 as S2

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "reports" / "phase7"; OUT.mkdir(parents=True, exist_ok=True)
R = pd.read_parquet(ROOT / "data/proxies_ext/returns.parquet"); L = pd.read_parquet(ROOT / "data/proxies_ext/levels.parquet")
WIN = ("1991-01-04", "2026-09-18"); PERIODS = {"design": ("1991-01-04", "2015-12-31"), "confirm": ("2016-01-04", "2026-09-18"), "full": WIN}
led = pd.read_csv(ROOT / "TRIAL_LEDGER.csv"); led["note"] = led["note"].fillna("")
already = set(led[(led.phase == "P7") & ~led.note.str.startswith("duplicate")].cell)
KEYS = ["CAGR", "Vol", "Sharpe", "Sortino", "MaxDD", "MAR", "MaxDD_trough", "AvgLeverage", "TradesPerYear", "ConsecRT"]


def full_run(w, band=0.02):
    idx = R.index[(R.index >= WIN[0]) & (R.index <= WIN[1])]
    return run(w.reindex(R.index)[ALL_COLS].loc[idx], R[ALL_COLS], R["CASH"], cost_model(1.0), lag=BASE_LAG, leverage=LEVERAGE, rebalance_threshold=band)


def sm(res, a, b):
    keep = (res.returns.index >= a) & (res.returns.index <= b); ret = res.returns[keep]
    m = summary(ret, rf=R["CASH"], spy=R["SPY_X"], weights_held=res.weights_held[keep], gross_leverage=res.gross_leverage.abs()[keep], turnover=res.turnover[keep], trades=res.trades[keep])
    m["ConsecRT"] = consecutive_roundtrips(res.deltas[keep]) / (len(ret) / 252); m["ConsecRoundTripsPerYear"] = m["ConsecRT"]; return m


curves = {}; rows = []
def ev(name, family, p, note="P7 exploratory"):
    res = full_run(S2.build2(R, L, p)); curves[name] = res; out = {}
    for per, (a, b) in PERIODS.items():
        m = sm(res, a, b); cell = f"{name} [{per}]"
        tid = None if cell in already else log("P7", family, cell, {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()}, (a, b), BASE_LAG, 1.0, m, note)
        rows.append({"name": name, "family": family, "period": per, "trial": tid, **{k: m[k] for k in KEYS}}); out[per] = m
    return out


def md(d, fmt="{:.3f}"):
    cols = list(d.columns); o = ["| | " + " | ".join(cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for i, r in d.iterrows():
        o.append("| " + str(i) + " | " + " | ".join((fmt.format(v) if isinstance(v, (float, np.floating)) else str(v)) for v in r) + " |")
    return "\n".join(o)


def table(names, per):
    return pd.DataFrame({n: rows_by[(n, per)] for n in names if (n, per) in rows_by}).T[KEYS]


P0 = dict(S2.PARAMS2, lever=1.0)
DIP = dict(dip_n=10, dip_hold=5, dip_mult=2.0); GOLD = dict(w_gold=0.3, gold_vt=0.10)
T6 = dict(P0, **DIP, **GOLD)

# ---- (1) add-ons at 2.5x --------------------------------------------------------------------------------------
part1 = {"TALOS 2.5x": dict(P0, lever=2.5),
         "TALOS+dip 2.5x": dict(P0, **DIP, lever=2.5),
         "TALOS+gold 2.5x": dict(P0, **GOLD, lever=2.5),
         "TALOS+dip+gold 2.5x": dict(T6, lever=2.5),
         "TALOS+residTLT 2.5x": dict(P0, resid_set=("TLT",), lever=2.5),
         "TALOS+dip+residTLT 2.5x": dict(P0, **DIP, resid_set=("TLT",), lever=2.5),
         "TALOS+levgold(2x) 2.5x": dict(P0, **GOLD, gold_lev=2.0, lever=2.5),
         "TALOS+dip+levgold(2x) 2.5x": dict(T6, gold_lev=2.0, lever=2.5)}
for n, p in part1.items():
    ev(n, "P7-2.5x", p)

# ---- (2) free-rein ideas on the P6 candidate at 1x ----------------------------------------------------------------
base = ev("T6 = TALOS+dip+gold 1x", "P7-base", T6); ev("TALOS 1x", "P7-base", P0)
ideas = {"gate band 1%": dict(gate_band=0.01), "gate band 2%": dict(gate_band=0.02),
         "vol = max(20d, 60d)": dict(vol_win2=60), "vol = max(20d, 120d)": dict(vol_win2=120),
         "momentum fallback (IEF/TLT/GLD)": dict(fallback="mom"),
         "no rotation sleeve": dict(w_core=1.0), "rotation 50%": dict(w_core=0.5),
         "levered gold 1.5x": dict(gold_lev=1.5), "levered gold 2x": dict(gold_lev=2.0),
         "gold 20%": dict(w_gold=0.2), "gold 40%": dict(w_gold=0.4), "gold vt 15%": dict(gold_vt=0.15),
         "core vt 12%": dict(vol_target=0.12), "SMA 150": dict(sma_len=150), "SMA 250": dict(sma_len=250)}
res_ideas = {n: ev(f"T6 + {n}", "P7-idea", dict(T6, **d)) for n, d in ideas.items()}
def beats(m, b):
    return all(m[per]["CAGR"] > b[per]["CAGR"] and m[per]["MAR"] > b[per]["MAR"] for per in ("design", "confirm"))
passed = [n for n, m in res_ideas.items() if beats(m, base)]
print("ideas that beat T6 on CAGR and MAR in both windows:", passed)
# pairwise combos of passers (at most 6 pairs to stay within budget), then the best pair vs base at 1.25x and 2.5x
combos = {}
for a, b in list(itertools.combinations(passed, 2))[:6]:
    if any(k in ideas[b] for k in ideas[a]):   # same knob twice: skip
        continue
    n = f"T6 + {a} + {b}"; combos[n] = ev(n, "P7-combo", dict(T6, **ideas[a], **ideas[b]))
cand = {**{f"T6 + {n}": res_ideas[n] for n in passed}, **combos}
final = max(cand, key=lambda n: cand[n]["full"]["MAR"]) if cand else None
print("best by full-window MAR:", final)
rows_by = {(r["name"], r["period"]): r for r in rows}
if final:
    pf = dict(T6, **{k: v for n in ideas if f"T6 + {n}" == final or n in final.replace("T6 + ", "").split(" + ") for k, v in ideas[n].items()})
    for lev in (1.25, 1.5, 2.5):
        ev(f"{final} {lev}x", "P7-final", dict(pf, lever=lev)); ev(f"T6 {lev}x", "P7-base", dict(T6, lever=lev))
    rows_by = {(r["name"], r["period"]): r for r in rows}
    import json; json.dump({"final": final, "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in pf.items()}}, open(OUT / "selection.json", "w"), indent=2)

df = pd.DataFrame(rows); df.to_csv(OUT / "phase7_metrics.csv", index=False)
lines = ["# Phase 7 (exploratory): add-ons at 2.5x and free-rein ideas\n", "Panel proxies_ext; design 1991-2015, confirm 2016-2026, full 1991-2026; band 0.02, lag 2, costs x1. Ledger phase P7.\n"]
for per in PERIODS:
    lines.append(f"\n## Part 1: add-ons at 2.5x — {per}\n\n" + md(table(list(part1), per)) + "\n")
names2 = ["TALOS 1x", "T6 = TALOS+dip+gold 1x"] + [f"T6 + {n}" for n in ideas] + list(combos)
for per in PERIODS:
    lines.append(f"\n## Part 2: ideas on T6 at 1x — {per}\n\n" + md(table(names2, per)) + "\n")
lines.append(f"\nIdeas beating T6 on CAGR and MAR in both windows: {passed}\n\nBest by full-window MAR: {final}\n")
if final:
    n3 = [f"T6 {lev}x" for lev in (1.25, 1.5, 2.5)] + [f"{final} {lev}x" for lev in (1.25, 1.5, 2.5)]
    for per in PERIODS:
        lines.append(f"\n## Part 3: best idea across the multiplier — {per}\n\n" + md(table(n3, per)) + "\n")
(OUT / "summary.md").write_text("".join(lines)); print("".join(lines[-4:]))

# ---- chart: requested curves -----------------------------------------------------------------------------------
for n, p in {"TALOS+dip+gold 1x": T6, "TALOS+dip+gold 1.25x": dict(T6, lever=1.25), "TALOS+dip+gold 1.5x": dict(T6, lever=1.5)}.items():
    if n not in curves: curves[n] = full_run(S2.build2(R, L, p))
curves["SPY B&H"] = full_run(b1_spy(R, L), 0.0)
plt.rcParams.update({"font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#eeede9"})
fig, ax = plt.subplots(2, 2, figsize=(15, 8), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
groups = {0: [("TALOS 1x", "#2a78d6"), ("TALOS+dip+gold 1x", "#e0a020"), ("TALOS+dip+gold 1.25x", "#eb6834"), ("TALOS+dip+gold 1.5x", "#b23a1a"), ("SPY B&H", "#1baf7a")],
          1: [("TALOS 2.5x", "#2a78d6"), ("TALOS+dip 2.5x", "#9b59b6"), ("TALOS+gold 2.5x", "#e0a020"), ("TALOS+dip+gold 2.5x", "#eb6834"), ("TALOS+dip+levgold(2x) 2.5x", "#b23a1a"), ("SPY B&H", "#1baf7a")]}
for j, items in groups.items():
    for k, col in items:
        eq = (1 + curves[k].returns).cumprod(); m = sm(curves[k], *WIN)
        ax[0, j].plot(eq, color=col, lw=1.0, label=f"{k}: CAGR {m['CAGR']:.1%}, MaxDD {m['MaxDD']:.0%}, MAR {m['MAR']:.2f}")
        ax[1, j].plot(drawdown_series(eq), color=col, lw=0.8)
    ax[0, j].set_yscale("log"); ax[0, j].legend(loc="upper left", frameon=False, fontsize=7.5)
    ax[1, j].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    for a_ in ax[:, j]: a_.axvline(pd.Timestamp("2016-01-04"), color="#bbb", lw=0.8, ls="--")
ax[0, 0].set_title("1x to 1.5x: TALOS vs TALOS + dip + gold (1991-2026, log)"); ax[0, 1].set_title("2.5x: TALOS and each add-on (levgold = gold sleeve up to 2x via UGL)")
ax[1, 0].set_ylabel("drawdown"); fig.tight_layout(); fig.savefig(OUT / "equity_phase7.png", dpi=130); plt.close(fig)
pd.DataFrame({k: v.returns for k, v in curves.items()}).to_parquet(OUT / "daily_returns.parquet")
