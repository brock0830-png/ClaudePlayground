"""Phase 7c: robustness of the phase-7 candidate T7 = TALOS + vol-scaled dip + gold sleeve + 1% gate hysteresis + SMA 250
at 1.25x: parameter neighbourhood (gate band x SMA length), lag and cost sensitivities, and the final chart."""
from __future__ import annotations
import sys, itertools
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trials import cost_model, log, consecutive_roundtrips
from engine import run, BASE_LAG
from metrics import summary, drawdown_series
from strategies import ALL_COLS, LEVERAGE
import system2 as S2

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "reports" / "phase7"
R = pd.read_parquet(ROOT / "data/proxies_ext/returns.parquet"); L = pd.read_parquet(ROOT / "data/proxies_ext/levels.parquet")
WIN = ("1991-01-04", "2026-09-18"); PERIODS = {"design": ("1991-01-04", "2015-12-31"), "confirm": ("2016-01-04", "2026-09-18"), "full": WIN}
led = pd.read_csv(ROOT / "TRIAL_LEDGER.csv"); led["note"] = led["note"].fillna("")
already = set(led[(led.phase == "P7") & ~led.note.str.startswith("duplicate")].cell)
P0 = dict(S2.PARAMS2, lever=1.0)
T6 = dict(P0, dip_n=10, dip_hold=5, dip_mult=2.0, w_gold=0.3, gold_vt=0.10)
T7 = dict(T6, gate_band=0.01, sma_len=250, lever=1.25)


def full_run(w, lag=BASE_LAG, cost_mult=1.0, band=0.02):
    idx = R.index[(R.index >= WIN[0]) & (R.index <= WIN[1])]
    return run(w.reindex(R.index)[ALL_COLS].loc[idx], R[ALL_COLS], R["CASH"], cost_model(cost_mult), lag=lag, leverage=LEVERAGE, rebalance_threshold=band)


def sm(res, a, b):
    keep = (res.returns.index >= a) & (res.returns.index <= b); ret = res.returns[keep]
    m = summary(ret, rf=R["CASH"], spy=R["SPY_X"], weights_held=res.weights_held[keep], gross_leverage=res.gross_leverage.abs()[keep], turnover=res.turnover[keep], trades=res.trades[keep])
    m["ConsecRoundTripsPerYear"] = consecutive_roundtrips(res.deltas[keep]) / (len(ret) / 252); return m


rows = []
def ev(name, p, lag=BASE_LAG, cost_mult=1.0, fam="P7-robust"):
    res = full_run(S2.build2(R, L, p), lag, cost_mult)
    for per, (a, b) in PERIODS.items():
        m = sm(res, a, b); cell = f"{name} [{per}]"
        if cell not in already:
            log("P7", fam, cell, {**{k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()}, "lag": lag, "cost_mult": cost_mult}, (a, b), lag, cost_mult, m, "P7 robustness of T7")
        rows.append({"name": name, "period": per, "gate_band": p["gate_band"], "sma_len": p["sma_len"], "lag": lag, "cost_mult": cost_mult, **{k: m[k] for k in ("CAGR", "Vol", "Sharpe", "MaxDD", "MAR", "TradesPerYear", "ConsecRoundTripsPerYear")}, "MaxDD_trough": m["MaxDD_trough"]})
    return res


for gb, sl in itertools.product([0.005, 0.01, 0.015, 0.02], [200, 225, 250, 275, 300]):
    ev(f"T7nbr gate={gb} sma={sl} 1.25x", dict(T7, gate_band=gb, sma_len=sl))
for tag, kw in [("lag3", dict(lag=3)), ("lag1", dict(lag=1)), ("cost0", dict(cost_mult=0.0)), ("cost3", dict(cost_mult=3.0))]:
    ev(f"T7 {tag} 1.25x", T7, fam="P7-sens", **kw)
df = pd.DataFrame(rows); df.to_csv(OUT / "robustness.csv", index=False)
for per in ("full", "design", "confirm"):
    d = df[df.period == per]
    print(f"\n== neighbourhood MAR ({per}); CAGR in brackets")
    piv = d[d.name.str.startswith("T7nbr")].pivot(index="gate_band", columns="sma_len", values=["MAR", "CAGR"]).round(3); print(piv.to_string())
print("\n== sensitivities (full)"); print(df[(df.period == "full") & df.name.str.startswith("T7 ")][["name", "CAGR", "MaxDD", "MAR", "Sharpe"]].round(3).to_string(index=False))

# final chart from saved curves
D = pd.read_parquet(OUT / "daily_returns.parquet")
def mm(s):
    eq = (1 + s).cumprod(); dd = eq / eq.cummax() - 1; yrs = len(s) / 252; c = eq.iloc[-1] ** (1 / yrs) - 1
    return c, dd.min(), c / abs(dd.min())
plt.rcParams.update({"font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#eeede9"})
fig, ax = plt.subplots(2, 2, figsize=(15, 8), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
groups = {0: [("TALOS 1x", "TALOS 1x", "#2a78d6"), ("TALOS+dip+gold 1x", "T6 1x", "#e0a020"), ("TALOS+dip+gold 1.25x", "T6 1.25x", "#eb6834"), ("TALOS+dip+gold 1.5x", "T6 1.5x", "#b23a1a"),
             ("T6+gate1%+SMA250 lever=1.25", "T7 = T6 + gate 1% + SMA250, 1.25x", "#111111"), ("SPY B&H", "SPY B&H", "#1baf7a")],
          1: [("TALOS 2.5x", "TALOS 2.5x", "#2a78d6"), ("TALOS+dip 2.5x", "TALOS+dip 2.5x", "#9b59b6"), ("TALOS+gold 2.5x", "TALOS+gold 2.5x", "#e0a020"), ("TALOS+dip+gold 2.5x", "T6 2.5x", "#eb6834"),
             ("TALOS+dip+levgold(2x) 2.5x", "T6 with gold sleeve up to 2x (UGL), 2.5x", "#b23a1a"), ("T6+gate1%+SMA250 lever=2.5", "T7 2.5x", "#111111"), ("SPY B&H", "SPY B&H", "#1baf7a")]}
for j, items in groups.items():
    for k, lab, col in items:
        s = D[k].dropna(); c, d_, r = mm(s); eq = (1 + s).cumprod()
        ax[0, j].plot(eq, color=col, lw=1.0, label=f"{lab}: CAGR {c:.1%}, MaxDD {d_:.0%}, MAR {r:.2f}"); ax[1, j].plot(drawdown_series(eq), color=col, lw=0.8)
    ax[0, j].set_yscale("log"); ax[0, j].legend(loc="upper left", frameon=False, fontsize=7.5); ax[1, j].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    for a_ in ax[:, j]: a_.axvline(pd.Timestamp("2016-01-04"), color="#bbb", lw=0.8, ls="--")
ax[0, 0].set_title("1x-1.5x: TALOS, TALOS + dip + gold (T6), and T7 (1991-2026, log; dashed = confirmation window)"); ax[0, 1].set_title("2.5x: TALOS and each add-on")
ax[1, 0].set_ylabel("drawdown"); fig.tight_layout(); fig.savefig(OUT / "equity_phase7.png", dpi=130); plt.close(fig)
