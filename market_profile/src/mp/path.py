"""Intrabar price path used for every fill decision.

Each 1-minute bar becomes four points: open, first extreme, second extreme, close. An up bar
(close >= open) is assumed to go O -> L -> H -> C and a down bar O -> H -> L -> C; a flat bar
visits the extreme nearer the open first [C8]. Between points the price moves monotonically, so a
level is crossed at most once per segment and the order of stop, target and entry events inside a
bar is well defined. The open point of every bar is a "jump" from the previous close: a level
crossed on a jump fills at the open (gap fill), otherwise it fills at the level itself.
"""
from __future__ import annotations

import numpy as np


def bar_points(o, h, l, c) -> np.ndarray:
    o, h, l, c = (np.asarray(x, dtype=np.int64) for x in (o, h, l, c))
    up = (c > o) | ((c == o) & (o - l <= h - o))
    x1 = np.where(up, l, h)
    x2 = np.where(up, h, l)
    return np.stack([o, x1, x2, c], axis=1).reshape(-1)


class Path:
    def __init__(self, o, h, l, c):
        self.P = bar_points(o, h, l, c)
        n = len(self.P)
        self.jump = np.zeros(n, dtype=bool)
        self.jump[0::4] = True

    def fill(self, k: int, level: int) -> int:
        return int(self.P[k]) if self.jump[k] else int(level)

    def first_at_or_above(self, k0: int, k1: int, level: float) -> int:
        seg = self.P[k0:k1] >= level
        return k0 + int(seg.argmax()) if seg.any() else -1

    def first_at_or_below(self, k0: int, k1: int, level: float) -> int:
        seg = self.P[k0:k1] <= level
        return k0 + int(seg.argmax()) if seg.any() else -1

    def first_beyond(self, k0: int, k1: int, level: float, up: bool) -> int:
        return self.first_at_or_above(k0, k1, level) if up else self.first_at_or_below(k0, k1, level)

    def touch(self, k0: int, k1: int, level: int, from_below: bool, armed_at_start: bool = False) -> int:
        """First point in [k0, k1) where price reaches `level` coming from the given side.

        The level is armed once a point lies strictly on the approach side. With armed_at_start the
        very first point must already be on that side, otherwise there is no touch."""
        seg = self.P[k0:k1]
        if not len(seg):
            return -1
        side = seg < level if from_below else seg > level
        if armed_at_start and not side[0]:
            return -1
        if not side.any():
            return -1
        a = int(side.argmax())
        hit = seg[a:] >= level if from_below else seg[a:] <= level
        return k0 + a + int(hit.argmax()) if hit.any() else -1
