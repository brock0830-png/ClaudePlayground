"""Phase 4: ONE-SHOT holdout run. Computes all requested metrics for the final system (frontier points) and the
baselines over the full period, design window, holdout, and the four stress episodes; logs to the ledger (phase P4);
writes reports/holdout/*.csv and charts. Refuses to run twice (writes reports/holdout/RAN_ONCE)."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trials import load_panel, cost_model, log, consecutive_roundtrips, UNLOCK, DESIGN, HOLDOUT
from engine import run, BASE_LAG
from metrics import summary, deflated_sharpe, drawdown_series
from strategies import ALL_COLS, LEVERAGE, b1_spy, b2_6040, b3_spy_sma, b4_voltarget
import system as S
from trials import drag_panel

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "reports" / "holdout"; OUT.mkdir(parents=True, exist_ok=True)
if (OUT / "RAN_ONCE").exists():
    raise SystemExit("holdout already run once; refusing (see PREREG section 4)")
UNLOCK.write_text("unlocked at freeze commit 06a6f79 for the single holdout run\n")
R, L, VIX = load_panel()
FULL = ("1998-01-02", "2026-09-18")
PERIODS = {"full": FULL, "design": DESIGN, "holdout": HOLDOUT, "2000-02": ("2000-01-03", "2002-12-31"),
           "2007-09": ("2007-01-03", "2009-12-31"), "2020": ("2020-01-02", "2020-12-31"), "2022": ("2022-01-03", "2022-12-30")}
P = dict(S.PARAMS); BAND = 0.02


def final_weights(lever, Rx=R):
    return S.build(Rx, L, {**P, "lever": lever})


configs = {"FINAL lever=1.0": (lambda: final_weights(1.0), BAND), "FINAL lever=2.5": (lambda: final_weights(2.5), BAND),
           "FINAL lever=3.0": (lambda: final_weights(3.0), BAND),
           "B1 SPY": (lambda: b1_spy(R, L), 0.0), "B2 60/40": (lambda: b2_6040(R, L), 0.0),
           "B3 SPY/200": (lambda: b3_spy_sma(R, L), 0.0), "B4 volSPY": (lambda: b4_voltarget(R, L), 0.0)}


def full_run(w, band, lag=BASE_LAG, cost_mult=1.0, Rx=R):
    idx = Rx.index[(Rx.index >= FULL[0]) & (Rx.index <= FULL[1])]
    return run(w.reindex(Rx.index)[ALL_COLS].loc[idx], Rx[ALL_COLS], Rx["CASH"], cost_model(cost_mult), lag=lag,
               leverage=LEVERAGE, rebalance_threshold=band)


def slice_metrics(res, a, b, Rx=R):
    keep = (res.returns.index >= a) & (res.returns.index <= b)
    ret = res.returns[keep]
    m = summary(ret, rf=Rx["CASH"], spy=Rx["SPY_X"], weights_held=res.weights_held[keep], gross_leverage=res.gross_leverage.abs()[keep],
                turnover=res.turnover[keep], trades=res.trades[keep])
    m["ConsecRoundTripsPerYear"] = consecutive_roundtrips(res.deltas[keep]) / (len(ret) / 252)
    m["T"] = int(len(ret))
    return m


rows = []; curves = {}
for name, (mk, band) in configs.items():
    res = full_run(mk(), band); curves[name] = res
    for per, (a, b) in PERIODS.items():
        m = slice_metrics(res, a, b)
        tid = log("P4", name.split()[0], f"{name} [{per}]", {"config": name, "period": per}, (a, b), BASE_LAG, 1.0, m, "one-shot holdout run")
        rows.append({"config": name, "period": per, "trial": tid, **{k: v for k, v in m.items()}})
# sensitivities on the final at lever 1.0 and 2.5, holdout and full
for lev in [1.0, 2.5]:
    for tag, kw in [("lag3", {"lag": 3}), ("lag1", {"lag": 1}), ("cost0", {"cost_mult": 0.0}), ("cost3", {"cost_mult": 3.0})]:
        res = full_run(final_weights(lev), BAND, **kw)
        for per in ["holdout", "full"]:
            m = slice_metrics(res, *PERIODS[per])
            tid = log("P4", "FINAL", f"FINAL lever={lev} {tag} [{per}]", {"lever": lev, **kw, "period": per}, PERIODS[per], kw.get("lag", BASE_LAG), kw.get("cost_mult", 1.0), m, "sensitivity")
            rows.append({"config": f"FINAL lever={lev} {tag}", "period": per, "trial": tid, **m})
    for d in [-0.01, 0.01]:
        Rx = drag_panel(R, d); res = full_run(final_weights(lev, Rx), BAND, Rx=Rx)
        for per in ["design", "full"]:
            m = slice_metrics(res, *PERIODS[per], Rx=Rx)
            tid = log("P4", "FINAL", f"FINAL lever={lev} simdrag{d:+.0%} [{per}]", {"lever": lev, "sim_drag": d, "period": per}, PERIODS[per], BASE_LAG, 1.0, m, "sensitivity")
            rows.append({"config": f"FINAL lever={lev} simdrag{d:+.0%}", "period": per, "trial": tid, **m})

df = pd.DataFrame(rows); df.to_csv(OUT / "holdout_metrics.csv", index=False)
# deflated Sharpe
led = pd.read_csv(ROOT / "TRIAL_LEDGER.csv"); led["note"] = led["note"].fillna("")
valid = led[~led.note.str.startswith("superseded") & ~led.note.str.startswith("duplicate") & led.phase.isin(["P3", "P3R", "P3C"])]
n_trials = int(len(valid)); sr_var = float(valid.sharpe.var())
dsr = {}
for cfg in ["FINAL lever=1.0", "FINAL lever=2.5"]:
    for per in ["design", "holdout", "full"]:
        r = df[(df.config == cfg) & (df.period == per)].iloc[0]
        ret = curves[cfg].returns; a, b = PERIODS[per]; rr = ret[(ret.index >= a) & (ret.index <= b)]
        dsr[f"{cfg} [{per}]"] = {"sharpe": float(r.Sharpe), "T": int(r["T"]), "n_trials": n_trials, "sr_var_trials": sr_var,
                                 "skew": float(rr.skew()), "kurt": float(rr.kurt() + 3),
                                 "PSR_vs_max_of_trials": deflated_sharpe(float(r.Sharpe), n_trials, int(r["T"]), float(rr.skew()), float(rr.kurt() + 3), sr_var)}
(OUT / "deflated_sharpe.json").write_text(json.dumps(dsr, indent=2))
# charts
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#eeede9",
                     "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb"})
cols = {"FINAL lever=1.0": "#2a78d6", "FINAL lever=2.5": "#eb6834", "B1 SPY": "#1baf7a", "B3 SPY/200": "#eda100", "B2 60/40": "#e87ba4"}
fig, ax = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
for name, c in cols.items():
    eq = curves[name].equity; ax[0].plot(eq, color=c, lw=1.5, label=name); ax[1].plot(drawdown_series(eq), color=c, lw=1.1)
ax[0].set_yscale("log"); ax[0].axvline(pd.Timestamp(HOLDOUT[0]), color="#52514e", lw=0.8, ls="--"); ax[1].axvline(pd.Timestamp(HOLDOUT[0]), color="#52514e", lw=0.8, ls="--")
ax[0].text(pd.Timestamp(HOLDOUT[0]), ax[0].get_ylim()[1], " holdout ->", va="top", fontsize=8, color="#52514e")
ax[0].set_title("Growth of 1, 1998-2026 (log); dashed line = start of locked holdout", loc="left", fontsize=10)
ax[0].legend(frameon=False, loc="upper left", fontsize=8); ax[1].set_ylabel("drawdown"); ax[1].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
fig.tight_layout(); fig.savefig(OUT / "equity_full.png", dpi=130); plt.close(fig)
# holdout-only chart rebased
fig, ax = plt.subplots(figsize=(9, 4))
for name, c in cols.items():
    r = curves[name].returns; r = r[r.index >= HOLDOUT[0]]; ax.plot((1 + r).cumprod(), color=c, lw=1.5, label=name)
ax.set_yscale("log"); ax.set_title("Holdout 2016-2026, growth of 1 (log)", loc="left", fontsize=10); ax.legend(frameon=False, fontsize=8)
fig.tight_layout(); fig.savefig(OUT / "equity_holdout.png", dpi=130); plt.close(fig)
# save daily returns of curves for the report
pd.DataFrame({k: v.returns for k, v in curves.items()}).to_parquet(OUT / "daily_returns.parquet")
(OUT / "RAN_ONCE").write_text("holdout executed once\n")
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
show = df[["config", "period", "CAGR", "Vol", "Sharpe", "Sortino", "MaxDD", "MAR", "LongestUnderwater_days", "WorstDay", "WorstMonth", "Worst12m", "TimeInMarket", "AvgLeverage", "Turnover_ann", "TradesPerYear", "ConsecRoundTripsPerYear", "CorrSPY"]]
print(show.round(3).to_string()); print(json.dumps(dsr, indent=1))
