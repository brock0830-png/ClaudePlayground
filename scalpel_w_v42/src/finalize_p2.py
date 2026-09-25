"""Phase 2 gate table from stored outputs (validation_p2_holdouts.csv, validation_p2_loto.csv).
Never re-opens the holdouts."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, skew

from common import LINEAGE, OUT, ROOT
from deflate import dsr, sr0_floor
from finalize import n_trials


def gates():
    fin = pd.read_csv(ROOT / "finalists_p2.csv")
    v = pd.read_csv(OUT / "validation_p2_holdouts.csv")
    lo = pd.read_csv(OUT / "validation_p2_loto.csv")
    tr = pd.read_csv(OUT / "finalist_p2_trades_all.csv")
    T = n_trials()
    ne_txt = (OUT / "neff.txt").read_text().split()
    ne = int(ne_txt[0])
    fl_all = sr0_floor(T["var_sr"], T["n_all"])
    fl_eff = sr0_floor(T["var_sr"], ne)
    fl_null_eff = sr0_floor(1.0 / 188.0, ne)

    def get(fid, run, per, sc):
        q = v[(v.finalist == fid) & (v.run == run) & (v.period == per) & (v.scope == sc)]
        return q.iloc[0] if len(q) else None

    rows = []
    for f in fin.itertuples():
        bi = get(f.finalist, "base", "IS", "POOLED")
        b = get(f.finalist, "base", "OOS2", "POOLED")
        s2 = get(f.finalist, "slip2", "OOS2", "POOLED")
        m95 = get(f.finalist, "x0.95", "OOS2", "POOLED")
        m105 = get(f.finalist, "x1.05", "OOS2", "POOLED")
        plc = [get(f.finalist, r, "OOS2", "POOLED") for r in ("plc-0.30", "plc-0.15", "plc+0.15", "plc+0.30")]
        plc_e = np.array([p.expR if p is not None and p.n > 0 else np.nan for p in plc], float)
        gc = get(f.finalist, "base", "GC_HOLDOUT", "GC")
        gplc = [get(f.finalist, r, "GC_HOLDOUT", "GC") for r in ("plc-0.30", "plc-0.15", "plc+0.15", "plc+0.30")]
        gplc_e = np.array([p.expR if p is not None and p.n > 0 else np.nan for p in gplc], float)
        l = lo[lo.finalist == f.finalist]
        t_is = tr[(tr.finalist == f.finalist) & (tr.period == "IS")]
        sr = t_is.R.mean() / t_is.R.std(ddof=1) if len(t_is) > 2 else np.nan
        sk = float(skew(t_is.R)) if len(t_is) > 2 else 0.0
        ku = float(kurtosis(t_is.R, fisher=False)) if len(t_is) > 3 else 3.0
        parts = f.config.split("|")
        unit, d, stop = parts[2], float(parts[3][1:]), parts[6]
        conv = 1.0 if unit == "ATR" else 1.0 / 0.41
        s_units = float(stop[1:]) if stop.startswith("s") else np.nan
        small = (d > 0 and d * conv < 0.3) or (np.isfinite(s_units) and s_units * conv < 0.3)
        mult_na = m95 is None
        g = dict(lineage=LINEAGE, finalist=f.finalist, tier=f.tier, variant=f.variant, config=f.config,
                 IS_n=bi.n, IS_pf=bi.pf, IS_expR=bi.expR,
                 OOS2_n=b.n, OOS2_pf=b.pf, OOS2_expR=b.expR, OOS2_usd=b.usd,
                 G1_oos2=bool(b.n >= 100 and b.expR > 0 and b.exp_usd > 0 and b.pf >= 1.20),
                 LOTO_pos=int(l.positive.sum()), G2_loto=bool(l.positive.sum() >= 3),
                 OOS2_expR_slip2=s2.expR, G3_slip2=bool(s2.n > 0 and s2.expR > 0),
                 OOS2_expR_x095=np.nan if mult_na else m95.expR, OOS2_expR_x105=np.nan if mult_na else m105.expR,
                 G4_mult=True if mult_na else bool(m95.n > 0 and m105.n > 0 and m95.expR > 0 and m105.expR > 0),
                 OOS2_plc_mean=np.nanmean(plc_e), OOS2_plc_max=np.nanmax(plc_e),
                 G5_placebo=bool(b.n > 0 and b.expR > np.nanmean(plc_e)),
                 IS_SR_trade=sr, DSR_Nall=dsr(sr, len(t_is), sk, ku, fl_all) if np.isfinite(sr) else np.nan,
                 G6_dsr=bool(np.isfinite(sr) and sr > fl_all and sr > fl_eff),
                 G6_lenient=bool(np.isfinite(sr) and sr > fl_null_eff),
                 G7_needs_15m=bool(small),
                 GC_n=gc.n if gc is not None else 0, GC_pf=gc.pf if gc is not None else np.nan,
                 GC_expR=gc.expR if gc is not None else np.nan, GC_usd=gc.usd if gc is not None else 0.0,
                 GC_plc_mean=np.nanmean(gplc_e) if np.isfinite(gplc_e).any() else np.nan,
                 GC_plc_max=np.nanmax(gplc_e) if np.isfinite(gplc_e).any() else np.nan)
        g["G8_gc"] = bool(gc is not None and gc.n >= 20 and gc.expR > 0 and gc.exp_usd > 0
                          and (not np.isfinite(g["GC_plc_mean"]) or gc.expR > g["GC_plc_mean"]))
        names = ["G1 OOS2", "G2 LOTO", "G3 2x slip", "G4 x0.95/x1.05", "G5 placebo", "G6 DSR", "G8 GC holdout"]
        oks = [g["G1_oos2"], g["G2_loto"], g["G3_slip2"], g["G4_mult"], g["G5_placebo"], g["G6_dsr"], g["G8_gc"]]
        g["failed"] = ", ".join(n for n, ok in zip(names, oks) if not ok) + (", G7 path (needs 15m)" if small else "")
        g["all_gates"] = bool(all(oks) and not small)
        rows.append(g)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "validation_p2_gates.csv", index=False)
    pd.Series(dict(n_unique=T["n_unique"], n_all=T["n_all"], n_eff=ne, sr0_all=fl_all, sr0_eff=fl_eff,
                   sr0_null_eff=fl_null_eff)).to_csv(OUT / "deflation_p2.csv", header=False)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    print(gates().round(3).to_string())
