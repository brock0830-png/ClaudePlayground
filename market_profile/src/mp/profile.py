"""TPO profile of one RTH session: SPEC_market_profile_ES_v3.md section 3, "Core structure".

Everything here works in integer ticks (price / 0.25). A 30-minute period prints one TPO in
every row from the row holding its low to the row holding its high. Row k covers ticks
[k*rs, k*rs + rs - 1], where rs is the row size in ticks (1, or 2 when the 1-tick profile
would exceed 400 rows).

Conventions where the spec is silent are listed in CONVENTIONS.md and referenced as [C#].
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

MAX_ROWS_1TICK = 400
VA_FRACTION = 0.70


def row_size_for(lo_t: int, hi_t: int) -> int:
    """Spec 1: 1 tick, or 2 ticks if the 1-tick profile would exceed 400 rows."""
    return 1 if (hi_t - lo_t + 1) <= MAX_ROWS_1TICK else 2


def value_area(counts: np.ndarray, poc: int, fraction: float = VA_FRACTION) -> tuple[int, int]:
    """Appendix 1 pairwise method. Returns (lo_row, hi_row), inclusive.

    Start at the POC; compare the sum of the next two rows above with the next two rows below and
    add the larger pair; repeat until the area holds at least `fraction` of all TPOs. Near an edge
    a "pair" is whatever rows remain (one or none). Equal pairs: add both [C1].
    """
    n = len(counts)
    need = fraction * counts.sum()
    lo = hi = poc
    acc = counts[poc]
    while acc < need and (lo > 0 or hi < n - 1):
        up_rows = counts[hi + 1:hi + 3]
        dn_rows = counts[max(0, lo - 2):lo]
        up, dn = up_rows.sum(), dn_rows.sum()
        if len(up_rows) and (not len(dn_rows) or up > dn):
            hi += len(up_rows); acc += up
        elif len(dn_rows) and (not len(up_rows) or dn > up):
            lo -= len(dn_rows); acc += dn
        else:
            hi += len(up_rows); lo -= len(dn_rows); acc += up + dn
    return lo, hi


def poc_row(counts: np.ndarray, row_mid: np.ndarray, center: float) -> int:
    """Row with the most TPOs; ties go to the row closest to the range center, then the lower row [C2]."""
    m = counts.max()
    cand = np.flatnonzero(counts == m)
    d = np.abs(row_mid[cand] - center)
    return int(cand[np.flatnonzero(d == d.min())[0]])


@dataclass
class Profile:
    rs: int                      # row size in ticks
    row0: int                    # row index of the lowest row
    counts: np.ndarray           # TPOs per row, ascending price
    member: np.ndarray           # bool [row, period]: did the period print in the row
    lo_t: int                    # session low, ticks
    hi_t: int                    # session high, ticks
    last_period: int             # index of the session's final period
    poc: int = 0                 # row index (0-based within this profile)
    va_lo: int = 0
    va_hi: int = 0
    tail_hi_len: int = 0         # rows in the selling tail (0 if none)
    tail_lo_len: int = 0         # rows in the buying tail (0 if none)
    poor_high: bool = False
    poor_low: bool = False
    single_runs: list = field(default_factory=list)   # [(lo_row, hi_row)] mid-profile single prints
    tpo_above: int = 0
    tpo_below: int = 0

    # ---- prices (ticks) ----
    def row_low(self, i: int) -> int:
        return (self.row0 + i) * self.rs

    def row_high(self, i: int) -> int:
        return (self.row0 + i) * self.rs + self.rs - 1

    def row_mid(self, i) -> float:
        return (self.row0 + np.asarray(i)) * self.rs + (self.rs - 1) / 2

    @property
    def n_rows(self) -> int:
        return len(self.counts)

    @property
    def poc_t(self) -> int:
        """POC price: the row's low tick [C3]."""
        return self.row_low(self.poc)

    @property
    def vah_t(self) -> int:
        return min(self.row_high(self.va_hi), self.hi_t)

    @property
    def val_t(self) -> int:
        return max(self.row_low(self.va_lo), self.lo_t)

    @property
    def total(self) -> int:
        return int(self.counts.sum())

    @property
    def max_width(self) -> int:
        return int(self.counts.max())

    def tail_hi_inner_t(self) -> int | None:
        """Lowest tick of the selling tail (its inner edge)."""
        return self.row_low(self.n_rows - self.tail_hi_len) if self.tail_hi_len else None

    def tail_lo_inner_t(self) -> int | None:
        """Highest tick of the buying tail (its inner edge)."""
        return min(self.row_high(self.tail_lo_len - 1), self.hi_t) if self.tail_lo_len else None

    def single_runs_t(self) -> list[tuple[int, int]]:
        return [(self.row_low(a), self.row_high(b)) for a, b in self.single_runs]

    @property
    def tpo_dir(self) -> int:
        """+1 buyers favored (more TPOs below the POC), -1 sellers favored, 0 even (spec p.41-45)."""
        return int(np.sign(self.tpo_below - self.tpo_above))


def build_profile(p_lo: np.ndarray, p_hi: np.ndarray, rs: int | None = None,
                  last_period: int | None = None) -> Profile:
    """Profile from per-period lows/highs in ticks (periods in time order, A first)."""
    p_lo = np.asarray(p_lo, dtype=np.int64)
    p_hi = np.asarray(p_hi, dtype=np.int64)
    lo_t, hi_t = int(p_lo.min()), int(p_hi.max())
    if rs is None:
        rs = row_size_for(lo_t, hi_t)
    row0 = lo_t // rs
    n_rows = hi_t // rs - row0 + 1
    n_per = len(p_lo)
    member = np.zeros((n_rows, n_per), dtype=bool)
    for j in range(n_per):
        member[p_lo[j] // rs - row0: p_hi[j] // rs - row0 + 1, j] = True
    counts = member.sum(axis=1).astype(np.int64)
    pr = Profile(rs=rs, row0=row0, counts=counts, member=member, lo_t=lo_t, hi_t=hi_t,
                 last_period=n_per - 1 if last_period is None else last_period)
    center = (lo_t + hi_t) / 2
    pr.poc = poc_row(counts, pr.row_mid(np.arange(n_rows)), center)
    pr.va_lo, pr.va_hi = value_area(counts, pr.poc)
    _tails(pr)
    _single_prints(pr)
    _tpo_count(pr)
    return pr


def _run_from_extreme(pr: Profile, top: bool) -> int:
    """Single-print rows counted inward from an extreme, stopping at the first row printed by the
    last period (a tail may not be formed in the last period) [C4]."""
    n = pr.n_rows
    order = range(n - 1, -1, -1) if top else range(n)
    k = 0
    for i in order:
        if pr.counts[i] != 1:
            break
        if int(np.flatnonzero(pr.member[i])[0]) == pr.last_period:
            break
        k += 1
    return k


def _tails(pr: Profile) -> None:
    hi_len = _run_from_extreme(pr, top=True)
    lo_len = _run_from_extreme(pr, top=False)
    if hi_len >= pr.n_rows or lo_len >= pr.n_rows:          # degenerate one-period profile
        hi_len = lo_len = 0
    pr.tail_hi_len = hi_len if hi_len >= 2 else 0
    pr.tail_lo_len = lo_len if lo_len >= 2 else 0
    pr.poor_high = pr.tail_hi_len == 0 and pr.counts[-1] >= 2
    pr.poor_low = pr.tail_lo_len == 0 and pr.counts[0] >= 2


def _single_prints(pr: Profile) -> None:
    """Runs of >= 3 consecutive single-TPO rows that touch neither the top nor the bottom row."""
    runs, n, i = [], pr.n_rows, 0
    c = pr.counts
    while i < n:
        if c[i] == 1:
            j = i
            while j + 1 < n and c[j + 1] == 1:
                j += 1
            if j - i + 1 >= 3 and i > 0 and j < n - 1:
                runs.append((i, j))
            i = j + 1
        else:
            i += 1
    pr.single_runs = runs


def _tpo_count(pr: Profile) -> None:
    """TPOs above vs below the POC row, excluding tail rows."""
    keep = np.ones(pr.n_rows, dtype=bool)
    if pr.tail_hi_len:
        keep[pr.n_rows - pr.tail_hi_len:] = False
    if pr.tail_lo_len:
        keep[:pr.tail_lo_len] = False
    idx = np.arange(pr.n_rows)
    pr.tpo_above = int(pr.counts[(idx > pr.poc) & keep].sum())
    pr.tpo_below = int(pr.counts[(idx < pr.poc) & keep].sum())


def rotation_factor(p_lo, p_hi) -> int:
    """Spec p.112-113: for each period after A, +1/-1/0 on the high vs prior high, same for lows; sum."""
    p_lo, p_hi = np.asarray(p_lo), np.asarray(p_hi)
    return int(np.sign(np.diff(p_hi)).sum() + np.sign(np.diff(p_lo)).sum())


def volume_profile(bar_lo_t, bar_hi_t, bar_vol, rs: int, row0: int, n_rows: int):
    """Volume per row, spreading each 1-minute bar's volume evenly over the ticks it traded [C5]."""
    vol = np.zeros(n_rows)
    for lo, hi, v in zip(bar_lo_t, bar_hi_t, bar_vol):
        ticks = np.arange(lo, hi + 1)
        np.add.at(vol, ticks // rs - row0, v / len(ticks))
    return vol


def volume_va(pr: Profile, bar_lo_t, bar_hi_t, bar_vol) -> tuple[int, int, int]:
    """Volume POC / VAL / VAH in ticks (robustness check only, spec section 3)."""
    vol = volume_profile(bar_lo_t, bar_hi_t, bar_vol, pr.rs, pr.row0, pr.n_rows)
    poc = poc_row(vol, pr.row_mid(np.arange(pr.n_rows)), (pr.lo_t + pr.hi_t) / 2)
    lo, hi = value_area(vol, poc)
    return pr.row_low(poc), max(pr.row_low(lo), pr.lo_t), min(pr.row_high(hi), pr.hi_t)
