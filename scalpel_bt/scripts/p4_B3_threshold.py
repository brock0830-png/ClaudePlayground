"""
B3 (PROTOCOL_P4.md): P3B score threshold 0.86..0.94 (step 0.01) on DEVELOPMENT data only:
SPY 1994-01-03..2012-12-31 (market-on-close) + ES 2013-2019 (next open), pooled. Excess over random entries
(1,000 draws per dataset). 0.90 is on a plateau if every threshold 0.88..0.92 has pooled excess > 0 with
month-clustered CI lower bound > 0, and the excess at 0.89 and 0.91 is each >= 50% of the excess at 0.90.
Also: dev-window agreement of SPX vs SPY score signals at 0.90.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from scalpel import p4

TAG = "B3_threshold"
TH = [round(0.86 + 0.01 * k, 2) for k in range(9)]


def main():
    p4.check_lock()
    out = p4.OUT / TAG
    if (out / "results.json").exists():
        raise SystemExit("B3 already ran once")
    out.mkdir(parents=True, exist_ok=True)
    spy = p4.load_etf("SPY")
    s0, s1 = p4.window(spy, "1994-01-03", "2012-12-31")
    es = p4.load_es("dev")
    raw = p4.es_raw_prices("dev")
    rng = np.random.default_rng(431)
    rows, res = [], {}
    for th in TH:
        spec = {"entry": [f"os_score>{th}"], "hold": 5}
        a = p4.trades(spy, spec, "close", s0, s1)
        a, _ = p4.add_excess(spy, a, "close", s0, s1, rng)
        b = p4.trades(es, spec, "next_open", 0, len(es))
        b = p4.with_raw_denominator(b, raw)
        draws = p4.random_entries(es, b, "next_open", 0, len(es), rng)
        # ES random draws are in % of the roll-adjusted price; rescale by the dataset's mean raw/adjusted ratio
        ratio = float((b["px_in"] / b["px_raw"]).mean()) if len(b) else 1.0
        b = b.assign(bench=float(np.nanmean(draws)) * ratio)
        b["excess"] = b["ret"] - b["bench"]
        P = pd.concat([a, b], ignore_index=True)
        m, lo, hi = p4.month_ci(P["excess"], P["date"])
        r = dict(threshold=th, n=len(P), n_spy=len(a), n_es=len(b), mean_pct=float(P["ret"].mean() * 100),
                 excess_pct=m * 100, ci_lo_pct=lo * 100, ci_hi_pct=hi * 100,
                 t=float(P["excess"].mean() / P["excess"].std(ddof=1) * np.sqrt(len(P))))
        res[str(th)] = r
        rows.append(dict(test="B3", variant=f"os_score>{th}", system="P3B", universe="dev SPY94-12+ES13-19",
                         mode="close/next_open", cost_case="base", n=r["n"], mean_ret_pct=r["mean_pct"],
                         excess_pct=r["excess_pct"], ci_lo_pct=r["ci_lo_pct"], ci_hi_pct=r["ci_hi_pct"],
                         verdict="sensitivity"))
    e = {k: res[k]["excess_pct"] for k in res}
    core = [str(x) for x in (0.88, 0.89, 0.9, 0.91, 0.92)]
    plateau = bool(all(res[k]["excess_pct"] > 0 and res[k]["ci_lo_pct"] > 0 for k in core)
                   and e["0.89"] >= 0.5 * e["0.9"] and e["0.91"] >= 0.5 * e["0.9"])
    spx = p4.load_gspc()
    x0, x1 = p4.window(spx, "1994-01-03", "2012-12-31")
    sa = set(pd.DatetimeIndex(spy["date"].values[s0:s1])[spy["os_score"].values[s0:s1] > 0.9])
    sb = set(pd.DatetimeIndex(spx["date"].values[x0:x1])[spx["os_score"].values[x0:x1] > 0.9])
    res["spx_vs_spy_score_days_dev"] = dict(spy=len(sa), spx=len(sb), both=len(sa & sb),
                                            jaccard=len(sa & sb) / len(sa | sb))
    res["PLATEAU"] = plateau
    (out / "results.json").write_text(json.dumps(res, indent=1))
    rows.append(dict(test="B3", variant="plateau check 0.88-0.92", system="P3B", universe="dev",
                     verdict="PASS" if plateau else "FAIL"))
    p4.log(rows)
    print(pd.DataFrame([res[str(t)] for t in TH]).round(3).to_string(index=False))
    print("plateau:", plateau, "| SPX vs SPY score>0.90 days (dev):", res["spx_vs_spy_score_days_dev"])


if __name__ == "__main__":
    main()
