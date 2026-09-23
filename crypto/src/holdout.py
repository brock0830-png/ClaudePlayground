"""One-shot holdout run (crypto/PREREG.md section 1 holdout rules and section 2 holdout rules).

Eligible: only design-stage PASS families. At freeze that is H4 (selected cell SMA50 with BTC gate).
Information only, declared at the freeze commit before this ran: the 'promising' event family H1|V5|long|G4h, the
near-miss H3|k=3.0|clv=off|long|G4h, and the client's own V1 and V6 on G30/C15. These failed the design stage, so no
holdout result can make them eligible.

Refuses to run twice (crypto/reports/holdout/RAN_ONCE).
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

import cdata
import portfolio as pf
import research as R

OUT = cdata.ROOT / "reports" / "holdout"
ONCE = OUT / "RAN_ONCE"


def main():
    if not cdata.UNLOCK.exists():
        sys.exit("holdout locked")
    if ONCE.exists():
        sys.exit("holdout already ran once; refusing")
    OUT.mkdir(parents=True, exist_ok=True)
    w = cdata.DAILY_HOLDOUT
    rep = {"portfolio": {}, "events": {}}

    # ---------------- H4 finalist + benchmarks + neighbourhood
    rows = []
    for b in ("BM1", "BM2", "BM3"):
        m, r, _ = R.run_portfolio(b, {}, w)
        R.port_row("holdout", "BM", b, b, {}, w, 0, 1.0, m)
        rows.append({"cell": b, **m})
        r.to_frame("ret").to_parquet(OUT / f"ret_{b}.parquet")
    sel = {"N": 50, "btc_gate": True}
    fam_sh = []
    for hyp, rule, p in R.portfolio_cells():
        if hyp != "H4":
            continue
        m, r, res = R.run_portfolio(rule, p, w)
        name = R.cell_name(rule, p)
        is_sel = rule == "SMA" and p == sel
        R.port_row("holdout", "H4", "H4", name, p, w, 0, 1.0, m, note="SELECTED" if is_sel else "neighbourhood")
        rows.append({"cell": name, **m})
        fam_sh.append(m["sharpe"])
        if is_sel:
            r.to_frame("ret").to_parquet(OUT / "ret_H4_selected.parquet")
            res["held"].to_parquet(OUT / "held_H4_selected.parquet")
    checks = {}
    for tag, kw in (("delay1", {"delay": 1}), ("cost2x", {"cost_mult": 2.0}), ("fee40bp", {"fee_bp": 40.0})):
        m, _, _ = R.run_portfolio("SMA", sel, w, **kw)
        R.port_row(f"holdout-{tag}", "H4", "H4", "SMA50 btcgate=on", sel, w, kw.get("delay", 0),
                   kw.get("cost_mult", 1.0), m, note=tag)
        rows.append({"cell": f"SMA50 btcgate=on [{tag}]", **m})
        checks[tag] = m
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "portfolio_holdout.csv", index=False)
    s = tab.set_index("cell")
    selm, bm1 = s.loc["SMA50 btcgate=on"], s.loc["BM1"]
    verdict = {"CAGR>0": bool(selm.cagr > 0), "Sharpe>=BM1": bool(selm.sharpe >= bm1.sharpe),
               "MaxDD<=BM1": bool(selm.maxdd >= bm1.maxdd)}
    verdict["PASS"] = all(verdict.values())
    verdict["neighbourhood_median_sharpe"] = float(np.median(fam_sh))
    # deflated Sharpe: trials = live (non-superseded) ledger rows at freeze; spread = design Sharpe std of portfolio cells
    L = pd.read_csv(R.LEDGER)
    live = L[~L["note"].fillna("").str.contains("superseded")]
    n_trials = int((live["phase"].str.startswith("design")).sum())
    dcells = pd.read_csv(cdata.ROOT / "reports" / "design" / "portfolio_cells.csv")
    sr_std = float(dcells.loc[dcells.hyp.isin(["H4", "H5"]), "sharpe"].std())
    r_sel = pd.read_parquet(OUT / "ret_H4_selected.parquet")["ret"].dropna()
    md, rd, _ = R.run_portfolio("SMA", sel, cdata.DAILY_DESIGN)
    verdict["deflated_sharpe_design"] = pf.deflated_sharpe(md["sharpe"], n_trials, md["days"], md["skew"], md["kurt"], sr_std)
    verdict["deflated_sharpe_holdout"] = pf.deflated_sharpe(selm["sharpe"], n_trials, int(selm["days"]), float(selm["skew"]),
                                                            float(selm["kurt"]), sr_std)
    verdict["n_trials"] = n_trials
    verdict["sr_std_trials"] = sr_std
    rep["portfolio"] = {"table": tab.to_dict(orient="records"), "verdict": verdict}

    # ---------------- event families, information only
    info = [("H1", "V5", "long", "G4h", 8), ("H3", "k=3.0|clv=off", "long", "G4h", 6),
            ("H1", "V1", "long", "G30", 8), ("H1", "V1", "short", "G30", 8),
            ("H1", "V6", "long", "G30", 8), ("H1", "V6", "short", "G30", 8)]
    erows = []
    for hyp, var, side, grp, H in info:
        interval, _ = cdata.group(grp)
        grps = [grp] + (["C1h"] if grp == "G4h" else ["C15"])
        for g in grps:
            iv, _ = cdata.group(g)
            s_, _ = R.eval_event(hyp, var, side, g, H, cdata.holdout_window(iv))
            R.event_row("holdout-info", hyp, f"{hyp}|{var}|{side}|{grp}", f"H={H}", {"variant": var, "side": side, "H": H},
                        g, cdata.holdout_window(iv), 0, 1.0, s_, note="information only; failed design stage")
            erows.append({"family": f"{hyp}|{var}|{side}|{grp}", "dataset": g, "H": H, **s_})
    et = pd.DataFrame(erows)
    et.to_csv(OUT / "events_holdout_info.csv", index=False)
    rep["events"] = et.to_dict(orient="records")
    (OUT / "holdout.json").write_text(json.dumps(rep, indent=2, default=float))
    ONCE.write_text("holdout ran once\n")
    pd.set_option("display.width", 250)
    print(tab.round(3).to_string())
    print(json.dumps(verdict, indent=2, default=float))
    print(et[["family", "dataset", "n", "mean_net", "t_clust", "excess", "breadth", "win_rate"]].round(4).to_string())


if __name__ == "__main__":
    main()
