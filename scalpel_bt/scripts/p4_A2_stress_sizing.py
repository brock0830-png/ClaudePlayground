"""
A2 (PROTOCOL_P4.md): crash stress and sizing. P2A, P3B and P2A+P3B (1 unit each) on ES (points, MES costs)
and on SPY (% of position), 2013-01 to the end of data. Daily mark-to-market P&L, block bootstrap by calendar
month (10,000 paths of the historical length). Max drawdown and longest losing streak at the 50/95/99th pct.
Writes results/p4/sizing_table.md.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from scalpel import p3, p4

TAG = "A2_stress_sizing"
MES_RT, MES_ROLL, MES_USD = 0.84, 0.84, 5.0
TOLS = [0.15, 0.20, 0.25]
ACCOUNTS = [25_000, 50_000, 100_000, 250_000]
N_PATHS = 10_000
START = "2013-01-01"


def mes_costs(t):
    """Swap ES costs (0.60 + 0.60/roll) for MES costs (0.84 + 0.84/roll), in points."""
    es_cost = (t["px_out"] - t["px_in"]) - t["pnl"]
    rolls = np.round((es_cost - p3.ES_RT_PTS) / p3.ES_ROLL_PTS).clip(lower=0)
    pnl = (t["px_out"] - t["px_in"]) - (MES_RT + MES_ROLL * rolls)
    return t.assign(pnl=pnl, ret=pnl / t["px_in"])


def system_series(D, spec, mode, unit, i0, i1, mes=False):
    t = p4.trades(D, spec, mode, i0, i1)
    if mes:
        t = mes_costs(t)
    daily = p4.daily_mtm(D, t, mode, unit)
    daily = daily[daily.index >= pd.Timestamp(START)]
    x = t["pnl"] if unit == "pts" else t["pnl"] / t["px_in"]
    tr = pd.DataFrame({"exit": pd.DatetimeIndex(D["date"].values[t["exit"].values]), "pnl": x.values})
    return daily, tr


def longest_streak(x):
    best = cur = 0
    for v in x:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    return best


def bootstrap(daily: pd.Series, tr: pd.DataFrame, seed):
    rng = np.random.default_rng(seed)
    months = daily.index.to_period("M")
    keys = months.unique()
    blocks = [daily.values[months == k] for k in keys]
    tmon = tr["exit"].dt.to_period("M")
    tblocks = [tr["pnl"].values[tmon == k] for k in keys]
    dd, st = np.empty(N_PATHS), np.empty(N_PATHS)
    for p in range(N_PATHS):
        idx = rng.integers(0, len(keys), len(keys))
        eq = np.cumsum(np.concatenate([blocks[i] for i in idx]))
        dd[p] = -(eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]).min()
        st[p] = longest_streak(np.concatenate([tblocks[i] for i in idx]))
    eq = daily.cumsum().values
    hist_dd = -(eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]).min()
    worst_month = daily.groupby(months).sum().min()
    q = lambda a: {f"p{k}": float(np.percentile(a, k)) for k in (50, 95, 99)}
    return {"max_dd": q(dd), "losing_streak": q(st), "historical_max_dd": float(hist_dd),
            "historical_streak": int(longest_streak(tr.sort_values("exit")["pnl"].values)),
            "worst_month": float(worst_month), "trades": int(len(tr)), "months": int(len(keys)),
            "total": float(daily.sum())}


def main():
    p4.check_lock()
    out = p4.OUT / TAG
    if (out / "results.json").exists():
        raise SystemExit("A2 already ran once")
    out.mkdir(parents=True, exist_ok=True)
    es = p4.load_es("all")
    spy = p4.load_etf("SPY")
    e0, e1 = 0, len(es)
    s0, s1 = p4.window(spy, START)
    res = {}
    series = {}
    for name, spec in (("P2A", p4.P2A), ("P3B", p4.P3B)):
        series[("ES", name)] = system_series(es, spec, "next_open", "pts", e0, e1, mes=True)
        series[("SPY", name)] = system_series(spy, spec, "close", "pct", s0, s1)
    for mkt in ("ES", "SPY"):
        a, b = series[(mkt, "P2A")], series[(mkt, "P3B")]
        daily = a[0].add(b[0], fill_value=0.0)
        series[(mkt, "P2A+P3B")] = (daily, pd.concat([a[1], b[1]], ignore_index=True))
    for k, (daily, tr) in series.items():
        res[f"{k[0]} {k[1]}"] = bootstrap(daily, tr, seed=421 + len(res))
    (out / "results.json").write_text(json.dumps(res, indent=1))
    p4.log([dict(test="A2", variant=k, system=k.split()[1], universe=k.split()[0], mode="mtm", cost_case="base",
                 n=v["trades"], verdict="descriptive",
                 note=f"maxDD p50/p95/p99 {v['max_dd']['p50']:.4g}/{v['max_dd']['p95']:.4g}/{v['max_dd']['p99']:.4g}; "
                      f"streak p99 {v['losing_streak']['p99']:.0f}") for k, v in res.items()])
    write_table(res, out)
    print(json.dumps(res, indent=1))


def write_table(res, out):
    L = ["# A2 sizing table (99th-percentile drawdown, block bootstrap by calendar month, 10,000 paths)", "",
         "Daily mark-to-market drawdown, fixed size (no compounding), 2013-01 to 2026-09. ES figures are points per",
         "contract with MES costs (0.84 pt per round trip and per roll); 1 MES = $5 per point. SPY figures are",
         "% of the position. P2A+P3B = one unit of each, held independently (up to 2 units at once).", "",
         "## Drawdown and losing streaks", "",
         "| System | Trades | Hist. max DD | DD p50 | DD p95 | DD p99 | Worst month | Longest losing streak p50 / p95 / p99 (hist.) |",
         "|---|---|---|---|---|---|---|---|"]
    for k, v in res.items():
        f = (lambda x: f"{x:.0f} pt") if k.startswith("ES") else (lambda x: f"{x * 100:.1f}%")
        wm = f(-v["worst_month"]) if v["worst_month"] < 0 else "none"
        L.append(f"| {k} | {v['trades']} | {f(v['historical_max_dd'])} | {f(v['max_dd']['p50'])} | "
                 f"{f(v['max_dd']['p95'])} | {f(v['max_dd']['p99'])} | -{wm} | "
                 f"{v['losing_streak']['p50']:.0f} / {v['losing_streak']['p95']:.0f} / {v['losing_streak']['p99']:.0f} "
                 f"({v['historical_streak']}) |")
    L += ["", "## MES sizing (drawdown tolerance at the 99th percentile)", "",
          "| System | Tolerance | Account $ per MES | MES at $25k | $50k | $100k | $250k |", "|---|---|---|---|---|---|---|"]
    for k, v in res.items():
        if not k.startswith("ES"):
            continue
        dd = v["max_dd"]["p99"] * MES_USD
        for tol in TOLS:
            per = dd / tol
            L.append(f"| {k[3:]} | {tol:.0%} | ${per:,.0f} | " + " | ".join(str(int(a // per)) for a in ACCOUNTS) + " |")
    L += ["", "For P2A+P3B the count is MES per system (each system trades that many contracts).", "",
          "## SPY sizing (dollars of SPY per $1 of account)", "",
          "| System | 15% | 20% | 25% |", "|---|---|---|---|"]
    for k, v in res.items():
        if k.startswith("SPY"):
            dd = v["max_dd"]["p99"]
            L.append(f"| {k[4:]} | " + " | ".join(f"{tol / dd:.2f}" for tol in TOLS) + " |")
    L += ["", "A value above 1.00 means the tolerance allows more than 1x the account in SPY, which needs margin "
              "(see A5). Reg T caps overnight stock leverage at 2x.", ""]
    (p4.OUT / "sizing_table.md").write_text("\n".join(L))


if __name__ == "__main__":
    main()
