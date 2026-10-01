"""Validation comparison on synthetic live snapshots (no network)."""
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import validate as va  # noqa: E402

D = date(2026, 10, 2)
ET = "America/New_York"


def write_live(day_dir: Path, slot: str, values: dict[float, float], price=7650.0):
    rows = [{"strike": str(k), "price": str(price), "time": f"{D} 14:00:00+00:00",
             "call_gamma_ask": str(v), "call_gamma_bid": "0", "put_gamma_ask": "0", "put_gamma_bid": "0",
             "call_gamma_oi": "1", "put_gamma_oi": "-1", "call_gamma_vol": "1", "put_gamma_vol": "-2"}
            for k, v in values.items()]
    (day_dir / f"{slot}_spx_expiry_strike_p0.json").write_text(json.dumps({"data": rows}))
    (day_dir / f"{slot}_spx_expiry_strike_p1.json").write_text(json.dumps({"data": []}))


def heat(slot, values, variant="D-tag-exclude-G1", view="D"):
    t = pd.Timestamp(f"{D} {slot[:2]}:{slot[2:]}", tz=ET)
    return pd.DataFrame({"snap": t, "variant": variant, "view": view,
                         "strike": list(values), "net": list(values.values())})


def test_identical_profiles_match(tmp_path):
    vals = {7600.0 + 5 * i: float(np.sin(i)) * 1e9 for i in range(20)}
    vals[7680.0] = 9e9
    write_live(tmp_path, "1000", vals)
    live = va.load_live_day(tmp_path)
    res = va.validate_day(D, live, heat("1000", vals))
    r = res.iloc[0]
    assert r.top_exact and r.top_uw == 7680.0 and r.spearman > 0.999
    assert va.sign_report(live)["put_gamma_vol"] == -1.0


def test_wrong_top_node_detected(tmp_path):
    vals = {7600.0 + 5 * i: 1e9 for i in range(20)}
    vals[7680.0] = 9e9
    ours = dict(vals)
    ours[7680.0], ours[7700.0] = 1e9, 9e9
    write_live(tmp_path, "1000", vals)
    res = va.validate_day(D, va.load_live_day(tmp_path), heat("1000", ours))
    assert not res.iloc[0].top_exact and not res.iloc[0].top_within5


def test_strikes_outside_band_ignored(tmp_path):
    vals = {7650.0 + 5 * i: 1e9 * (i + 1) for i in range(-10, 10)}
    vals[8000.0] = 1e12                                    # 4.6% away: outside +-1.5%
    write_live(tmp_path, "1000", vals)
    res = va.validate_day(D, va.load_live_day(tmp_path), heat("1000", {k: v for k, v in vals.items() if k != 8000.0}))
    assert res.iloc[0].top_exact and res.iloc[0].top_uw == 7695.0


def test_summary_pass_bar():
    rows = [{"date": f"d{i % 5}", "slot": str(i), "variant": "D-x", "view": "D", "spearman": 0.9,
             "top_exact": i % 10 != 0, "top_within5": True} for i in range(320)]
    s = va.summarize(pd.DataFrame(rows))
    assert bool(s.iloc[0]["pass"]) and abs(s.iloc[0]["top_exact"] - 0.9) < 1e-9
    rows = rows[:299]
    assert not bool(va.summarize(pd.DataFrame(rows)).iloc[0]["pass"])   # < 300 snapshots
