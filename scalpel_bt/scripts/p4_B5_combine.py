"""
B5 (PROTOCOL_P4.md): combine P3B with P2A, 1 unit each, independent positions.
  ES 2013-2026 (next open; points and % of the raw traded price) and SPY 1994-2026 (market-on-close, %).
Report: share of P3B entries made while a P2A trade is open or on the same day; correlation of daily
mark-to-market P&L on days both are in position and on all days; combined max drawdown and worst month vs P2A
alone. P3B earns a place only if (1) B1's ungated P3B fresh-set excess has CI lower bound > 0 and (2) on both
windows the combined return / max-drawdown ratio is >= P2A alone's.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from scalpel import p4

TAG = "B5_combine"


def held_mask(D, t, mode):
    m = np.zeros(len(D), bool)
    for r in t.itertuples():
        a, b = (int(r.entry), int(r.exit)) if mode == "next_open" else (int(r.entry) + 1, int(r.exit))
        m[a:b + 1] = True
    return m


def stats(daily):
    eq = daily.cumsum().values
    dd = -(eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]).min()
    wm = daily.groupby(daily.index.to_period("M")).sum().min()
    return dict(total=float(daily.sum()), max_dd=float(dd), ratio=float(daily.sum() / dd) if dd > 0 else np.inf,
                worst_month=float(wm))


def window_result(D, mode, unit, i0, i1, raw=None):
    a = p4.trades(D, p4.P2A, mode, i0, i1)
    b = p4.trades(D, p4.P3B, mode, i0, i1)
    denom = "px_in"
    if raw is not None:
        a, b, denom = p4.with_raw_denominator(a, raw), p4.with_raw_denominator(b, raw), "px_raw"
    da = p4.daily_mtm(D, a, mode, unit, denom)
    db = p4.daily_mtm(D, b, mode, unit, denom)
    start = pd.Timestamp(D["date"].iat[i0])
    da, db = da[da.index >= start], db[db.index >= start]
    ha, hb = held_mask(D, a, mode), held_mask(D, b, mode)
    ea = set(a["entry"].values)
    same_day = np.isin(b["entry"].values, list(ea))
    inside = ha[b["entry"].values]
    both = pd.Series(ha & hb, index=pd.DatetimeIndex(D["date"]))[da.index].values
    res = {"n_P2A": len(a), "n_P3B": len(b),
           "share_P3B_entries_during_P2A_or_same_day": float((same_day | inside).mean()),
           "share_days_both_in_position_of_P3B_days": float(both.sum() / max((db != 0).sum(), 1)),
           "corr_daily_pnl_both_in_position": float(np.corrcoef(da.values[both], db.values[both])[0, 1]) if both.sum() > 2 else None,
           "corr_daily_pnl_all_days": float(np.corrcoef(da.values, db.values)[0, 1]),
           "P2A": stats(da), "P3B": stats(db), "combined": stats(da + db)}
    lose_a = da < 0
    res["P3B_loss_on_P2A_loss_days_share"] = float(((db < 0) & lose_a).sum() / max((db < 0).sum(), 1))
    res["combined_ratio_ge_P2A"] = bool(res["combined"]["ratio"] >= res["P2A"]["ratio"])
    return res


def main():
    p4.check_lock()
    out = p4.OUT / TAG
    if (out / "results.json").exists():
        raise SystemExit("B5 already ran once")
    out.mkdir(parents=True, exist_ok=True)
    b1 = json.loads((p4.OUT / "B1_trend_gate" / "results.json").read_text())
    cond1 = bool(b1["ungated"]["ci_lo_pct"] > 0)
    es, raw = p4.load_es("all"), p4.es_raw_prices("all")
    spy = p4.load_etf("SPY")
    res = {"cond1_B1_ungated_ci_lo_pct": b1["ungated"]["ci_lo_pct"], "cond1": cond1,
           "cond1_highvix_ci_lo_pct": b1["ungated_highvix"]["ci_lo_pct"]}
    res["ES_points_2013_2026"] = window_result(es, "next_open", "pts", 0, len(es))
    res["ES_pct_2013_2026"] = window_result(es, "next_open", "pct", 0, len(es), raw=raw)
    s0, s1 = p4.window(spy, "1994-01-03")
    res["SPY_pct_1994_2026"] = window_result(spy, "close", "pct", s0, s1)
    cond2 = bool(res["ES_pct_2013_2026"]["combined_ratio_ge_P2A"] and res["SPY_pct_1994_2026"]["combined_ratio_ge_P2A"])
    res["cond2"] = cond2
    res["PASS"] = bool(cond1 and cond2)
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    p4.log([dict(test="B5", variant=f"P2A+P3B {k}", system="P2A+P3B", universe=k, mode="mtm", cost_case="base",
                 n=v["n_P2A"] + v["n_P3B"], verdict="PASS" if res["PASS"] else "FAIL",
                 note=f"ratio P2A {v['P2A']['ratio']:.2f} combined {v['combined']['ratio']:.2f}; corr(both) "
                      f"{v['corr_daily_pnl_both_in_position']}")
            for k, v in res.items() if isinstance(v, dict) and "P2A" in v])
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
