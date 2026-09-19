"""Build spliced and simulated total-return series for the instrument set.

Outputs data/proxies/panel.parquet: daily total-return *index levels* (start
at 1.0) on the SPY trading calendar, plus data/proxies/meta.json with
calibration results. Every proxy is documented in PROXY_VALIDATION.md.

Conventions
- rf: daily risk-free accrual. 3-month CMT / 252 while available (1997-01 to
  2007-06), then BIL daily total return plus BIL expense ratio / 252.
- Bond proxies: constant-maturity par-bond total return from CMT yields.
- Equity proxies: price-index return plus a calibrated constant daily carry.
- Leveraged proxies: L * base return - (L-1) * (rf + spread) - ER/252 with
  spread calibrated on the live overlap.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from data import load_close, load_treasury, trading_calendar

OUT = Path(__file__).resolve().parents[1] / "data" / "proxies"
START = "1997-01-02"

# Expense ratios (annual, decimal). Current prospectus values.
ER = {
    "SPY": 0.000945, "QQQ": 0.0020, "IWM": 0.0019, "DIA": 0.0016,
    "TLT": 0.0015, "IEF": 0.0015, "SHY": 0.0015, "BIL": 0.001356, "SHV": 0.0015,
    "GLD": 0.0040, "SLV": 0.0050, "DBC": 0.0085, "USO": 0.0060, "EDV": 0.0005,
    "SSO": 0.0089, "UPRO": 0.0091, "SPXL": 0.0091, "QLD": 0.0095, "TQQQ": 0.0084,
    "UBT": 0.0095, "TMF": 0.0106, "UST": 0.0095, "UGL": 0.0095,
}

# Leveraged fund -> (base series, leverage)
LEVERED = {
    "SSO": ("SPY", 2), "UPRO": ("SPY", 3), "SPXL": ("SPY", 3),
    "QLD": ("QQQ", 2), "TQQQ": ("QQQ", 3),
    "UBT": ("TLT", 2), "TMF": ("TLT", 3), "UST": ("IEF", 2), "UGL": ("GLD", 2),
}


def par_bond_tr(y: pd.Series, maturity: float) -> pd.Series:
    """Daily total return of a constant-maturity par bond (semiannual coupons).

    Each day the bond bought yesterday at par with coupon y[t-1] is revalued at
    today's yield y[t]; accrued coupon y[t-1]/252 is added.
    """
    y = y.astype(float)
    c = y.shift(1)
    n = 2 * maturity
    v = (1 + y / 2) ** (-n)
    price = (c / y) * (1 - v) + v
    r = price - 1 + c / 252
    return r.dropna()


def ann_stats(diff: pd.Series) -> dict:
    """Tracking error (annualised std of daily return difference) and drift (annualised mean)."""
    return {"te_ann": float(diff.std() * np.sqrt(252)), "drift_ann": float(diff.mean() * 252), "n": int(len(diff))}


def splice(early_ret: pd.Series, live_ret: pd.Series) -> pd.Series:
    """Use live returns from their first date; proxy returns before that."""
    first = live_ret.first_valid_index()
    out = pd.concat([early_ret[early_ret.index < first], live_ret[live_ret.index >= first]])
    return out[~out.index.duplicated(keep="last")].sort_index()


def build(verbose=True) -> tuple[pd.DataFrame, dict]:
    cal = trading_calendar(START)
    meta = {}
    R = {}  # daily simple returns

    # ---- risk free ----------------------------------------------------
    tsy = load_treasury().reindex(cal).ffill(limit=5)
    bil = load_close("BIL").reindex(cal).pct_change()
    rf_cmt = (tsy["m3"] / 252)
    rf = rf_cmt.copy()
    bil_start = load_close("BIL").index[0]
    rf.loc[cal >= bil_start] = (bil + ER["BIL"] / 252).loc[cal >= bil_start]
    rf = rf.ffill()
    overlap = (cal >= bil_start) & (cal <= "2007-06-29")
    meta["rf"] = {"cmt_until": str(bil_start.date()), **ann_stats((bil + ER["BIL"] / 252 - rf_cmt)[overlap].dropna())}
    R["CASH"] = rf

    # ---- plain ETFs with full history in the window ----------------------
    for s in ["SPY", "QQQ", "IWM", "DIA", "TLT", "IEF", "SHY", "GLD", "SLV", "DBC", "USO", "EDV", "BIL", "SHV"]:
        R[s] = load_close(s).reindex(cal).pct_change()

    # ---- equity proxies: price index + calibrated carry -----------------
    for etf, idx in [("QQQ", "NDX"), ("IWM", "RUT"), ("SPY", "GSPC")]:
        p = load_close(idx).reindex(cal).ffill(limit=3).pct_change()
        live = R[etf]
        both = pd.concat([live, p], axis=1, keys=["live", "idx"]).dropna()
        early = both.iloc[:5 * 252]
        carry = float((early.live - early.idx).mean())  # daily carry from first 5y of overlap
        sim = p + carry
        d = (both.live - (both.idx + carry))
        # split-half drift check
        h = len(both) // 2
        c1 = float((both.live - both.idx).iloc[:h].mean()); c2 = float((both.live - both.idx).iloc[h:].mean())
        meta[f"{etf}_proxy"] = {"index": idx, "carry_ann": carry * 252, "carry_window": "first 5y of overlap",
                                "carry_full_overlap_ann": float((both.live - both.idx).mean() * 252),
                                "carry_first_half_ann": c1 * 252, "carry_second_half_ann": c2 * 252,
                                "oos_drift_ann_if_calibrated_on_first_half": (c2 - c1) * 252,
                                **ann_stats(d), "live_start": str(live.first_valid_index().date())}
        R[etf + "_X"] = splice(sim, live)

    # ---- gold -----------------------------------------------------------
    gc = load_close("GCUSD").reindex(cal).ffill(limit=3).pct_change()
    live = R["GLD"]
    both = pd.concat([live, gc], axis=1, keys=["live", "idx"]).dropna()
    carry = float((both.iloc[:5 * 252].live - both.iloc[:5 * 252].idx).mean())
    h = len(both) // 2
    c1 = float((both.live - both.idx).iloc[:h].mean()); c2 = float((both.live - both.idx).iloc[h:].mean())
    meta["GLD_proxy"] = {"index": "GCUSD", "carry_ann": carry * 252, "carry_window": "first 5y of overlap",
                         "carry_full_overlap_ann": float((both.live - both.idx).mean() * 252), "carry_first_half_ann": c1 * 252,
                         "carry_second_half_ann": c2 * 252, "oos_drift_ann_if_calibrated_on_first_half": (c2 - c1) * 252,
                         **ann_stats(both.live - (both.idx + carry)), "live_start": str(live.first_valid_index().date())}
    R["GLD_X"] = splice(gc + carry, live)

    # ---- bond proxies from CMT yields ------------------------------------
    bond_specs = {"TLT": [("y20", 20.0), ("y20", 25.0), ("y30", 30.0)],
                  "IEF": [("y7", 7.0), ("y10", 8.5), ("y10", 10.0)],
                  "SHY": [("y2", 2.0), ("y2", 1.9), ("y1", 1.0)]}
    for etf, specs in bond_specs.items():
        live = R[etf]
        best = None
        for col, m in specs:
            y = tsy[col].dropna()
            if len(y) == 0:
                continue
            sim = par_bond_tr(y, m).reindex(cal)
            both = pd.concat([live, sim], axis=1, keys=["live", "sim"]).dropna()
            both = both[both.index <= "2007-06-29"]  # yield data ends there
            if len(both) < 250:
                continue
            st = ann_stats(both.live - both.sim)
            beta = float(np.polyfit(both.sim, both.live, 1)[0])
            corr = float(both.live.corr(both.sim))
            rec = {"yield": col, "maturity": m, "beta": beta, "corr": corr, **st}
            meta.setdefault(f"{etf}_proxy_candidates", []).append(rec)
            if best is None or abs(st["te_ann"]) < abs(best[1]["te_ann"]):
                best = ((col, m), rec)
        (col, m), rec = best
        sim = par_bond_tr(tsy[col].dropna(), m).reindex(cal) - ER[etf] / 252
        meta[f"{etf}_proxy"] = {**rec, "live_start": str(live.first_valid_index().date())}
        R[etf + "_X"] = splice(sim, live)

    # ---- leveraged ETFs --------------------------------------------------
    for fund, (base, L) in LEVERED.items():
        base_ret = R[base + "_X"] if base + "_X" in R else R[base]
        live = load_close(fund).reindex(cal).pct_change()
        er = ER[fund]
        raw_sim = L * base_ret - (L - 1) * rf - er / 252   # before spread
        both = pd.concat([live, raw_sim], axis=1, keys=["live", "sim"]).dropna()
        # spread so that mean daily return matches: live = sim - (L-1)*spread/252
        spread = float(-(both.live - both.sim).mean() * 252 / (L - 1))
        h = len(both) // 2
        s1 = float(-(both.live - both.sim).iloc[:h].mean() * 252 / (L - 1))
        s2 = float(-(both.live - both.sim).iloc[h:].mean() * 252 / (L - 1))
        sim = raw_sim - (L - 1) * spread / 252
        d = both.live - (both.sim - (L - 1) * spread / 252)
        # cumulative drift over the overlap after full-sample calibration (geometric)
        cum_live = (1 + both.live).prod(); cum_sim = (1 + both.sim - (L - 1) * spread / 252).prod()
        yrs = len(both) / 252
        meta[f"{fund}_sim"] = {"base": base, "L": L, "expense_ratio": er, "spread_ann": spread,
                               "spread_first_half_ann": s1, "spread_second_half_ann": s2,
                               "oos_drift_ann_if_calibrated_on_first_half": (s1 - s2) * (L - 1),
                               "geom_drift_ann_after_calibration": float((cum_live / cum_sim) ** (1 / yrs) - 1),
                               "corr": float(both.live.corr(both.sim)),
                               **ann_stats(d), "live_start": str(live.first_valid_index().date()),
                               "usable": abs(float((cum_live / cum_sim) ** (1 / yrs) - 1)) <= 0.01,
                               "split_half_drift_exceeds_1pct": abs((s1 - s2) * (L - 1)) > 0.01}
        R[fund + "_X"] = splice(sim, live)

    # ---- assemble ----------------------------------------------------------
    panel_r = pd.DataFrame(R).reindex(cal)
    panel_r = panel_r[panel_r.index >= START]
    # levels
    levels = (1 + panel_r.fillna(0)).cumprod()
    levels[panel_r.isna() & (panel_r.ffill().isna())] = np.nan  # before first data
    OUT.mkdir(parents=True, exist_ok=True)
    panel_r.to_parquet(OUT / "returns.parquet")
    levels.to_parquet(OUT / "levels.parquet")
    vix = load_close("VIX").reindex(cal).ffill(limit=3)
    vix[vix.index >= START].to_frame("VIX").to_parquet(OUT / "vix.parquet")
    tsy[tsy.index >= START].to_parquet(OUT / "treasury.parquet")
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2, default=float))
    if verbose:
        for k, v in meta.items():
            if isinstance(v, dict):
                print(k, {kk: (round(vv, 5) if isinstance(vv, float) else vv) for kk, vv in v.items()})
    return panel_r, meta


if __name__ == "__main__":
    build()
