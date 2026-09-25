import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from features import divergence, tpo_profile, wilder_rsi  # noqa: E402


def test_rsi_bounds_and_trend():
    up = wilder_rsi(np.arange(1, 40, dtype=float))
    assert np.isnan(up[13]) and up[14] == 100.0
    x = 100 + np.sin(np.arange(200) / 5.0)
    r = wilder_rsi(x)
    assert np.nanmin(r) > 0 and np.nanmax(r) < 100


def test_tpo_profile_poc_and_value_area():
    # four bars pile time around 100-101, one outlier bar up to 110
    H = np.array([101, 101, 101.5, 110.0])
    L = np.array([100, 99.5, 100, 101.5])
    poc, vah, val = tpo_profile(H, L, np.ones(4), 0.5)
    assert 100 <= poc <= 101
    assert val <= poc <= vah
    assert vah < 110          # the thin outlier range stays mostly outside the 70% value area


def test_bullish_divergence_needs_lower_low_and_higher_rsi():
    L = np.array([10, 9, 8, 9, 10, 11, 10, 9, 7.5, 9.0])
    H = L + 1
    rsi = np.array([50, 40, 20, 35, 45, 50, 45, 35, 30, 40.0])
    bull, bear = divergence(L, H, rsi, 2, 30)
    # pivot low at bar 2 (8, rsi 20) confirmed at bar 4; bar 8 makes 7.5 < 8 with rsi 30 > 20
    assert bull[8] and not bull[:8].any()
    rsi2 = rsi.copy(); rsi2[8] = 15.0          # lower RSI too: no divergence
    assert not divergence(L, H, rsi2, 2, 30)[0][8]


def test_divergence_ignores_unconfirmed_pivot():
    # the lower low at bar 3 comes before the bar-2 pivot can be confirmed (bar 4): no signal
    L = np.array([10, 9, 8, 7.0, 9, 10])
    rsi = np.array([50, 40, 20, 30, 40, 50.0])
    assert not divergence(L, L + 1, rsi, 2, 30)[0][3]
