"""Heatmap rebuild on a hand-made tape (no network)."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import rebuild as rb  # noqa: E402

D = date(2026, 10, 2)
ET = "America/New_York"


def bars(spot=7650.0):
    idx = pd.date_range(f"{D} 09:30", f"{D} 15:59", freq="1min", tz=ET)
    return pd.DataFrame({"open": spot, "high": spot + 1, "low": spot - 1, "close": spot}, index=idx)


def trade(hhmmss, occ, strike, typ, size, price, bid, ask, gamma, tags, iv=0.15, oi=100, und=7650.0):
    return {"executed_at": pd.Timestamp(f"{D} {hhmmss}", tz=ET).tz_convert("UTC"),
            "option_chain_id": occ, "expiry": D, "canceled": False, "strike": float(strike),
            "option_type": typ, "size": size, "price": price, "nbbo_bid": bid, "nbbo_ask": ask,
            "gamma": gamma, "implied_volatility": iv, "open_interest": oi,
            "underlying_price": und, "tags": tags}


@pytest.fixture
def tape():
    return pd.DataFrame([
        trade("10:02:00", "SPXW261002C07680000", 7680, "call", 10, 2.0, 1.9, 2.0, 0.004, "{ask_side}"),
        trade("10:03:00", "SPXW261002C07680000", 7680, "call", 4, 1.9, 1.9, 2.0, 0.005, "{bid_side}"),
        trade("10:04:00", "SPXW261002P07620000", 7620, "put", 6, 1.95, 1.9, 2.0, 0.003, "{mid_side}"),
        trade("10:04:30", "SPXW261002P07620000", 7620, "put", 2, 1.0, 0.0, 0.0, 0.003, "{no_side}"),
        trade("10:01:00", "SPXW261005C07680000", 7680, "call", 99, 2.0, 1.9, 2.0, 0.004, "{ask_side}"),
    ]).assign(expiry=[D, D, D, D, date(2026, 10, 5)])  # last row is not 0DTE


def get(res, variant, snap, strike, col="net"):
    r = res[(res.variant == variant) & (res.snap == pd.Timestamp(f"{D} {snap}", tz=ET)) & (res.strike == strike)]
    return float(r[col].iloc[0]) if len(r) else np.nan


def test_no_lookahead_and_signs(tape):
    res = rb.rebuild_day(tape, bars(), D)
    S2 = 7650.0 ** 2
    assert get(res, "D-tag-exclude-G1", "10:00", 7680) == 0.0             # 10:02 trade not yet in
    g1 = (-10 * 0.004 + 4 * 0.005) * S2                                  # ask -, bid +
    assert get(res, "D-tag-exclude-G1", "10:05", 7680) == pytest.approx(g1)
    assert get(res, "D-tag-exclude-G1", "10:05", 7680, "call_ask") == pytest.approx(-10 * 0.004 * S2)
    # G3: latest observed gamma (0.005) times cumulative signed contracts
    assert get(res, "D-tag-exclude-G3", "10:05", 7680) == pytest.approx((-10 + 4) * 0.005 * S2)
    # split moves half the mid trade into each bucket and leaves net unchanged
    assert get(res, "D-tag-split-G1", "10:05", 7620) == pytest.approx(0.0)
    assert get(res, "D-tag-split-G1", "10:05", 7620, "put_ask") == pytest.approx(-0.5 * 6 * 0.003 * S2)
    assert get(res, "D-tag-exclude-G1", "10:05", 7620, "put_ask") == pytest.approx(0.0)
    # quote rule: price 2.0 at ask, 1.9 at bid; crossed/zero quote counts as no side
    assert get(res, "D-quote-exclude-G1", "10:05", 7680) == pytest.approx(g1)
    # volume and OI views: calls +, puts -
    assert get(res, "V-G1", "10:05", 7620) == pytest.approx(-(6 + 2) * 0.003 * S2)
    assert get(res, "O-G3", "10:05", 7680) == pytest.approx(100 * 0.005 * S2)
    # the 3-day expiry trade never enters the 0DTE profile
    assert get(res, "V-G1", "10:05", 7680) == pytest.approx((10 * 0.004 + 4 * 0.005) * S2)


def test_g2_matches_black_scholes(tape):
    res = rb.rebuild_day(tape, bars(), D)
    S, K, sig = 7650.0, 7680.0, 0.15
    tau = 355 / 525_600  # 10:05 -> 16:00
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * tau) / (sig * np.sqrt(tau))
    g = norm.pdf(d1) / (S * sig * np.sqrt(tau))
    assert get(res, "O-G2", "10:05", 7680) == pytest.approx(100 * g * S * S, rel=1e-9)


def test_variant_count():
    assert len(rb.VARIANTS) == 17 and len({v.id for v in rb.VARIANTS}) == 17
