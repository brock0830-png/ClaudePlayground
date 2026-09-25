"""STEP 1 - level strength map with placebo control (in-sample weeks only).

For every level on every ticker-week, the first touch is the first 4h bar that trades through
the level (high > level for levels above WO, low < level below WO). Outcomes are measured in
units of the week's sigma (WO * vol / sqrt(52)).

Touch-bar convention (same for real and placebo levels): an extension beyond the level inside
the touch bar is credited (price must pass the level first); a move back toward WO inside the
touch bar is credited only if the bar CLOSES there (the low/high may precede the touch). If both
happen in one bar the outcome is 'ambiguous'. P(reject) = reject / (reject + extend + ambiguous),
i.e. ambiguous counts against the level. Unresolved touches (neither by week end) are excluded.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

from common import LEVELS, LINEAGE, OUT, TICKERS, UPPER
from data import load_all

XS = (0.25, 0.5)
WINDOWS = (1, 3, 6, 99)          # bars after the touch bar; 99 = to week end
SHIFTS = (-0.30, -0.15, 0.15, 0.30)


@njit(cache=True)
def touch_kernel(H, L, C, nb, P, d, sig, X):
    nW = H.shape[0]
    touched = np.zeros(nW, np.bool_)
    tbar = np.full(nW, -1, np.int64)
    outc = np.zeros(nW, np.int64)          # 0 unresolved, 1 reject, 2 extend, 3 ambiguous
    mfe = np.full((nW, 4), np.nan)
    mae = np.full((nW, 4), np.nan)
    wins = (1, 3, 6, 99)
    for w in range(nW):
        p = P[w]
        if not np.isfinite(p):
            continue
        n = nb[w]
        i = -1
        for j in range(n):
            if (d > 0 and H[w, j] > p) or (d < 0 and L[w, j] < p):
                i = j
                break
        if i < 0:
            continue
        # a touch in bar 0 whose open is already beyond the level is not a touch from WO's side
        touched[w] = True
        tbar[w] = i
        s = sig[w]
        x = X * s
        # ---- reject / extend
        if d > 0:
            ext = H[w, i] >= p + x
            rev = C[w, i] <= p - x
        else:
            ext = L[w, i] <= p - x
            rev = C[w, i] >= p + x
        if ext and rev:
            outc[w] = 3
        elif ext:
            outc[w] = 2
        elif rev:
            outc[w] = 1
        else:
            for j in range(i + 1, n):
                if d > 0:
                    e = H[w, j] >= p + x
                    r = L[w, j] <= p - x
                else:
                    e = L[w, j] <= p - x
                    r = H[w, j] >= p + x
                if e and r:
                    outc[w] = 3
                    break
                if e:
                    outc[w] = 2
                    break
                if r:
                    outc[w] = 1
                    break
        # ---- MFE / MAE toward WO (fade direction), in sigma
        if d > 0:
            f0 = max(0.0, p - C[w, i])
            a0 = max(0.0, H[w, i] - p)
        else:
            f0 = max(0.0, C[w, i] - p)
            a0 = max(0.0, p - L[w, i])
        for k in range(4):
            f = f0
            a = a0
            last = min(n - 1, i + wins[k])
            for j in range(i + 1, last + 1):
                if d > 0:
                    f = max(f, p - L[w, j])
                    a = max(a, H[w, j] - p)
                else:
                    f = max(f, H[w, j] - p)
                    a = max(a, p - L[w, j])
            mfe[w, k] = f / s
            mae[w, k] = a / s
    return touched, tbar, outc, mfe, mae


def level_dist(b, name):
    """Distance of a level from WO in sigma units (positive), per week."""
    return np.abs(b.levels[name] - b.wo) / b.sigma


def evaluate(b, P, d):
    res = {}
    for X in XS:
        t, tb, oc, mfe, mae = touch_kernel(b.H, b.L, b.C, b.nb, P, d, b.sigma, X)
        res[X] = oc
    res["touched"] = t
    res["tbar"] = tb
    res["mfe"] = mfe
    res["mae"] = mae
    wc = b.weeks["WC"].values
    res["close_thru"] = np.where(t, (d * (wc - P) > 0).astype(float), np.nan)
    return res


def summarize(r, idx=None):
    """Aggregate per-week outcomes (optionally over a bootstrap index)."""
    sl = (lambda a: a) if idx is None else (lambda a: a[idx])
    t = sl(r["touched"])
    out = {"n_touch": int(t.sum())}
    for X in XS:
        oc = sl(r[X])
        rej = np.sum(oc == 1); ext = np.sum(oc == 2); amb = np.sum(oc == 3)
        den = rej + ext + amb
        out[f"prej_{X}"] = rej / den if den else np.nan
        out[f"nres_{X}"] = int(den)
    mfe = sl(r["mfe"]); mae = sl(r["mae"])
    for k, wv in enumerate(WINDOWS):
        tag = "we" if wv == 99 else f"{wv}b"
        out[f"mfe_{tag}"] = np.nanmean(mfe[t, k]) if t.any() else np.nan
        out[f"mae_{tag}"] = np.nanmean(mae[t, k]) if t.any() else np.nan
    ct = sl(r["close_thru"])
    out["p_close_thru"] = np.nanmean(ct[t]) if t.any() else np.nan
    return out


def placebo_prices(b, name, shift):
    d = 1 if name in UPPER else -1
    dist = level_dist(b, name) + shift
    P = b.wo + d * dist * b.sigma
    P[dist < 0.05] = np.nan      # placebo would sit on or across WO: dropped
    return P


METRICS = ["prej_0.25", "prej_0.5", "mfe_1b", "mae_1b", "mfe_3b", "mae_3b", "mfe_6b", "mae_6b",
           "mfe_we", "mae_we", "p_close_thru"]


def run(nboot=2000, seed=7):
    rng = np.random.default_rng(seed)
    B = load_all()
    rows = []
    per = {}  # (tk, level) -> dict(real=res, plc=[res...])
    for tk, b in B.items():
        for name in LEVELS:
            d = 1 if name in UPPER else -1
            real = evaluate(b, b.levels[name], d)
            plc = [evaluate(b, placebo_prices(b, name, s), d) for s in SHIFTS]
            per[(tk, name)] = dict(real=real, plc=plc, d=d, dist=float(np.median(level_dist(b, name))))
    # ---- per ticker and pooled summaries with paired week bootstrap
    for scope in TICKERS + ["POOLED"]:
        tks = TICKERS if scope == "POOLED" else [scope]
        for name in LEVELS:
            def agg(idxmap):
                # pooled = concatenate weeks across tickers
                real_parts, plc_parts = [], [[] for _ in SHIFTS]
                for tk in tks:
                    e = per[(tk, name)]
                    ix = idxmap[tk]
                    real_parts.append({k: (v[ix] if isinstance(v, np.ndarray) else v) for k, v in e["real"].items()})
                    for j, p in enumerate(e["plc"]):
                        plc_parts[j].append({k: (v[ix] if isinstance(v, np.ndarray) else v) for k, v in p.items()})
                cat = lambda parts: {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
                s_real = summarize(cat(real_parts))
                s_plc = [summarize(cat(pp)) for pp in plc_parts]
                return s_real, s_plc
            base_idx = {tk: np.arange(len(B[tk].wo)) for tk in tks}
            s_real, s_plc = agg(base_idx)
            row = {"lineage": LINEAGE, "scope": scope, "level": name,
                   "side": "upper" if name in UPPER else "lower",
                   "dist_sigma": np.mean([per[(tk, name)]["dist"] for tk in tks]),
                   "n_touch": s_real["n_touch"], "touch_rate": s_real["n_touch"] / sum(len(B[tk].wo) for tk in tks)}
            for m in METRICS:
                pv = np.array([sp[m] for sp in s_plc], dtype=float)
                row[m] = s_real[m]
                row[m + "_plc"] = np.nanmean(pv)
                row[m + "_xs"] = s_real[m] - np.nanmean(pv)
            row["n_plc_used"] = int(np.sum(np.isfinite([sp["prej_0.25"] for sp in s_plc])))
            # bootstrap CI for the key excess metrics
            bx = {m: [] for m in ["prej_0.25", "prej_0.5", "mfe_6b", "mae_6b"]}
            for _ in range(nboot):
                idx = {tk: rng.integers(0, len(B[tk].wo), len(B[tk].wo)) for tk in tks}
                sr, sp = agg(idx)
                for m in bx:
                    bx[m].append(sr[m] - np.nanmean([q[m] for q in sp]))
            for m, v in bx.items():
                v = np.array(v, dtype=float)
                row[m + "_xs_lo"] = np.nanpercentile(v, 2.5)
                row[m + "_xs_hi"] = np.nanpercentile(v, 97.5)
                row[m + "_xs_p"] = float(np.mean(v <= 0)) if m != "mae_6b" else float(np.mean(v >= 0))
            rows.append(row)
    df = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    df.to_csv(OUT / "step1_level_strength.csv", index=False)
    return df, per, B


def dense_curve(B, step=0.05, lo=0.10, hi=2.50):
    """P(reject) as a function of distance from WO for arbitrary lines (the null curve)."""
    rows = []
    for tk, b in B.items():
        for d in (1, -1):
            for dist in np.arange(lo, hi + 1e-9, step):
                P = b.wo + d * dist * b.sigma
                r = evaluate(b, P, d)
                s = summarize(r)
                rows.append({"lineage": LINEAGE, "ticker": tk, "side": "upper" if d > 0 else "lower",
                             "dist_sigma": round(dist, 3), **s})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "step1_null_curve.csv", index=False)
    return df


if __name__ == "__main__":
    import time
    t0 = time.time()
    df, per, B = run()
    print("strength map", time.time() - t0)
    dc = dense_curve(B)
    print("null curve", time.time() - t0)
    pd.set_option("display.width", 250)
    cols = ["scope", "level", "dist_sigma", "n_touch", "prej_0.25", "prej_0.25_plc", "prej_0.25_xs",
            "prej_0.25_xs_lo", "prej_0.25_xs_hi", "prej_0.5_xs", "prej_0.5_xs_lo", "prej_0.5_xs_hi",
            "mfe_6b_xs", "mae_6b_xs", "p_close_thru_xs"]
    print(df[df.scope == "POOLED"][cols].round(3).to_string())
