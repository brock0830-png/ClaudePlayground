"""
Scalpel / TrueALGO-clone level engine — a line-for-line port of the
daily/weekly/monthly engines in docs_scalpel_v37.pine.

    sigma = PO * vol/100 / sqrt(periods)
    ts = sigma * bias/0.5            (upside scale)
    bs = sigma * (1-bias)/0.5        (downside scale)
    upper levels = PO + ts * mult,  lower levels = PO - bs * mult
    GP boxes at 0.618/0.650 of the inner range; range boxes = WRH/WRL +/- sigma*half

In v37 vol and bias are CONSTANTS, so every level is a fixed % of the period open.
mode="fixed"  -> reproduces TradingView exactly.
mode="scaled" -> pass `vol` = a point-in-time series (e.g. 252d mean VIX as of the
                 prior period close); bias stays constant (true TrueALGO bias history
                 is unknown — see CLAUDE.md).
"""
from __future__ import annotations
import pandas as pd
from .params_es import ES, GP_OUTER, GP_INNER


def level_frame(po: pd.Series, tf: str = "W", params: dict = ES,
                vol: pd.Series | float | None = None) -> pd.DataFrame:
    p = params[tf]
    v = p["vol"] if vol is None else vol
    sigma = po * (v / 100.0) / p["periods"] ** 0.5
    ts = sigma * (p["bias"] / 0.5)
    bs = sigma * ((1.0 - p["bias"]) / 0.5)
    o = pd.DataFrame(index=po.index)
    o["OPEN"] = po
    o["GB_TOP"] = po + ts * p["gbtop"]
    o["TH2"] = po + ts * p["wth2"]
    o["TH1"] = po + ts * p["wth1"]
    o["GB_BOT"] = po + ts * p["inner_top"]
    o["RH"] = po + ts * p["wrh"]
    o["RL"] = po - bs * p["wrl"]
    o["RB_TOP"] = po - bs * p["inner_bot"]
    o["TL1"] = po - bs * p["tl1"]
    o["TL2"] = po - bs * p["tl2"]
    o["RB_BOT"] = po - bs * p["rbbot"]
    inner = o["GB_BOT"] - o["RB_TOP"]
    o["GP_T_OUT"] = o["RB_TOP"] + inner * GP_OUTER
    o["GP_T_IN"] = o["RB_TOP"] + inner * GP_INNER
    o["GP_B_OUT"] = o["RB_TOP"] + inner * (1 - GP_OUTER)
    o["GP_B_IN"] = o["RB_TOP"] + inner * (1 - GP_INNER)
    o["RNG_T_HI"] = o["RH"] + sigma * p["rng_top"]
    o["RNG_T_LO"] = o["RH"] - sigma * p["rng_top"]
    o["RNG_B_HI"] = o["RL"] + sigma * p["rng_bot"]
    o["RNG_B_LO"] = o["RL"] - sigma * p["rng_bot"]
    return o.add_prefix(tf + "_")


def friday_rollover_holidays() -> set:
    """NYSE holidays that fall on a Friday, excluding Good Friday."""
    import pandas_market_calendars as mcal
    from pandas.tseries.offsets import Easter
    hol = pd.DatetimeIndex(mcal.get_calendar("NYSE").holidays().holidays)
    hol = hol[(hol.year >= 1990) & (hol.year <= 2035) & (hol.dayofweek == 4)]
    good_fridays = {pd.Timestamp(y, 1, 1) + Easter() - pd.Timedelta(days=2) for y in range(1990, 2036)}
    return {d for d in hol if d not in good_fridays}


def weekly_id(bars: pd.DataFrame) -> pd.Series:
    """
    Week id per bar (tz-aware America/New_York index). New CME week = first
    session after a >=40h gap (Sunday 18:00 ET). When Friday is an exchange holiday
    (July 4 / Juneteenth type, not Good Friday) TradingView starts the week on
    Thursday 18:00 and the following Sunday is NOT a new week. Verified against the
    2025-26 export; re-verify on longer history.
    """
    t = bars.index.to_series()
    new_week = t.diff().dt.total_seconds().div(3600).fillna(1e9) >= 40
    day = t.dt.tz_localize(None).dt.normalize()
    thu_eve = (t.dt.dayofweek == 3) & (t.dt.hour >= 17)
    rolls = thu_eve & (day + pd.Timedelta(days=1)).isin(friday_rollover_holidays())
    roll_start = rolls & ~rolls.shift(1, fill_value=False)
    last_roll = t.where(roll_start).ffill()
    new_week = new_week & ~((t - last_roll) < pd.Timedelta(days=4))
    return (new_week | roll_start).cumsum()


def weekly_open(bars: pd.DataFrame) -> pd.Series:
    """Weekly open per bar; week boundaries from weekly_id()."""
    return bars["open"].groupby(weekly_id(bars)).transform("first")
