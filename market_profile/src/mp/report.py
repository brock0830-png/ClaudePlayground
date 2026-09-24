"""EXPLORE_REPORT.md from the ledger and the frozen-candidate file (spec section 6 layout)."""
from __future__ import annotations

import json

import pandas as pd

from .data import ROOT
from .run_explore import LEDGER, FROZEN


def fmt(x, nd=2):
    return "" if x != x else f"{x:.{nd}f}"


def main():
    L = pd.read_csv(LEDGER)
    F = json.load(open(FROZEN))
    info = json.load(open(ROOT / "ledger" / "data_info.json"))
    lines = [f"# Explore stage report (ES)",
             "",
             f"**Ledger count: {len(L)} evaluations** (`ledger/EXPLORE_LEDGER.csv`, ids 1-{len(L)}); "
             f"{int(L['eligible'].sum())} eligible for freezing, {int((~L['eligible']).sum())} robustness-only.",
             "",
             f"Spec `SPEC_market_profile_ES_v3.md` sha256 `{F['spec_sha256']}`; code commit `{F['code_commit']}`; run {F['frozen_utc']}.",
             "",
             "## Data",
             "",
             f"- Databento `GLBX.MDP3` `ohlcv-1m`, `ES.v.0` + `NQ.v.0` (volume roll), full history. "
             f"Billed ${info['cost_usd']:.2f} (equal to the free estimate); first available date {info['first_date']}.",
             f"- Explore sample: {F['explore_sample'][0]} to {F['explore_sample'][1]}, {info['explore_sessions']} RTH sessions. "
             f"Nothing after 2016-12-31 was loaded into the explore run.",
             f"- Rolls in the explore sample: {info['explore_rolls']} (full list in `rolls_ES.csv`). "
             f"Sessions dropped as unusable: {info['explore_dropped']} (`sessions_dropped_ES.csv`).",
             f"- 2-tick rows (profile > 400 one-tick rows): {info['explore_rs2']} explore session(s) (`ledger/row_size_log_ES.csv`).",
             f"- Costs: 1 tick slippage per side + $5 round turn = {F['cost_ticks_round_turn']:.1f} ticks per trade.",
             "",
             "## Rule",
             "",
             f"Advance to confirm if {F['rule']} (spec section 6). Matched baseline: same entry clock time, "
             "side and exit rule, over all sessions or sessions with the same open location (CONVENTIONS.md C20).",
             "",
             "## Frozen candidates",
             ""]
    if F["candidates"]:
        lines += ["| Family | Variant | Ledger id | Trades | Mean net ticks | t vs baseline |", "|---|---|---|---|---|---|"]
        for c in F["candidates"]:
            lines.append(f"| {c['family']} | {c['variant_id']} ({c['variant_desc']}) | {c['ledger_id']} | {c['n_trades']} | "
                         f"{c['mean_net_ticks']:.2f} | {c['t_vs_baseline']:.2f} |")
    else:
        lines.append("None. No eligible variant met the explore rule.")
    lines += ["", "## All evaluations", "",
              "| id | Family | Variant | Baseline | Trades | Win % | Mean net | Median net | Mean gross | t vs base | t alt base | Max DD | Meets |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in L.itertuples():
        lines.append(f"| {r.ledger_id} | {r.family} | {r.variant_id}{'' if r.eligible else ' (robustness)'} | "
                     f"{'open loc' if r.baseline.startswith('same') else 'all'} | {int(r.n_trades) if r.n_trades == r.n_trades else 0} | "
                     f"{fmt(100 * r.win_rate, 1)} | {fmt(r.mean_net_ticks)} | {fmt(r.median_net_ticks)} | {fmt(r.mean_gross_ticks)} | "
                     f"{fmt(r.t_vs_baseline)} | {fmt(r.t_vs_alt_baseline)} | {fmt(r.max_dd_ticks, 0)} | {'yes' if r.meets_explore_rule else ''} |")
    lines += ["", "Net and gross are ticks per trade; max drawdown is in ticks on cumulative net.", "",
              "## Book descriptive statistics (explore period)", ""]
    for k, v in F["book_descriptives"].items():
        lines.append(f"- **{k}**: " + "; ".join(f"{a} = {fmt(b, 3) if isinstance(b, float) else b}" for a, b in v.items()))
    n_elig = int(L["eligible"].sum())
    lines += ["", "## Reading the result", "",
              f"{n_elig} eligible evaluations were tested at t >= 2.0 (one-sided p about 0.023 each), so about "
              f"{0.023 * n_elig:.1f} would pass by chance alone if no hypothesis had any edge. That is why the confirm stage (t >= 2.5 "
              "on 2017-2021, frozen definitions only) exists. The confirm stage has not been run.",
              "", "Observations on the explore results (no definitions changed): `reports/EXPLORE_NOTES.md`.", "",
              "Profile parity against TradingView for the 3 latest sessions: `reports/PARITY_ES.md`."]
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "EXPLORE_REPORT.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
