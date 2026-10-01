"""
B2 (PROTOCOL_P4.md; descriptive, post-hoc): P3B decay analysis across every market tested so far.
  index markets : SPY 1994-2026, ES 2013-2026 (next open, % of raw price), QQQ IWM DIA
  other ETFs    : EFA EWG EWJ EWU (Phase 3 test) + the 15 fresh ETFs
  stocks        : the B4 point-in-time S&P 500 universe (variant a)
Excess by year: benchmark = random entries in the same market and year. Excess by VIX bucket (<15, 15-20,
20-25, >25) and trend state (ma50 > ma200): benchmark = random entries in the same market on days of the same
bucket / state. Fade decomposition (2005-2019 vs 2020-2026) over the 8 VIX x trend cells:
  change = composition (shift in cell weights at the old cell excess) + within-cell (change in cell excess).
"""
import json
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

from scalpel import p4

TAG = "B2_decay"
INDEX = ["SPY", "QQQ", "IWM", "DIA"]
OTHER = ["EFA", "EWG", "EWJ", "EWU"] + p4.FRESH
BUCKETS = [(-np.inf, 15, "<15"), (15, 20, "15-20"), (20, 25, "20-25"), (25, np.inf, ">25")]


def vix_bucket(v):
    out = np.full(len(v), "", dtype=object)
    for lo, hi, nm in BUCKETS:
        out[(v >= lo) & (v < hi)] = nm
    return out


def grouped_excess(D, t, mode, i0, i1, rng, labels, base_elig=None, raw_open=None):
    """excess of each trade vs random entries restricted to days carrying the trade's own label."""
    ex = np.full(len(t), np.nan)
    lab_t = labels[t["sig"].values]
    for g in pd.unique(lab_t):
        m = lab_t == g
        elig = labels == g
        if base_elig is not None:
            elig = elig & base_elig
        dr = p4.random_entries(D, t[m], mode, i0, i1, rng, n_draws=300, eligible=elig, raw_open=raw_open)
        ex[m] = t["ret"].values[m] - np.nanmean(dr)
    return ex


def analyse(D, t, mode, i0, i1, seed, base_elig=None, raw_open=None):
    rng = np.random.default_rng(seed)
    dates = pd.DatetimeIndex(D["date"])
    vb = vix_bucket(np.nan_to_num(D["vix"].values.astype(float), nan=-1))
    tr = np.where((D["ma50"] > D["ma200"]).values, "up", "down")
    t = t.copy()
    t["year"] = dates.year.values[t["sig"].values]
    t["vixb"] = vb[t["sig"].values]
    t["trend_state"] = tr[t["sig"].values]
    t["ex_year"] = grouped_excess(D, t, mode, i0, i1, rng, dates.year.values.astype(str), base_elig, raw_open)
    t["ex_vix"] = grouped_excess(D, t, mode, i0, i1, rng, vb, base_elig, raw_open)
    t["ex_trend"] = grouped_excess(D, t, mode, i0, i1, rng, tr, base_elig, raw_open)
    cell = np.char.add(vb.astype(str), np.char.add("|", tr.astype(str)))
    t["cell"] = cell[t["sig"].values]
    t["ex_cell"] = grouped_excess(D, t, mode, i0, i1, rng, cell, base_elig, raw_open)
    return t


def etf_job(sym):
    D = p4.load_etf(sym)
    i0, i1 = p4.window(D, "1994-01-03")
    t = p4.trades(D, p4.P3B, "close", i0, i1)
    return analyse(D, t, "close", i0, i1, zlib.crc32(sym.encode())).assign(group="index" if sym in INDEX else "other ETF")


def stock_job(args):
    import p4_B4_stocks as b4
    tk, P = args
    if not b4._G:
        b4._init()
    D = b4.stock_frame(tk, P)
    if len(D) < 300:
        return None
    i0 = max(252, int(np.searchsorted(D["date"].values, np.datetime64(b4.START))))
    spec = {"entry": list(p4.P3B["entry"]) + ["member>0.5"], "hold": p4.P3B["hold"]}
    t = p4.trades(D, spec, "close", i0, len(D))
    if len(t) == 0:
        return None
    return analyse(D, t, "close", i0, len(D), zlib.crc32(tk.encode()), base_elig=D["member"].values > 0.5) \
        .assign(group="stock")


def decompose(T, col="ex_cell"):
    pre, post = T[(T["year"] >= 2005) & (T["year"] <= 2019)], T[T["year"] >= 2020]
    wa, wb = pre["cell"].value_counts(normalize=True), post["cell"].value_counts(normalize=True)
    ea, eb = pre.groupby("cell")[col].mean(), post.groupby("cell")[col].mean()
    cells = sorted(set(wa.index) | set(wb.index))
    wa, wb, ea, eb = (s.reindex(cells).fillna(0.0) for s in (wa, wb, ea, eb))
    comp = float(((wb - wa) * ea).sum())
    within = float((wb * (eb - ea)).sum())
    return dict(pre_excess_pct=float(pre[col].mean() * 100), post_excess_pct=float(post[col].mean() * 100),
                composition_pct=comp * 100, within_cell_pct=within * 100,
                n_pre=len(pre), n_post=len(post),
                cells=pd.DataFrame({"w_pre": wa, "w_post": wb, "ex_pre_pct": ea * 100, "ex_post_pct": eb * 100})
                .round(3).to_dict("index"))


def main():
    p4.check_lock()
    out = p4.OUT / TAG
    if (out / "results.json").exists():
        raise SystemExit("B2 already ran once")
    out.mkdir(parents=True, exist_ok=True)
    parts = [etf_job(s) for s in INDEX + OTHER]
    es, raw = p4.load_es("all"), p4.es_raw_prices("all")
    t = p4.with_raw_denominator(p4.trades(es, p4.P3B, "next_open", 0, len(es)), raw)
    parts.append(analyse(es, t, "next_open", 0, len(es), 7, raw_open=raw["raw_open"].values).assign(group="index"))
    import p4_B4_stocks as b4
    M = pd.read_parquet(b4.SH / "membership.parquet")
    univ = sorted(set(M.loc[M["end"].isna() | (M["end"] > b4.START), "ticker"]) - b4.SEEN)
    prices = pd.read_parquet(b4.SH / "prices.parquet")
    jobs = [(tk, g) for tk, g in prices[prices["ticker"].isin(univ)].groupby("ticker")]
    with Pool(4, initializer=b4._init) as pool:
        for k, r in enumerate(pool.imap_unordered(stock_job, jobs, chunksize=4), 1):
            if r is not None:
                parts.append(r)
    T = pd.concat(parts, ignore_index=True)
    T.drop(columns=[c for c in ("entry", "exit") if c in T]).to_parquet(out / "trades.parquet", index=False)
    res = {}
    for g, G in T.groupby("group"):
        yr = G.groupby("year").agg(n=("ex_year", "size"), excess_pct=("ex_year", lambda x: x.mean() * 100),
                                   raw_pct=("ret", lambda x: x.mean() * 100))
        res[g] = {"by_year": yr.round(3).to_dict("index"),
                  "by_vix": G.groupby("vixb")["ex_vix"].agg(["size", "mean"]).assign(mean=lambda d: d["mean"] * 100)
                  .round(3).to_dict("index"),
                  "by_trend": G.groupby("trend_state")["ex_trend"].agg(["size", "mean"])
                  .assign(mean=lambda d: d["mean"] * 100).round(3).to_dict("index"),
                  "fade_2005_19_vs_2020_26": decompose(G)}
        for per, X in (("2005-2019", G[(G.year >= 2005) & (G.year <= 2019)]), ("2020-2026", G[G.year >= 2020])):
            m, lo, hi = p4.month_ci(X["ex_year"], X["date"])
            res[g][f"excess_{per}"] = [m * 100, lo * 100, hi * 100, len(X)]
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    p4.log([dict(test="B2", variant=f"decay {g}", system="P3B", universe=g, mode="close", cost_case="base",
                 n=int((T.group == g).sum()), verdict="descriptive",
                 note=f"2005-19 {res[g]['excess_2005-2019'][0]:.3f}% vs 2020-26 {res[g]['excess_2020-2026'][0]:.3f}%; "
                      f"composition {res[g]['fade_2005_19_vs_2020_26']['composition_pct']:.3f}%, within "
                      f"{res[g]['fade_2005_19_vs_2020_26']['within_cell_pct']:.3f}%") for g in res])
    for g in res:
        d = res[g]["fade_2005_19_vs_2020_26"]
        print(f"\n== {g}: 2005-19 {res[g]['excess_2005-2019']}  2020-26 {res[g]['excess_2020-2026']}")
        print(f"   fade: pre {d['pre_excess_pct']:.3f}% -> post {d['post_excess_pct']:.3f}%; composition "
              f"{d['composition_pct']:.3f}%, within-cell {d['within_cell_pct']:.3f}%")
        print("   by VIX:", res[g]["by_vix"], "\n   by trend:", res[g]["by_trend"])
        print("   cells:", json.dumps(d["cells"]))


if __name__ == "__main__":
    main()
