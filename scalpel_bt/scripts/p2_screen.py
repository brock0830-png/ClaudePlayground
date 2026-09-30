"""
Phase 2 screen on DEV (ES 2013-2019) with the pre-DEV SPX 1990-2012 robustness check.
Grids below are fixed before running (PROTOCOL_P2.md section 4). Output: results/p2/log.csv.
Usage: python scripts/p2_screen.py
"""
import sys, json, itertools, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from scalpel.data import load_bars, RESULTS
from scalpel import p2

OUT = RESULTS / "p2"
N_RAND = 500
N_BOOT = 10000


# ------------------------------------------------------------------ grids (pre-registered)
def grids():
    V = []
    windows = {"ON_18_10": [18, 22, 2, 6], "ON_18_06": [18, 22, 2], "ON_18_02": [18, 22], "ON_22_10": [22, 2, 6],
               "ON_02_10": [2, 6], "B18": [18], "B22": [22], "B02": [2], "B06": [6], "B10": [10], "B14": [14],
               "DAY_10_17": [10, 14]}
    f1_filters = [[], ["close>ma50"], ["close>ma200"], ["close<ma50"], ["vix<20"], ["vix<vix_mean252"],
                  ["vts<1.0"], ["close<open"], ["close>open"]]
    for (wn, hrs), flt, side in itertools.product(windows.items(), f1_filters, ["long", "short"]):
        V.append(dict(family="F1_session", name=wn, kind="session", hours=hrs, filters=flt, side=side))
    mr_long = [["rsi2<5"], ["rsi2<10"], ["rsi2<20"], ["close<minc5"], ["close<minc10"], ["dnstreak>=3"],
               ["dnstreak>=4"], ["ibs<0.2"], ["ibs<0.3"]]
    for ent, ex, flt in itertools.product(mr_long, ["close>ma5", "rsi2>70", "hold1", "hold3", "hold5"],
                                          [[], ["close>ma200"], ["close>ma50"], ["vix>20"], ["vix>vix_mean252"]]):
        V.append(dict(family="F2_meanrev", kind="entry_exit", entry=ent, exit=ex, filters=flt, side="long", max_hold=10))
    mr_short = [["rsi2>95"], ["rsi2>90"], ["rsi2>80"], ["close>maxc5"], ["close>maxc10"], ["upstreak>=3"],
                ["upstreak>=4"], ["ibs>0.8"], ["ibs>0.7"]]
    for ent, ex, flt in itertools.product(mr_short, ["close<ma5", "rsi2<30", "hold1", "hold3", "hold5"],
                                          [[], ["close<ma200"], ["close<ma50"]]):
        V.append(dict(family="F2_meanrev", kind="entry_exit", entry=ent, exit=ex, filters=flt, side="short", max_hold=10))
    for on, ls in itertools.product([["close>ma20"], ["close>ma50"], ["close>ma100"], ["close>ma200"], ["mom63>zero"],
                                     ["mom126>zero"], ["mom252>zero"], ["ma20>ma50"], ["ma50>ma200"]], [False, True]):
        V.append(dict(family="F3_trend", kind="regime", on=on, longshort=ls, side="long"))
    for ent, ex, side in [(["close>maxc20"], "close<minc10", "long"), (["close>maxc55"], "close<minc20", "long"),
                          (["close<minc20"], "close>maxc10", "short"), (["close<minc55"], "close>maxc20", "short")]:
        V.append(dict(family="F3_trend", kind="entry_exit", entry=ent, exit=ex, filters=[], side=side, max_hold=100000))
    for on in [["vts<0.9"], ["vts<0.95"], ["vts<1.0"], ["vix<15"], ["vix<20"], ["vix<25"], ["vix<vix_ma10"],
               ["vix<vix_ma20"], ["vix<vix_mean252"]]:
        V.append(dict(family="F4_vol", kind="regime", on=on, longshort=False, side="long"))
    for on in [["vts<1.0"], ["vix<vix_ma10"]]:
        V.append(dict(family="F4_vol", kind="regime", on=on, longshort=True, side="long"))
    for x, h in itertools.product(["1.1", "1.2", "1.3"], ["hold3", "hold5", "hold10"]):
        V.append(dict(family="F4_vol", kind="entry_exit", entry=[f"vix_x_ma10>{x}"], exit=h, filters=[], side="long"))
    for x, h in itertools.product(["90", "95"], ["hold3", "hold5"]):
        V.append(dict(family="F4_vol", kind="entry_exit", entry=[f"vix_rsi2>{x}"], exit=h, filters=[], side="long"))
    for k, j in itertools.product([1, 2, 3], [1, 2, 3, 4]):
        V.append(dict(family="F5_calendar", kind="calendar", cal=["tom", k, j], side="long"))
    V.append(dict(family="F5_calendar", kind="calendar", cal=["preholiday"], side="long"))
    for w in range(5):
        V.append(dict(family="F5_calendar", kind="calendar", cal=["weekday", w], side="long"))
    return V


# ------------------------------------------------------------------ evaluation
def block_boot(weekly: np.ndarray, rng, n=N_BOOT):
    idx = rng.integers(0, len(weekly), size=(n, len(weekly)))
    m = weekly[idx].mean(axis=1)
    return float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))


def eval_es(ctx, tgt, i0, i1, rng, years):
    res = p2.run_bars(ctx, tgt, i0, i1)
    tr = res["trades"]
    o = ctx["o"][i0:i1]
    oo = np.r_[o[1:], ctx["c"][i1 - 1]] - o                      # open-to-open move while hold[t] is on
    hold = res["hold"]
    cost = p2.SIDE_COST * np.abs(hold - np.r_[0.0, hold[:-1]])
    sw = ctx["sw"][i0:i1]
    cost += p2.ROLL_COST * np.abs(hold) * (sw & (np.r_[0.0, hold[:-1]] == hold) & (hold != 0))
    cost[-1] += p2.SIDE_COST * abs(hold[-1])
    mu = oo.mean()
    y = hold * oo - cost                                          # net per bar
    x = hold * (oo - mu) - cost                                   # timing excess per bar
    wk = ctx["week"][i0:i1]
    W = pd.DataFrame({"w": wk, "y": y, "x": x}).groupby("w").sum()
    out = {"n": len(tr)}
    if len(tr) == 0:
        return out
    net = tr["net"].values
    out.update(ev=float(net.mean()), total=float(y.sum()), win=float((net > 0).mean()),
               pf=float(net[net > 0].sum() / -net[net < 0].sum()) if (net < 0).any() else np.inf,
               bars_in=int((hold != 0).sum()), sessions_in=int(pd.Series(ctx["tday"][i0:i1][hold != 0]).nunique()),
               avg_bars=float(tr["bars"].mean()))
    out["ci_lo"], out["ci_hi"] = block_boot(W["y"].values, rng)
    out["excess"] = float(x.sum())
    out["excess_t"] = float(W["x"].mean() / W["x"].std(ddof=1) * np.sqrt(len(W))) if W["x"].std() > 0 else 0.0
    out["ex_ci_lo"], _ = block_boot(W["x"].values, rng)
    yr = ctx["year"][i0:i1]
    Y = pd.DataFrame({"yr": yr, "y": y, "x": x}).groupby("yr").sum()
    for yy in years:
        out[f"pnl_{yy}"] = float(Y["y"].get(yy, 0.0))
    ys = np.array([out[f"pnl_{yy}"] for yy in years])
    out["pos_years"] = int((ys > 0).sum())
    out["ex_best"] = float(ys.sum() - ys.max())
    out["half1_excess"] = float(Y["x"][[yy for yy in Y.index if yy <= 2016]].sum())
    out["half2_excess"] = float(Y["x"][[yy for yy in Y.index if yy >= 2017]].sum())
    # random exposure: same count, durations, directions; random starts
    O = np.r_[ctx["o"][i0:i1], ctx["c"][i1 - 1]]
    csw = np.r_[0, np.cumsum(sw)]
    L = tr["bars"].values
    d = tr["dir"].values
    starts = (rng.random((N_RAND, len(L))) * (i1 - i0 - L)[None, :]).astype(int)
    ends = starts + L[None, :]
    rolls = csw[np.minimum(ends, len(sw))] - csw[starts + 1]
    pn = d[None, :] * (O[ends] - O[starts]) - 2 * p2.SIDE_COST - p2.ROLL_COST * np.maximum(rolls, 0)
    rev = pn.mean(axis=1)
    out["rand_mean"] = float(rev.mean())
    out["rand_pct"] = float((rev < out["ev"]).mean() * 100)
    out["sharpe_ann"] = float(pd.Series(y).groupby(ctx["tday"][i0:i1]).sum().pipe(lambda s: s.mean() / s.std() * np.sqrt(252)))
    return out


def eval_spx(S, tgt, i0, i1):
    res = p2.run_daily_close(S, tgt, i0, i1)
    tr = res["trades"]
    if len(tr) == 0:
        return {"spx_n": 0}
    mu = res["r"][:-1].mean()
    cost = p2.SPX_RT_COST / 2 * np.abs(res["hold"] - np.r_[0.0, res["hold"][:-1]])
    x = res["hold"] * (res["r"] - mu) - cost
    return {"spx_n": len(tr), "spx_ev_pct": float(tr["net"].mean() * 100),
            "spx_excess_pct": float(x.sum() * 100), "spx_total_pct": float(res["pnl"].sum() * 100)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bars = load_bars("dev")
    ctx = p2.es_context(bars)
    i0, i1 = 0, len(bars)
    S = p2.spx_context()
    s0 = int(np.searchsorted(pd.DatetimeIndex(S["date"]), pd.Timestamp("1990-01-02")))
    rng = np.random.default_rng(20260930)
    years = list(range(2013, 2020))
    rows = []
    t0 = time.time()
    for k, spec in enumerate(grids()):
        if spec["kind"] == "session":
            tgt = p2.session_target(ctx, spec)
            spx = None
        else:
            td = p2.daily_target(ctx["D"], spec)
            tgt = None if td is None else p2.bar_target_from_daily(ctx, td)
            ts = p2.daily_target(S, spec)
            spx = None if ts is None else eval_spx(S, ts, s0, len(S))
        row = {"variant_id": k + 1, "family": spec["family"], "side": spec["side"],
               "spec": json.dumps(spec), "robust_mode": "spx" if spx is not None else "halves"}
        if tgt is not None:
            row.update(eval_es(ctx, tgt, i0, i1, rng, years))
        if spx is not None:
            row.update(spx)
        rows.append(row)
        if (k + 1) % 100 == 0:
            print(k + 1, round(time.time() - t0), "s", flush=True)
    log = pd.DataFrame(rows)
    log.to_csv(OUT / "log.csv", index=False)
    print("done", len(log))


if __name__ == "__main__":
    main()
