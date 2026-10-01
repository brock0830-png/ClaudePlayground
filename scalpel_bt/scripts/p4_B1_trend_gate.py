"""
B1 (PROTOCOL_P4.md): P3B ungated vs P3B gated by ma50 > ma200 on the 15 fresh ETFs, market-on-close. ONE run.
Pass: pooled excess(gated) - pooled excess(ungated) > 0 with a paired month-clustered CI lower bound > 0.
Both arms use the same random-entry benchmark (all eligible days). Secondary: the gated arm against random
entries drawn only from uptrend days (is the gate more than trend drift?).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from scalpel import p4

TAG = "B1_trend_gate"
GATED = {"entry": list(p4.P3B["entry"]) + ["ma50>ma200"], "hold": p4.P3B["hold"]}


def uptrend_benchmark(P, seed=413):
    rng = np.random.default_rng(seed)
    parts = []
    for sym, g in P.groupby("sym"):
        D = p4.load_etf(sym)
        i0, i1 = p4.window(D)
        up = (D["ma50"] > D["ma200"]).values
        g, _ = p4.add_excess(D, g.drop(columns=["bench", "excess"]), "close", i0, i1, rng, eligible=up)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def main():
    p4.check_lock()
    out = p4.OUT / TAG
    if (out / "results.json").exists():
        raise SystemExit("B1 already ran once")
    out.mkdir(parents=True, exist_ok=True)
    U, per_u = p4.run_universe(p4.FRESH, p4.P3B, "close", seed=411)
    G, per_g = p4.run_universe(p4.FRESH, GATED, "close", seed=412)
    Su, Sg = p4.pooled_summary(U, per_u), p4.pooled_summary(G, per_g)
    Su_hv, Sg_hv = p4.pooled_summary(U, per_u, "excess_hv", "ret_hv"), p4.pooled_summary(G, per_g, "excess_hv", "ret_hv")
    diff = p4.paired_month_ci(G, U, "excess")
    diff_hv = p4.paired_month_ci(G, U, "excess_hv")
    Gu = uptrend_benchmark(G)
    up_m = p4.month_ci(Gu["excess"], Gu["date"])
    passed = bool(diff[0] > 0 and diff[1] > 0)
    d_u, d_g = p4.dsr(U["ret"].values), p4.dsr(G["ret"].values)
    res = {"test": TAG, "ungated": Su, "gated": Sg, "ungated_highvix": Su_hv, "gated_highvix": Sg_hv,
           "gated_minus_ungated_excess_pct": [x * 100 for x in diff],
           "gated_minus_ungated_excess_highvix_pct": [x * 100 for x in diff_hv],
           "gated_vs_uptrend_only_random_pct": [x * 100 for x in up_m],
           "per_market_ungated": per_u, "per_market_gated": per_g, "dsr_ungated": d_u, "dsr_gated": d_g,
           "PASS": passed, "highvix_flips_verdict": bool((diff_hv[0] > 0 and diff_hv[1] > 0) != passed)}
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    U.to_csv(out / "trades_ungated.csv", index=False)
    G.to_csv(out / "trades_gated.csv", index=False)
    rows = []
    for nm, S, d in (("P3B ungated", Su, d_u), ("P3B + ma50>ma200", Sg, d_g)):
        rows.append(dict(test="B1", variant=nm, system="P3B", universe="fresh15", mode="close", cost_case="base",
                         n=S["n"], markets=S["markets"], mean_ret_pct=S["mean_pct"], excess_pct=S["excess_pct"],
                         ci_lo_pct=S["ci_lo_pct"], ci_hi_pct=S["ci_hi_pct"], share_markets_pos=S["share_markets_pos"],
                         dsr=d.get("dsr"), n_trials=d.get("n_trials"),
                         verdict=("PASS" if passed else "FAIL") if "ma50" in nm else "arm",
                         note=f"gated-ungated excess {diff[0]*100:.3f}% [{diff[1]*100:.3f},{diff[2]*100:.3f}]"))
    p4.log(rows)
    print(json.dumps({k: res[k] for k in res if not k.startswith("per_market")}, indent=1, default=str))
    print(pd.DataFrame({"ungated": {k: v.get("excess_pct") for k, v in per_u.items()},
                        "gated": {k: v.get("excess_pct") for k, v in per_g.items()},
                        "n_u": {k: v.get("n") for k, v in per_u.items()},
                        "n_g": {k: v.get("n") for k, v in per_g.items()}}).round(3).to_string())


if __name__ == "__main__":
    main()
