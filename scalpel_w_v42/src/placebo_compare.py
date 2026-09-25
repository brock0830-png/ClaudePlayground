"""Whole-search placebo: run the identical grid + screen on shifted levels and compare."""
import numpy as np
import pandas as pd

from common import LINEAGE, OUT
from screen import screen

VARIANTS = ["", "_shift-0.30", "_shift-0.15", "_shift+0.15", "_shift+0.30", "_scale0.95", "_scale1.05", "_slip2"]


def main():
    rows = []
    screens = {}
    for v in VARIANTS:
        df = pd.read_parquet(OUT / f"grid_F0{v}.parquet")
        s = screen(df)
        s.to_parquet(OUT / f"screen_F0{v}.parquet")
        screens[v] = s
        q = s[s.n >= 100]
        top = q.sort_values("expR", ascending=False)
        rows.append(dict(lineage=LINEAGE, variant=v or "REAL", configs_n100=len(q),
                         share_pos=(q.expR > 0).mean(), share_pf13=(q.pf >= 1.3).mean(),
                         base_ok=int(s.base_ok.sum()), breadth_ok=int((s.base_ok & s.breadth_ok).sum()),
                         screen_pass=int(s.screen_pass.sum()),
                         top1_expR=top.expR.iloc[0], top10_mean_expR=top.expR.head(10).mean(),
                         top100_mean_expR=top.expR.head(100).mean(),
                         pass_long=int(s[s.screen_pass & (((s.side == "bounce") & s.level.isin(LOW)) | ((s.side == "breakout") & s.level.isin(UP)))].shape[0])))
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "placebo_whole_search.csv", index=False)
    print(t.round(3).to_string())
    return screens


from common import LOWER as LOW, UPPER as UP  # noqa: E402

if __name__ == "__main__":
    main()
