"""
A3 (PROTOCOL_P4.md): frozen P2A on the 15 fresh ETFs, market-on-close. ONE run.
Pass: pooled excess per trade over random entries > 0 with month-clustered CI lower bound > 0, and at least
9 of 15 markets with positive excess. Also: raw return, next-open, high-VIX slippage, per market, by decade, DSR.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from scalpel import p4

TAG = "A3_fresh_P2A"


def main():
    p4.check_lock()
    out = p4.OUT / TAG
    if (out / "results.json").exists():
        raise SystemExit("A3 already ran once; results are in results/p4/A3_fresh_P2A/")
    out.mkdir(parents=True, exist_ok=True)
    P, per = p4.run_universe(p4.FRESH, p4.P2A, "close", seed=401)
    S = p4.pooled_summary(P, per)
    S_hv = p4.pooled_summary(P, per, col="excess_hv", raw="ret_hv")
    N, per_no = p4.run_universe(p4.FRESH, p4.P2A, "next_open", seed=402, highvix=False)
    S_no = p4.pooled_summary(N, per_no)
    dec = (pd.DatetimeIndex(P["date"]).year // 10) * 10
    by_dec = {int(k): dict(p4.basic(g["ret"].values), excess_pct=float(g["excess"].mean() * 100))
              for k, g in P.groupby(dec)}
    d_raw, d_ex = p4.dsr(P["ret"].values), p4.dsr(P["excess"].values)
    passed = bool(S["excess_pct"] > 0 and S["ci_lo_pct"] > 0 and S["markets_pos"] >= 9)
    flips = bool((S_hv["excess_pct"] > 0 and S_hv["ci_lo_pct"] > 0 and S_hv["markets_pos"] >= 9) != passed)
    res = {"test": TAG, "pooled_close": S, "pooled_close_highvix": S_hv, "pooled_next_open": S_no,
           "per_market": per, "per_market_next_open": per_no, "by_decade": by_dec, "dsr_raw": d_raw,
           "dsr_excess": d_ex, "PASS": passed, "highvix_flips_verdict": flips}
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    P.to_csv(out / "trades_close.csv", index=False)
    N.to_csv(out / "trades_next_open.csv", index=False)
    base = dict(test="A3", system="P2A", universe="fresh15")
    p4.log([
        dict(base, variant="P2A frozen", mode="close", cost_case="base", n=S["n"], markets=S["markets"],
             mean_ret_pct=S["mean_pct"], excess_pct=S["excess_pct"], ci_lo_pct=S["ci_lo_pct"],
             ci_hi_pct=S["ci_hi_pct"], share_markets_pos=S["share_markets_pos"], dsr=d_raw.get("dsr"),
             n_trials=d_raw.get("n_trials"), verdict="PASS" if passed else "FAIL"),
        dict(base, variant="P2A frozen", mode="close", cost_case="highvix", n=S_hv["n"], markets=S_hv["markets"],
             mean_ret_pct=S_hv["mean_pct"], excess_pct=S_hv["excess_pct"], ci_lo_pct=S_hv["ci_lo_pct"],
             ci_hi_pct=S_hv["ci_hi_pct"], share_markets_pos=S_hv["share_markets_pos"], verdict="robustness"),
        dict(base, variant="P2A frozen", mode="next_open", cost_case="base", n=S_no["n"], markets=S_no["markets"],
             mean_ret_pct=S_no["mean_pct"], excess_pct=S_no["excess_pct"], ci_lo_pct=S_no["ci_lo_pct"],
             ci_hi_pct=S_no["ci_hi_pct"], share_markets_pos=S_no["share_markets_pos"], verdict="robustness"),
    ])
    print(json.dumps({k: res[k] for k in ("pooled_close", "pooled_close_highvix", "pooled_next_open", "PASS",
                                          "highvix_flips_verdict")}, indent=1, default=str))
    print(pd.DataFrame(per).T[["n", "mean_pct", "bench_pct", "excess_pct", "rand_pctile", "pf", "start"]].round(3)
          .to_string())
    print("by decade:", json.dumps(by_dec, default=str))
    print("DSR raw:", d_raw, "\nDSR excess:", d_ex)


if __name__ == "__main__":
    main()
