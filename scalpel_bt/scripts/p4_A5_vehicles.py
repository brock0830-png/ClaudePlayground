"""
A5 (PROTOCOL_P4.md): vehicle comparison, no options. The same P2A ES signals, 2013-2026.
  MES   : ES price return 18:00 -> 18:00 (raw traded entry price) minus MES costs (0.84 pt + 0.84/roll), plus
          3m T-bill interest on the capital for the calendar days held (capital stays in bills; margin is
          posted from it).
  SPY   : the same signal executed at the next 09:30 open, exit at the 09:30 open 5 sessions later
          (dividend-adjusted), minus 0.05%.
  SPY 2x: 2 x SPY return minus 2 x 0.05% minus borrowing on the second notional at 3m T-bill + 1.5%
          (sensitivity: + 5%), act/360.
Per $ of capital at 1x and 2x exposure; after-tax at 37% (SPY, short-term) and 26.8% (MES, Section 1256 60/40).
Decision rule: highest after-tax return per $ of capital at the exposure A2 allows; SPY shares for accounts
below the 1-MES threshold.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from scalpel import p4
from scalpel.data import ROOT

TAG = "A5_vehicles"
MES_RT, MES_ROLL = 0.84, 0.84
TAX_SPY, TAX_MES = 0.37, 0.6 * 0.20 + 0.4 * 0.37


def tbill():
    t = pd.read_parquet(ROOT.parent / "data" / "raw" / "fmp" / "TREASURY.parquet")
    return pd.Series(t["month3"].values / 100.0, index=pd.to_datetime(t["date"])).sort_index()


def main():
    p4.check_lock()
    out = p4.OUT / TAG
    if (out / "results.json").exists():
        raise SystemExit("A5 already ran once")
    out.mkdir(parents=True, exist_ok=True)
    es, raw, spy = p4.load_es("all"), p4.es_raw_prices("all"), p4.load_etf("SPY")
    t = p4.trades(es, p4.P2A, "next_open", 0, len(es))
    es_cost = (t["px_out"] - t["px_in"]) - t["pnl"]
    rolls = np.round((es_cost - 0.60) / 0.60).clip(lower=0)
    t["mes_pnl"] = (t["px_out"] - t["px_in"]) - (MES_RT + MES_ROLL * rolls)
    t["px_raw"] = raw["raw_open"].values[t["entry"].values]
    ed = pd.DatetimeIndex(es["date"])
    # calendar time held: 18:00 on the eve of session `entry` to 18:00 on the eve of session `exit`
    t["entry_dt"] = ed[t["entry"].values - 1]
    t["exit_dt"] = ed[t["exit"].values - 1]
    t["days"] = (t["exit_dt"] - t["entry_dt"]).dt.days.clip(lower=1)
    rf = tbill().reindex(pd.DatetimeIndex(t["entry_dt"]), method="ffill").values
    t["rf"] = rf
    t["mes_1x"] = t["mes_pnl"] / t["px_raw"] + rf * t["days"] / 360
    t["mes_2x"] = 2 * t["mes_pnl"] / t["px_raw"] + rf * t["days"] / 360
    sd = pd.DatetimeIndex(spy["date"])
    O = spy["open"].values
    spy_r, spy_days = [], []
    for e_dt, x_dt in zip(ed[t["entry"].values], ed[t["exit"].values]):
        i, j = sd.searchsorted(e_dt), sd.searchsorted(x_dt)
        if j >= len(sd):
            spy_r.append(np.nan); spy_days.append(np.nan); continue
        spy_r.append((O[j] - O[i] - 0.0005 * O[i]) / O[i])
        spy_days.append((sd[j] - sd[i]).days)
    t["spy_1x"] = spy_r
    t["spy_days"] = spy_days
    t["spy_2x"] = 2 * t["spy_1x"] + 0.0  # costs: 2 x 0.05% is inside 2 x spy_1x
    t["borrow_base"] = (t["rf"] + 0.015) * t["spy_days"] / 360
    t["borrow_retail"] = (t["rf"] + 0.05) * t["spy_days"] / 360
    t["spy_2x_base"] = t["spy_2x"] - t["borrow_base"]
    t["spy_2x_retail"] = t["spy_2x"] - t["borrow_retail"]
    t["date"] = es["date"].values[t["sig"].values]
    t = t.dropna(subset=["spy_1x"])
    t.to_csv(out / "trades.csv", index=False)
    res = {"trades": len(t), "period": [str(t["date"].min().date()), str(t["date"].max().date())],
           "mean_days_held": float(t["days"].mean()), "mean_tbill": float(t["rf"].mean())}
    cols = {"MES 1x": ("mes_1x", TAX_MES), "MES 2x": ("mes_2x", TAX_MES), "SPY 1x": ("spy_1x", TAX_SPY),
            "SPY 2x (T-bill+1.5%)": ("spy_2x_base", TAX_SPY), "SPY 2x (T-bill+5%)": ("spy_2x_retail", TAX_SPY)}
    rows = []
    for nm, (c, tax) in cols.items():
        m, lo, hi = p4.month_ci(t[c], t["date"])
        r = dict(vehicle=nm, mean_pct=m * 100, ci=[lo * 100, hi * 100], after_tax_pct=m * (1 - tax) * 100,
                 tax_rate=tax, total_pct=float(t[c].sum() * 100))
        if "2x" in nm and "SPY" in nm:
            r["financing_per_trade_pct"] = float(t["borrow_base" if "1.5" in nm else "borrow_retail"].mean() * 100)
        if nm.startswith("MES"):
            r["tbill_income_per_trade_pct"] = float((t["rf"] * t["days"] / 360).mean() * 100)
        rows.append(r)
    res["vehicles"] = rows
    res["mes_vs_spy_timing_note"] = ("MES enters 18:00 on the signal day; SPY enters at the next 09:30 open; "
                                    "A4 measures that timing gap on its own.")
    res["mes_notional_today"] = float(raw["raw_close"].iat[-1] * 5)
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    p4.log([dict(test="A5", variant=r["vehicle"], system="P2A", universe="ES signals", mode="vehicle",
                 cost_case="base", n=len(t), mean_ret_pct=r["mean_pct"], ci_lo_pct=r["ci"][0], ci_hi_pct=r["ci"][1],
                 verdict="descriptive", note=f"after-tax {r['after_tax_pct']:.3f}%") for r in rows])
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
