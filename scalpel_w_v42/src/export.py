"""Consolidate the persistent search files: results_all (IS metrics only) and coverage.

results_all_F0.csv.gz       every F0 config x scope (4 tickers + POOLED), full metrics
results_expand_roundN.csv.gz  every EXPAND-variant config with >= 100 pooled IS trades (the only ones
                            that can pass the screen), pooled metrics + per-ticker n / expectancy
coverage.csv.gz             every (variant, cell, ticker): status and number of entries
The full per-variant tables are regenerated deterministically by run_all.sh.
"""
import pandas as pd

from common import LINEAGE, OUT, ROOT

FAM = OUT / "families"


def main():
    g = pd.read_parquet(OUT / "grid_F0.parquet")
    cols = ["lineage", "family", "config", "scope", "n", "wr", "pf", "expR", "sdR", "exp_usd", "usd", "maxdd_usd"]
    g = g[cols].copy()
    for c in ["wr", "pf", "expR", "sdR"]:
        g[c] = g[c].astype(float).round(4)
    for c in ["exp_usd", "usd", "maxdd_usd"]:
        g[c] = g[c].astype(float).round(1)
    g.to_csv(ROOT / "results_all_F0.csv.gz", index=False, compression="gzip")
    rows = []
    for p in sorted(FAM.glob("screen_*.parquet")):
        name = p.stem.replace("screen_", "")
        if "_shift" in name:
            continue
        s = pd.read_parquet(p)
        s = s[s.n >= 100]
        keep = ["config", "n", "wr", "pf", "expR", "sdR", "exp_usd", "maxdd_usd", "n_ES", "n_NQ", "n_CL", "n_6J",
                "expR_ES", "expR_NQ", "expR_CL", "expR_6J", "nb_med_pf", "screen_pass"]
        s = s[[c for c in keep if c in s.columns]].copy()
        s.insert(0, "variant", name)
        rows.append(s)
    if rows:
        e = pd.concat(rows, ignore_index=True)
        for c in e.columns:
            if e[c].dtype.kind == "f":
                e[c] = e[c].round(4)
        e.insert(0, "lineage", LINEAGE)
        rmap = {}
        for p in sorted(FAM.glob("*round*_summary.csv")):
            for v in pd.read_csv(p).variant:
                rmap[v] = p.stem.split("_")[0]
        e["round"] = e.variant.map(rmap)
        (ROOT / "results_expand.csv.gz").unlink(missing_ok=True)
        for rnd, g in e.groupby("round"):
            g.drop(columns=["round"]).to_csv(ROOT / f"results_expand_{rnd}.csv.gz", index=False, compression="gzip")
    cov = [pd.read_csv(OUT / "coverage_F0.csv")]
    cov += [pd.read_csv(p) for p in sorted(FAM.glob("coverage_*.csv"))]
    c = pd.concat(cov, ignore_index=True)
    c["lineage"] = LINEAGE
    c.to_csv(ROOT / "coverage.csv.gz", index=False, compression="gzip")
    summ = c.groupby("family").agg(cells=("level", "size"), done=("status", lambda x: (x == "done").sum()),
                                   errored=("status", lambda x: x.str.startswith("error").sum()),
                                   empty=("n_entries", lambda x: (x == 0).sum())).reset_index()
    summ["pending"] = 0
    summ.insert(0, "lineage", LINEAGE)
    summ.to_csv(ROOT / "coverage_summary.csv", index=False)
    print(summ.to_string())


if __name__ == "__main__":
    main()
