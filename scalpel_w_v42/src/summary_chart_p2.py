"""Phase 2 finalists: in-sample vs 2021+ second look, with the second-look placebo range."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from common import LINEAGE, OUT  # noqa: E402

INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
IS_C, OOS_C, PLC_C = "#2a78d6", "#eb6834", "#c3c2b7"


def main():
    g = pd.read_csv(OUT / "validation_p2_gates.csv").iloc[::-1].reset_index(drop=True)
    v = pd.read_csv(OUT / "validation_p2_holdouts.csv")
    fig, ax = plt.subplots(figsize=(9.5, 6.6), facecolor=SURF)
    ax.set_facecolor(SURF)
    for i, r in g.iterrows():
        plc = v[(v.finalist == r.finalist) & (v.period == "OOS2") & (v.scope == "POOLED") & v.run.str.startswith("plc")]
        ax.plot([plc.expR.min(), plc.expR.max()], [i, i], color=PLC_C, lw=7, solid_capstyle="round", zorder=1,
                label="2021+ placebo levels (min-max of 4 shifts)" if i == 0 else None)
        ax.plot([r.IS_expR, r.OOS2_expR], [i, i], color=GRID, lw=1.5, zorder=2)
        ax.scatter(r.IS_expR, i, s=64, facecolor=SURF, edgecolor=IS_C, lw=2, zorder=3,
                   label="in-sample 2013-2020" if i == 0 else None)
        ax.scatter(r.OOS2_expR, i, s=64, color=OOS_C, edgecolor=SURF, lw=2, zorder=4,
                   label="2021-2026 second look" if i == 0 else None)
    ax.set_yticks(range(len(g)))
    ax.set_yticklabels([f"{r.finalist} {r.tier}  {r.variant}: {r.config.split('|')[0]} {r.config.split('|')[1]}"
                        for _, r in g.iterrows()], fontsize=8, color=INK)
    ax.axvline(0, color=MUTED, lw=1)
    ax.set_xlabel("net expectancy per trade (R), pooled ES / NQ / CL / 6J, after costs", fontsize=9, color=INK)
    ax.tick_params(axis="x", colors=MUTED, labelsize=8)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.suptitle(f"{LINEAGE} phase 2: only the 'reclaim prior value from below' rules (P02, P13) held up after 2020",
                 fontsize=10, color=INK, x=0.02, ha="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.35, -0.09), ncol=3, fontsize=8, frameon=False, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(OUT / "finalists_p2_is_vs_oos2.png", dpi=130, facecolor=SURF)


if __name__ == "__main__":
    main()
