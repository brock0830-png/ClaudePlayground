"""Explore stage (spec section 2): ES, first available session to 2016-12-30.

Hard guard: bars and sessions are cut at EXPLORE_END *before* any feature is computed, so no
2017+ price can reach a feature, a trade or a baseline. Every (family, variant) evaluation is
appended to ledger/EXPLORE_LEDGER.csv. Families meeting the explore rule (net-positive and
t >= 2.0 over the matched baseline, eligible variants only) are frozen in
ledger/FROZEN_CANDIDATES.json. The confirm stage is not run here.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .data import build_market, ROOT
from .engine import Ctx, Baseline, run_trades, evaluate, append_ledger, COST_TICKS
from .features import session_features, cross_session
from .families import FAMILIES, composite_count

EXPLORE_END = pd.Timestamp("2016-12-31")
T_EXPLORE = 2.0
LEDGER = ROOT / "ledger" / "EXPLORE_LEDGER.csv"
TRADES = ROOT / "ledger" / "explore_trades.csv.gz"
FROZEN = ROOT / "ledger" / "FROZEN_CANDIDATES.json"
SPEC = ROOT / "SPEC_market_profile_ES_v3.md"


def build_ctx(sym: str, end: pd.Timestamp) -> Ctx:
    m = build_market(sym)
    S = m.sessions[m.sessions["date"] <= end].reset_index(drop=True)
    bars = m.bars.iloc[:int(S["b1"].iloc[-1])].reset_index(drop=True)
    assert bars["session"].max() == len(S) - 1
    feats = []
    for i in range(len(S)):
        b = bars.iloc[S["b0"].iloc[i]:S["b1"].iloc[i]]
        feats.append(session_features(b.o, b.h, b.l, b.c, b.v, b.minute, raw_offset=int(S["offset_t"].iloc[i])))
    D = cross_session(S, bars, feats)
    return Ctx(sym, bars, S, D, feats)


def git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()


def tree_clean() -> bool:
    out = subprocess.run(["git", "status", "--porcelain", "src", "tests", "CONVENTIONS.md"],
                         capture_output=True, text=True, cwd=ROOT).stdout
    return not out.strip()


def descriptive(ctx: Ctx, tr_by: dict) -> dict:
    """Book statistics for MP3, MP13, MP14, MP25, MP26 (spec section 6), explore period."""
    D, out = ctx.D, {}
    # MP3: does the initial extreme hold (< 50% per the book)?
    orr = np.flatnonzero(D["open_A"].to_numpy() == "ORR")
    held = [(D["H"].iloc[d] == D["orr_ext"].iloc[d]) if D["orr_dir"].iloc[d] < 0 else
            (D["L"].iloc[d] == D["orr_ext"].iloc[d]) for d in orr]
    out["MP3"] = dict(orr_days=len(orr), initial_extreme_held=float(np.mean(held)) if held else None,
                      book="initial extreme holds < 50% of the time")

    def next_day_stats(days, dirs):
        beyond90, closed_ok = [], []
        for d, s in zip(days, dirs):
            if d + 1 >= ctx.n:
                continue
            k0, k1 = ctx.k_start(d + 1), ctx.k_open(d + 1, 660)
            seg = ctx.P[k0:k1]
            vah, val = D["vah"].iloc[d], D["val"].iloc[d]
            beyond90.append(bool((seg > vah).any()) if s > 0 else bool((seg < val).any()))
            c = D["C"].iloc[d + 1]
            closed_ok.append(c >= val if s > 0 else c <= vah)
        return dict(n=len(beyond90), traded_beyond_va_first_90min=float(np.mean(beyond90)) if beyond90 else None,
                    closed_within_or_beyond_va=float(np.mean(closed_ok)) if closed_ok else None)

    ne = np.flatnonzero(D["day_type"].to_numpy() == "Neutral-Extreme")
    ne_dir = [1 if D["C"].iloc[d] >= D["H"].iloc[d] - 0.15 * D["range"].iloc[d] else -1 for d in ne]
    out["MP13"] = dict(next_day_stats(ne, ne_dir), book="next day beyond prior VA in first 90 min: 64% (T-bonds 86-87)")
    ti = np.flatnonzero(D["three_i"].to_numpy() != 0)
    out["MP14"] = dict(next_day_stats(ti, D["three_i"].to_numpy()[ti]), book="94% beyond VA in first 90 min; 97% closed within or beyond")
    tr = np.flatnonzero(D["two_i_one_r"].to_numpy() != 0)
    out["MP14b"] = dict(next_day_stats(tr, D["two_i_one_r"].to_numpy()[tr]), book="71% / 82%")
    nr = np.flatnonzero((D["range"] <= 0.6 * D["med20_range"]).to_numpy()[:-1])
    nxt = [D["range"].iloc[d + 1] > D["med20_range"].iloc[d + 1] for d in nr]
    base = (D["range"] > D["med20_range"])[D["med20_range"].notna()].mean()
    out["MP25"] = dict(narrow_days=len(nr), next_range_above_median=float(np.mean(nxt)) if nxt else None,
                       all_days_range_above_median=float(base),
                       book="narrow days come before big days")
    rows = []
    for d in range(ctx.n - 3):
        cnt, dr = composite_count(ctx, d)
        if cnt < 0 or dr == 0:
            continue
        fwd = D["C"].iloc[d + 3] - D["O"].iloc[d + 1]
        rows.append((cnt, dr, np.sign(fwd) * dr))
    R = pd.DataFrame(rows, columns=["cnt", "dir", "with"])
    out["MP26"] = dict(
        n_days=len(R),
        over43=dict(n=int((R.cnt >= 43).sum()), frac_next3_against=float((R[R.cnt >= 43]["with"] < 0).mean()) if (R.cnt >= 43).any() else None),
        under18=dict(n=int((R.cnt <= 18).sum()), frac_next3_with=float((R[R.cnt <= 18]["with"] > 0).mean()) if (R.cnt <= 18).any() else None),
        middle=dict(n=int(((R.cnt > 18) & (R.cnt < 43)).sum()),
                    frac_next3_with=float((R[(R.cnt > 18) & (R.cnt < 43)]["with"] > 0).mean())),
        book="0-18 trend continuation; 43+ price should move opposite")
    return out


def main(argv=None):
    if not tree_clean() and "--allow-dirty" not in (argv or sys.argv[1:]):
        sys.exit("commit src/, tests/ and CONVENTIONS.md first: the ledger records the code commit")
    spec_sha = hashlib.sha256(SPEC.read_bytes()).hexdigest()
    commit = git_head()
    ctx = build_ctx("ES", EXPLORE_END)
    assert ctx.S["date"].max() <= EXPLORE_END
    base = Baseline(ctx)
    LEDGER.parent.mkdir(exist_ok=True)
    if LEDGER.exists():
        sys.exit(f"{LEDGER} exists: the explore ledger is append-once; remove it deliberately to rerun")
    run_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    s0, s1 = str(ctx.S["date"].min().date()), str(ctx.S["date"].max().date())
    all_trades, rows, lid = [], [], 0
    for fam, gen, btype, variants in FAMILIES:
        for v in variants:
            lid += 1
            tr = run_trades(ctx, gen(ctx, v))
            st = evaluate(ctx, base, tr, btype)
            meets = bool(v["eligible"] and st.get("n_trades", 0) >= 2 and st["mean_net_ticks"] > 0
                         and st["t_vs_baseline"] == st["t_vs_baseline"] and st["t_vs_baseline"] >= T_EXPLORE)
            row = dict(ledger_id=lid, run_utc=run_utc, spec_sha256=spec_sha, code_commit=commit, stage="explore",
                       market="ES", family=fam, variant_id=v["id"], variant_desc=v["desc"], eligible=v["eligible"],
                       baseline="same open location" if btype == "loc" else "all days",
                       sample_start=s0, sample_end=s1, meets_explore_rule=meets, **st)
            append_ledger(LEDGER, row)
            rows.append(row)
            if not tr.empty:
                t = tr.drop(columns=["k_entry", "k_exit"]).assign(family=fam, variant_id=v["id"], ledger_id=lid)
                all_trades.append(t)
            print(f"{lid:3d} {fam:6s} {v['id']:11s} n={st.get('n_trades', 0):5d} "
                  f"mean_net={st.get('mean_net_ticks', float('nan')):7.2f} t_base={st.get('t_vs_baseline', float('nan')):6.2f} "
                  f"{'MEETS' if meets else ''}", flush=True)
    T = pd.concat(all_trades, ignore_index=True)
    T["rule"] = T["rule"].astype(str)
    T.to_csv(TRADES, index=False, compression="gzip")
    frozen = [dict(family=r["family"], variant_id=r["variant_id"], variant_desc=r["variant_desc"],
                   ledger_id=r["ledger_id"], n_trades=r["n_trades"], mean_net_ticks=round(r["mean_net_ticks"], 3),
                   t_vs_baseline=round(r["t_vs_baseline"], 3)) for r in rows if r["meets_explore_rule"]]
    desc = descriptive(ctx, {})
    json.dump(dict(frozen_utc=run_utc, spec_sha256=spec_sha, code_commit=commit, stage="explore",
                   rule=f"eligible variant, mean net ticks > 0 and t over matched baseline >= {T_EXPLORE}",
                   explore_sample=[s0, s1], ledger_rows=len(rows), cost_ticks_round_turn=COST_TICKS["ES"],
                   candidates=frozen, book_descriptives=desc),
              open(FROZEN, "w"), indent=2, default=float)
    print(f"\nledger rows: {len(rows)}; frozen candidates: {len(frozen)}")
    for f in frozen:
        print("  ", f)


if __name__ == "__main__":
    main()
