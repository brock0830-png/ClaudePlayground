"""
Phase 2 candidate evaluation over a window (DEV pages now; the identical code runs OOS once).
Usage: python scripts/p2_candidates.py dev|oos
OOS requires results/p2/OOS_UNLOCKED naming the Phase 2 freeze commit, with frozen files unchanged.
"""
import sys, json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np
import pandas as pd
from scalpel.data import load_bars, RESULTS, OOS_START, DEV_END
from scalpel import p2
from scalpel.stats import boot_ci_mean, max_drawdown, profit_factor, deflated_sharpe, psr
from p2_screen import eval_es

OUT = RESULTS / "p2"
MES_USD, MES_COST = 5.0, 3.0
VIX_BINS, VIX_LAB = [0, 15, 20, 30, 1000], ["<15", "15-20", "20-30", ">30"]


def target_for(ctx, spec):
    if spec["kind"] == "session":
        return p2.session_target(ctx, spec)
    return p2.bar_target_from_daily(ctx, p2.daily_target(ctx["D"], spec))


def trade_table(ctx, res):
    b = ctx["bars"]
    t = res["trades"].copy()
    t["entry_time"] = b.index[t["s"].values]
    ex = np.minimum(t["e"].values + 1, len(b) - 1)
    t["exit_time"] = b.index[ex]
    t["year"] = pd.DatetimeIndex(b["tday"].values[t["s"].values]).year
    D = ctx["D"]
    sess = ctx["sess"][t["s"].values]
    t["vix_prev"] = D["vix"].values[np.clip(sess - 1, 0, None)]
    atr = (D["high"] - D["low"]).rolling(20).mean().values
    t["atr20"] = atr[np.clip(sess - 1, 0, None)]
    return t


def fixed_fractional(t, start=100_000.0, risk=0.01):
    eq, rows = start, []
    for _, r in t.iterrows():
        per = 2 * r["atr20"] * MES_USD + MES_COST
        k = int(np.floor(risk * eq / per)) if per > 0 and np.isfinite(per) else 0
        eq += k * r["net"] * MES_USD
        rows.append((r["exit_time"], k, eq))
    return pd.DataFrame(rows, columns=["exit_time", "contracts", "equity"])


def metrics(ctx, spec, i0, i1, years, trial_var, n_trials, rng):
    tgt = target_for(ctx, spec)
    res = p2.run_bars(ctx, tgt, i0, i1)
    t = trade_table(ctx, res)
    ev = eval_es(ctx, tgt, i0, i1, rng, years)
    x = t["net"].values
    daily = pd.Series(res["pnl"]).groupby(ctx["tday"][i0:i1]).sum()
    months = pd.to_datetime(t["exit_time"]).dt.tz_localize(None).dt.to_period("M")
    mp = t.groupby(months)["net"].sum()
    ff = fixed_fractional(t)
    ffe = ff["equity"].values
    yrs = (pd.Timestamp(ctx["tday"][i1 - 1]) - pd.Timestamp(ctx["tday"][i0])).days / 365.25
    sr_day = daily.mean() / daily.std(ddof=1)
    m = dict(trades=len(t), win_rate=float((x > 0).mean()), ev_pts=float(x.mean()), ev_usd_es=float(x.mean() * 50),
             ev_ci95=boot_ci_mean(x), profit_factor=profit_factor(x), total_pts=float(x.sum()),
             max_dd_pts=max_drawdown(x), worst_trade_pts=float(x.min()), best_trade_pts=float(x.max()),
             worst_month_pts=float(mp.min()), worst_month=str(mp.idxmin()), sharpe_ann=float(sr_day * np.sqrt(252)),
             sessions_in=ev["sessions_in"], avg_bars=float(t["bars"].mean()),
             rand_pct=ev["rand_pct"], rand_mean_ev=ev["rand_mean"], timing_excess_pts=ev["excess"],
             excess_t=ev["excess_t"], weekly_ci=(ev["ci_lo"], ev["ci_hi"]),
             ff_final=float(ffe[-1]), ff_cagr=float((ffe[-1] / 1e5) ** (1 / yrs) - 1), ff_max_dd=float(
                 (ffe / np.maximum.accumulate(np.r_[1e5, ffe])[1:] - 1).min()),
             dsr=deflated_sharpe(float(sr_day), len(daily), float(daily.skew()), float(daily.kurt() + 3), trial_var, n_trials),
             dsr_noise_var=deflated_sharpe(float(sr_day), len(daily), float(daily.skew()), float(daily.kurt() + 3),
                                           1.0 / len(daily), n_trials),
             psr_vs_0=psr(float(sr_day), len(daily), float(daily.skew()), float(daily.kurt() + 3)))
    by_year = t.groupby("year").agg(trades=("net", "size"), win=("net", lambda s: (s > 0).mean()),
                                    ev_pts=("net", "mean"), total_pts=("net", "sum"))
    reg = pd.cut(t["vix_prev"], VIX_BINS, labels=VIX_LAB, right=False)
    by_vix = t.groupby(reg, observed=False).agg(trades=("net", "size"), ev_pts=("net", "mean"), total_pts=("net", "sum"))
    return m, by_year, by_vix, t, daily, ff


def buy_hold(ctx, i0, i1):
    tgt = np.ones(len(ctx["o"]))
    res = p2.run_bars(ctx, tgt, i0, i1)
    d = pd.Series(res["pnl"]).groupby(ctx["tday"][i0:i1]).sum()
    eq = d.cumsum()
    return dict(total_pts=float(d.sum()), sharpe_ann=float(d.mean() / d.std() * np.sqrt(252)),
                max_dd_pts=float((eq - eq.cummax()).min())), d


def plot(daily_by, ff_by, bh_daily, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    cols = ["#1f5fa8", "#c2571a", "#2a7d4f", "#6b3fa0"]
    x = pd.to_datetime(bh_daily.index)
    ax[0].plot(x, bh_daily.cumsum().values, color="#9a9a9a", lw=1.2, label="buy & hold 1 ES")
    for (name, d), col in zip(daily_by.items(), cols):
        ax[0].plot(pd.to_datetime(d.index), d.cumsum().values, color=col, lw=1.6, label=name)
    ax[0].axhline(0, color="#555", lw=0.8); ax[0].set_ylabel("cumulative net points (1 ES)")
    ax[0].legend(fontsize=8, frameon=False, loc="upper left"); ax[0].grid(alpha=0.25); ax[0].set_title(title, fontsize=11)
    for (name, f), col in zip(ff_by.items(), cols):
        ax[1].plot(pd.to_datetime(f["exit_time"]).dt.tz_localize(None), f["equity"].values, color=col, lw=1.4, label=name)
    ax[1].axhline(1e5, color="#555", lw=0.8); ax[1].set_ylabel("$ equity (1% vol-risk, MES)"); ax[1].grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def check_lock():
    lock = OUT / "OOS_UNLOCKED"
    if not lock.exists():
        raise SystemExit("Phase 2 OOS locked")
    h = lock.read_text().split()[0]
    froz = subprocess.run(["git", "log", "-1", "--format=%H", "--", "results/p2/frozen_rules.md", "results/p2/frozen_candidates.json"],
                          cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "results/p2/frozen_rules.md", "results/p2/frozen_candidates.json",
                            "scalpel", "scripts"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if h != froz or dirty:
        raise SystemExit(f"lock {h} != freeze {froz} or frozen files modified:\n{dirty}")


def main(which):
    cands = json.loads((OUT / "frozen_candidates.json").read_text())
    log = pd.read_csv(OUT / "log.csv")
    trial_var = float((log.loc[log["n"] >= 30, "sharpe_ann"] / np.sqrt(252)).var())
    n_trials = len(log)
    if which == "dev":
        bars = load_bars("dev"); i0, years = 0, list(range(2013, 2020))
    else:
        check_lock()
        bars = load_bars("all"); years = list(range(2020, 2027))
    ctx = p2.es_context(bars)
    i1 = len(bars)
    if which == "oos":
        i0 = int(np.searchsorted(bars.index, OOS_START))
    rng = np.random.default_rng(7)
    out = {"window": which, "n_trials_p2": n_trials, "trial_var_day": trial_var, "candidates": []}
    daily_by, ff_by = {}, {}
    port = None
    for c in cands:
        m, by, bv, t, daily, ff = metrics(ctx, c["spec"], i0, i1, years, trial_var, n_trials, rng)
        t.to_csv(OUT / f"{which}_trades_{c['name']}.csv", index=False)
        out["candidates"].append({"name": c["name"], "metrics": m, "by_year": by.round(3).reset_index().to_dict("records"),
                                  "by_vix": bv.round(3).reset_index().astype({"vix_prev": str}).to_dict("records")})
        daily_by[c["name"]] = daily; ff_by[c["name"]] = ff
        port = daily if port is None else port.add(daily, fill_value=0.0)
    bh, bh_d = buy_hold(ctx, i0, i1)
    out["buy_hold"] = bh
    out["combined_1_1_1"] = dict(total_pts=float(port.sum()), sharpe_ann=float(port.mean() / port.std() * np.sqrt(252)),
                                 max_dd_pts=float((port.cumsum() - port.cumsum().cummax()).min()),
                                 psr_vs_0=psr(float(port.mean() / port.std()), len(port), float(port.skew()), float(port.kurt() + 3)))
    daily_by["combined 1+1+1"] = port
    plot(daily_by, ff_by, bh_d, OUT / f"{which}_equity.png", f"Phase 2 {which.upper()}: frozen candidates vs buy & hold (net pts, 1 ES each)")
    (OUT / f"{which}_results.json").write_text(json.dumps(out, indent=1, default=str))
    for c in out["candidates"]:
        m = c["metrics"]
        print(c["name"], m["trades"], round(m["ev_pts"], 2), [round(v, 2) for v in m["ev_ci95"]], "PF", round(m["profit_factor"], 2),
              "Sh", round(m["sharpe_ann"], 2), "rand", m["rand_pct"], "excess", round(m["timing_excess_pts"], 1),
              "DSR", round(m["dsr"]["dsr"], 4), round(m["dsr_noise_var"]["dsr"], 4), "PSR", round(m["psr_vs_0"], 3))
    print("buy&hold", bh); print("combined", out["combined_1_1_1"])


if __name__ == "__main__":
    main(sys.argv[1])
