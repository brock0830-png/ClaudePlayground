"""
POST-HOC (after the one-shot Phase 3 test; no rule changed): the seven test markets crash on the same days,
so pooled trades are not independent. Re-estimate the pooled mean's 95% CI by resampling calendar MONTHS
(all trades signalled in a month move together), and report the share of months with a positive sum.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from scalpel.data import RESULTS

OUT = RESULTS / "p3"
res = {}
rng = np.random.default_rng(5)
for name in ["P2A_reference", "P3A_stack3_IBS_VIX", "P3B_oversold_score90", "P3C_momentum126"]:
    t = pd.read_csv(OUT / f"test_trades_{name}.csv", parse_dates=["date"])
    m = t.groupby(t["date"].dt.to_period("M"))["ret"].agg(["sum", "size"])
    S, N = m["sum"].values, m["size"].values
    idx = rng.integers(0, len(m), size=(10000, len(m)))
    boot = S[idx].sum(axis=1) / N[idx].sum(axis=1)
    res[name] = {"months_with_trades": int(len(m)), "mean_pct": float(S.sum() / N.sum() * 100),
                 "month_clustered_ci95_pct": [float(np.quantile(boot, 0.025) * 100), float(np.quantile(boot, 0.975) * 100)],
                 "share_months_positive": float((S > 0).mean())}
    print(name, res[name])
(OUT / "test_posthoc_clustered.json").write_text(json.dumps(res, indent=1))
