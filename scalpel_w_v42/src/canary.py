"""STEP 0 canary + full-history check of the level engine against the ES export.

Only week opens and level columns are read here (level math), never price outcomes, so this
does not touch the sealed 2021+ outcomes.
"""
import sys

import numpy as np
import pandas as pd

from common import DATA, LINEAGE, OUT
from data import read_bars, weekly_levels

TOL = 0.05
CANARY = {
    "ES": dict(WO=7722.00, GB_TOP=8070.75, GB_BOT=7912.99, RB_TOP=7515.92, RB_BOT=7370.84, _sigma=198.54),
    "GC": dict(WO=4413.00, GB_TOP=4666.18, GB_BOT=4575.50, RB_TOP=4299.14, RB_BOT=4212.94),
}
EXPORT_COLS = {"W GB Top": "GB_TOP", "W GB Bot": "GB_BOT", "WTH2": "WTH2", "WTH1": "WTH1",
               "W RB Top": "RB_TOP", "W RB Bot": "RB_BOT", "WTL1": "WTL1", "WTL2": "WTL2",
               "WRH": "WRH", "WRL": "WRL", "W Rng T Hi": "RNG_T_HI", "W Rng T Lo": "RNG_T_LO",
               "W Rng B Hi": "RNG_B_HI", "W Rng B Lo": "RNG_B_LO", "W GP T Out": "GP_T_OUT",
               "W GP T In": "GP_T_IN", "W GP B In": "GP_B_IN", "W GP B Out": "GP_B_OUT"}


def main():
    OUT.mkdir(exist_ok=True)
    lines = [f"# {LINEAGE} canary report", ""]
    ok = True
    # ES: WO computed from the data (first 4h open of the week of 2026-09-21)
    bars = read_bars("ES")
    wk = pd.Timestamp("2026-09-21")
    wo_es = float(bars.loc[bars["week"] == wk, "open"].iloc[0])
    for tk, ref in CANARY.items():
        wo = wo_es if tk == "ES" else ref["WO"]   # no GC bars supplied: WO taken from the prompt
        L = weekly_levels(tk, np.array([wo]))
        L["WO"] = np.array([wo])
        for k, v in ref.items():
            got = float(L[k][0])
            err = abs(got - v)
            ok &= err <= TOL
            lines.append(f"{tk} {k:7s} ref {v:10.2f}  got {got:12.4f}  err {err:.4f}  {'ok' if err <= TOL else 'FAIL'}")
    lines.append("")
    # Full-history check: every ES level column vs the TradingView export, per week
    raw = pd.read_csv(DATA / "ES_240.csv")
    raw["week"] = bars["week"].values
    first = raw.groupby("week").first()
    wo_bucket = bars.groupby("week")["open"].first()
    same_wo = np.isclose(first["WO"].values, wo_bucket.values)
    L = weekly_levels("ES", first["WO"].values)
    worst = 0.0
    for col, name in EXPORT_COLS.items():
        worst = max(worst, float(np.nanmax(np.abs(first[col].values - L[name]))))
    lines.append(f"ES export check: {len(first)} weeks; level math from exported WO, worst abs error "
                 f"across 18 level columns = {worst:.2e} pt")
    lines.append(f"ES export WO == first 4h open of Sunday-18:00 bucket in {same_wo.sum()}/{len(first)} weeks; "
                 f"differences: " + ", ".join(str(d.date()) for d in first.index[~same_wo]))
    lines.append("(the differing weeks are the partial first week and TradingView holiday-week boundary quirks; "
                 "this study uses the Sunday-18:00 bucket as the prompt specifies)")
    ok &= worst <= TOL
    lines.append("")
    lines.append("CANARY PASS" if ok else "CANARY FAIL")
    txt = "\n".join(lines)
    (OUT / "canary.txt").write_text(txt + "\n")
    print(txt)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
