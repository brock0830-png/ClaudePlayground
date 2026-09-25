"""Gate table, per-ticker / per-year tables and deflation numbers for the frozen finalists.
Reads only stored outputs (validation_oos.csv, validation_loto.csv, screens) - never re-opens 2021+.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, skew

from common import LINEAGE, OUT, ROOT, TICKERS
from deflate import dsr, sr0_floor

FAM = OUT / "families"


def n_trials():
    """Honest N: every real-level config evaluated in F0 and every EXPAND variant (screens on disk),
    plus the pre-fix sizing run of F0 and round 1 (same configs, evaluated and looked at)."""
    files = [OUT / "screen_F0.parquet"] + [p for p in sorted(FAM.glob("screen_*.parquet")) if "_shift" not in p.stem]
    n_unique = 0
    srs = []
    for p in files:
        s = pd.read_parquet(p, columns=["n", "expR", "sdR"])
        n_unique += len(s)
        q = s[(s.n >= 100) & (s.sdR > 0)]
        srs.append((q.expR / q.sdR).values)
    stale = OUT / "stale"
    n_prefix = 0
    if stale.exists():
        n_prefix += 229_068 * (1 + len([p for p in (stale / "families_prefix").glob("screen_*.parquet") if "_shift" not in p.stem]))
    sr = np.concatenate(srs)
    return dict(n_unique=n_unique, n_all=n_unique + n_prefix, var_sr=float(np.var(sr, ddof=1)), n_sr=len(sr))


def n_eff():
    p = OUT / "neff.txt"
    return int(p.read_text().split()[0]) if p.exists() else None


def gates():
    fin = pd.read_csv(ROOT / "finalists.csv")
    v = pd.read_csv(OUT / "validation_oos.csv")
    lo = pd.read_csv(OUT / "validation_loto.csv")
    tr = pd.read_csv(OUT / "finalist_trades_all.csv", parse_dates=["week", "entry_time", "exit_time"])
    T = n_trials()
    ne = n_eff()
    floor_all = sr0_floor(T["var_sr"], T["n_all"])
    floor_eff = sr0_floor(T["var_sr"], ne) if ne else np.nan
    rows = []

    def get(fid, run, per, sc="POOLED"):
        q = v[(v.finalist == fid) & (v.run == run) & (v.period == per) & (v.scope == sc)]
        return q.iloc[0] if len(q) else None

    for f in fin.itertuples():
        b = get(f.finalist, "base", "OOS")
        bi = get(f.finalist, "base", "IS")
        plc = [get(f.finalist, r, "OOS") for r in ("plc-0.30", "plc-0.15", "plc+0.15", "plc+0.30")]
        plc_e = np.array([p.expR if p is not None and p.n > 0 else np.nan for p in plc], float)
        s2 = get(f.finalist, "slip2", "OOS")
        m95 = get(f.finalist, "x0.95", "OOS")
        m105 = get(f.finalist, "x1.05", "OOS")
        l = lo[lo.finalist == f.finalist]
        t_is = tr[(tr.finalist == f.finalist) & (tr.period == "IS")]
        sr = t_is.R.mean() / t_is.R.std(ddof=1) if len(t_is) > 2 else np.nan
        sk = float(skew(t_is.R)) if len(t_is) > 2 else 0.0
        ku = float(kurtosis(t_is.R, fisher=False)) if len(t_is) > 3 else 3.0
        # path-resolution flag: stop distance and pierce vs ATR at the median trade
        parts = f.config.split("|")
        unit, d = parts[2], float(parts[3][1:])
        g = dict(lineage=LINEAGE, finalist=f.finalist, variant=f.variant, config=f.config,
                 IS_n=bi.n, IS_pf=bi.pf, IS_expR=bi.expR,
                 OOS_n=b.n, OOS_wr=b.wr, OOS_pf=b.pf, OOS_expR=b.expR, OOS_exp_usd=b.exp_usd, OOS_usd=b.usd,
                 OOS_maxdd=b.maxdd_usd,
                 G1_oos=bool(b.n >= 100 and b.expR > 0 and b.exp_usd > 0 and b.pf >= 1.20),
                 LOTO_pos=int(l.positive.sum()), G2_loto=bool(l.positive.sum() >= 3),
                 OOS_expR_slip2=s2.expR, G3_slip2=bool(s2.n > 0 and s2.expR > 0),
                 OOS_expR_x095=m95.expR, OOS_expR_x105=m105.expR,
                 G4_mult=bool(m95.n > 0 and m105.n > 0 and m95.expR > 0 and m105.expR > 0),
                 OOS_plc_mean=np.nanmean(plc_e), OOS_plc_max=np.nanmax(plc_e),
                 G5_placebo=bool(np.isfinite(b.expR) and b.expR > np.nanmean(plc_e)),
                 IS_SR_trade=sr, SR0_Nall=floor_all, SR0_Neff=floor_eff,
                 DSR_Nall=dsr(sr, len(t_is), sk, ku, floor_all) if np.isfinite(sr) else np.nan,
                 G6_dsr=bool(np.isfinite(sr) and sr > floor_all and (not np.isfinite(floor_eff) or sr > floor_eff)))
        # G7: resolution needed when pierce or stop < 0.3 ATR (sigma units converted with the median ATR/sigma)
        atr_per_sig = 0.41
        stop = parts[6]
        s_units = float(stop[1:]) if stop.startswith("s") else np.nan
        conv = 1.0 if unit == "ATR" else 1.0 / atr_per_sig
        small = (d > 0 and d * conv < 0.3) or (np.isfinite(s_units) and s_units * conv < 0.3)
        g["G7_needs_15m"] = bool(small)
        gs = [g["G1_oos"], g["G2_loto"], g["G3_slip2"], g["G4_mult"], g["G5_placebo"], g["G6_dsr"]]
        g["all_gates"] = bool(all(gs) and not small)
        g["failed"] = ", ".join(n for n, ok in zip(["G1 OOS", "G2 LOTO", "G3 2x slip", "G4 x0.95/x1.05",
                                                     "G5 placebo", "G6 DSR"], gs) if not ok) + (
            (", G7 path (needs 15m)" if small else ""))
        rows.append(g)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "validation_gates.csv", index=False)
    meta = dict(n_unique=T["n_unique"], n_all=T["n_all"], n_eff=ne, var_sr=T["var_sr"], n_sr=T["n_sr"],
                sr0_all=floor_all, sr0_eff=floor_eff)
    pd.Series(meta).to_csv(OUT / "deflation.csv", header=False)
    return df, meta


def year_table(fid):
    tr = pd.read_csv(OUT / "finalist_trades_all.csv", parse_dates=["week", "exit_time"])
    t = tr[tr.finalist == fid].copy()
    rows = []
    for (tk, yr), g in list(t.groupby(["ticker", "year"])) + [(("ALL", yr), g) for yr, g in t.groupby("year")]:
        p = g.pnl_usd.values
        gl = -p[p < 0].sum()
        eq = np.cumsum(g.sort_values("exit_time").pnl_usd.values)
        dd = (np.maximum.accumulate(np.maximum(eq, 0)) - eq).max() if len(eq) else 0
        rows.append(dict(lineage=LINEAGE, finalist=fid, ticker=tk, year=yr, period="OOS" if yr >= 2021 else "IS",
                         n=len(g), wr=(g.R > 0).mean(), pf=p[p > 0].sum() / gl if gl > 0 else np.inf,
                         expR=g.R.mean(), usd=p.sum(), maxdd_usd=dd))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df, meta = gates()
    print(meta)
    pd.set_option("display.width", 250)
    print(df.round(3).to_string())
