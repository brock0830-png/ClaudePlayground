"""Explore addendum 1 (requested 2026-09-24, after the first freeze, before any confirm data):
one extra logged variant for MP2 and MP4, "drive05" - the drive must also reach at least 0.5x the
20-day median A-period range beyond the opening range by 10:00. Explore period only. Appends
ledger rows 50-51, reports how often the new labels occur, and re-freezes the full candidate list.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .engine import Baseline, run_trades, evaluate, append_ledger
from .families import FAMILIES
from .run_explore import (build_ctx, git_head, tree_clean, EXPLORE_END, T_EXPLORE, LEDGER, FROZEN, SPEC, ROOT)

ADDENDUM = [("MP2", "drive05"), ("MP4", "drive05")]
REGRESSION = {("MP2", "P"): 5, ("MP4", "P"): 7}          # ledger ids that must reproduce exactly


def label_counts(D: pd.DataFrame) -> dict:
    hist = D["med20_arange"].notna()
    thr = 0.5 * D["med20_arange"]
    od_a = D["open_A"] == "OD"
    od_f = D["open_type"] == "OD"
    otd = D["open_A"] == "OTD"
    n = int(len(D)); nh = int(hist.sum())
    pct = lambda k, base: round(100.0 * k / base, 1)
    c = dict(sessions=n, sessions_with_20_session_history=nh,
             od_at_1000_old=int(od_a.sum()), od_at_1000_new=int((od_a & (D["od_dist"] >= thr)).sum()),
             od_final_old=int(od_f.sum()), od_final_new=int((od_f & (D["od_dist"] >= thr)).sum()),
             otd_old=int(otd.sum()), otd_new=int((otd & (D["otd_dist"] >= thr)).sum()),
             otd_traded_back_through_or_after_reversal=int((otd & D["otd_back"].astype(bool)).sum()),
             od_at_1000_old_with_history=int((od_a & hist).sum()), otd_old_with_history=int((otd & hist).sum()))
    c["pct_of_sessions_with_history"] = {k: pct(c[k], nh) for k in
                                         ("od_at_1000_new", "od_final_new", "otd_new")}
    c["pct_of_sessions_with_history"].update(od_at_1000_old=pct(c["od_at_1000_old_with_history"], nh),
                                             otd_old=pct(c["otd_old_with_history"], nh))
    return c


def main():
    if not tree_clean():
        sys.exit("commit src/, tests/ and CONVENTIONS.md first")
    L = pd.read_csv(LEDGER)
    if len(L) != 49 or (L["variant_id"] == "drive05").any():
        sys.exit("addendum 1 already applied (or ledger not at 49 rows): it runs once")
    ctx = build_ctx("ES", EXPLORE_END)
    assert ctx.S["date"].max() <= EXPLORE_END
    base = Baseline(ctx)
    reg = {(f, v["id"]): (g, bt, v) for f, g, bt, vs in FAMILIES for v in vs}
    for key, lid in REGRESSION.items():                   # code drift guard, not a new evaluation
        g, bt, v = reg[key]
        st = evaluate(ctx, base, run_trades(ctx, g(ctx, v)), bt)
        row = L[L["ledger_id"] == lid].iloc[0]
        assert st["n_trades"] == row["n_trades"] and np.isclose(st["mean_net_ticks"], row["mean_net_ticks"]), key
    spec_sha = hashlib.sha256(SPEC.read_bytes()).hexdigest()
    commit, run_utc = git_head(), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    s0, s1 = str(ctx.S["date"].min().date()), str(ctx.S["date"].max().date())
    rows, trades, lid = [], [], int(L["ledger_id"].max())
    for key in ADDENDUM:
        g, bt, v = reg[key]
        lid += 1
        tr = run_trades(ctx, g(ctx, v))
        st = evaluate(ctx, base, tr, bt)
        meets = bool(v["eligible"] and st.get("n_trades", 0) >= 2 and st["mean_net_ticks"] > 0
                     and st["t_vs_baseline"] == st["t_vs_baseline"] and st["t_vs_baseline"] >= T_EXPLORE)
        row = dict(ledger_id=lid, run_utc=run_utc, spec_sha256=spec_sha, code_commit=commit, stage="explore",
                   market="ES", family=key[0], variant_id=v["id"], variant_desc=v["desc"], eligible=v["eligible"],
                   baseline="all days", sample_start=s0, sample_end=s1, meets_explore_rule=meets,
                   notes="addendum 1: requested after the first freeze, before any confirm-stage data", **st)
        append_ledger(LEDGER, row)
        rows.append(row)
        if not tr.empty:
            trades.append(tr.drop(columns=["k_entry", "k_exit"]).assign(family=key[0], variant_id=v["id"], ledger_id=lid))
        print(f"{lid} {key[0]} {v['id']} n={st['n_trades']} mean_net={st['mean_net_ticks']:.2f} "
              f"t_base={st['t_vs_baseline']:.2f} {'MEETS' if meets else ''}")
    T = pd.concat(trades, ignore_index=True)
    T["rule"] = T["rule"].astype(str)
    T.to_csv(ROOT / "ledger" / "explore_trades_addendum1.csv.gz", index=False, compression="gzip")
    counts = label_counts(ctx.D)
    json.dump(dict(run_utc=run_utc, code_commit=commit, variant=reg[ADDENDUM[0]][2], label_counts=counts),
              open(ROOT / "ledger" / "addendum_1.json", "w"), indent=2, default=str)
    F = json.load(open(FROZEN))
    first = dict(frozen_utc=F["frozen_utc"], code_commit=F["code_commit"], ledger_rows=F["ledger_rows"],
                 candidates=F["candidates"])
    new = [dict(family=r["family"], variant_id=r["variant_id"], variant_desc=r["variant_desc"], ledger_id=r["ledger_id"],
                n_trades=r["n_trades"], mean_net_ticks=round(r["mean_net_ticks"], 3),
                t_vs_baseline=round(r["t_vs_baseline"], 3)) for r in rows if r["meets_explore_rule"]]
    F["freeze_history"] = [dict(first, note="first freeze, ledger rows 1-49"),
                           dict(frozen_utc=run_utc, code_commit=commit, ledger_rows=len(L) + len(rows),
                                added=new, note="addendum 1: MP2/MP4 drive05, ledger rows 50-51")]
    F["candidates"] = F["candidates"] + new
    F["ledger_rows"] = len(L) + len(rows)
    F["frozen_utc"], F["code_commit"] = run_utc, commit
    json.dump(F, open(FROZEN, "w"), indent=2, default=float)
    print(json.dumps(counts, indent=1))
    print("full frozen list:", [(c["family"], c["variant_id"]) for c in F["candidates"]])


if __name__ == "__main__":
    main()
