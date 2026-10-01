"""NYSE trading calendar for the gamma-node study.

Hand-maintained table from https://www.nyse.com/markets/hours-calendars (checked
against the table in UW's uw-options-data-lake script for 2025-2027). Running past
the table is a loud failure: a guessed holiday is indistinguishable from a real one.
"""
from __future__ import annotations

from datetime import date, timedelta

HOLIDAYS = {
    2023: "01-02 01-16 02-20 04-07 05-29 06-19 07-04 09-04 11-23 12-25",
    2024: "01-01 01-15 02-19 03-29 05-27 06-19 07-04 09-02 11-28 12-25",
    2025: "01-01 01-09 01-20 02-17 04-18 05-26 06-19 07-04 09-01 11-27 12-25",
    2026: "01-01 01-19 02-16 04-03 05-25 06-19 07-03 09-07 11-26 12-25",
    2027: "01-01 01-18 02-15 03-26 05-31 06-18 07-05 09-06 11-25 12-24",
}
# 13:00 ET equity close; SPXW PM-settled 0DTE options stop trading at 13:15 and
# settle on the 13:00 index close.
EARLY_CLOSES = {
    2023: "07-03 11-24",
    2024: "07-03 11-29 12-24",
    2025: "07-03 11-28 12-24",
    2026: "11-27 12-24",
    2027: "11-26",
}


def _days(src: dict[int, str], y: int) -> frozenset[date]:
    if y not in src:
        raise KeyError(f"calendar has no entry for {y}; add it from the NYSE page")
    return frozenset(date(y, int(md[:2]), int(md[3:])) for md in src[y].split())


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _days(HOLIDAYS, d.year)


def is_early_close(d: date) -> bool:
    return d in _days(EARLY_CLOSES, d.year)


def close_time_et(d: date) -> tuple[int, int]:
    return (13, 0) if is_early_close(d) else (16, 0)


def next_trading_day(d: date) -> date:
    for _ in range(15):
        d += timedelta(days=1)
        if is_trading_day(d):
            return d
    raise ValueError(f"no trading day after {d}")


def previous_trading_day(d: date) -> date:
    for _ in range(15):
        d -= timedelta(days=1)
        if is_trading_day(d):
            return d
    raise ValueError(f"no trading day before {d}")


def trading_days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def last_n_trading_days(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if is_trading_day(d):
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]
