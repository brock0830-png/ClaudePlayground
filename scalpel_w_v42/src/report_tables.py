"""Markdown tables for REPORT.md, read straight from the output CSVs (no numbers typed by hand)."""
import numpy as np
import pandas as pd

from common import LEVELS, OUT, TICKERS


def f(x, nd=3, sign=True):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "-"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def step1_table():
    df = pd.read_csv(OUT / "step1_level_strength.csv")
    p = df[df.scope == "POOLED"].set_index("level").loc[LEVELS]
    lines = ["| level | dist (sigma) | touches | P(rej 0.25) | placebo | excess [95% CI] | P(rej 0.5) excess [95% CI] | MFE6 - MAE6 excess | P(close thru) excess | per-ticker excess 0.25 (ES / NQ / CL / 6J) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for lv, r in p.iterrows():
        per = []
        for tk in TICKERS:
            q = df[(df.scope == tk) & (df.level == lv)].iloc[0]
            per.append(f(q["prej_0.25_xs"], 2))
        edge = (r["mfe_6b_xs"] - r["mae_6b_xs"])
        lines.append(f"| {lv} | {r.dist_sigma:.2f} | {int(r.n_touch)} | {r['prej_0.25']:.3f} | {r['prej_0.25_plc']:.3f} | "
                     f"{f(r['prej_0.25_xs'])} [{f(r['prej_0.25_xs_lo'], 2)}, {f(r['prej_0.25_xs_hi'], 2)}] | "
                     f"{f(r['prej_0.5_xs'])} [{f(r['prej_0.5_xs_lo'], 2)}, {f(r['prej_0.5_xs_hi'], 2)}] | "
                     f"{f(edge)} | {f(r['p_close_thru_xs'])} | {' / '.join(per)} |")
    return "\n".join(lines)


def placebo_table():
    t = pd.read_csv(OUT / "placebo_whole_search.csv")
    lines = ["| level set | configs with n >= 100 | share net positive | pass n/PF | + breadth | + plateau (screen pass) | top-10 mean expR | top-100 mean expR |",
             "|---|---|---|---|---|---|---|---|"]
    for r in t.itertuples():
        lines.append(f"| {r.variant.strip('_')} | {r.configs_n100:,} | {r.share_pos:.3f} | {r.base_ok} | {r.breadth_ok} | "
                     f"{r.screen_pass} | {r.top10_mean_expR:.3f} | {r.top100_mean_expR:.3f} |")
    return "\n".join(lines)


def family_table():
    rows = []
    for p in sorted(OUT.glob("families/round*_summary.csv")):
        d = pd.read_csv(p)
        d["round"] = p.stem.split("_")[0]
        rows.append(d)
    if not rows:
        return ""
    d = pd.concat(rows)
    lines = ["| round | variant | real passers | placebo passers (mean / max) | real top-10 expR | placebo top-10 (mean / max) | beats placebo (count / top-10) | family screen |",
             "|---|---|---|---|---|---|---|---|"]
    for r in d.itertuples():
        lines.append(f"| {r.round} | {r.variant} | {r.real_pass} | {r.plc_pass_mean:.0f} / {r.plc_pass_max} | {r.real_top10:.3f} | "
                     f"{r.plc_top10_mean:.3f} / {r.plc_top10_max:.3f} | {r.beats_plc_pass}/4, {r.beats_plc_top10}/4 | "
                     f"{'PASS' if r.family_pass else 'fail' + (' (b)' if r.screen_a else ' (a)')} |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(step1_table())
    print()
    print(placebo_table())
    print()
    print(family_table())
