"""Unit tests for session and multi-session definitions (spec section 3), on hand-built sessions."""
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from mp.features import (opening_type, day_type, balance_run, value_rel, acceptance_period,  # noqa: E402
                         cross_session, spike)
from mp.path import bar_points  # noqa: E402
from helpers import bars_from_path, bars_from_periods, feats  # noqa: E402

NAN = float("nan")


def flat(lo, hi, n=14):
    """A balanced session: every period opens and closes at `lo` and trades lo..hi."""
    return bars_from_periods([(lo, lo, hi, lo)] * n)


def run_cross(bars_list, on=None):
    parts, rows, b = [], [], 0
    for i, bs in enumerate(bars_list):
        bs = bs.copy(); bs["session"] = i
        parts.append(bs)
        rows.append(dict(date=pd.Timestamp("2015-01-05") + pd.Timedelta(days=i), early_close=False, b0=b,
                         b1=b + len(bs), on_hi_t=on[i][1] if on else NAN, on_lo_t=on[i][0] if on else NAN))
        b += len(bs)
    return cross_session(pd.DataFrame(rows), pd.concat(parts, ignore_index=True), [feats(x) for x in bars_list])


def otype(bars, prior_hi, prior_lo, bal_hi=NAN, bal_lo=NAN, med_arange=40):
    f = feats(bars)
    P = bar_points(bars.o, bars.h, bars.l, bars.c)
    return opening_type(P, None, bars.minute.to_numpy(), f, prior_hi, prior_lo, bal_hi, bal_lo, med_arange)


# ---------------------------------------------------------------- IB and range extension
def test_ib_ratio_narrow_and_wide():
    base = [bars_from_periods([(100, 100, 120, 110), (110, 100, 120, 110)] + [(110, 105, 115, 110)] * 12)] * 20
    narrow = bars_from_periods([(100, 100, 110, 105), (105, 100, 110, 105)] + [(105, 102, 108, 105)] * 12)
    wide = bars_from_periods([(100, 100, 130, 110), (110, 100, 130, 110)] + [(110, 105, 115, 110)] * 12)
    D = run_cross(base + [narrow, wide])
    assert np.isnan(D["ib_ratio"].iloc[19])                       # fewer than 20 prior sessions
    assert D["ib_ratio"].iloc[20] == 0.5 and D["ib_narrow"].iloc[20]
    assert D["ib_wide"].iloc[21]                                  # 30 / median(20) = 1.5


def test_range_extension_side_order_and_period():
    per = [(110, 100, 120, 110), (110, 104, 116, 110), (110, 108, 118, 110), (110, 95, 112, 110),
           (110, 108, 124, 112)] + [(112, 108, 116, 112)] * 9
    f = feats(bars_from_periods(per))
    assert f["re_dn"] and f["re_up"]
    assert f["re_dn_per"] == 3 and f["re_up_per"] == 4 and f["re_first"] == -1


# ---------------------------------------------------------------- opening types (p.63-73)
def test_open_drive_up():
    b = bars_from_path([(0, 1000), (5, 1004), (60, 1040), (405, 1040)])
    o = otype(b, prior_hi=1100, prior_lo=900)
    assert o["open_A"] == "OD" and o["od_dir"] == 1 and o["open_type"] == "OD"


def test_open_drive_that_trades_back_through_or_in_b_is_open_auction():
    b = bars_from_path([(0, 1000), (5, 1004), (30, 1030), (50, 990), (405, 1000)])
    o = otype(b, prior_hi=1020, prior_lo=980)
    assert o["open_A"] == "OD"                   # what a trader knows at 10:00
    assert o["open_type"] == "OA-in"             # final label needs A and B


def test_open_test_drive_down_after_testing_prior_high():
    # OR 1000-1003; tests prior high 1010 by 3 ticks, reverses below the OR low, A closes below it
    b = bars_from_path([(0, 1000), (5, 1003), (12, 1013), (25, 990), (30, 988), (405, 980)])
    o = otype(b, prior_hi=1010, prior_lo=950)
    assert o["open_A"] == "OTD" and o["otd_dir"] == -1


def test_open_test_drive_needs_two_ticks_beyond_reference():
    b = bars_from_path([(0, 1000), (5, 1003), (12, 1011), (25, 990), (30, 988), (405, 980)])
    o = otype(b, prior_hi=1010, prior_lo=950, med_arange=200)     # 1 tick beyond only, ORR threshold out of reach
    assert o["open_A"] != "OTD"


def test_open_test_drive_can_use_bracket_low():
    b = bars_from_path([(0, 1000), (5, 997), (12, 986), (25, 1010), (30, 1012), (405, 1020)])
    o = otype(b, prior_hi=1100, prior_lo=900, bal_hi=1100, bal_lo=988)
    assert o["open_A"] == "OTD" and o["otd_dir"] == 1


def test_open_rejection_reverse():
    # up 12 ticks (>= 0.25 x 40), back below the OR low, A closes back inside the OR: no reference, no drive
    b = bars_from_path([(0, 1000), (5, 1006), (10, 1012), (20, 995), (30, 1001), (405, 1001)])
    o = otype(b, prior_hi=1100, prior_lo=900)
    assert o["open_A"] == "ORR" and o["orr_dir"] == -1 and o["orr_ext"] == 1012


def test_open_rejection_reverse_needs_quarter_of_median_a_range():
    b = bars_from_path([(0, 1000), (5, 1006), (10, 1009), (20, 995), (30, 1001), (405, 1001)])
    assert otype(b, prior_hi=1100, prior_lo=900)["open_A"] != "ORR"      # 9 < 10


def test_open_auction_in_and_out_of_range():
    b = bars_from_path([(0, 1000), (5, 1003), (15, 997), (25, 1004), (30, 1000), (405, 1000)])
    assert otype(b, prior_hi=1020, prior_lo=980)["open_type"] == "OA-in"
    assert otype(b, prior_hi=1050, prior_lo=1010)["open_type"] == "OA-out"


# ---------------------------------------------------------------- acceptance (p.75, 244)
def test_acceptance_two_consecutive_periods():
    p_lo = np.array([130, 118, 125, 112, 110]); p_hi = np.array([140, 128, 135, 119, 118])
    assert acceptance_period(p_lo, p_hi, 100, 120) == 4          # periods 3 and 4 (period 1 alone is rejection)
    assert acceptance_period(p_lo[:4], p_hi[:4], 100, 120) == -1


# ---------------------------------------------------------------- day types (p.19-31)
def test_nontrend_normal_and_unclassified_no_re():
    f = feats(bars_from_periods([(100, 100, 120, 110), (110, 100, 120, 110)] + [(110, 105, 115, 110)] * 12))
    assert day_type(f, True, False) == "Nontrend"
    assert day_type(f, False, True) == "Normal"
    assert day_type(f, False, False) == "Other-noRE"


def test_normal_variation():
    per = [(110, 100, 120, 110), (110, 104, 116, 110), (110, 108, 125, 112)] + [(112, 108, 116, 112)] * 11
    assert day_type(feats(bars_from_periods(per)), False, False) == "Normal-Variation"


def test_trend_day():
    per = [(100 + 8 * j, 100 + 8 * j, 110 + 8 * j, 108 + 8 * j) for j in range(14)]
    f = feats(bars_from_periods(per))
    assert f["max_width"] <= 5 and f["re_up"]
    assert day_type(f, False, False) == "Trend"


def test_double_distribution_trend():
    per = [(100, 100, 110, 105), (105, 102, 110, 106), (106, 104, 110, 108), (108, 104, 110, 110),
           (110, 110, 140, 135)] + [(135, 130, 140, 135)] * 9
    f = feats(bars_from_periods(per))
    assert f["single_runs"] and f["single_runs"][0][0] > 110
    assert day_type(f, True, False) == "DD-Trend"


def test_neutral_extreme_and_center():
    ext = [(110, 100, 120, 110), (110, 104, 116, 110), (110, 95, 112, 110), (110, 106, 118, 112)] \
        + [(112, 108, 116, 112)] * 8 + [(112, 110, 125, 124), (124, 122, 125, 125)]
    assert day_type(feats(bars_from_periods(ext)), False, False) == "Neutral-Extreme"
    ctr = ext[:-2] + [(112, 110, 125, 112), (112, 110, 114, 112)]
    assert day_type(feats(bars_from_periods(ctr)), False, False) == "Neutral-Center"


# ---------------------------------------------------------------- balance area (p.252-259)
def test_balance_run_needs_common_va_overlap():
    val = np.array([100, 105, 108, 120]); vah = np.array([110, 115, 112, 130])
    assert balance_run(val, vah, 2) == 3 and balance_run(val, vah, 3) == 1


def test_balance_extremes_from_cross_session():
    s = [flat(100, 120), flat(104, 124), flat(102, 118), flat(140, 160)]
    D = run_cross(s)
    assert D["bal_run"].iloc[2] == 3
    assert (D["bal3_lo"].iloc[2], D["bal3_hi"].iloc[2]) == (100, 124)
    assert np.isnan(D["bal5_hi"].iloc[2]) and np.isnan(D["bal3_hi"].iloc[3])


# ---------------------------------------------------------------- spike (p.247-252)
def test_spike_up_in_last_two_periods():
    per = [(110, 100, 120, 110)] * 11 + [(110, 105, 118, 118), (118, 118, 140, 138), (138, 136, 150, 150)]
    f = feats(bars_from_periods(per))
    assert f["spike_dir"] == 1 and (f["spike_lo"], f["spike_hi"]) == (118, 150)


def test_no_spike_when_last_periods_stay_in_value():
    per = [(110, 100, 120, 110)] * 14
    assert feats(bars_from_periods(per))["spike_dir"] == 0


def test_no_spike_when_it_covers_less_than_a_quarter_of_the_range():
    per = [(110, 60, 160, 110)] + [(110, 100, 120, 110)] * 11 + [(110, 105, 118, 118), (118, 118, 126, 126)]
    assert spike(*[np.array(x) for x in zip(*[(p[1], p[2], p[0]) for p in per])], H=160, L=60)["spike_dir"] == 0


# ---------------------------------------------------------------- open location, value placement
def test_open_location_categories():
    prior = flat(90, 130)                       # range 90-130, VA inside it
    D = run_cross([prior, bars_from_path([(0, 110), (405, 110)]), ])
    va = (D["val"].iloc[0], D["vah"].iloc[0])
    assert va[0] > 90 and va[1] < 130 and D["open_loc"].iloc[1] == 0
    D2 = run_cross([prior, bars_from_path([(0, va[1] + 2), (405, va[1] + 2)])])
    assert D2["open_loc"].iloc[1] == 1 and D2["open_side"].iloc[1] == 1
    D3 = run_cross([prior, bars_from_path([(0, 135), (405, 135)])])
    assert D3["open_loc"].iloc[1] == 2


def test_value_relationship():
    assert list(value_rel(np.array([100, 104, 104, 90, 85]), np.array([110, 114, 115, 100, 120]))) == [0, 1, 1, -1, 0]


# ---------------------------------------------------------------- overnight inventory
def test_overnight_inventory():
    prior = bars_from_path([(0, 110), (405, 110)])                     # prior close 110
    up = bars_from_path([(0, 118), (405, 118)])
    dn = bars_from_path([(0, 102), (405, 102)])
    mid = bars_from_path([(0, 111), (405, 111)])
    on = [(NAN, NAN), (100, 120)]
    assert run_cross([prior, up], on)["inventory"].iloc[1] == 1
    assert run_cross([prior, dn], on)["inventory"].iloc[1] == -1
    assert run_cross([prior, mid], on)["inventory"].iloc[1] == 0


# ---------------------------------------------------------------- 3-to-I and 2I-1R (p.239-241)
def _three_i_day():
    # buying tail 118-121 (A only), range extension up to 135, POC 133 with more TPOs below it
    return bars_from_periods([(124, 118, 126, 125), (125, 122, 128, 127), (127, 124, 130, 129),
                              (129, 126, 132, 131), (131, 128, 134, 133)] + [(133, 133, 135, 133)] * 9)


def test_three_to_i_day():
    D = run_cross([flat(100, 120), _three_i_day()])
    r = D.iloc[1]
    assert r["tail_lo_len"] == 4 and r["tail_hi_len"] == 0 and r["re_dir"] == 1 and r["tpo_dir"] == 1
    assert r["three_i"] == 1 and r["two_i_one_r"] == 0


def test_two_i_one_r_day_has_responsive_tail():
    D = run_cross([flat(122, 140), _three_i_day()])          # prior VAL above the buying tail
    r = D.iloc[1]
    assert not r["tail_init"] and r["re_init"] and r["tpo_init"]
    assert r["three_i"] == 0 and r["two_i_one_r"] == 1


# ---------------------------------------------------------------- P and b shapes (p.123-128)
def test_p_shape_after_two_sessions_of_lower_value():
    p_day = bars_from_periods([(150, 140, 160, 158), (158, 158, 170, 168), (168, 168, 175, 170)]
                              + [(170, 165, 175, 170)] * 11)
    D = run_cross([flat(200, 220), flat(180, 200), flat(160, 180), p_day])
    assert D["p_shape"].iloc[3] and not D["b_shape"].iloc[3]
    D2 = run_cross([flat(160, 180), flat(180, 200), flat(160, 180), p_day])   # value not lower twice
    assert not D2["p_shape"].iloc[3]


def test_b_shape_after_two_sessions_of_higher_value():
    b_day = bars_from_periods([(180, 170, 190, 172), (172, 160, 172, 162), (162, 155, 162, 160)]
                              + [(160, 155, 165, 160)] * 11)
    D = run_cross([flat(100, 120), flat(120, 140), flat(140, 160), b_day])
    assert D["b_shape"].iloc[3] and not D["p_shape"].iloc[3]


# ---------------------------------------------------------------- addendum 1: drive distance by 10:00
def test_open_drive_distance_beyond_or_by_ten():
    # OR 1000-1004; by 10:00 the drive reaches 1024 -> 20 ticks beyond the OR high
    b = bars_from_path([(0, 1000), (5, 1004), (30, 1024), (405, 1030)])
    o = otype(b, prior_hi=1100, prior_lo=900)
    assert o["open_A"] == "OD" and o["od_dist"] == 20
    b2 = bars_from_path([(0, 1000), (5, 1004), (30, 1023), (405, 1030)])
    assert otype(b2, prior_hi=1100, prior_lo=900)["od_dist"] == 19


def test_open_test_drive_distance_and_trade_back():
    b = bars_from_path([(0, 1000), (5, 1003), (12, 1013), (25, 990), (30, 988), (405, 980)])
    o = otype(b, prior_hi=1010, prior_lo=950)
    assert o["open_A"] == "OTD" and o["otd_dist"] == 12 and not o["otd_back"]
    assert np.isnan(o["od_dist"])
