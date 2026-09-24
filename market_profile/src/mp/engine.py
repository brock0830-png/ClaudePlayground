"""Trade simulation, matched baseline, statistics and the fixed-schema ledger (spec sections 4, 6).

Fills: see path.py. Costs: 1 tick slippage per side plus $5 per round turn (spec section 1),
i.e. 2.4 ticks per ES round turn. Every result is also reported gross.

Matched baseline (spec section 4): for a trade entered at clock time tau with side s and exit rule
X, the baseline is the average price change from tau to X over every session in the same sample
(or every session with the same open location), taken with side s and the same costs. The
comparison statistic is the excess of each trade over its matched baseline mean, and
t = mean(excess) / (sd(excess) / sqrt(n)) [C20].
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .path import Path as PricePath
from .features import period_index

COST_TICKS = {"ES": 2 + 5 / 12.5, "NQ": 2 + 5 / 5.0}
TICK_USD = {"ES": 12.5, "NQ": 5.0}


@dataclass
class Trade:
    d: int                       # entry session index
    k: int                       # entry point index (global path)
    px: int                      # entry price, ticks
    side: int                    # +1 long, -1 short
    tau: object                  # entry clock minute, or "close"
    exit: tuple                  # ("close", n) or ("time", n, minute); n = sessions after entry session
    stop: float = math.nan       # stop level: touching it exits
    target: float = math.nan
    check_from: int = -1         # first point checked for stop/target (default k + 1)
    pc_stop: float = math.nan    # exit at a 30-minute close beyond this level (against the trade)
    tag: str = ""


class Ctx:
    """Everything the hypothesis generators need, for one market and one sample."""

    def __init__(self, sym: str, bars: pd.DataFrame, sessions: pd.DataFrame, D: pd.DataFrame, feats: list):
        self.sym = sym
        self.bars, self.S, self.D, self.F = bars, sessions.reset_index(drop=True), D, feats
        self.n = len(self.S)
        self.path = PricePath(bars["o"].to_numpy(), bars["h"].to_numpy(), bars["l"].to_numpy(), bars["c"].to_numpy())
        self.P, self.jump = self.path.P, self.path.jump
        self.minute = bars["minute"].to_numpy()
        self.b0 = self.S["b0"].to_numpy(); self.b1 = self.S["b1"].to_numpy()
        per = period_index(self.minute)
        last_in_period = np.r_[per[1:] != per[:-1], True]
        self.pend = np.zeros(len(self.P), dtype=bool)
        self.pend[4 * np.flatnonzero(last_in_period) + 3] = True
        self.offset = self.S["offset_t"].to_numpy() if "offset_t" in self.S else np.zeros(self.n, dtype=int)
        # kmat[d, m]: open point of the first bar at or after minute 570 + m in session d (-1: none)
        self.kmat = np.full((self.n, 406), -1, dtype=np.int64)
        grid = 570 + np.arange(406)
        for d in range(self.n):
            mm = self.minute[self.b0[d]:self.b1[d]]
            i = np.searchsorted(mm, grid)
            ok = i < len(mm)
            self.kmat[d, ok] = 4 * (self.b0[d] + i[ok])

    # ---- indexing helpers
    def bar_at(self, d: int, minute: int) -> int:
        k = self.k_open(d, minute)
        return k // 4 if k >= 0 else -1

    def k_open(self, d: int, minute: int) -> int:
        m = minute - 570
        if m < 0:
            return self.k_start(d)
        return int(self.kmat[d, m]) if m <= 405 else -1

    def k_close(self, d: int) -> int:
        return 4 * self.b1[d] - 1

    def k_start(self, d: int) -> int:
        return 4 * self.b0[d]

    def k_end(self, d: int) -> int:
        """One past the session's last point."""
        return 4 * self.b1[d]

    def period_k(self, d: int, j: int) -> tuple[int, int]:
        """Point range [k0, k1) of period j of session d."""
        m0 = 570 + 30 * j
        b0 = self.bar_at(d, m0)
        b1 = self.bar_at(d, m0 + 30)
        return 4 * b0, (4 * b1 if b1 >= 0 else self.k_end(d))

    def exit_point(self, d: int, rule: tuple) -> int:
        dd = d + rule[1]
        if dd >= self.n:
            return -1
        if rule[0] == "close":
            return self.k_close(dd)
        return self.k_open(dd, rule[2])

    def entry_point(self, d: int, tau) -> int:
        return self.k_close(d) if tau == "close" else self.k_open(d, tau)


def simulate(ctx: Ctx, tr: Trade) -> dict | None:
    kx = ctx.exit_point(tr.d, tr.exit)
    if kx < 0 or kx < tr.k:
        return None
    P, jump, s = ctx.P, ctx.jump, tr.side
    k0 = tr.check_from if tr.check_from >= 0 else tr.k + 1
    best = (kx, float(P[kx]), "time")
    seg = P[k0:kx + 1]
    if len(seg):
        if tr.stop == tr.stop:
            hit = seg <= tr.stop if s > 0 else seg >= tr.stop
            if hit.any():
                k = k0 + int(hit.argmax())
                if k < best[0] or (k == best[0] and best[2] == "time"):
                    best = (k, float(P[k]) if jump[k] else float(tr.stop), "stop")
        if tr.target == tr.target:
            hit = seg >= tr.target if s > 0 else seg <= tr.target
            if hit.any():
                k = k0 + int(hit.argmax())
                if k < best[0]:
                    best = (k, float(P[k]) if jump[k] else float(tr.target), "target")
        if tr.pc_stop == tr.pc_stop:
            pe = ctx.pend[k0:kx + 1]
            hit = pe & ((seg < tr.pc_stop) if s > 0 else (seg > tr.pc_stop))
            if hit.any():
                k = k0 + int(hit.argmax())
                if k < best[0]:
                    best = (k, float(P[k]), "pc_stop")
    kx, px_x, why = best
    gross = s * (px_x - tr.px)
    return dict(d=tr.d, date=ctx.S["date"].iloc[tr.d], side=s, tau=tr.tau, rule=tr.exit, entry=tr.px,
                exit=px_x, k_entry=tr.k, k_exit=kx, why=why, gross=gross,
                net=gross - COST_TICKS[ctx.sym], move=px_x - tr.px, tag=tr.tag,
                open_loc=ctx.D["open_loc"].iloc[tr.d])


def run_trades(ctx: Ctx, trades: list[Trade]) -> pd.DataFrame:
    """Simulate in time order, one open position at a time per evaluation [C21]."""
    out, last_exit = [], -1
    for tr in sorted(trades, key=lambda t: (t.k, t.d)):
        if tr.k < last_exit:
            continue
        r = simulate(ctx, tr)
        if r is None:
            continue
        out.append(r)
        last_exit = r["k_exit"]
    return pd.DataFrame(out)


class Baseline:
    """Unconditional moves from clock time tau to exit rule X, per session (cached)."""

    def __init__(self, ctx: Ctx, mask: np.ndarray | None = None):
        """mask: sessions that make up the stage's sample (default: all sessions in ctx). The
        confirm stage builds its context with earlier sessions for look-back only and passes the
        2017-2021 sessions here, so the baseline comes from the same sample as the trades."""
        self.ctx = ctx
        self.cache: dict = {}
        self.loc = ctx.D["open_loc"].to_numpy()
        self.mask = np.ones(ctx.n, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)

    def moves(self, tau, rule: tuple) -> np.ndarray:
        key = (tau, rule)
        if key not in self.cache:
            c = self.ctx
            d = np.arange(c.n)
            ke = 4 * c.b1 - 1 if tau == "close" else c.kmat[:, tau - 570]
            dd = d + rule[1]
            ok = dd < c.n
            kx = np.full(c.n, -1, dtype=np.int64)
            if rule[0] == "close":
                kx[ok] = 4 * c.b1[dd[ok]] - 1
            else:
                kx[ok] = c.kmat[dd[ok], rule[2] - 570]
            good = (ke >= 0) & (kx >= 0) & (kx >= ke)
            m = np.full(c.n, np.nan)
            m[good] = c.P[kx[good]] - c.P[ke[good]]
            self.cache[key] = m
        return self.cache[key]

    def expected(self, tau, rule: tuple, loc=None) -> float:
        m = self.moves(tau, rule)
        keep = self.mask if loc is None else self.mask & (self.loc == loc)
        m = m[keep]
        return float(np.nanmean(m)) if np.isfinite(m).any() else math.nan


def _t(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if len(x) < 2 or x.std(ddof=1) == 0:
        return math.nan
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def max_dd(net: np.ndarray) -> float:
    if not len(net):
        return 0.0
    eq = np.concatenate([[0.0], np.cumsum(net)])
    return float((np.maximum.accumulate(eq) - eq).max())


def evaluate(ctx: Ctx, base: Baseline, tr: pd.DataFrame, baseline_type: str) -> dict:
    cost = COST_TICKS[ctx.sym]
    if tr.empty:
        return dict(n_trades=0)
    rule = list(tr["rule"])
    exp_all = np.array([base.expected(t, r) for t, r in zip(tr["tau"], rule)])
    exp_loc = np.array([base.expected(t, r, l) for t, r, l in zip(tr["tau"], rule, tr["open_loc"])])
    s = tr["side"].to_numpy()
    ex_all = s * (tr["move"].to_numpy() - exp_all)
    ex_loc = s * (tr["move"].to_numpy() - exp_loc)
    primary, alt = (ex_loc, ex_all) if baseline_type == "loc" else (ex_all, ex_loc)
    exp_p = exp_loc if baseline_type == "loc" else exp_all
    net = tr["net"].to_numpy()
    return dict(
        n_trades=len(tr), n_long=int((s > 0).sum()), n_short=int((s < 0).sum()),
        win_rate=float((net > 0).mean()), mean_net_ticks=float(net.mean()),
        median_net_ticks=float(np.median(net)), mean_gross_ticks=float(tr["gross"].mean()),
        sd_net_ticks=float(net.std(ddof=1)) if len(net) > 1 else math.nan,
        t_net_vs_zero=_t(net), baseline_mean_net_ticks=float(np.nanmean(s * exp_p) - cost),
        mean_excess_ticks=float(np.nanmean(primary)), t_vs_baseline=_t(primary),
        t_vs_alt_baseline=_t(alt), max_dd_ticks=max_dd(net), total_net_ticks=float(net.sum()),
        total_net_usd=float(net.sum() * TICK_USD[ctx.sym]),
        exits=";".join(f"{k}:{v}" for k, v in tr["why"].value_counts().items()))


LEDGER_COLUMNS = [
    "ledger_id", "run_utc", "spec_sha256", "code_commit", "stage", "market", "family", "variant_id",
    "variant_desc", "eligible", "baseline", "sample_start", "sample_end", "n_trades", "n_long", "n_short",
    "win_rate", "mean_net_ticks", "median_net_ticks", "mean_gross_ticks", "sd_net_ticks", "t_net_vs_zero",
    "baseline_mean_net_ticks", "mean_excess_ticks", "t_vs_baseline", "t_vs_alt_baseline", "max_dd_ticks",
    "total_net_ticks", "total_net_usd", "exits", "meets_explore_rule", "notes",
]


def append_ledger(path: Path, row: dict) -> None:
    new = not path.exists()
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_COLUMNS, extrasaction="raise")
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in LEDGER_COLUMNS})
