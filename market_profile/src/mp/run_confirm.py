"""Confirm stage (spec section 2): ES 2017-01-01 to 2021-12-31, frozen candidates only, run once.

Hard guards: bars and sessions are cut at CONFIRM_END before anything is computed, so no 2022+
price is loaded. Sessions before 2017 are kept only as look-back for features (20-day medians,
prior-day structure, balance areas); trades and the matched baseline both come from 2017-2021
sessions. Definitions are the frozen code at the recorded commit; nothing is re-tuned here.
Pass rule for this stage (spec section 6): net-positive and t >= 2.5 over the matched baseline.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .engine import Baseline, run_trades, evaluate, append_ledger, COST_TICKS
from .families import FAMILIES
from .run_explore import build_ctx, git_head, tree_clean, LEDGER, FROZEN, SPEC, ROOT

CONFIRM_START, CONFIRM_END = pd.Timestamp("2017-01-01"), pd.Timestamp("2021-12-31")
T_CONFIRM = 2.5
CLEDGER = ROOT / "ledger" / "CONFIRM_LEDGER.csv"


def main():
    if not tree_clean():
        sys.exit("commit src/, tests/ and CONVENTIONS.md first")
    if CLEDGER.exists():
        sys.exit(f"{CLEDGER} exists: the confirm stage runs once")
    F = json.load(open(FROZEN))
    cands = F["candidates"]
    reg = {(f, v["id"]): (g, bt, v) for f, g, bt, vs in FAMILIES for v in vs}
    ctx = build_ctx("ES", CONFIRM_END)
    assert ctx.S["date"].max() <= CONFIRM_END
    in_stage = (ctx.S["date"] >= CONFIRM_START).to_numpy()
    first = int(np.flatnonzero(in_stage)[0])
    base = Baseline(ctx, mask=in_stage)
    spec_sha = hashlib.sha256(SPEC.read_bytes()).hexdigest()
    commit, run_utc = git_head(), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    s0, s1 = str(ctx.S["date"].iloc[first].date()), str(ctx.S["date"].max().date())
    lid = int(pd.read_csv(LEDGER)["ledger_id"].max())
    rows, trades = [], []
    for c in cands:
        g, bt, v = reg[(c["family"], c["variant_id"])]
        lid += 1
        tr = run_trades(ctx, [t for t in g(ctx, v) if t.d >= first])
        st = evaluate(ctx, base, tr, bt)
        passes = bool(st.get("n_trades", 0) >= 2 and st["mean_net_ticks"] > 0
                      and st["t_vs_baseline"] == st["t_vs_baseline"] and st["t_vs_baseline"] >= T_CONFIRM)
        by_year = (tr.groupby(pd.to_datetime(tr["date"]).dt.year)["net"].agg(["count", "mean"]).round(2)
                   .to_dict("index") if len(tr) else {})
        row = dict(ledger_id=lid, run_utc=run_utc, spec_sha256=spec_sha, code_commit=commit, stage="confirm",
                   market="ES", family=c["family"], variant_id=v["id"], variant_desc=v["desc"], eligible=True,
                   baseline="same open location" if bt == "loc" else "all days", sample_start=s0, sample_end=s1,
                   meets_explore_rule=passes, notes=f"confirm rule: net > 0 and t >= {T_CONFIRM}; explore ledger id "
                                                    f"{c['ledger_id']}", **st)
        append_ledger(CLEDGER, row)
        rows.append(dict(row, by_year=by_year, explore=c))
        if len(tr):
            trades.append(tr.drop(columns=["k_entry", "k_exit"]).assign(family=c["family"], variant_id=v["id"], ledger_id=lid))
        print(f"{lid} {c['family']} {v['id']} n={st.get('n_trades', 0)} mean_net={st.get('mean_net_ticks', float('nan')):.2f} "
              f"t_base={st.get('t_vs_baseline', float('nan')):.2f} {'PASSES' if passes else 'fails'}")
    if trades:
        T = pd.concat(trades, ignore_index=True)
        T["rule"] = T["rule"].astype(str)
        T.to_csv(ROOT / "ledger" / "confirm_trades.csv.gz", index=False, compression="gzip")
    out = dict(run_utc=run_utc, code_commit=commit, spec_sha256=spec_sha, stage="confirm", sample=[s0, s1],
               sessions=int(in_stage.sum()), rule=f"net-positive and t over matched baseline >= {T_CONFIRM}",
               cost_ticks_round_turn=COST_TICKS["ES"], ledger_rows_total=lid,
               results=[{k: r[k] for k in ("ledger_id", "family", "variant_id", "variant_desc", "baseline", "n_trades",
                                            "n_long", "n_short", "win_rate", "mean_net_ticks", "median_net_ticks",
                                            "mean_gross_ticks", "t_vs_baseline", "t_vs_alt_baseline", "max_dd_ticks",
                                            "total_net_ticks", "total_net_usd", "exits", "meets_explore_rule", "by_year",
                                            "explore") if k in r} for r in rows],
               survivors=[(r["family"], r["variant_id"]) for r in rows if r["meets_explore_rule"]])
    json.dump(out, open(ROOT / "ledger" / "CONFIRM_RESULTS.json", "w"), indent=2, default=float)
    write_report(out)
    print("survivors:", out["survivors"])


def write_report(o: dict) -> None:
    f = lambda x, n=2: "" if x is None or x != x else f"{x:.{n}f}"
    L = ["# Confirm stage report (ES 2017-2021)", "",
         f"**Ledger count: {o['ledger_rows_total']} evaluations in total** (explore rows 1-51 in "
         f"`ledger/EXPLORE_LEDGER.csv`, confirm rows 52-{o['ledger_rows_total']} in `ledger/CONFIRM_LEDGER.csv`).", "",
         f"Sample {o['sample'][0]} to {o['sample'][1]} ({o['sessions']} RTH sessions), run once at {o['run_utc']}, "
         f"code commit `{o['code_commit']}`. Nothing after 2021-12-31 was loaded. Rule: {o['rule']}. "
         f"Costs {o['cost_ticks_round_turn']:.1f} ticks per round turn. The ledger schema is fixed, so on confirm rows "
         "the `meets_explore_rule` column holds the confirm-stage rule result.", "",
         "| id | Candidate | Baseline | Trades | Win % | Mean net | Median net | Mean gross | t vs base | t alt base | Max DD | Result |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in o["results"]:
        n = r.get("n_trades", 0)
        L.append(f"| {r['ledger_id']} | {r['family']} {r['variant_id']} | {r['baseline']} | {n} | "
                 f"{f(100 * r['win_rate'], 1) if n else ''} | {f(r.get('mean_net_ticks'))} | {f(r.get('median_net_ticks'))} | "
                 f"{f(r.get('mean_gross_ticks'))} | {f(r.get('t_vs_baseline'))} | {f(r.get('t_vs_alt_baseline'))} | "
                 f"{f(r.get('max_dd_ticks'), 0)} | {'**passes**' if r['meets_explore_rule'] else 'fails'} |")
    L += ["", "Explore-stage figures for the same candidates, for comparison:", "",
          "| Candidate | Explore trades | Explore mean net | Explore t |", "|---|---|---|---|"]
    for r in o["results"]:
        e = r["explore"]
        L.append(f"| {r['family']} {r['variant_id']} | {e['n_trades']} | {e['mean_net_ticks']:.2f} | {e['t_vs_baseline']:.2f} |")
    L += ["", "By year (confirm trades, mean net ticks):", ""]
    for r in o["results"]:
        L.append(f"- {r['family']} {r['variant_id']}: " + ", ".join(f"{y}: {v['mean']:+.1f} (n={int(v['count'])})"
                                                                     for y, v in r["by_year"].items()))
    L += ["", f"Survivors to the final (2022-2026-08) look: {', '.join(f'{a} {b}' for a, b in o['survivors']) or 'none'}. "
          "The final stage has not been run."]
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "CONFIRM_REPORT.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
