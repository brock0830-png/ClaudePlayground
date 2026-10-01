"""SPX 1-minute bars and settlement close from UW, stored raw under DATA_ROOT/prices/.

  prices/SPX_1m_YYYY-MM-DD.json   GET /api/stock/SPX/ohlc/1m?date=D&limit=2500 (raw body)
  prices/SPX_1d_YYYY.json         GET /api/stock/SPX/ohlc/1d?timeframe=... (raw body)

`load_1m(d)` returns regular-session bars (market_time == 'r') indexed by bar start in
US/Eastern. PROTOCOL gate D3 is `check_day_d3`.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gn_calendar as cal  # noqa: E402
from gn_config import WORK, Config  # noqa: E402
from gn_store import Store  # noqa: E402

API = "https://api.unusualwhales.com/api"
ET = "America/New_York"


def _get(url: str, key: str) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}",
                                               "Accept": "application/json",
                                               "User-Agent": "gamma-nodes/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch_1m(d: date, cfg: Config, store: Store) -> Path:
    """Fetch and store the day's raw 1-minute bars once; return a local copy path."""
    rel = f"prices/SPX_1m_{d.isoformat()}.json"
    local = WORK / "prices" / Path(rel).name
    local.parent.mkdir(parents=True, exist_ok=True)
    if store.exists(rel):
        local.write_text(store.read_text(rel))
        return local
    body = _get(f"{API}/stock/SPX/ohlc/1m?" + urllib.parse.urlencode({"date": d.isoformat(), "limit": 2500}),
                cfg.api_key)
    local.write_bytes(body)
    store.put(local, rel)
    return local


def parse_1m(raw: bytes | str, d: date) -> pd.DataFrame:
    obj = json.loads(raw)
    df = pd.DataFrame(obj.get("data", obj))
    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    df = df[df["market_time"] == "r"].copy()
    df["start"] = pd.to_datetime(df["start_time"], utc=True).dt.tz_convert(ET)
    df = df[df["start"].dt.date == d]
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float)
    return df.set_index("start").sort_index()[["open", "high", "low", "close"]]


def spot_at(bars: pd.DataFrame, t: pd.Timestamp) -> float:
    """Close of the 1-minute bar ending at t (start = t - 1 min); else the last bar before t."""
    prior = bars[bars.index <= t - pd.Timedelta(minutes=1)]
    return float(prior["close"].iloc[-1]) if len(prior) else np.nan


def check_day_d3(bars: pd.DataFrame, tape_spxw: pd.DataFrame, d: date) -> dict:
    """PROTOCOL D3: coverage of the session and agreement with tape underlying_price."""
    h, m = cal.close_time_et(d)
    session = pd.date_range(pd.Timestamp(d.isoformat() + " 09:30", tz=ET),
                            pd.Timestamp(f"{d.isoformat()} {h:02d}:{m:02d}", tz=ET),
                            freq="1min", inclusive="left")
    missing = int((~session.isin(bars.index)).sum())
    t = tape_spxw["executed_at"].dt.tz_convert(ET).dt.floor("1min")
    tape_med = tape_spxw.groupby(t)["underlying_price"].median()
    j = bars["close"].to_frame().join(tape_med.rename("tape"), how="inner")
    med_abs = float((j["close"] - j["tape"]).abs().median()) if len(j) else np.nan
    return {"date": d.isoformat(), "bars": len(bars), "missing_minutes": missing,
            "matched_minutes": len(j), "median_abs_diff_pts": med_abs,
            "pass": bool(missing <= 5 and len(j) > 0 and med_abs <= 1.0)}
