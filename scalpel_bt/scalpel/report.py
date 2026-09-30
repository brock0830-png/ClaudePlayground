"""Full metric set for one strategy's trades (DEV or OOS), fixed-fractional account, plots."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .data import PT_USD
from .stats import boot_ci_mean, max_drawdown, profit_factor

MES_PT_USD = 5.0
MES_COST_USD = 3.0   # 1 tick slippage x2 ($2.50) + $0.25 commission x2 per round trip
VIX_BINS = [0, 15, 20, 30, 1000]
VIX_LABELS = ["<15", "15-20", "20-30", ">30"]


def daily_pnl(t: pd.DataFrame, col="net") -> pd.Series:
    """P&L booked on the exit trading day (points)."""
    d = pd.to_datetime(t["exit_time"]).dt.tz_localize(None).dt.normalize()
    return t.groupby(d)[col].sum()


def fixed_fractional(t: pd.DataFrame, start_eq=100_000.0, risk=0.01) -> pd.DataFrame:
    eq = start_eq
    rows = []
    for _, r in t.sort_values("entry_time").iterrows():
        per = r["risk"] * MES_PT_USD + MES_COST_USD
        k = int(np.floor(risk * eq / per)) if per > 0 else 0
        pnl = k * (r["net"] * MES_PT_USD) if k > 0 else 0.0
        eq += pnl
        rows.append((r["exit_time"], k, pnl, eq))
    return pd.DataFrame(rows, columns=["exit_time", "contracts", "pnl_usd", "equity"])


def full_metrics(t: pd.DataFrame, bdays: int | None = None) -> dict:
    x = t["net"].values
    n = len(x)
    if n == 0:
        return dict(trades=0)
    dp = daily_pnl(t)
    months = pd.to_datetime(t["exit_time"]).dt.tz_localize(None).dt.to_period("M")
    mp = t.groupby(months)["net"].sum()
    lo, hi = boot_ci_mean(x)
    rlo, rhi = boot_ci_mean(t["R"].values)
    # annualised Sharpe from daily P&L on all business days of the span
    span = pd.bdate_range(pd.to_datetime(t["entry_time"]).min().tz_localize(None).normalize(),
                          pd.to_datetime(t["exit_time"]).max().tz_localize(None).normalize())
    dfull = dp.reindex(span, fill_value=0.0)
    sh_ann = float(dfull.mean() / dfull.std(ddof=1) * np.sqrt(252)) if dfull.std() > 0 else np.nan
    ff = fixed_fractional(t)
    ffe = ff["equity"].values
    ff_dd = float((ffe / np.maximum.accumulate(np.r_[100_000.0, ffe])[1:] - 1).min()) if len(ffe) else 0.0
    yrs = max((span[-1] - span[0]).days / 365.25, 1e-9)
    return dict(
        trades=n, win_rate=float((x > 0).mean()), ev_pts=float(x.mean()), ev_usd_es=float(x.mean() * PT_USD),
        ev_ci95=(lo, hi), ev_R=float(t["R"].mean()), ev_R_ci95=(rlo, rhi),
        profit_factor=profit_factor(x), total_pts=float(x.sum()), total_usd_es=float(x.sum() * PT_USD),
        max_dd_pts=max_drawdown(x), worst_trade_pts=float(x.min()), best_trade_pts=float(x.max()),
        worst_month_pts=float(mp.min()), worst_month=str(mp.idxmin()), sharpe_per_trade=float(x.mean() / x.std(ddof=1)),
        sharpe_ann_daily=sh_ann, avg_bars_held=float(t["bars_held"].mean()),
        ff_final_equity=float(ffe[-1]) if len(ffe) else 100_000.0,
        ff_cagr=float((ffe[-1] / 100_000.0) ** (1 / yrs) - 1) if len(ffe) else 0.0,
        ff_max_dd=ff_dd, ff_trades_taken=int((ff["contracts"] > 0).sum()),
        skew=float(pd.Series(x).skew()), kurt=float(pd.Series(x).kurt() + 3.0),
    )


def by_year(t: pd.DataFrame) -> pd.DataFrame:
    return t.groupby("year").agg(trades=("net", "size"), win=("net", lambda s: (s > 0).mean()),
                                 ev_pts=("net", "mean"), total_pts=("net", "sum"), ev_R=("R", "mean"))


def by_vix(t: pd.DataFrame) -> pd.DataFrame:
    reg = pd.cut(t["vix_prev"], VIX_BINS, labels=VIX_LABELS, right=False)
    return t.groupby(reg, observed=False).agg(trades=("net", "size"), win=("net", lambda s: (s > 0).mean()),
                                              ev_pts=("net", "mean"), total_pts=("net", "sum"), ev_R=("R", "mean"))


def plot_equity(t: pd.DataFrame, path, title: str, jitter_curves: list | None = None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    tt = t.sort_values("exit_time")
    xt = pd.to_datetime(tt["exit_time"]).dt.tz_localize(None)
    ax = axes[0]
    if jitter_curves:
        for k, (jx, jy) in enumerate(jitter_curves):
            ax.plot(jx, jy, color="#b8b8b8", lw=0.6, alpha=0.5, label="jittered levels" if k == 0 else None)
    ax.plot(xt, tt["net"].cumsum().values, color="#1f5fa8", lw=1.8, label="strategy (net pts, 1 ES)")
    ax.axhline(0, color="#555", lw=0.8)
    ax.set_ylabel("cumulative net points")
    ax.set_title(title, fontsize=11)
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    ax.grid(alpha=0.25)
    ff = fixed_fractional(tt)
    axes[1].plot(pd.to_datetime(ff["exit_time"]).dt.tz_localize(None), ff["equity"].values, color="#2a7d4f", lw=1.5)
    axes[1].axhline(100_000, color="#555", lw=0.8)
    axes[1].set_ylabel("$ equity (1% risk, MES)")
    axes[1].grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
