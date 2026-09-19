"""Phase 6 report: chart + summary.md for the candidate add-on (vol-scaled dip + vol-targeted gold sleeve) vs TALOS."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trials import cost_model, consecutive_roundtrips
from engine import run, BASE_LAG
from metrics import summary, drawdown_series
from strategies import ALL_COLS, LEVERAGE, b1_spy
import system2 as S2

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "reports" / "phase6"
R = pd.read_parquet(ROOT / "data/proxies_ext/returns.parquet"); L = pd.read_parquet(ROOT / "data/proxies_ext/levels.parquet")
WIN = ("1991-01-04", "2026-09-18"); PERIODS = {"design 1991-2015": ("1991-01-04", "2015-12-31"), "confirm 2016-2026": ("2016-01-04", "2026-09-18"), "full 1991-2026": WIN}
P0 = dict(S2.PARAMS2, lever=1.0)
ADD = dict(dip_n=10, dip_hold=5, dip_mult=2.0, w_gold=0.3, gold_vt=0.10)
V = {"TALOS 1x": dict(P0), "TALOS 1.25x": dict(P0, lever=1.25),
     "TALOS+dip 1x": dict(P0, dip_n=10, dip_hold=5, dip_mult=2.0),
     "TALOS+dip+gold 1x": dict(P0, **ADD), "TALOS+dip+gold 1.25x": dict(P0, **ADD, lever=1.25), "TALOS+dip+gold 1.5x": dict(P0, **ADD, lever=1.5),
     "TALOS 2.5x": dict(P0, lever=2.5), "TALOS+dip+gold 2.5x": dict(P0, **ADD, lever=2.5)}


def full_run(w, band=0.02):
    idx = R.index[(R.index >= WIN[0]) & (R.index <= WIN[1])]
    return run(w.reindex(R.index)[ALL_COLS].loc[idx], R[ALL_COLS], R["CASH"], cost_model(1.0), lag=BASE_LAG, leverage=LEVERAGE, rebalance_threshold=band)


def sm(res, a, b):
    keep = (res.returns.index >= a) & (res.returns.index <= b); ret = res.returns[keep]
    m = summary(ret, rf=R["CASH"], spy=R["SPY_X"], weights_held=res.weights_held[keep], gross_leverage=res.gross_leverage.abs()[keep], turnover=res.turnover[keep], trades=res.trades[keep])
    m["ConsecRT"] = consecutive_roundtrips(res.deltas[keep]) / (len(ret) / 252); return m


curves = {k: full_run(S2.build2(R, L, p)) for k, p in V.items()}; curves["SPY B&H"] = full_run(b1_spy(R, L), 0.0)
keys = ["CAGR", "Vol", "Sharpe", "Sortino", "MaxDD", "MAR", "MaxDD_trough", "AvgLeverage", "TradesPerYear", "ConsecRT", "CorrSPY"]


def md(d, fmt="{:.3f}"):
    cols = list(d.columns); out = ["| | " + " | ".join(cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for i, r in d.iterrows():
        out.append("| " + str(i) + " | " + " | ".join((fmt.format(v) if isinstance(v, (float, np.floating)) else str(v)) for v in r) + " |")
    return "\n".join(out)


lines = ["# Phase 6: add-on search on TALOS (post-holdout, exploratory)\n",
         "Panel data/proxies_ext (1990 start). Design 1991-01-04..2015-12-31, confirmation 2016-01-04..2026-09-18 (pseudo-holdout: seen once before), full 1991-2026. Band 0.02, lag 2, costs x1. All cells in TRIAL_LEDGER.csv phase P6 (grid: reports/phase6/phase6_metrics.csv, frontier.csv, metals.csv, selection.json).\n",
         "\nCandidate add-on: (C2) buy-the-dip inside the core: when QQQ is above its 200d SMA and today's close is the lowest of the last 10 closes, hold QQQ at min(1, 2 x vol-target size) of the sleeve for 5 days; (B) a third sleeve of 30% of capital in GLD when GLD > its 200d SMA, sized 10%/vol20 (capped at 100% of the sleeve), funded pro rata from the two TALOS sleeves. Five new parameters (dip_n, dip_hold, dip_mult, w_gold, gold_vt); gold_len shares the 200d length.\n"]
for per, (a, b) in PERIODS.items():
    t = pd.DataFrame({k: sm(v, a, b) for k, v in curves.items()}).T[keys]
    lines.append(f"\n## {per}\n\n" + md(t) + "\n")
ann = pd.DataFrame({k: (1 + v.returns).groupby(v.returns.index.year).prod() - 1 for k, v in curves.items() if k in ("TALOS 1x", "TALOS+dip+gold 1.25x", "TALOS+dip+gold 1x", "SPY B&H")})
lines.append("\n## Annual returns\n\n" + md(ann, "{:.1%}") + "\n"); ann.to_csv(OUT / "annual_returns.csv")
(OUT / "summary.md").write_text("".join(lines)); print("".join(lines))

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#eeede9"})
fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
for k, col in [("TALOS 1x", "#2a78d6"), ("TALOS+dip+gold 1.25x", "#eb6834"), ("TALOS+dip+gold 1x", "#e0a020"), ("TALOS 2.5x", "#7fa8d8"), ("TALOS+dip+gold 2.5x", "#b23a1a"), ("SPY B&H", "#1baf7a")]:
    eq = (1 + curves[k].returns).cumprod(); m = sm(curves[k], *WIN)
    ax[0].plot(eq, color=col, lw=1.1, label=f"{k}: CAGR {m['CAGR']:.1%}, MaxDD {m['MaxDD']:.0%}, MAR {m['MAR']:.2f}")
    ax[1].plot(drawdown_series(eq), color=col, lw=0.9)
ax[0].set_yscale("log"); ax[0].legend(loc="upper left", frameon=False, fontsize=8); ax[0].set_title("TALOS vs TALOS + dip + gold sleeve, 1991-2026 (log scale; dashed = start of confirmation window)")
ax[1].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0)); ax[1].set_ylabel("drawdown")
for a_ in ax: a_.axvline(pd.Timestamp("2016-01-04"), color="#bbb", lw=0.8, ls="--")
fig.tight_layout(); fig.savefig(OUT / "equity_phase6.png", dpi=130); plt.close(fig)
pd.DataFrame({k: v.returns for k, v in curves.items()}).to_parquet(OUT / "daily_returns.parquet")
