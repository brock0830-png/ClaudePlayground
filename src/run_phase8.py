"""Phase 8 (exploratory): base-substitution test. Is the rule set sound, or was it riding the US large-cap wave?
For each base ETF X the same rules are run with X as the core asset and compared with X's own buy-and-hold over X's
own live history (start = first print + 260 trading days for warm-up; end 2026-09-18). Three configurations per base:
  engine v1  : the pre-registered core only (SMA200 gate, 10% vol target, IEF fallback), 100% of capital, 1x
  engine T7  : the v2 core only (SMA250, 1% band, dip boost, IEF fallback), 100% of capital, 1x
  full T7    : v2 with X replacing QQQ in the core; rotation (SPY/QQQ/IWM/TLT/GLD) and gold sleeve unchanged; 1.25x
Live ETF data only (no proxies) for the bases; the rotation/gold/IEF columns come from the extension panel.
Costs 2 bp + 1 bp half-spread on every base (the emerging-market ETFs trade wider; a 3x cost row is included)."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import load_close
from trials import cost_model, log, consecutive_roundtrips
from engine import run, BASE_LAG
from metrics import summary, drawdown_series
from strategies import ALL_COLS, LEVERAGE
import system2 as S2

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "reports" / "phase8"; OUT.mkdir(parents=True, exist_ok=True)
R = pd.read_parquet(ROOT / "data/proxies_ext/returns.parquet").copy(); L = pd.read_parquet(ROOT / "data/proxies_ext/levels.parquet").copy()
END = "2026-09-18"
BASES = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "DIA": "Dow 30", "IWM": "Russell 2000", "XLF": "US financials", "XLE": "US energy",
         "EFA": "Developed ex-US", "VGK": "Europe", "EWG": "Germany", "EWU": "UK", "EWJ": "Japan",
         "EEM": "Emerging markets", "FXI": "China", "EWZ": "Brazil", "ILF": "Latin America"}
# live columns for every base (SPY/QQQ/IWM: replace the spliced proxy column with the live-only series for this test)
for b in BASES:
    live = load_close(b).reindex(R.index).pct_change()
    R[f"{b}_X"] = live; lv = (1 + live.fillna(0)).cumprod(); lv[live.isna() & live.ffill().isna()] = np.nan; L[f"{b}_X"] = lv
led = pd.read_csv(ROOT / "TRIAL_LEDGER.csv"); led["note"] = led["note"].fillna("")
already = set(led[(led.phase == "P8") & ~led.note.str.startswith("duplicate")].cell)
COLS = sorted(set(ALL_COLS) | {f"{b}_X" for b in BASES}); LEV = {**LEVERAGE, **{f"{b}_X": 1 for b in BASES}}
P0 = dict(S2.PARAMS2, lever=1.0)
ENG_V1 = dict(P0, w_core=1.0)                                                     # core only, pre-registered
ENG_T7 = dict(P0, w_core=1.0, sma_len=250, gate_band=0.01, dip_n=10, dip_hold=5, dip_mult=2.0)
FULL_T7 = dict(S2.PARAMS_T7)


def run_w(w, a, b, cost_mult=1.0):
    idx = R.index[(R.index >= a) & (R.index <= b)]
    return run(w.reindex(R.index).reindex(columns=COLS).fillna(0.0).loc[idx], R[COLS], R["CASH"], cost_model(cost_mult), lag=BASE_LAG, leverage=LEV, rebalance_threshold=0.02)


def sm(res, a, b, spy_col):
    keep = (res.returns.index >= a) & (res.returns.index <= b); ret = res.returns[keep]
    m = summary(ret, rf=R["CASH"], spy=R[spy_col], weights_held=res.weights_held[keep], gross_leverage=res.gross_leverage.abs()[keep], turnover=res.turnover[keep], trades=res.trades[keep])
    m["ConsecRoundTripsPerYear"] = consecutive_roundtrips(res.deltas[keep]) / (len(ret) / 252); return m


rows = []; curves = {}
for b, label in BASES.items():
    first = R[f"{b}_X"].first_valid_index(); a = R.index[R.index.get_loc(first) + 260]
    bh = pd.DataFrame(0.0, R.index, COLS); bh[f"{b}_X"] = 1.0
    cfgs = {"buy&hold": (bh, 1.0), "engine v1": (S2.build2(R, L, dict(ENG_V1, core_asset=b)), 1.0),
            "engine T7": (S2.build2(R, L, dict(ENG_T7, core_asset=b)), 1.0), "full T7 1.25x": (S2.build2(R, L, dict(FULL_T7, core_asset=b)), 1.0),
            "engine T7 cost3": (S2.build2(R, L, dict(ENG_T7, core_asset=b)), 3.0),
            # risk-budget-matched variant: vol target = the base's own full-window realised vol, so the vol target no longer
            # throttles exposure (the engine is then essentially the trend gate + dip boost, near 100% when on)
            "engine T7 vt=base": (S2.build2(R, L, dict(ENG_T7, core_asset=b, vol_target=float(R[f"{b}_X"].loc[first:].std() * 252 ** 0.5))), 1.0)}
    for cfg, (w, cm) in cfgs.items():
        res = run_w(w, a, END, cm); m = sm(res, a, END, f"{b}_X"); curves[(b, cfg)] = res.returns
        cell = f"P8 {b} {cfg} [{a.date()}..{END}]"
        if cell not in already and cfg != "buy&hold":
            log("P8", "BASE-SUB", cell, {"base": b, "config": cfg, "cost_mult": cm}, (str(a.date()), END), BASE_LAG, cm, m, "P8 base-substitution test, live ETF data")
        rows.append({"base": b, "label": label, "config": cfg, "start": a.date(), "years": round(len(res.returns) / 252, 1),
                     **{k: m[k] for k in ("CAGR", "Vol", "Sharpe", "MaxDD", "MAR", "TradesPerYear")}, "TimeInMarket": m.get("TimeInMarket", np.nan)})
df = pd.DataFrame(rows); df.to_csv(OUT / "base_substitution.csv", index=False)

# summary table: each config vs its own base
piv = df.pivot(index="base", columns="config", values=["CAGR", "MaxDD", "MAR", "Sharpe"])
tab = pd.DataFrame({"market": [BASES[b] for b in piv.index], "start": [df[(df.base == b)].start.iloc[0] for b in piv.index],
                    "B&H CAGR": piv["CAGR"]["buy&hold"], "B&H MaxDD": piv["MaxDD"]["buy&hold"], "B&H MAR": piv["MAR"]["buy&hold"],
                    "v1 CAGR": piv["CAGR"]["engine v1"], "v1 MaxDD": piv["MaxDD"]["engine v1"], "v1 MAR": piv["MAR"]["engine v1"],
                    "T7 CAGR": piv["CAGR"]["engine T7"], "T7 MaxDD": piv["MaxDD"]["engine T7"], "T7 MAR": piv["MAR"]["engine T7"], "T7 Sharpe": piv["Sharpe"]["engine T7"], "B&H Sharpe": piv["Sharpe"]["buy&hold"],
                    "T7 cost3 MAR": piv["MAR"]["engine T7 cost3"],
                    "vt=base CAGR": piv["CAGR"]["engine T7 vt=base"], "vt=base MaxDD": piv["MaxDD"]["engine T7 vt=base"], "vt=base MAR": piv["MAR"]["engine T7 vt=base"], "vt=base Sharpe": piv["Sharpe"]["engine T7 vt=base"],
                    "full CAGR": piv["CAGR"]["full T7 1.25x"], "full MaxDD": piv["MaxDD"]["full T7 1.25x"], "full MAR": piv["MAR"]["full T7 1.25x"]}, index=piv.index)
tab = tab.loc[list(BASES)]
tab["T7 beats B&H: MAR"] = tab["T7 MAR"] > tab["B&H MAR"]; tab["T7 beats B&H: CAGR"] = tab["T7 CAGR"] > tab["B&H CAGR"]; tab["T7 beats B&H: Sharpe"] = tab["T7 Sharpe"] > tab["B&H Sharpe"]
tab.to_csv(OUT / "summary_table.csv")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
show = tab[["market", "start", "B&H CAGR", "B&H MaxDD", "B&H MAR", "B&H Sharpe", "T7 CAGR", "T7 MaxDD", "T7 MAR", "T7 Sharpe", "vt=base CAGR", "vt=base MaxDD", "vt=base MAR", "vt=base Sharpe", "full CAGR", "full MaxDD", "full MAR"]].copy()
for c in show.columns:
    if "CAGR" in c or "MaxDD" in c: show[c] = (show[c] * 100).round(1)
    elif "MAR" in c or "Sharpe" in c: show[c] = show[c].round(2)
print(show.to_string())
print("\nengine T7 beats its own base on MAR:", int(tab["T7 beats B&H: MAR"].sum()), "of", len(tab), "| on CAGR:", int(tab["T7 beats B&H: CAGR"].sum()), "| on Sharpe:", int(tab["T7 beats B&H: Sharpe"].sum()))
print("engine T7 vt=base beats base on MAR:", int((tab["vt=base MAR"] > tab["B&H MAR"]).sum()), "| on CAGR:", int((tab["vt=base CAGR"] > tab["B&H CAGR"]).sum()), "| on Sharpe:", int((tab["vt=base Sharpe"] > tab["B&H Sharpe"]).sum()))
print("engine v1 beats its own base on MAR:", int((tab["v1 MAR"] > tab["B&H MAR"]).sum()), "| on CAGR:", int((tab["v1 CAGR"] > tab["B&H CAGR"]).sum()))
print("full T7 1.25x beats base on MAR:", int((tab["full MAR"] > tab["B&H MAR"]).sum()), "| on CAGR:", int((tab["full CAGR"] > tab["B&H CAGR"]).sum()))

# chart: small multiples
plt.rcParams.update({"font.size": 7.5, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#eeede9"})
fig, axes = plt.subplots(3, 5, figsize=(17, 9)); axes = axes.ravel()
for i, (b, label) in enumerate(BASES.items()):
    ax = axes[i]
    for cfg, col in [("buy&hold", "#9aa0a6"), ("engine T7", "#eb6834"), ("full T7 1.25x", "#2a78d6")]:
        s = curves[(b, cfg)]; eq = (1 + s).cumprod(); r = tab.loc[b]
        ax.plot(eq, color=col, lw=0.9, label=cfg)
    ax.set_yscale("log"); ax.set_title(f"{b} {label}: B&H MAR {tab.loc[b,'B&H MAR']:.2f} | engine {tab.loc[b,'T7 MAR']:.2f} | full {tab.loc[b,'full MAR']:.2f}", fontsize=7.5)
    if i == 0: ax.legend(frameon=False, fontsize=7)
fig.suptitle("Base-substitution test: same rules, each base vs its own buy-and-hold (log scale, live ETF history)", fontsize=10)
fig.tight_layout(); fig.savefig(OUT / "base_substitution.png", dpi=130); plt.close(fig)
pd.DataFrame({f"{b}|{c}": s for (b, c), s in curves.items()}).to_parquet(OUT / "daily_returns.parquet")
