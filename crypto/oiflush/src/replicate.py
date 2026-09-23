"""Independent replication of the client's OI Flush Signals v2 (crypto/oiflush/PREREG_OIFLUSH.md).

  python crypto/oiflush/src/replicate.py
Writes crypto/oiflush/reports/*.csv and prints the pass/fail table.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

OF = Path(__file__).resolve().parents[1]
CRYPTO = OF.parent
sys.path.insert(0, str(CRYPTO / "src"))
sys.path.insert(0, str(CRYPTO / "perp" / "src"))
sys.path.insert(0, str(CRYPTO / "flow" / "src"))
import events as ev  # noqa: E402
import indicators as ind  # noqa: E402
import perp_research as pr  # noqa: E402
import flow_research as fr  # noqa: E402

OUT = OF / "reports"
K9 = ["BTC", "ETH", "SOL", "XRP", "ADA", "LINK", "DOGE", "LTC", "AVAX"]
X7 = ["BNB", "DOT", "TRX", "BCH", "SUI", "NEAR", "APT"]
P1 = (pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2023-12-31 23:59:59", tz="UTC"))
P2 = (pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2026-09-22 23:59:59", tz="UTC"))
FULL = (P1[0], P2[1])
PERIODS = {"2022-23": P1, "2024-26": P2, "full": FULL}


def usd_features(c):
    d = fr.load(c)
    ret24 = d["close"] / d["close"].shift(24) - 1
    oi24 = d["oi"] / d["oi"].shift(24) - 1
    return d, ret24, oi24


def tier(oi24):
    return np.where(oi24 <= -0.06, 2.0, np.where(oi24 <= -0.032, 1.5, 1.0))


def usd_trades(coins, window, pr_th=-0.046, oi_th=-0.018, H=24, delay=0, rt_cost=None):
    trs, unc = [], {}
    for c in coins:
        d, r24, o24 = usd_features(c)
        sig = (r24 <= pr_th) & (o24 <= oi_th)
        cost = pr.perp_cost(c) if rt_cost is None else rt_cost / 2
        tr = pr.trades(d, sig, H, "long", window, cost, fr.funding(c), delay, c)
        if len(tr):
            tr["oi24"] = o24.reindex(tr.signal_time).to_numpy()
            tr["tier"] = tier(tr["oi24"].to_numpy())
            trs.append(tr)
        unc[c], _ = ev.unconditional(d, H, "long", window, delay)
    tr = pd.concat(trs, ignore_index=True) if trs else pd.DataFrame()
    return tr, unc


def stats(tr, unc, window):
    if not len(tr):
        return {"n": 0}
    weeks = (window[1] - window[0]).days / 7
    et = pd.to_datetime(tr.entry_time, utc=True)
    wk = tr.groupby(et.dt.tz_localize(None).dt.to_period("W")).net.sum()
    allw = pd.period_range(window[0].tz_localize(None), window[1].tz_localize(None), freq="W")
    wk = wk.reindex(allw, fill_value=0.0)
    return {"n": len(tr), "per_week": len(tr) / weeks, "gross_%": 100 * tr.gross.mean(), "net_%": 100 * tr.net.mean(),
            "win": (tr.net > 0).mean(), "t_day": ev.clustered_t(tr), "t_week": wk.mean() / (wk.std() / np.sqrt(len(wk))),
            "excess_%": 100 * (tr.gross - tr.sym.map(unc)).mean(), "funding_%": 100 * tr.funding.mean(),
            "top5_days_share": tr.groupby(et.dt.floor("D")).net.sum().nlargest(5).sum() / tr.net.sum() if tr.net.sum() > 0 else np.nan}


def portfolio(tr, window, K=5, tiers=False):
    """At most K open positions, 1/K of equity each (x tier if tiers), deepest OI first when the cap binds."""
    if not len(tr):
        return {}
    t = tr.sort_values(["entry_time", "oi24"]).reset_index(drop=True)
    open_exits, rows = [], []
    for et, grp in t.groupby("entry_time", sort=True):
        open_exits = [x for x in open_exits if x > et]
        free = K - len(open_exits)
        for _, r in grp.sort_values("oi24").iterrows():
            if free <= 0:
                break
            w = (r.tier if tiers else 1.0) / K
            rows.append((r.exit_time, w * r.net))
            open_exits.append(r.exit_time)
            free -= 1
    p = pd.DataFrame(rows, columns=["exit", "pnl"])
    days = pd.date_range(window[0].normalize(), window[1].normalize(), freq="D", tz="UTC")
    daily = p.groupby(pd.to_datetime(p.exit, utc=True).dt.floor("D")).pnl.sum().reindex(days, fill_value=0.0)
    eq = (1 + daily).cumprod()
    yrs = len(daily) / 365
    return {"taken": len(p), "of": len(tr), "cagr": eq.iloc[-1] ** (1 / yrs) - 1,
            "sharpe": daily.mean() / daily.std() * np.sqrt(365), "maxdd": (eq / eq.cummax() - 1).min()}


# ------------------------------------------------------------------ Alt/BTC mode (30m synthetic ALT/BTC)
def bars30(c):
    k = pd.read_parquet(fr.BV / f"{c}_klines_15m.parquet")
    b = k.resample("30min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    m = pd.read_parquet(fr.BV / f"{c}_metrics_15m.parquet")["sum_open_interest"].resample("30min").last()
    return b.join(m.rename("oi"))


def rel_trades(coins, window, delay=0, H=48, rt_mult=1.0):
    btc = bars30("BTC")
    fb = fr.funding("BTC")
    rows = []
    for c in coins:
        a = bars30(c)
        j = a.index.intersection(btc.index)
        a, b = a.loc[j], btc.loc[j]
        ratio = a["close"] / b["close"]
        d = [ratio / ind.ema(ratio, n) - 1 for n in (50, 100, 200)]
        oi24 = a["oi"] / a["oi"].shift(48) - 1
        sig = ((d[0] <= -0.03) & (d[1] <= -0.04) & (d[2] <= -0.05) & (oi24 <= -0.031)).to_numpy()
        fa = fr.funding(c)
        ao, bo, idx = a["open"].to_numpy(), b["open"].to_numpy(), a.index
        cost = 2 * (pr.perp_cost(c) + pr.perp_cost("BTC")) * rt_mult
        free = 0
        for t in np.flatnonzero(sig):
            if idx[t] < window[0] or idx[t] > window[1]:
                continue
            e, x = t + 1 + delay, t + 1 + delay + H
            if e < free or x >= len(idx) or idx[x] > window[1]:
                continue
            te, tx = idx[e], idx[x]
            f_alt = fa[(fa.index > te) & (fa.index <= tx)].sum()
            f_btc = fb[(fb.index > te) & (fb.index <= tx)].sum()
            gross = (ao[x] / ao[e] - 1) - (bo[x] / bo[e] - 1)
            net = gross - cost - f_alt + f_btc
            rows.append((c, idx[t], te, tx, H, gross, net, 0.0, f_alt - f_btc, float(oi24.iloc[t])))
            free = x
    tr = pd.DataFrame(rows, columns=["sym", "signal_time", "entry_time", "exit_time", "bars", "gross", "net", "adverse", "funding", "oi24"])
    tr["tier"] = np.where(tr["oi24"] <= -0.084, 2.0, 1.0)
    return tr


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    rows = []
    for label, coins in (("K9", K9), ("X7", X7), ("all16", K9 + X7)):
        for pn, w in PERIODS.items():
            tr, unc = usd_trades(coins, w)
            s = stats(tr, unc, w)
            trd, uncd = usd_trades(coins, w, delay=1)
            tr20, _ = usd_trades(coins, w, rt_cost=0.0020)
            tr30, _ = usd_trades(coins, w, rt_cost=0.0030)
            s.update({"late1h_net_%": 100 * trd.net.mean() if len(trd) else np.nan,
                      "rt20bp_net_%": 100 * tr20.net.mean() if len(tr20) else np.nan,
                      "rt30bp_net_%": 100 * tr30.net.mean() if len(tr30) else np.nan})
            for tiers in (False, True):
                pf = portfolio(tr, w, tiers=tiers)
                s.update({f"pf{'_tier' if tiers else ''}_{k}": v for k, v in pf.items()})
            rows.append({"set": label, "period": pn, **s})
            res[(label, pn)] = (tr, s)
            if label == "K9" and pn != "full":
                t = tr.groupby("tier").net.agg(["count", "mean"])
                print(f"tiers {pn}:", {k: (int(v["count"]), round(100 * v["mean"], 2)) for k, v in t.iterrows()})
                per_coin = tr.groupby("sym").agg(n=("net", "size"), gross=("gross", "mean"), net=("net", "mean"))
                per_coin.to_csv(OUT / f"usd_per_coin_{pn}.csv")
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "usd_summary.csv", index=False)

    # neighbourhood, K9
    nb = []
    for pth in (-0.03, -0.04, -0.046, -0.05, -0.06, -0.07):
        for oth in (-0.01, -0.018, -0.025, -0.035):
            for H in (12, 24, 48):
                for pn in ("2022-23", "2024-26"):
                    tr, _ = usd_trades(K9, PERIODS[pn], pth, oth, H)
                    nb.append({"price24": pth, "oi24": oth, "H": H, "period": pn, "n": len(tr),
                               "net_%": 100 * tr.net.mean() if len(tr) else np.nan})
    nb = pd.DataFrame(nb)
    nb.to_csv(OUT / "usd_neighbourhood.csv", index=False)

    # alt/BTC mode
    rel = []
    alts = [c for c in K9 + X7 if c != "BTC"]
    for pn, w in PERIODS.items():
        tr = rel_trades(alts, w)
        trd = rel_trades(alts, w, delay=1)
        et = pd.to_datetime(tr.entry_time, utc=True) if len(tr) else None
        s = {"period": pn, "n": len(tr), "per_week": len(tr) / ((w[1] - w[0]).days / 7),
             "gross_%": 100 * tr.gross.mean() if len(tr) else np.nan, "net_%": 100 * tr.net.mean() if len(tr) else np.nan,
             "win": (tr.net > 0).mean() if len(tr) else np.nan, "t_day": ev.clustered_t(tr) if len(tr) > 2 else np.nan,
             "late30m_net_%": 100 * trd.net.mean() if len(trd) else np.nan}
        if len(tr):
            s["tier2x_net_%"] = 100 * tr.loc[tr.tier == 2, "net"].mean()
            s["tier1x_net_%"] = 100 * tr.loc[tr.tier == 1, "net"].mean()
        rel.append(s)
    rel = pd.DataFrame(rel)
    rel.to_csv(OUT / "rel_summary.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(tab.round(3).to_string())
    print(nb.groupby("period")["net_%"].describe().round(3).to_string())
    print(rel.round(3).to_string())

    k = {pn: res[("K9", pn)][1] for pn in PERIODS}
    nbm = nb.groupby("period")["net_%"].median()
    checks = {
        "O1 net>0 both periods": bool(k["2022-23"]["net_%"] > 0 and k["2024-26"]["net_%"] > 0),
        "O2 weekly t>=2 full": bool(k["full"]["t_week"] >= 2.0),
        "O3 excess>0 both": bool(k["2022-23"]["excess_%"] > 0 and k["2024-26"]["excess_%"] > 0),
        "O4 1h late net>0 both": bool(k["2022-23"]["late1h_net_%"] > 0 and k["2024-26"]["late1h_net_%"] > 0),
        "O5 neighbourhood median>0 both": bool(nbm["2022-23"] > 0 and nbm["2024-26"] > 0),
        "O6 X7 full net>0": bool(res[("X7", "full")][1]["net_%"] > 0),
        "O7 20bp RT net>0 both": bool(k["2022-23"]["rt20bp_net_%"] > 0 and k["2024-26"]["rt20bp_net_%"] > 0),
        "O8 capped pf Sharpe>=1, DD>-25%": bool(k["full"]["pf_sharpe"] >= 1.0 and k["full"]["pf_maxdd"] > -0.25),
    }
    checks["PASS"] = all(checks.values())
    (OUT / "verdict.json").write_text(json.dumps(checks, indent=2))
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
