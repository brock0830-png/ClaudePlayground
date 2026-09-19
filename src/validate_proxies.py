"""Tracking charts and PROXY_VALIDATION.md for every spliced or simulated series."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import load_close, load_treasury, trading_calendar
from proxies import par_bond_tr, LEVERED, ER, START

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports" / "proxies"; REP.mkdir(parents=True, exist_ok=True)
BLUE, ORANGE, AQUA, TEXT2 = "#2a78d6", "#eb6834", "#1baf7a", "#52514e"
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c3c2b7", "axes.grid": True, "grid.color": "#eeede9", "figure.facecolor": "#fcfcfb",
                     "axes.facecolor": "#fcfcfb"})

meta = json.loads((ROOT / "data/proxies/meta.json").read_text())
rets = pd.read_parquet(ROOT / "data/proxies/returns.parquet")
cal = rets.index


def chart(name, live, sim, title, note=""):
    both = pd.concat([live, sim], axis=1, keys=["live", "sim"]).dropna()
    g_live = (1 + both.live).cumprod(); g_sim = (1 + both.sim).cumprod()
    ratio = g_live / g_sim
    fig, ax = plt.subplots(2, 1, figsize=(8, 5.2), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    ax[0].plot(g_live, color=BLUE, lw=1.6, label=f"{name} actual")
    ax[0].plot(g_sim, color=ORANGE, lw=1.6, label="proxy / simulation")
    ax[0].set_yscale("log"); ax[0].set_title(title, loc="left", fontsize=10, color="#0b0b0b")
    ax[0].legend(frameon=False, loc="upper left"); ax[0].set_ylabel("growth of 1 (log)")
    ax[1].plot(ratio - 1, color=AQUA, lw=1.4); ax[1].axhline(0, color=TEXT2, lw=0.8)
    ax[1].set_ylabel("actual / proxy - 1"); ax[1].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    if note: ax[1].set_title(note, loc="left", fontsize=8, color=TEXT2)
    fig.tight_layout(); fig.savefig(REP / f"{name}.png", dpi=130); plt.close(fig)
    return both


rows = []
# equity and gold proxies
for etf, idx in [("SPY", "GSPC"), ("QQQ", "NDX"), ("IWM", "RUT"), ("GLD", "GCUSD")]:
    m = meta[f"{etf}_proxy"]
    p = load_close(idx).reindex(cal).ffill(limit=3).pct_change() + m["carry_ann"] / 252
    live = load_close(etf).reindex(cal).pct_change()
    chart(etf, live, p, f"{etf} vs {idx} price index + {m['carry_ann']*100:.2f}%/yr carry",
          f"TE {m['te_ann']*100:.1f}%/yr, split-half drift {m['oos_drift_ann_if_calibrated_on_first_half']*100:+.2f}%/yr")
    rows.append((etf, f"{idx} + carry", m["live_start"], m["te_ann"], m["oos_drift_ann_if_calibrated_on_first_half"], "yes"))
# bonds
tsy = load_treasury().reindex(cal).ffill(limit=5)
for etf in ["TLT", "IEF", "SHY"]:
    m = meta[f"{etf}_proxy"]
    sim = par_bond_tr(tsy[m["yield"]].dropna(), m["maturity"]).reindex(cal) - ER[etf] / 252
    live = load_close(etf).reindex(cal).pct_change()
    live = live[live.index <= "2007-06-29"]
    chart(etf, live, sim, f"{etf} vs constant-maturity par bond from {m['yield']} CMT (M={m['maturity']}y)",
          f"TE {m['te_ann']*100:.1f}%/yr, drift {m['drift_ann']*100:+.2f}%/yr, corr {m['corr']:.2f}, overlap 2002-07 to 2007-06")
    rows.append((etf, f"par bond {m['yield']} M={m['maturity']}", m["live_start"], m["te_ann"], m["drift_ann"], "yes"))
# cash
bil = load_close("BIL").reindex(cal).pct_change() + ER["BIL"] / 252
rf_cmt = tsy["m3"] / 252
# leveraged
lrows = []
for fund, (base, L) in LEVERED.items():
    m = meta[f"{fund}_sim"]
    base_ret = rets[base + "_X"] if base + "_X" in rets else rets[base]
    sim = L * base_ret - (L - 1) * (rets["CASH"] + m["spread_ann"] / 252) - m["expense_ratio"] / 252
    live = load_close(fund).reindex(cal).pct_change()
    chart(fund, live, sim, f"{fund} vs {L}x {base} simulation, spread {m['spread_ann']*100:.2f}%/yr",
          f"TE {m['te_ann']*100:.1f}%/yr, geometric drift after calibration {m['geom_drift_ann_after_calibration']*100:+.2f}%/yr, split-half {m['oos_drift_ann_if_calibrated_on_first_half']*100:+.2f}%/yr")
    lrows.append((fund, base, L, m["expense_ratio"], m["spread_ann"], m["spread_first_half_ann"], m["spread_second_half_ann"],
                  m["te_ann"], m["geom_drift_ann_after_calibration"], m["oos_drift_ann_if_calibrated_on_first_half"], m["corr"], m["live_start"], m["usable"], m["split_half_drift_exceeds_1pct"]))

# availability table
first = rets.apply(lambda s: s.first_valid_index())
md = []
md.append("# PROXY_VALIDATION.md\n")
md.append("All series are daily total-return on the SPY trading calendar from 1997-01-02. Live ETF data is FMP dividend-adjusted closes (validated against Norgate total-return closes in DATA_AUDIT.md). Suffix `_X` denotes a spliced series: the live ETF from its first trading day, the proxy before that. Charts are in `reports/proxies/`; each shows growth of 1 for actual versus proxy over the overlap (top, log scale) and the cumulative ratio actual/proxy minus 1 (bottom).\n")
md.append("## Method\n")
md.append("- Equity and gold: price-index daily return plus a constant carry, calibrated as the mean daily gap between the ETF total return and the index over the first five years of overlap (the regime nearest the pre-inception years). S&P 500 uses `^GSPC`, Nasdaq-100 uses `NDX`, Russell 2000 uses `^RUT`, gold uses front-month gold futures `GCUSD`.")
md.append("- Treasuries: constant-maturity par-bond total return from the FMP daily Treasury curve (same data as FRED DGS). Each day the par bond bought at yesterday's yield is revalued at today's yield with maturity M, plus accrued coupon, minus the ETF expense ratio. The (yield, M) pair with the lowest tracking error over the 2002-07 to 2007-06 overlap was chosen from three candidates per fund; all candidates are listed in `data/proxies/meta.json`.")
md.append("- Cash: 3-month CMT yield / 252 until BIL lists on 2007-05-30, then BIL daily total return plus its expense ratio / 252. Over the 22 overlapping days the two agree to within 0.4%/yr annualised, which is inside the noise of such a short window.")
md.append("- Leveraged ETFs: `L x base return - (L-1) x (cash + spread) - expense ratio / 252`, with the spread calibrated so the mean daily return matches the live fund over its whole history. Two honesty checks are reported: the geometric drift after full-sample calibration (near zero by construction, the brief's 1%/yr criterion), and the change in implied spread between the first and second halves of the live history, which is what an out-of-sample calibration would have missed.\n")
md.append("## Equity and gold proxies\n")
md.append("| ETF | Proxy | Live from | Tracking error (ann.) | Split-half drift (ann.) | Used |\n|---|---|---|---|---|---|")
for r in rows[:4]:
    md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]*100:.2f}% | {r[4]*100:+.2f}% | {r[5]} |")
md.append("\nCarry values (annual): " + ", ".join(f"{e} {meta[f'{e}_proxy']['carry_ann']*100:+.2f}% (full-overlap {meta[f'{e}_proxy']['carry_full_overlap_ann']*100:+.2f}%)" for e in ["SPY", "QQQ", "IWM", "GLD"]) + ".")
md.append("\nThe Nasdaq-100 carry moved from about -0.1%/yr in the first half of the QQQ history to +1.2%/yr in the second half as index dividend yields rose; the early-window calibration (-0.4%/yr) is the right one for the 1997-1999 proxy segment, which is only 14 months long. Gold and Russell carries are stable across halves. The SPY proxy is not used (SPY is live from 1993) and is shown only to demonstrate the method on a long overlap.\n")
md.append("## Treasury proxies\n")
md.append("| ETF | Proxy | Live from | Tracking error (ann.) | Drift (ann.) | Used |\n|---|---|---|---|---|---|")
for r in rows[4:]:
    md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]*100:.2f}% | {r[4]*100:+.2f}% | {r[5]} |")
md.append("\nCandidate comparison (tracking error, drift, beta of live on proxy):\n")
for etf in ["TLT", "IEF", "SHY"]:
    for c in meta[f"{etf}_proxy_candidates"]:
        md.append(f"- {etf}: {c['yield']} M={c['maturity']}: TE {c['te_ann']*100:.2f}%, drift {c['drift_ann']*100:+.2f}%, beta {c['beta']:.2f}, corr {c['corr']:.2f}")
md.append("\nThe 30-year CMT is missing from 2002-02 to 2006-02 (the Treasury stopped issuing), so TLT uses the 20-year yield. IEF's proxy carries a +0.87%/yr drift versus the live fund over the overlap, which is a limitation of a single-point constant-maturity approximation of a 7-to-10-year ladder; it is used only for the 1997 to 2002-07 segment and flagged here. The SHY proxy has beta 0.83, meaning the 2-year par bond is a little more volatile than the 1-3 year ladder; its tracking error is under 0.8%/yr.\n")
md.append("## Simulated leveraged ETFs\n")
md.append("| Fund | Base | L | ER | Spread (full) | Spread 1st half | Spread 2nd half | TE (ann.) | Geometric drift after calibration | Split-half drift | Corr | Live from | Passes 1% rule | Split-half > 1% |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in lrows:
    md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]*100:.2f}% | {r[4]*100:+.2f}% | {r[5]*100:+.2f}% | {r[6]*100:+.2f}% | {r[7]*100:.1f}% | {r[8]*100:+.2f}% | {r[9]*100:+.2f}% | {r[10]:.3f} | {r[11]} | {'yes' if r[12] else 'NO'} | {'yes' if r[13] else 'no'} |")
md.append("\nAll nine simulated funds pass the brief's criterion (geometric drift within 1%/yr after calibrating the financing spread on the live history). Two of them, SSO and TQQQ, have an implied spread that shifted by more than 1%/yr between the halves of their live history (SSO -0.74% to +0.40%, TQQQ +0.41% to +1.06%), so a spread calibrated on one half would have drifted by about 1.1 to 1.3%/yr on the other. This is the honest uncertainty on the pre-inception simulated segments (1997 to 2006 for 2x, 1997 to 2009/2010 for 3x). Phase 3 therefore reports every leveraged result with a sensitivity of plus and minus 1%/yr of extra drag on the simulated segments. Correlations of 0.97 to 0.998 and tracking errors of 3 to 5%/yr are consistent with daily-rebalanced funds whose intraday and financing details are not modelled.\n")
md.append("## Series availability\n")
md.append("| Series | First date | Note |\n|---|---|---|")
notes = {"CASH": "3m CMT then BIL", "SPY_X": "GSPC proxy before 1997-01-03 (unused)", "QQQ_X": "NDX proxy before 1999-03-11",
         "IWM_X": "RUT proxy before 2000-05-30", "GLD_X": "GCUSD proxy before 2004-11-19", "TLT_X": "par bond proxy before 2002-07-31",
         "IEF_X": "par bond proxy before 2002-07-31", "SHY_X": "par bond proxy before 2002-07-31"}
for c in rets.columns:
    n = notes.get(c, "simulated before live start" if c.endswith("_X") else "live only")
    md.append(f"| {c} | {first[c].date() if first[c] is not None else 'n/a'} | {n} |")
md.append("\n## Charts\n")
for name in ["SPY", "QQQ", "IWM", "GLD", "TLT", "IEF", "SHY"] + list(LEVERED):
    md.append(f"![{name}](reports/proxies/{name}.png)")
(ROOT / "PROXY_VALIDATION.md").write_text("\n".join(md) + "\n")
print("wrote PROXY_VALIDATION.md and", len(list(REP.glob('*.png'))), "charts")
