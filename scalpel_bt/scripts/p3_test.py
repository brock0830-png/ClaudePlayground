"""
ONE-SHOT Phase 3 test on the untouched markets (PROTOCOL_P3.md): QQQ IWM DIA EFA EWG EWJ EWU.
Refuses to run unless results/p3/TEST_UNLOCKED names the commit that froze results/p3/frozen_rules.md
and results/p3/frozen_candidates.json, and scalpel/ scripts/ are unchanged since.
Also reports ES 2020-2026 (third look at that window: not part of any verdict).
Usage: python scripts/p3_test.py
"""
import sys, json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from scalpel.data import load_bars, RESULTS, OOS_START
from scalpel import p3
from scalpel.stats import boot_ci_mean, deflated_sharpe

OUT = RESULTS / "p3"
N_RAND = 500


def check_lock():
    lock = p3.TEST_LOCK
    if not lock.exists():
        raise SystemExit("Phase 3 test locked")
    h = lock.read_text().split()[0]
    froz = subprocess.run(["git", "log", "-1", "--format=%H", "--", "results/p3/frozen_rules.md", "results/p3/frozen_candidates.json"],
                          cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "results/p3/frozen_rules.md", "results/p3/frozen_candidates.json",
                            "scalpel", "scripts"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if h != froz or dirty:
        raise SystemExit(f"lock {h} != freeze {froz} or frozen files modified:\n{dirty}")


def stats(r):
    r = np.asarray(r, float)
    if len(r) == 0:
        return dict(n=0)
    return dict(n=int(len(r)), ev_pct=float(r.mean() * 100), win=float((r > 0).mean()),
                pf=float(r[r > 0].sum() / -r[r < 0].sum()) if (r < 0).any() else float("inf"),
                t=float(r.mean() / r.std(ddof=1) * np.sqrt(len(r))) if len(r) > 1 and r.std() > 0 else 0.0,
                total_pct=float(r.sum() * 100), worst_pct=float(r.min() * 100))


def run_system(spec, mode, rng):
    per, pooled, rnd_sum, cnt, curves = {}, [], np.zeros(N_RAND), 0, {}
    for sym in p3.TEST_SYMBOLS:
        D = p3.etf_daily(sym)
        i0, i1 = 252, len(D)
        t = p3.simulate(D, spec, mode, i0, i1)
        s = stats(t["ret"].values)
        if len(t):
            rnd = p3.random_exposure(D, t, mode, i0, i1, rng, N_RAND)
            s["rand_pct"] = float((rnd < t["ret"].mean()).mean() * 100)
            rnd_sum += rnd * len(t); cnt += len(t)
            t = t.assign(sym=sym, date=D["date"].values[t["sig"].values])
            pooled.append(t)
            curves[sym] = t
        s["start"] = str(pd.Timestamp(D["date"].iat[i0]).date())
        per[sym] = s
    P = pd.concat(pooled, ignore_index=True) if pooled else pd.DataFrame()
    out = {"per_market": per, "pooled": stats(P["ret"].values) if len(P) else {"n": 0}}
    if len(P):
        lo, hi = boot_ci_mean(P["ret"].values)
        out["pooled"]["ci95_pct"] = (lo * 100, hi * 100)
        out["pooled"]["rand_pct"] = float(((rnd_sum / cnt) < P["ret"].mean()).mean() * 100)
        out["markets_positive"] = int(sum(1 for s in per.values() if s.get("n", 0) and s["ev_pct"] > 0))
        dec = (pd.DatetimeIndex(P["date"]).year // 10) * 10
        out["by_decade"] = {int(k): stats(v["ret"].values) for k, v in P.groupby(dec)}
    return out, P


def es_window(spec):
    D = p3.es_daily(load_bars("all"))
    i0 = int(np.searchsorted(pd.DatetimeIndex(D["date"]), OOS_START.tz_localize(None)))
    t = p3.simulate(D, spec, "next_open", i0, len(D))
    s = stats(t["ret"].values)
    if len(t):
        s["ev_pts"] = float(t["pnl"].mean()); s["total_pts"] = float(t["pnl"].sum())
        s["pf_pts"] = float(t.loc[t.pnl > 0, "pnl"].sum() / -t.loc[t.pnl < 0, "pnl"].sum())
    return s, t.assign(date=D["date"].values[t["sig"].values]) if len(t) else t


def plot(all_pooled, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = list(all_pooled)
    fig, axes = plt.subplots(len(names), 1, figsize=(10, 3.0 * len(names)), sharex=True)
    axes = np.atleast_1d(axes)
    cols = {"QQQ": "#1f5fa8", "IWM": "#c2571a", "DIA": "#2a7d4f", "EFA": "#6b3fa0", "EWG": "#b8860b",
            "EWJ": "#c0392b", "EWU": "#5d6d7e"}
    for ax, nm in zip(axes, names):
        P = all_pooled[nm]
        for sym, g in P.groupby("sym"):
            g = g.sort_values("date")
            ax.plot(pd.to_datetime(g["date"]), (g["ret"].cumsum() * 100).values, lw=1.3, color=cols.get(sym), label=sym)
        ax.axhline(0, color="#555", lw=0.8); ax.grid(alpha=0.25)
        ax.set_title(f"{nm}: cumulative return per trade, % (untouched markets)", fontsize=10)
        ax.set_ylabel("sum of trade %")
    axes[0].legend(ncol=7, fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def main():
    check_lock()
    cands = json.loads((OUT / "frozen_candidates.json").read_text())
    log = pd.read_csv(OUT / "log.csv")
    trial_var = float(log.loc[log["n"] >= 60, "sharpe_trade"].var())
    rng = np.random.default_rng(11)
    res, pooled_by = {"n_trials_p3": int(len(log)), "trial_var_trade": trial_var, "systems": []}, {}
    for c in cands:
        main_out, P = run_system(c["spec"], "close", rng)
        rob_out, _ = run_system(c["spec"], "next_open", rng)
        es_s, es_t = es_window(c["spec"])
        r = P["ret"].values if len(P) else np.array([])
        dsr = deflated_sharpe(float(r.mean() / r.std(ddof=1)), len(r), float(pd.Series(r).skew()),
                              float(pd.Series(r).kurt() + 3), trial_var, len(log)) if len(r) > 2 else None
        pm = main_out["pooled"]
        confirmed = bool(pm.get("n", 0) and pm["ev_pct"] > 0 and pm["ci95_pct"][0] > 0
                         and main_out["markets_positive"] >= 5 and pm["rand_pct"] >= 90)
        res["systems"].append({"name": c["name"], "spec": c["spec"], "test_close": main_out,
                               "test_next_open": rob_out, "es_2020_2026_third_look": es_s,
                               "dsr_pooled_test": dsr, "confirmed": confirmed})
        pooled_by[c["name"]] = P
        P.to_csv(OUT / f"test_trades_{c['name']}.csv", index=False)
        if len(es_t):
            es_t.to_csv(OUT / f"es2020_trades_{c['name']}.csv", index=False)
        print(c["name"], "CONFIRMED" if confirmed else "not confirmed", json.dumps(pm, default=str)[:300],
              "mkts+", main_out.get("markets_positive"), "| next-open", json.dumps(rob_out["pooled"], default=str)[:160],
              "| ES20-26", json.dumps(es_s, default=str)[:200], flush=True)
    plot(pooled_by, OUT / "test_equity.png")
    (OUT / "test_results.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
