"""
Audit of the stop-first rule (PROTOCOL 4): for trades whose exit bar reached BOTH the stop
and the target, look at the SPX 1-minute path inside that 4h bar (RTH minutes only) and
count which was reached first. ES prices are mapped to SPX with the basis at the bar's
first RTH minute. Informational only: backtest fills are never changed.
Usage (library): audit(trades_df, spx_parquet_path) -> dict
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def audit(t: pd.DataFrame, spx_path: str, bars: pd.DataFrame) -> dict:
    spx = pd.read_parquet(spx_path)
    spx.index = spx.index.tz_localize("America/Chicago", ambiguous="NaT", nonexistent="NaT").tz_convert("America/New_York")
    spx = spx[spx.index.notna()]
    amb = t[t["ambiguous"]]
    res = {"ambiguous_trades": int(len(amb)), "stop_first": 0, "target_first": 0, "unresolved": 0}
    for _, r in amb.iterrows():
        b0 = pd.Timestamp(r["exit_time"])
        w = spx.loc[b0: b0 + pd.Timedelta(hours=4) - pd.Timedelta(minutes=1)]
        if w.empty:
            res["unresolved"] += 1
            continue
        es_px = bars.loc[b0, "open"]
        basis = es_px - w["open"].iloc[0] if b0.hour in (10, 14) else np.nan
        if np.isnan(basis):
            res["unresolved"] += 1
            continue
        stop_s, tgt_s = r["stop"] - basis, r["target"] - basis
        long = r["side"] == "long"
        hit_s = (w["low"] <= stop_s) if long else (w["high"] >= stop_s)
        hit_t = (w["high"] >= tgt_s) if long else (w["low"] <= tgt_s)
        fs = hit_s.values.argmax() if hit_s.any() else None
        ft = hit_t.values.argmax() if hit_t.any() else None
        if fs is None and ft is None:
            res["unresolved"] += 1
        elif ft is None or (fs is not None and fs <= ft):
            res["stop_first"] += 1
        else:
            res["target_first"] += 1
    return res
