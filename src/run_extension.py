"""P5 history extension (post-holdout, exploratory, NOT part of the pre-registered evaluation).

Runs the frozen final system (1x and 2.5x) and SPY buy-and-hold on a second proxy panel that starts 1990-01-02
(data/proxies_ext, built by `python3 src/proxies.py --ext`). Evaluation window 1991-01-04 .. 2026-09-18 so the
200-day SMA and 126-day momentum lookbacks are warm on day one. The 1997+ part of the extension panel is identical
to the frozen panel (checked in this script), so 1998+ figures reproduce the holdout run; only the 1991-1997 segment
is new. Everything before the first live ETF print is proxy-only: SPY 1993-01, QQQ 1999-03, IWM 2000-05, TLT/IEF
2002-07, GLD 2004-11; 20y CMT yield is filled from 30y before 1993-10 (see data/proxies_ext/meta.json).
Rows are logged to TRIAL_LEDGER.csv with phase P5 and are excluded from the deflated-Sharpe trial count.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trials import cost_model, log, consecutive_roundtrips
from engine import run, BASE_LAG
from metrics import summary, drawdown_series
from strategies import ALL_COLS, LEVERAGE, b1_spy
import system as S

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "extension"; OUT.mkdir(parents=True, exist_ok=True)
EXT = ROOT / "data" / "proxies_ext"
R = pd.read_parquet(EXT / "returns.parquet"); L = pd.read_parquet(EXT / "levels.parquet")
R0 = pd.read_parquet(ROOT / "data" / "proxies" / "returns.parquet")
ov = R.loc[R0.index[0]:][R0.columns]
assert R0.index.equals(ov.index) and float((R0 - ov).abs().max().max()) == 0.0, "extension panel differs from frozen panel on 1997+"

WIN = ("1991-01-04", "2026-09-18")
PERIODS = {"ext_1991-1997": ("1991-01-04", "1997-12-31"), "ext_full_1991-2026": WIN,
           "1998-2026 (frozen window, check)": ("1998-01-02", "2026-09-18"),
           "1991-1993 (pre-SPY, all proxy)": ("1991-01-04", "1993-01-28"), "1994 bond bear": ("1994-01-03", "1994-12-30"),
           "1995-1997 melt-up": ("1995-01-03", "1997-12-31")}
P = dict(S.PARAMS); BAND = 0.02


def full_run(w, band):
    idx = R.index[(R.index >= WIN[0]) & (R.index <= WIN[1])]
    return run(w.reindex(R.index)[ALL_COLS].loc[idx], R[ALL_COLS], R["CASH"], cost_model(1.0), lag=BASE_LAG,
               leverage=LEVERAGE, rebalance_threshold=band)


def slice_metrics(res, a, b):
    keep = (res.returns.index >= a) & (res.returns.index <= b)
    ret = res.returns[keep]
    m = summary(ret, rf=R["CASH"], spy=R["SPY_X"], weights_held=res.weights_held[keep], gross_leverage=res.gross_leverage.abs()[keep],
                turnover=res.turnover[keep], trades=res.trades[keep])
    m["ConsecRoundTripsPerYear"] = consecutive_roundtrips(res.deltas[keep]) / (len(ret) / 252)
    m["T"] = int(len(ret))
    return m


configs = {"FINAL lever=1.0": (lambda: S.build(R, L, {**P, "lever": 1.0}), BAND),
           "FINAL lever=2.5": (lambda: S.build(R, L, {**P, "lever": 2.5}), BAND),
           "B1 SPY": (lambda: b1_spy(R, L), 0.0)}
led = pd.read_csv(ROOT / "TRIAL_LEDGER.csv") if (ROOT / "TRIAL_LEDGER.csv").exists() else pd.DataFrame(columns=["phase", "cell", "note"])
already = set(led[(led.phase == "P5") & ~led.note.fillna("").str.startswith("duplicate")].cell)
rows, curves = [], {}
for name, (mk, band) in configs.items():
    res = full_run(mk(), band); curves[name] = res
    for per, (a, b) in PERIODS.items():
        m = slice_metrics(res, a, b)
        cell = f"{name} [{per}]"
        tid = None if cell in already else log("P5", name.split()[0], cell, {"config": name, "period": per, "panel": "proxies_ext"}, (a, b), BASE_LAG, 1.0, m,
                  "P5 history extension on 1990-start proxy panel; exploratory, not pre-registered, excluded from DSR count")
        rows.append({"config": name, "period": per, "trial": tid, **m})
df = pd.DataFrame(rows); df.to_csv(OUT / "extension_metrics.csv", index=False)

# annual returns
ann = pd.DataFrame({k: (1 + v.returns).groupby(v.returns.index.year).prod() - 1 for k, v in curves.items()})
ann.to_csv(OUT / "annual_returns.csv")
pd.DataFrame({k: v.returns for k, v in curves.items()}).to_parquet(OUT / "daily_returns.parquet")

# chart
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#eeede9"})
cols = {"FINAL lever=1.0": "#2a78d6", "FINAL lever=2.5": "#eb6834", "B1 SPY": "#1baf7a"}
fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
for k, v in curves.items():
    eq = (1 + v.returns).cumprod()
    mm = df[(df.config == k) & (df.period == "ext_full_1991-2026")].iloc[0]
    ax[0].plot(eq, color=cols[k], lw=1.2, label=f"{k}  (1991-2026 CAGR {mm.CAGR:.1%}, MaxDD {mm.MaxDD:.0%}, MAR {mm.MAR:.2f})")
    ax[1].plot(drawdown_series(eq), color=cols[k], lw=1.0)
ax[0].set_yscale("log"); ax[0].set_title("History extension 1991-2026: final system vs SPY buy-and-hold (growth of $1, log scale)")
ax[0].legend(loc="upper left", frameon=False)
for x, lab in [("1993-01-29", "SPY live"), ("1999-03-10", "QQQ live"), ("2002-07-30", "TLT/IEF live"), ("2004-11-18", "GLD live"),
               ("1998-01-02", "frozen window starts")]:
    for a_ in ax: a_.axvline(pd.Timestamp(x), color="#bbb", lw=0.7, ls="--")
    ax[0].text(pd.Timestamp(x), ax[0].get_ylim()[0] * 1.15, lab, rotation=90, fontsize=7, color="#888", va="bottom")
ax[1].set_ylabel("drawdown"); ax[1].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
fig.tight_layout(); fig.savefig(OUT / "equity_extension.png", dpi=130); plt.close(fig)

# summary markdown
keys = ["CAGR", "Vol", "Sharpe", "Sortino", "MaxDD", "MAR", "MaxDD_start", "MaxDD_trough", "TimeInMarket", "AvgLeverage", "TradesPerYear", "Corr_SPY"]
keys = [k for k in keys if k in df.columns]
def md(d: pd.DataFrame, fmt) -> str:
    cols = list(d.columns); out = ["| | " + " | ".join(cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for i, r in d.iterrows():
        out.append("| " + str(i) + " | " + " | ".join((fmt.format(v) if isinstance(v, (float, np.floating)) else str(v)) for v in r) + " |")
    return "\n".join(out)


lines = ["# P5 history extension (exploratory)\n", "Panel: data/proxies_ext (start 1990-01-02). Window: %s to %s. Band 0.02, lag 2, cost x1.\n" % WIN,
         "Not pre-registered; 1998+ reproduces the holdout run exactly (asserted). Pre-1993 is entirely proxy data.\n"]
for per in PERIODS:
    sub = df[df.period == per].set_index("config")[keys]
    lines.append(f"\n## {per}\n\n" + md(sub, "{:.3f}") + "\n")
lines.append("\n## Annual returns\n\n" + md(ann, "{:.1%}") + "\n")
(OUT / "summary.md").write_text("".join(lines))
print("".join(lines))
