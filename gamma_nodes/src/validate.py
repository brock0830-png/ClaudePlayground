"""Step-3 validation gate: rebuilt profile vs UW's live snapshot (PROTOCOL §4).

For every complete live slot on a day with both tape and live data, and for every
rebuild variant, compare net values over strikes within +-1.5% of UW's snapshot price:
Spearman rank correlation, and whether the largest-|net| strike matches (exact, and
within +-5 points). Pooled per variant; pass bar per view: exact top-node match >= 80%
of snapshots and median Spearman >= 0.70, over >= 5 days and >= 300 snapshots.

CLI (from gamma_nodes/):  python src/validate.py 2026-10-02 2026-10-05 ...
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))

ET = "America/New_York"
BAND = 0.015
PASS_TOP = 0.80
PASS_SPEARMAN = 0.70
MIN_DAYS = 5
MIN_SNAPS = 300
MIN_SLOT_COVERAGE = 0.90

UW_VIEW = {
    "D": ("call_gamma_ask", "call_gamma_bid", "put_gamma_ask", "put_gamma_bid"),
    "O": ("call_gamma_oi", "put_gamma_oi"),
    "V": ("call_gamma_vol", "put_gamma_vol"),
}
UW_FIELDS = sorted({f for v in UW_VIEW.values() for f in v})


def load_live_day(day_dir: Path, ticker: str = "spx") -> pd.DataFrame:
    """All complete expiry-strike snapshots of one day, one row per (slot, strike)."""
    frames = []
    for p0 in sorted(day_dir.glob(f"*_{ticker}_expiry_strike_p0.json")):
        slot = p0.name[:4]
        rows = []
        for p in sorted(day_dir.glob(f"{slot}_{ticker}_expiry_strike_p*.json")):
            rows += json.loads(p.read_bytes()).get("data", [])
        if not rows:
            continue
        df = pd.DataFrame(rows)
        for c in ["strike", "price"] + UW_FIELDS:
            df[c] = pd.to_numeric(df.get(c), errors="coerce")
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df["slot"] = slot
        frames.append(df[["slot", "strike", "price", "time"] + UW_FIELDS])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def uw_net(live: pd.DataFrame, view: str) -> pd.Series:
    return live[list(UW_VIEW[view])].fillna(0.0).sum(axis=1)


def sign_report(live: pd.DataFrame) -> dict:
    """Sign of the median non-zero value of each UW field, to confirm conventions."""
    out = {}
    for f in UW_FIELDS:
        x = live[f].dropna()
        x = x[x != 0]
        out[f] = None if x.empty else float(np.sign(x.median()))
    return out


def compare_snapshot(uw: pd.DataFrame, ours: pd.DataFrame, view: str) -> dict | None:
    """uw: one slot's rows; ours: one (slot, variant)'s rows."""
    spot = float(uw.loc[uw["time"].idxmax(), "price"]) if uw["time"].notna().any() else float(uw["price"].median())
    if not np.isfinite(spot):
        return None
    a = pd.Series(uw_net(uw, view).to_numpy(), index=uw["strike"]).groupby(level=0).sum()
    b = ours.set_index("strike")["net"].groupby(level=0).sum()
    strikes = sorted(set(a.index) | set(b.index))
    strikes = [k for k in strikes if abs(k / spot - 1.0) <= BAND]
    if len(strikes) < 5:
        return None
    a, b = a.reindex(strikes, fill_value=0.0), b.reindex(strikes, fill_value=0.0)
    rho = spearmanr(a.to_numpy(), b.to_numpy()).statistic if a.nunique() > 1 and b.nunique() > 1 else np.nan
    ka, kb = a.abs().idxmax(), b.abs().idxmax()
    return {"spot": spot, "n_strikes": len(strikes), "spearman": float(rho),
            "top_uw": float(ka), "top_ours": float(kb), "top_exact": bool(ka == kb),
            "top_within5": bool(abs(ka - kb) <= 5.0)}


def validate_day(d: date, live: pd.DataFrame, heat: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for slot, uw in live.groupby("slot"):
        t = pd.Timestamp(f"{d.isoformat()} {slot[:2]}:{slot[2:]}", tz=ET)
        hs = heat[heat["snap"] == t]
        for vid, ours in hs.groupby("variant"):
            r = compare_snapshot(uw, ours, ours["view"].iloc[0])
            if r:
                rows.append({"date": d.isoformat(), "slot": slot, "variant": vid,
                             "view": ours["view"].iloc[0], **r})
    return pd.DataFrame(rows)


def summarize(per_snap: pd.DataFrame) -> pd.DataFrame:
    g = per_snap.groupby(["view", "variant"])
    s = g.agg(days=("date", "nunique"), snapshots=("slot", "size"),
              top_exact=("top_exact", "mean"), top_within5=("top_within5", "mean"),
              spearman_median=("spearman", "median")).reset_index()
    s["pass"] = ((s["top_exact"] >= PASS_TOP) & (s["spearman_median"] >= PASS_SPEARMAN)
                 & (s["days"] >= MIN_DAYS) & (s["snapshots"] >= MIN_SNAPS))
    return s.sort_values(["view", "top_exact"], ascending=[True, False])


def slot_coverage(day_dir: Path, d: date) -> float:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))
    import collect
    ok, n, _ = collect.check_day(day_dir.parent.parent, d)
    return ok / n if n else 0.0
