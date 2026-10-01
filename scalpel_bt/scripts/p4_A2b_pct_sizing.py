"""
A2 ADDENDUM (written after A2 ran; no rule or test changed). The pre-registered MES table sizes from drawdowns
in ES POINTS over 2013-2026, when ES traded at 1,400-7,700. Point drawdowns from low-price years understate
today's risk, so this addendum repeats the bootstrap in % of notional (ES trades, MES costs) and converts the
99th-percentile drawdown to dollars at the ES price of the last session (2026-09-30).
Percent is measured against the RAW traded entry price (the engine's ES series is roll-adjusted forward, so
its prices sit up to ~730 pt below the traded price by 2026); the conversion uses the raw last close.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from scalpel import p4
sys.path.insert(0, str(Path(__file__).resolve().parent))
import p4_A2_stress_sizing as a2

TAG = "A2_stress_sizing"


def main():
    p4.check_lock()
    out = p4.OUT / TAG
    if (out / "results_pct.json").exists():
        raise SystemExit("A2 addendum already ran")
    es = p4.load_es("all")
    raw = p4.es_raw_prices("all")
    px = float(raw["raw_close"].iat[-1])
    s = {}
    for name, spec in (("P2A", p4.P2A), ("P3B", p4.P3B)):
        t = p4.with_raw_denominator(a2.mes_costs(p4.trades(es, spec, "next_open", 0, len(es))), raw)
        daily = p4.daily_mtm(es, t, "next_open", "pct", denom="px_raw")
        daily = daily[daily.index >= pd.Timestamp(a2.START)]
        tr = pd.DataFrame({"exit": pd.DatetimeIndex(es["date"].values[t["exit"].values]), "pnl": t["ret"].values})
        s[name] = (daily, tr)
    s["P2A+P3B"] = (s["P2A"][0].add(s["P3B"][0], fill_value=0.0), pd.concat([s["P2A"][1], s["P3B"][1]]))
    res = {"es_price": px, "date": str(es["date"].iat[-1].date())}
    for k, (daily, tr) in s.items():
        res[k] = a2.bootstrap(daily, tr, seed=431 + len(res))
    (out / "results_pct.json").write_text(json.dumps(res, indent=1))
    L = ["", "## ADDENDUM (after the run): MES sizing from % drawdowns at today's ES price", "",
         f"The pre-registered MES table above uses point drawdowns from 2013-2026, when ES was much lower. "
         f"Measured in % of notional and converted at ES {px:,.0f} (close of {res['date']}), 1 MES is "
         f"${px * a2.MES_USD:,.0f} of notional. Percent drawdowns use the raw traded entry price. "
         f"**Use this table, not the one above.**", "",
         "| System | DD p99 (% of notional) | Tolerance | Account $ per MES | MES at $25k | $50k | $100k | $250k |",
         "|---|---|---|---|---|---|---|---|"]
    for k in ("P2A", "P3B", "P2A+P3B"):
        dd = res[k]["max_dd"]["p99"]
        for tol in a2.TOLS:
            per = dd * px * a2.MES_USD / tol
            L.append(f"| {k} | {dd:.1%} | {tol:.0%} | ${per:,.0f} | " +
                     " | ".join(str(int(a // per)) for a in a2.ACCOUNTS) + " |")
    L += ["", "For P2A+P3B the count is MES per system.", ""]
    with open(p4.OUT / "sizing_table.md", "a") as fh:
        fh.write("\n".join(L))
    p4.log([dict(test="A2", variant=f"ES {k} pct addendum", system=k, universe="ES", mode="mtm", cost_case="base",
                 n=res[k]["trades"], verdict="descriptive",
                 note=f"maxDD pct p50/p95/p99 {res[k]['max_dd']['p50']:.3f}/{res[k]['max_dd']['p95']:.3f}/"
                      f"{res[k]['max_dd']['p99']:.3f}; supersedes the earlier pct addendum rows, which divided by "
                      f"the roll-adjusted ES price") for k in ("P2A", "P3B", "P2A+P3B")])
    print("\n".join(L))


if __name__ == "__main__":
    main()
