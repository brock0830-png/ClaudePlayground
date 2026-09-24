"""Unit tests for the single-session profile (spec section 3, core structure)."""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from mp.profile import build_profile, row_size_for, value_area, poc_row, rotation_factor, volume_va  # noqa: E402
from helpers import bars_from_periods, feats  # noqa: E402


# ---------------------------------------------------------------- row size
def test_row_size_is_one_tick_up_to_400_rows_then_two():
    assert row_size_for(0, 399) == 1          # 400 rows
    assert row_size_for(0, 400) == 2          # 401 rows -> 2 ticks


def test_two_tick_rows_bin_on_the_contract_price():
    # 401-tick range forces 2-tick rows; profile built with a raw offset keeps row edges on raw ticks
    pr = build_profile([0, 100], [300, 400])
    assert pr.rs == 2 and pr.n_rows == 201
    assert pr.row_low(0) == 0 and pr.row_high(pr.n_rows - 1) == 401


# ---------------------------------------------------------------- POC
def test_poc_is_row_with_most_tpos():
    # periods: A 0-10, B 4-8, C 5-7 -> rows 5..7 have 3 TPOs; center of 0..10 is 5 -> POC 5
    pr = build_profile([0, 4, 5], [10, 8, 7])
    assert pr.counts.max() == 3
    assert pr.poc_t == 5


def test_poc_tie_goes_to_row_closest_to_range_center():
    # two separate 2-TPO clusters: rows 1-2 and 8-9; range 0..12, center 6 -> row 8 is closer
    counts = np.array([1, 2, 2, 1, 1, 1, 1, 1, 2, 2, 1, 1, 1])
    assert poc_row(counts, np.arange(13, dtype=float), 6.0) == 8


def test_poc_equidistant_tie_goes_to_lower_row():
    counts = np.array([1, 3, 1, 1, 3, 1])
    # center 2.5: rows 1 and 4 are 1.5 away -> lower row
    assert poc_row(counts, np.arange(6, dtype=float), 2.5) == 1


# ---------------------------------------------------------------- value area (Appendix 1)
def test_value_area_pairwise_worked_example():
    # counts bottom->top; total 42, 70% = 29.4. POC row 5 (8 TPOs).
    # step 1: above pair rows 6,7 = 10; below pair rows 4,3 = 12 -> add below (acc 20)
    # step 2: above pair 6,7 = 10; below pair 2,1 = 5 -> add above (acc 30 >= 29.4) -> stop
    counts = np.array([1, 2, 3, 5, 7, 8, 6, 4, 3, 2, 1])
    assert value_area(counts, 5) == (3, 7)


def test_value_area_uses_pairs_not_single_rows():
    # A single-row method would add row 4 (6) before row 2 (5). Pairwise compares rows 4+5 (7)
    # with rows 2+1 (10), so the area grows down first.
    counts = np.array([1, 5, 5, 9, 6, 1, 1])
    lo, hi = value_area(counts, 3)
    # total 28, need 19.6: acc 9 -> below pair (rows 2,1)=10 > above pair (rows 4,5)=7 -> acc 19
    # -> above pair rows 4,5 = 7 vs below row 0 = 1 -> above -> acc 26 -> stop
    assert (lo, hi) == (1, 5)


def test_value_area_equal_pairs_add_both():
    counts = np.array([1, 4, 5, 9, 5, 4, 1])       # total 29, need 20.3
    assert value_area(counts, 3) == (1, 5)          # 9 -> both pairs of 9 -> 27


def test_value_area_near_edge_uses_remaining_single_row():
    counts = np.array([2, 3, 9, 6])                  # POC row 2; above only row 3 (6) vs below 0+1 (5)
    assert value_area(counts, 2) == (2, 3)           # 9+6 = 15 >= 14 -> stop


def test_value_area_holds_at_least_70_percent():
    rng = np.random.default_rng(1)
    for _ in range(200):
        counts = rng.integers(1, 12, size=rng.integers(3, 60))
        poc = int(counts.argmax())
        lo, hi = value_area(counts, poc)
        assert counts[lo:hi + 1].sum() >= 0.7 * counts.sum()
        assert lo <= poc <= hi


# ---------------------------------------------------------------- tails, poor extremes, single prints
def _profile(periods):
    """Periods as (low, high) in ticks, A first; the last entry is the session's last period."""
    lo, hi = zip(*periods)
    return build_profile(np.array(lo), np.array(hi))


def test_selling_tail_two_single_prints_at_high():
    pr = _profile([(10, 22), (8, 19), (6, 18), (7, 18)])   # A alone at 20-22 -> 3-row tail
    assert pr.tail_hi_len == 3 and pr.tail_hi_inner_t() == 20
    assert not pr.poor_high


def test_one_single_print_is_not_a_tail_nor_poor():
    pr = _profile([(10, 20), (8, 19), (6, 18), (7, 18)])   # A alone at 20 only
    assert pr.tail_hi_len == 0 and not pr.poor_high


def test_single_prints_from_last_period_are_not_a_tail():
    pr = _profile([(10, 18), (8, 18), (6, 17), (9, 22)])   # last period alone at 19-22
    assert pr.tail_hi_len == 0
    assert not pr.poor_high                                 # extreme row holds 1 TPO


def test_poor_high_two_tpos_from_different_periods_at_extreme():
    pr = _profile([(10, 20), (8, 20), (6, 18), (7, 18)])   # A and B both print at 20
    assert pr.tail_hi_len == 0 and pr.poor_high


def test_buying_tail_and_poor_low_mirror():
    pr = _profile([(0, 10), (3, 12), (4, 12), (5, 11)])    # A alone at 0-2 -> buying tail 3 rows
    assert pr.tail_lo_len == 3 and pr.tail_lo_inner_t() == 2 and not pr.poor_low
    pr2 = _profile([(3, 10), (3, 12), (4, 12), (5, 11)])
    assert pr2.poor_low and pr2.tail_lo_len == 0


def test_mid_profile_single_prints_need_three_rows_not_at_extreme():
    # A 20-30, B 20-30, C 30-40 (C alone at 31-34), D 35-40, E 35-40 -> single rows 31..34 (4 rows)
    pr = _profile([(20, 30), (20, 30), (30, 40), (35, 40), (35, 40)])
    assert pr.single_runs_t() == [(31, 34)]
    # only 2 single rows (33-34) -> not a low-volume area
    pr2 = _profile([(20, 32), (20, 32), (30, 40), (35, 40), (35, 40)])
    assert pr2.single_runs_t() == []


def test_single_prints_at_an_extreme_are_a_tail_not_mid_profile():
    pr = _profile([(10, 25), (8, 19), (6, 18), (7, 18)])
    assert pr.single_runs == [] and pr.tail_hi_len == 6


def test_tpo_count_excludes_tails_and_favors_buyers_when_more_below():
    # A 0-20 (tail 17-20 is A alone), B 0-16, C 2-8, D 2-8, E 3-6
    pr = _profile([(0, 20), (0, 16), (2, 8), (2, 8), (3, 6)])
    assert pr.tail_hi_len == 4
    assert pr.poc_t in range(3, 7)
    above = pr.counts[pr.poc + 1:pr.n_rows - 4].sum()
    below = pr.counts[:pr.poc].sum() - (pr.counts[:pr.tail_lo_len].sum() if pr.tail_lo_len else 0)
    assert pr.tpo_above == above and pr.tpo_below == below
    assert pr.tpo_dir == int(np.sign(below - above))


# ---------------------------------------------------------------- rotation factor
def test_rotation_factor():
    # highs 10,12,12,11 -> +1, 0, -1 ; lows 5,6,4,4 -> +1, -1, 0 ; total 0
    assert rotation_factor([5, 6, 4, 4], [10, 12, 12, 11]) == 0
    assert rotation_factor([1, 2, 3], [5, 6, 7]) == 4


# ---------------------------------------------------------------- volume VA (robustness only)
def test_volume_va_concentrates_on_heavy_bars():
    pr = build_profile(np.array([0, 0]), np.array([20, 20]))
    lo = np.array([0, 9, 10, 20]); hi = np.array([20, 11, 10, 20]); v = np.array([21, 300, 500, 5])
    vpoc, vval, vvah = volume_va(pr, lo, hi, v)
    assert vpoc == 10 and vval <= 10 <= vvah and vvah - vval <= 4


# ---------------------------------------------------------------- end to end from minute bars
def test_session_ib_poc_va_from_bars():
    # A 100-120, B 104-116, C..N inside 106-114
    per = [(110, 100, 120, 112), (112, 104, 116, 108)] + [(108, 106, 114, 110), (110, 106, 114, 108)] * 6
    per[-1] = (per[-1][0], 106, 114, 110)
    f = feats(bars_from_periods(per))
    assert (f["ib_lo"], f["ib_hi"]) == (100, 120)
    assert (f["or_lo"], f["or_hi"]) == (105, 110)          # A heads from 110 to 100 over 10 minutes
    assert 106 <= f["poc"] <= 114 and f["val"] <= f["poc"] <= f["vah"]
    assert not f["re_up"] and not f["re_dn"]
