"""Effective number of independent trials across the whole search (F0 + every EXPAND variant).

Eligible trials = configs with >= 100 pooled IS trades (the screen's minimum). Configs are grouped
by entry set (variant, cell); entry sets are clustered greedily with Jaccard > 0.7. N_eff = number
of clusters. Written to outputs/neff.txt (first token = N_eff) and outputs/neff_detail.csv.
"""
import numpy as np
import pandas as pd

from common import LINEAGE, OUT
from data import load_all
from deflate import cell_entry_sets, greedy_cluster


def main():
    B = load_all()
    files = {"F0": OUT / "screen_F0.parquet"}
    for p in sorted((OUT / "families").glob("screen_*.parquet")):
        n = p.stem.replace("screen_", "")
        if "_shift" not in n:
            files[n] = p
    mats, meta = [], []
    n_elig_cfg = 0
    for v, p in files.items():
        s = pd.read_parquet(p, columns=["config", "n", "expR", "sdR"])
        s = s[(s.n >= 100) & (s.sdR > 0)]
        n_elig_cfg += len(s)
        s["cell"] = s.config.str.split("|").str[:6].str.join("|")
        s["t"] = s.expR / s.sdR * np.sqrt(s.n)
        best = s.groupby("cell").t.max()
        M, keys = cell_entry_sets(B, None if v == "F0" else v)
        idx = [i for i, k in enumerate(keys) if k in best.index]
        mats.append(M[idx])
        meta += [(v, keys[i], best[keys[i]]) for i in idx]
        print(v, len(s), "eligible configs,", len(idx), "cells", flush=True)
    M = np.vstack(mats)
    score = np.array([m[2] for m in meta])
    cid = greedy_cluster(M, score, 0.7)
    ne = int(cid.max() + 1)
    df = pd.DataFrame(meta, columns=["variant", "cell", "best_t"])
    df["cluster"] = cid
    df.insert(0, "lineage", LINEAGE)
    df.to_csv(OUT / "neff_detail.csv", index=False)
    (OUT / "neff.txt").write_text(f"{ne} clusters of {len(df)} eligible entry sets ({n_elig_cfg} eligible configs)\n")
    print((OUT / "neff.txt").read_text())


if __name__ == "__main__":
    main()
