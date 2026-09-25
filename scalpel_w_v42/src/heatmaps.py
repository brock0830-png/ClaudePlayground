"""MAP step: PF and net expectancy heatmaps over (pierce x stop x target), per level / side / unit.

One PNG per level-side-unit-metric. Panels: rows = pierce d, columns = entry style; each panel is
stop (rows) x target (columns). Reclaim styles use the D=1.5 slice (always defined). Cells with
fewer than 100 pooled in-sample trades are left blank. Pooled over tickers, 2013-2020.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402

from common import LINEAGE, OUT  # noqa: E402
from grid import D_PIERCE, STOP_NAMES, STYLES, TGT_NAMES  # noqa: E402

DIV = LinearSegmentedColormap.from_list(
    "div", ["#8f1d1c", "#e34948", "#f4b5b0", "#f0efec", "#9ec5f4", "#3987e5", "#104281"])
INK, MUTED, SURF = "#0b0b0b", "#52514e", "#fcfcfb"


def panel_matrix(sub, metric, targets):
    M = np.full((len(STOP_NAMES), len(targets)), np.nan)
    idx = {(r.stop, r.target): r for r in sub.itertuples()}
    for i, s in enumerate(STOP_NAMES):
        for j, t in enumerate(targets):
            r = idx.get((s, t))
            if r is not None and r.n >= 100:
                M[i, j] = getattr(r, metric)
    return M


def plot_one(p, level, side, unit, metric, outdir):
    sub = p[(p.level == level) & (p.side == side) & (p.unit == unit)]
    targets = [t for t in TGT_NAMES if not (side == "breakout" and t == "WO")]
    if metric == "expR":
        norm = TwoSlopeNorm(vcenter=0.0, vmin=-0.5, vmax=0.5)
        lab = "net expectancy (R per trade)"
    else:
        norm = TwoSlopeNorm(vcenter=1.0, vmin=0.5, vmax=2.0)
        lab = "profit factor (net $)"
    styles = list(STYLES.values())
    fig, axes = plt.subplots(len(D_PIERCE), len(styles), figsize=(2.0 * len(styles) + 1.2, 1.75 * len(D_PIERCE) + 0.8),
                             facecolor=SURF, squeeze=False)
    im = None
    for i, d in enumerate(D_PIERCE):
        for j, st in enumerate(styles):
            ax = axes[i, j]
            ax.set_facecolor(SURF)
            q = sub[(np.isclose(sub.d, d)) & (sub["style"] == st)]
            if side == "bounce" and st != "a_limit":
                q = q[np.isclose(q.D, 1.5)]
            M = panel_matrix(q, metric, targets)
            vals = np.clip(M, norm.vmin, norm.vmax)
            im = ax.imshow(vals, cmap=DIV, norm=norm, aspect="auto")
            ax.set_xticks(range(len(targets)))
            ax.set_yticks(range(len(STOP_NAMES)))
            ax.set_xticklabels([t.replace("t", "") for t in targets] if i == len(D_PIERCE) - 1 else [],
                               rotation=90, fontsize=6, color=MUTED)
            ax.set_yticklabels([s.replace("s", "") for s in STOP_NAMES] if j == 0 else [], fontsize=6, color=MUTED)
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.tick_params(length=0)
            if i == 0:
                ax.set_title(st, fontsize=8, color=INK)
            if j == 0:
                ax.set_ylabel(f"d={d:.2f}\nstop", fontsize=7, color=INK)
    fig.suptitle(f"{LINEAGE}  {level} {side} ({unit} units): {lab}, pooled IS 2013-2020, blank = n<100",
                 fontsize=9, color=INK)
    cb = fig.colorbar(im, ax=axes, shrink=0.5, pad=0.01)
    cb.ax.tick_params(labelsize=7, colors=MUTED)
    cb.outline.set_visible(False)
    fig.savefig(outdir / f"{level}_{side}_{unit}_{metric}.png", dpi=90, facecolor=SURF)
    plt.close(fig)


def main():
    outdir = OUT / "heatmaps"
    outdir.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(OUT / "grid_F0.parquet", columns=["level", "side", "unit", "d", "style", "D", "stop",
                                                            "target", "scope", "n", "expR", "pf"])
    p = df[df.scope == "POOLED"]
    for (level, side, unit), _ in p.groupby(["level", "side", "unit"]):
        for metric in ("expR", "pf"):
            plot_one(p, level, side, unit, metric, outdir)


if __name__ == "__main__":
    main()
