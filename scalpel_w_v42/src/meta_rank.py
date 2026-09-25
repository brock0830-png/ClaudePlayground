"""Meta-test across every EXPAND family: where does the real-level search rank among the five
searches (real + 4 placebo shifts)? Under the null that the v42 levels are no better than lines
0.15-0.30 sigma away, the real search is equally likely to take any rank 1..5, so it ranks first
20% of the time and its mean rank is 3. Ranks use (a) top-10 mean expectancy and (b) the number of
screen passers. The binomial p-value tests "ranked first more often than 20%"; the rank-sum p-value
(normal approximation, ties ignored) tests a mean rank below 3.
"""
import numpy as np
import pandas as pd
from scipy.stats import binomtest, norm

from common import LINEAGE, OUT

FAM = OUT / "families"


def ranks(tag_glob):
    rows = []
    for p in sorted(FAM.glob(tag_glob)):
        raw = pd.read_csv(p)
        for v, g in raw.groupby("variant"):
            if len(g) != 5 or g.top10.isna().any():
                continue
            real = g[g["shift"] == 0].iloc[0]
            r_top = 1 + int((g.top10 > real.top10).sum())
            r_pass = 1 + int((g.screen_pass > real.screen_pass).sum())
            rows.append(dict(file=p.stem, variant=v, rank_top10=r_top, rank_pass=r_pass))
    return pd.DataFrame(rows)


def summarize(df, label):
    out = []
    for col in ("rank_top10", "rank_pass"):
        n = len(df)
        k1 = int((df[col] == 1).sum())
        mean = df[col].mean()
        z = (3 - mean) / (np.sqrt(2.0) / np.sqrt(n))          # rank on 1..5 has variance 2
        out.append(dict(lineage=LINEAGE, phase=label, metric=col, families=n, ranked_first=k1,
                        share_first=k1 / n, p_first_binom=binomtest(k1, n, 0.2, alternative="greater").pvalue,
                        mean_rank=mean, p_mean_rank=1 - norm.cdf(z)))
    return out


def main():
    p1 = ranks("round*_raw.csv")
    p2 = ranks("p2round*_raw.csv")
    rows = summarize(p1, "phase 1") + summarize(p2, "phase 2") + summarize(pd.concat([p1, p2]), "all")
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "meta_rank.csv", index=False)
    pd.concat([p1.assign(phase=1), p2.assign(phase=2)]).to_csv(OUT / "meta_rank_detail.csv", index=False)
    print(t.round(3).to_string())


if __name__ == "__main__":
    main()
