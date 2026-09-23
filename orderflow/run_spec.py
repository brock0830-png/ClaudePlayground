"""Run SPEC_value_area_tests.md end to end.

    python orderflow/run_spec.py signals    # base signal, replication counts, base table
    python orderflow/run_spec.py features   # stream aggTrades, V1/V2/V3/F1r + X1 (resumable per coin)
    python orderflow/run_spec.py report     # pass-rule tables -> results/SPEC_RESULTS.md
"""
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import numpy as np                                    # noqa: E402
import pandas as pd                                   # noqa: E402

from of import load, signals, spec_analysis, va_features   # noqa: E402
from of.config import DEV, HOLDOUT, PQ, RESULTS, SPLIT      # noqa: E402

SIG = RESULTS / "flush_signals.csv"
FEAT_DIR = PQ / "va_features"
FEAT = RESULTS / "va_features.parquet"
TARGET = 1968


def stage_signals():
    rows, allt = [], {}
    for s in DEV + HOLDOUT:
        h, f = load.hourly(s), load.funding(s)
        for mode in ["all", "episode", "nonoverlap"]:
            for oi_col in ["oi_usd", "oi"]:
                tr = signals.trades(s, h, f, mode=mode, oi_col=oi_col)
                allt[(s, mode, oi_col)] = tr
                rows.append(dict(sym=s, mode=mode, oi=oi_col, n=len(tr),
                                 n_2223=int((tr.t < SPLIT).sum()) if len(tr) else 0,
                                 mean_net=tr.net.mean() if len(tr) else np.nan))
    C = pd.DataFrame(rows)
    dev = C[C.sym.isin(DEV)].groupby(["mode", "oi"]).agg(n=("n", "sum"), n_2223=("n_2223", "sum")).reset_index()
    print("Replication counts on the 9 dev coins (target 1,968):")
    print(dev.to_string(index=False))
    cand = dev.copy()
    cand["gap"] = (cand.n - TARGET).abs()
    best = cand.sort_values("gap").iloc[0]                 # chosen on counts only (implementation notes)
    mode, oi_col = best["mode"], best["oi"]
    print(f"\nchosen: dedup={mode} oi={oi_col} ({best.n} dev signals)")
    T = pd.concat([allt[(s, mode, oi_col)] for s in DEV + HOLDOUT], ignore_index=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    T.to_csv(SIG, index=False)
    dev.to_csv(RESULTS / "replication_counts.csv", index=False)
    C.to_csv(RESULTS / "replication_counts_by_coin.csv", index=False)
    (RESULTS / "dedup_rule.txt").write_text(f"dedup={mode} oi={oi_col}\n")
    print(spec_analysis.base_table(T).to_string(index=False))


def read_signals():
    T = pd.read_csv(SIG)
    for c in ["t", "entry_t", "exit_t"]:
        T[c] = pd.to_datetime(T[c], utc=True)
    return T


def one_coin(sym):
    out = FEAT_DIR / f"{sym}.parquet"
    if out.exists():
        return sym, "cached"
    t0 = time.time()
    try:
        T = read_signals()
        tr = T[T.sym == sym]
        F = va_features.coin_features(sym, tr, load.hourly(sym), load.klines_1m(sym), load.funding(sym), inflight=4)
        out.parent.mkdir(parents=True, exist_ok=True)
        F.to_parquet(out)
        return sym, f"{len(F)} signals, {int(F.missing.sum()) if len(F) else 0} missing, {time.time() - t0:.0f}s"
    except Exception:
        return sym, "FAILED\n" + traceback.format_exc()


def stage_features(syms=None, procs=4):
    syms = syms or DEV + HOLDOUT
    with ProcessPoolExecutor(procs) as ex:
        for f in as_completed([ex.submit(one_coin, s) for s in syms]):
            print(*f.result(), flush=True)
    parts = [pd.read_parquet(FEAT_DIR / f"{s}.parquet") for s in DEV + HOLDOUT if (FEAT_DIR / f"{s}.parquet").exists()]
    F = pd.concat([p for p in parts if len(p)], ignore_index=True)
    F.to_parquet(FEAT)
    print("features:", len(F), "rows ->", FEAT)


def stage_report():
    F = pd.read_parquet(FEAT)
    T = read_signals()
    base = spec_analysis.base_table(T)
    ft = spec_analysis.feature_table(F)
    xt = spec_analysis.x1_table(F)
    old = replication_old_features(F)
    lines = ["# SPEC_value_area_tests.md: results", "",
             f"Generated {pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M} UTC by `orderflow/run_spec.py report`.",
             f"Signal definition: `{(RESULTS / 'dedup_rule.txt').read_text().strip()}`.", "",
             "## Base signal", "", base.to_markdown(index=False), "",
             f"Signals with footprints: {int((F.missing == 0).sum())} of {len(F)} "
             f"(dropped {int(F.missing.sum())}: a missing aggTrades day or < 100 trades in a window).", "",
             "## Features V1, V2, V3, F1r", "", ft.to_markdown(index=False), "",
             "## Exit test X1", "", xt.to_markdown(index=False), "", f"X1 PASS: {xt.attrs['PASS']}", "",
             "## Replication check: earlier footprint features F1-F4 on the dev coins (not re-judged)", "",
             old.to_markdown(index=False), ""]
    (RESULTS / "SPEC_RESULTS.md").write_text("\n".join(lines))
    print("\n".join(lines))


def replication_old_features(F):
    """fp_analyze.py logic on our dev signals: pooled day-t over both dev periods."""
    F = F[(F.missing == 0) & F.sym.isin(DEV)]
    A, B = F[F.t < SPLIT], F[F.t >= SPLIT]
    rows = []
    for k, kind, good in [("F1_trapped", "cont", "high"), ("F2_absorb", "bin", 1), ("F3_thin", "cont", "low"),
                          ("F4_stacked", "bin", 1)]:
        if kind == "cont":
            q1, q2 = A[k].quantile([1 / 3, 2 / 3])
            g = (lambda x, k=k, q2=q2: x[x[k] > q2]) if good == "high" else (lambda x, k=k, q1=q1: x[x[k] <= q1])
            b = (lambda x, k=k, q1=q1: x[x[k] <= q1]) if good == "high" else (lambda x, k=k, q2=q2: x[x[k] > q2])
        else:
            g = lambda x, k=k: x[x[k] == 1]; b = lambda x, k=k: x[x[k] == 0]
        r = dict(feature=k)
        for lab, x in [("22-23", A), ("24-26", B)]:
            r[f"{lab} diff"] = round(100 * (g(x).net.mean() - b(x).net.mean()), 3)
            r[f"{lab} n good/bad"] = f"{len(g(x))}/{len(b(x))}"
        P = pd.concat([A, B])
        r["pooled day-t"] = round(spec_analysis.diff_t(g(P), b(P)), 2)
        rows.append(r)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    st = sys.argv[1]
    if st == "signals":
        stage_signals()
    elif st == "features":
        stage_features(sys.argv[2:] or None)
    elif st == "report":
        stage_report()
