"""STEP 4 - freeze finalists (in-sample only), leave-one-ticker-out, then ONE-SHOT out-of-sample.

    python validate.py freeze    # pre-registered selection -> finalists.csv, FREEZE.md (no 2021+ data)
    python validate.py loto      # leave-one-ticker-out on in-sample data
    python validate.py unseal    # writes OOS_UNSEALED and evaluates frozen finalists on 2021+ once

Finalist selection (frozen before any 2021+ data is read):
  1. Pool = every configuration that passes the config screen (screen.py) in F0 or in any EXPAND
     variant, on the real levels.
  2. Score = in-sample t-statistic of net R per trade (mean / sd * sqrt(n)), pooled over tickers.
  3. Cluster the pool by entry-set overlap (Jaccard of (ticker, week) entries > 0.7), greedy by score.
  4. Finalists = the best-scoring member of each of the 8 best clusters, plus the best-scoring
     configuration of each archive lead (WTL1 bounce; RB_TOP long bounce under DM40_lt; WRL bounce)
     when not already present. Archive leads that fail the screen are carried and flagged.
Gates (all required to call a finalist EV+):
  G1 OOS pooled: expectancy > 0 in R and $, PF >= 1.20, n >= 100
  G2 LOTO: the rule re-selected without ticker k is net positive on ticker k (IS) for >= 3 of 4
  G3 OOS with 2 ticks slippage: expectancy > 0
  G4 OOS with every SD multiplier x0.95 and x1.05: expectancy > 0 in both
  G5 OOS matched placebo: expectancy above the mean of the four placebo shifts, AND the variant's
     whole-search placebo check (family screen b) passed in-sample
  G6 in-sample per-trade Sharpe above the Deflated Sharpe floor for N_all and for N_eff
  G7 path resolution: stop distance and pierce >= 0.3 ATR at the median, else flagged (no 15m data)
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from common import LINEAGE, OOS_START, OUT, ROOT, SEAL_FILE, TICKERS
from screen import neighbours, keyof

FAM = OUT / "families"
K_CLUSTERS = 8
ARCHIVE = [
    ("F0", dict(level="WTL1", side="bounce"), "ARCHIVE WTL1 bounce (57.7% WR, PF 1.80)"),
    ("DM40_lt", dict(level="RB_TOP", side="bounce"), "ARCHIVE W RB Top long + momentum filter DM<0.40 (67 SPY trades, PF 1.54)"),
    ("F0", dict(level="WRL", side="bounce"), "ARCHIVE WRL bounce (69.4% WR, PF 1.44)"),
]


def variants():
    """Real-level screen files: F0 plus every family variant screened so far."""
    out = {"F0": OUT / "screen_F0.parquet"}
    for p in sorted(FAM.glob("screen_*.parquet")):
        name = p.stem.replace("screen_", "")
        if "_shift" in name:
            continue
        out[name] = p
    return out


def family_screens():
    rows = []
    for p in sorted(FAM.glob("round*_summary.csv")):
        rows.append(pd.read_csv(p))
    return pd.concat(rows) if rows else pd.DataFrame()


def load_pool():
    pool = []
    for v, p in variants().items():
        s = pd.read_parquet(p)
        s = s[s.screen_pass].copy()
        s["variant"] = v
        pool.append(s)
    pool = pd.concat(pool, ignore_index=True)
    pool["score"] = pool.expR / pool.sdR * np.sqrt(pool.n)
    return pool


def cell_of(cid):
    return "|".join(cid.split("|")[:6])


def freeze():
    if SEAL_FILE.exists():
        raise SystemExit("OOS already unsealed; finalists cannot be re-selected")
    from data import load_all
    from deflate import cell_entry_sets, greedy_cluster
    B = load_all()
    pool = load_pool()
    print("pool (screen passers across variants):", len(pool))
    # entry sets per (variant, cell)
    mats, keys = [], []
    for v in pool.variant.unique():
        M, ck = cell_entry_sets(B, None if v == "F0" else v)
        need = set(pool.loc[pool.variant == v, "config"].map(cell_of))
        idx = [i for i, k in enumerate(ck) if k in need]
        mats.append(M[idx])
        keys += [(v, ck[i]) for i in idx]
    M = np.vstack(mats)
    kidx = {k: i for i, k in enumerate(keys)}
    pool["set_idx"] = [kidx[(v, cell_of(c))] for v, c in zip(pool.variant, pool.config)]
    # cluster configs: expand the set matrix to config rows (configs share their cell's set)
    Mc = M[pool.set_idx.values]
    cid = greedy_cluster(Mc, pool.score.values, 0.7)
    pool["cluster"] = cid
    reps = pool.sort_values("score", ascending=False).groupby("cluster").head(1)
    reps = reps.sort_values("score", ascending=False)
    fin = reps.head(K_CLUSTERS).copy()
    fin["why"] = [f"top cluster #{i + 1} by IS t-stat" for i in range(len(fin))]
    # archive leads
    extra = []
    for v, flt, why in ARCHIVE:
        p = variants().get(v)
        if p is None:
            continue
        s = pd.read_parquet(p)
        s = s[(s.level == flt["level"]) & (s.side == flt["side"]) & (s.n >= 100)].copy()
        if "sdR" not in s:
            continue
        s["score"] = s.expR / s.sdR * np.sqrt(s.n)
        s["variant"] = v
        best_pass = s[s.screen_pass].sort_values("score", ascending=False).head(1)
        best = best_pass if len(best_pass) else s.sort_values("score", ascending=False).head(1)
        best = best.copy()
        best["why"] = why + ("" if len(best_pass) else " [fails IS screen, carried as lead]")
        if not ((fin.config == best.config.iloc[0]) & (fin.variant == v)).any():
            extra.append(best)
    if extra:
        fin = pd.concat([fin] + extra, ignore_index=True)
    fin["finalist"] = [f"F{i + 1:02d}" for i in range(len(fin))]
    cols = ["finalist", "variant", "config", "why", "n", "wr", "pf", "expR", "sdR", "score", "exp_usd",
            "maxdd_usd", "expR_ES", "expR_NQ", "expR_CL", "expR_6J", "n_ES", "n_NQ", "n_CL", "n_6J", "screen_pass"]
    fin = fin[[c for c in cols if c in fin.columns]]
    fin.insert(0, "lineage", LINEAGE)
    fin.to_csv(ROOT / "finalists.csv", index=False)
    pool[["variant", "config", "n", "expR", "sdR", "pf", "score", "cluster"]].to_csv(OUT / "finalist_pool.csv", index=False)
    h = hashlib.sha256((ROOT / "finalists.csv").read_bytes()).hexdigest()
    n_clusters = int(pool.cluster.max() + 1)
    txt = [f"# FREEZE - {LINEAGE}", "",
           f"Frozen {datetime.now(timezone.utc).isoformat()} from in-sample data only (weeks before {OOS_START}).",
           f"finalists.csv sha256 `{h}`", "",
           f"Pool: {len(pool)} screen-passing configs across {pool.variant.nunique()} variants, "
           f"{n_clusters} entry-overlap clusters.", "",
           "| id | variant | config | why | IS n | IS PF | IS expR | t-stat |", "|---|---|---|---|---|---|---|---|"]
    for r in fin.itertuples():
        txt.append(f"| {r.finalist} | {r.variant} | `{r.config}` | {r.why} | {r.n} | {r.pf:.2f} | {r.expR:.3f} | {r.score:.2f} |")
    (ROOT / "FREEZE.md").write_text("\n".join(txt) + "\n")
    print("\n".join(txt))
    return fin


# ------------------------------------------------------------------ LOTO (in-sample)
def _screen_frame(v):
    p = variants()[v]
    return pd.read_parquet(p)


def loto():
    from data import load_all
    from trades import config_trades, summary
    B = load_all()
    fin = pd.read_csv(ROOT / "finalists.csv")
    rows = []
    for f in fin.itertuples():
        s = _screen_frame(f.variant)
        lv, side, unit = f.config.split("|")[:3]
        loc = s[(s.level == lv) & (s.side == side) & (s.unit == unit)].copy()
        for k in TICKERS:
            others = [t for t in TICKERS if t != k]
            n3 = sum(loc[f"n_{t}"].fillna(0) for t in others)
            e3 = sum(loc[f"n_{t}"].fillna(0) * loc[f"expR_{t}"].fillna(0) for t in others) / n3.replace(0, np.nan)
            loc["n3"], loc["e3"] = n3, e3
            lut = {keyof(r): (r["e3"], r["n3"]) for r in loc[["level", "side", "unit", "d", "style", "D", "stop", "target", "e3", "n3"]].to_dict("records")}
            cand = loc[(loc.n3 >= 75) & (loc.e3 > 0)].copy()
            ok = []
            for _, r in cand.iterrows():
                nb = [lut.get(keyof(x)) for x in neighbours(r)]
                nb = [x for x in nb if x is not None]
                ok.append(bool(nb) and all(np.isfinite(x[0]) and x[0] > 0 for x in nb))
            cand = cand[np.array(ok, bool)] if len(cand) else cand
            if len(cand) == 0:
                rows.append(dict(lineage=LINEAGE, finalist=f.finalist, held_out=k, chosen="(none passes on 3 tickers)",
                                 n_k=0, expR_k=np.nan, positive=False))
                continue
            cand["t3"] = cand.e3 * np.sqrt(cand.n3)        # score proxy on 3 tickers
            ch = cand.sort_values("t3", ascending=False).iloc[0]
            tr = config_trades({k: B[k]}, ch.config, variant=None if f.variant == "F0" else f.variant)
            sm = summary(tr)
            rows.append(dict(lineage=LINEAGE, finalist=f.finalist, held_out=k, chosen=ch.config, n_k=sm["n"],
                             expR_k=sm["expR"], pf_k=sm["pf"], positive=bool(sm["n"] > 0 and sm["expR"] > 0)))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "validation_loto.csv", index=False)
    print(df.to_string())
    return df


# ------------------------------------------------------------------ one-shot OOS
def unseal():
    if SEAL_FILE.exists() and "--reprint" not in sys.argv:
        raise SystemExit("OOS already opened once; use --reprint to print stored results")
    if "--reprint" in sys.argv:
        print((OUT / "validation_oos.csv").read_text())
        return
    fin = pd.read_csv(ROOT / "finalists.csv")
    h = hashlib.sha256((ROOT / "finalists.csv").read_bytes()).hexdigest()
    SEAL_FILE.write_text(json.dumps(dict(opened_utc=datetime.now(timezone.utc).isoformat(), finalists_sha256=h)) + "\n")
    from data import load_all
    from trades import config_trades, summary
    B = load_all(full=True)
    oos0 = pd.Timestamp(OOS_START)
    runs = {"base": {}, "slip2": dict(slip=2.0), "x0.95": dict(scale=0.95), "x1.05": dict(scale=1.05),
            "plc-0.30": dict(shift=-0.30), "plc-0.15": dict(shift=-0.15), "plc+0.15": dict(shift=0.15),
            "plc+0.30": dict(shift=0.30)}
    rows, tl = [], []
    for f in fin.itertuples():
        v = None if f.variant == "F0" else f.variant
        for rn, kw in runs.items():
            tr = config_trades(B, f.config, variant=v, **kw)
            if len(tr) == 0:
                tr = pd.DataFrame(columns=["week", "ticker", "R", "pnl_usd", "exit_time", "year"])
            tr["period"] = np.where(pd.to_datetime(tr.week) >= oos0, "OOS", "IS")
            for per in ("IS", "OOS"):
                sub = tr[tr.period == per]
                for sc in TICKERS + ["POOLED"]:
                    x = sub if sc == "POOLED" else sub[sub.ticker == sc]
                    rows.append(dict(lineage=LINEAGE, finalist=f.finalist, run=rn, period=per, scope=sc, **summary(x)))
            if rn == "base":
                t2 = tr.copy()
                t2.insert(0, "finalist", f.finalist)
                tl.append(t2)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "validation_oos.csv", index=False)
    pd.concat(tl).to_csv(OUT / "finalist_trades_all.csv", index=False)
    print("OOS evaluated once; results in outputs/validation_oos.csv")
    return df


if __name__ == "__main__":
    {"freeze": freeze, "loto": loto, "unseal": unseal}[sys.argv[1]]()
