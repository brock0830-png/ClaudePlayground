"""Databento GLBX.MDP3 ohlcv-1m continuous front month -> RTH sessions, overnight, back-adjusted.

Spec section 1:
  * Session: RTH 09:30-16:15 ET in 30-minute periods A, B, C... (last period 15 minutes).
  * Overnight (ETH) kept separately: every bar between the prior RTH close and this RTH open [C6].
  * Roll on volume switch (Databento `ES.v.0`), back-adjusted, roll dates recorded (rolls_<SYM>.csv).

Back-adjustment is additive and anchored on the latest contract. At each roll the spread
new - old is measured at the last minute of the last all-old-contract RTH session where both
contracts traded (the new contract's bars are fetched separately, see fetch_roll_spreads) [C7].
Every price is stored as integer ticks. Within one RTH session the contract never changes (the
Databento switch happens at 00:00 UTC, i.e. in the evening ET), so a session's adjusted and raw
prices differ by one constant, `offset_t`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
DERIVED = ROOT / "data" / "derived"
TICK = {"ES": 0.25, "NQ": 0.25}
TICK_USD = {"ES": 12.50, "NQ": 5.00}
RTH_START = 9 * 60 + 30
ET = "America/New_York"


def key() -> str:
    """DATABENTO_API_KEY from the environment, else ~/.databento_key. Never stored in the repo."""
    import os
    return os.environ.get("DATABENTO_API_KEY") or (Path.home() / ".databento_key").read_text().strip()


def raw_file() -> Path:
    fs = sorted(RAW.rglob("*.dbn.zst"))
    if not fs:
        raise FileNotFoundError(f"no .dbn.zst under {RAW}")
    return fs[0]


def load_raw(sym: str) -> pd.DataFrame:
    import databento as db
    store = db.DBNStore.from_file(raw_file())
    df = store.to_df(price_type="float", pretty_ts=True, map_symbols=True)
    df = df[df["symbol"] == f"{sym}.v.0"].sort_index()
    return df[["instrument_id", "open", "high", "low", "close", "volume"]]


# ---------------------------------------------------------------- rolls
def roll_points(df: pd.DataFrame) -> pd.DataFrame:
    iid = df["instrument_id"].to_numpy()
    ch = np.flatnonzero(iid[1:] != iid[:-1]) + 1
    return pd.DataFrame({"ts_new": df.index[ch], "old_id": iid[ch - 1], "new_id": iid[ch]})


def fetch_roll_spreads(sym: str, df: pd.DataFrame, rth_end_of: dict) -> pd.DataFrame:
    """For each roll, fetch the new contract's 1-minute bars over the last RTH session that was
    entirely on the old contract and measure new - old at the last common minute. Cached in
    rolls_<SYM>.csv (committed), so this runs once."""
    out = ROOT / f"rolls_{sym}.csv"
    if out.exists():
        return pd.read_csv(out, parse_dates=["ts_new", "spread_ts"])
    import databento as db
    c = db.Historical(key())
    rp = roll_points(df)
    rows = []
    for r in rp.itertuples():
        et_new = r.ts_new.tz_convert(ET)
        # last RTH session that ended before the switch; widen to the whole session, then step
        # back up to 5 sessions, if the new contract has no common minute (degraded days) [C7]
        days = sorted(d for d in rth_end_of if rth_end_of[d] < et_new)
        both = None
        for back in range(6):
            d = days[-1 - back]
            end = rth_end_of[d]
            for start in (end - pd.Timedelta(minutes=45), pd.Timestamp(d).tz_localize(ET) + pd.Timedelta(minutes=RTH_START)):
                new = _retry(c.timeseries.get_range, dataset="GLBX.MDP3", schema="ohlcv-1m", symbols=[int(r.new_id)],
                                             stype_in="instrument_id", start=start.tz_convert("UTC"),
                                             end=end.tz_convert("UTC")).to_df(price_type="float")
                old = df.loc[start.tz_convert("UTC"):end.tz_convert("UTC") - pd.Timedelta(seconds=1)]
                old = old[old["instrument_id"] == r.old_id]
                if len(new) and len(old):
                    both = old[["close"]].join(new[["close"]], how="inner", lsuffix="_old", rsuffix="_new")
                    if len(both):
                        break
            if both is not None and len(both):
                break
        if both is None or both.empty:
            raise RuntimeError(f"no common minute for roll {r}")
        last = both.iloc[-1]
        sym_old = _retry(c.symbology.resolve, dataset="GLBX.MDP3", symbols=[str(r.old_id)], stype_in="instrument_id",
                                      stype_out="raw_symbol", start_date=d.strftime("%Y-%m-%d"),
                                      end_date=(d + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
        sym_new = _retry(c.symbology.resolve, dataset="GLBX.MDP3", symbols=[str(r.new_id)], stype_in="instrument_id",
                                      stype_out="raw_symbol", start_date=d.strftime("%Y-%m-%d"),
                                      end_date=(d + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
        rows.append(dict(ts_new=r.ts_new, old_id=r.old_id, new_id=r.new_id,
                         old_symbol=_first_symbol(sym_old, r.old_id), new_symbol=_first_symbol(sym_new, r.new_id),
                         last_old_session=d.strftime("%Y-%m-%d"), spread_ts=both.index[-1],
                         old_close=last["close_old"], new_close=last["close_new"],
                         spread=last["close_new"] - last["close_old"]))
    res = pd.DataFrame(rows)
    res.to_csv(out, index=False)
    return pd.read_csv(out, parse_dates=["ts_new", "spread_ts"])


def _retry(fn, *a, **kw):
    """Databento calls through the proxy occasionally 504; retry with backoff."""
    import time
    for i in range(5):
        try:
            return fn(*a, **kw)
        except Exception:
            if i == 4:
                raise
            time.sleep(5 * 2 ** i)


def _first_symbol(resp: dict, iid) -> str:
    m = resp.get("result", {}).get(str(iid), [])
    return m[0]["s"] if m else ""


# ---------------------------------------------------------------- sessions
def nyse_sessions(start: str, end: str) -> pd.DataFrame:
    """NYSE trading days. RTH ends 15 minutes after the NYSE close (16:15, or 13:15 on early closes)."""
    import exchange_calendars as xc
    cal = xc.get_calendar("XNYS", start="2005-01-01")
    s = cal.sessions_in_range(start, end)
    rows = []
    for d in s:
        cl = pd.Timestamp(cal.closes.loc[d])
        cl = (cl if cl.tzinfo else cl.tz_localize("UTC")).tz_convert(ET)
        rows.append(dict(date=d.date(), rth_open=pd.Timestamp(d.date()).tz_localize(ET) + pd.Timedelta(minutes=RTH_START),
                         rth_end=cl + pd.Timedelta(minutes=15), early_close=cl.hour < 16))
    return pd.DataFrame(rows)


@dataclass
class Market:
    sym: str
    tick: float
    bars: pd.DataFrame        # RTH bars: session, minute (ET minute of day), o h l c (adjusted ticks), v
    sessions: pd.DataFrame    # one row per RTH session
    rolls: pd.DataFrame

    def session_bars(self, i: int) -> pd.DataFrame:
        s = self.sessions.iloc[i]
        return self.bars.iloc[s.b0:s.b1]


MIN_RTH_BARS = 60


def build_market(sym: str, force: bool = False) -> Market:
    DERIVED.mkdir(parents=True, exist_ok=True)
    fb, fs = DERIVED / f"{sym}_rth_bars.parquet", DERIVED / f"{sym}_sessions.parquet"
    rolls_path = ROOT / f"rolls_{sym}.csv"
    if fb.exists() and fs.exists() and rolls_path.exists() and not force:
        return Market(sym, TICK[sym], pd.read_parquet(fb), pd.read_parquet(fs),
                      pd.read_csv(rolls_path, parse_dates=["ts_new", "spread_ts"]))
    tick = TICK[sym]
    df = load_raw(sym)
    cal = nyse_sessions(str(df.index[0].date()), str(df.index[-1].date()))
    rth_end_of = {pd.Timestamp(r.date): r.rth_end for r in cal.itertuples()}
    rolls = fetch_roll_spreads(sym, df, rth_end_of)

    # additive back-adjustment by contract, anchored on the latest contract
    spread_t = np.rint(rolls["spread"].to_numpy() / tick).astype(np.int64)
    ids = [rolls["old_id"].iloc[0]] + list(rolls["new_id"])
    cum_after = np.concatenate([np.cumsum(spread_t[::-1])[::-1], [0]])   # sum of spreads of later rolls
    # contracts can repeat ids only if Databento reuses them; guard by position in time instead
    seg = np.searchsorted(pd.DatetimeIndex(rolls["ts_new"]).as_unit("ns").asi8, df.index.as_unit("ns").asi8, side="right")
    off = cum_after[seg]
    assert (df["instrument_id"].to_numpy() == np.array(ids, dtype=np.int64)[seg]).all()

    px = {k: np.rint(df[k].to_numpy() / tick).astype(np.int64) + off for k in ("open", "high", "low", "close")}
    et = df.index.tz_convert(ET)
    allb = pd.DataFrame({"ts": et, "o": px["open"], "h": px["high"], "l": px["low"], "c": px["close"],
                         "v": df["volume"].to_numpy(), "off": off, "iid": df["instrument_id"].to_numpy()})

    ts = df.index.as_unit("ns").asi8       # UTC ns, sorted
    sess_rows, rth_parts, dropped = [], [], []
    prev_end = None
    for r in cal.itertuples():
        a = np.searchsorted(ts, r.rth_open.value, side="left")
        b = np.searchsorted(ts, r.rth_end.value, side="left")
        e0 = np.searchsorted(ts, prev_end.value, side="left") if prev_end is not None else a
        prev_end = r.rth_end
        rth = allb.iloc[a:b]
        eth = allb.iloc[e0:a]
        if len(rth) < MIN_RTH_BARS:
            dropped.append((r.date, len(rth), "fewer than 60 RTH bars"))
            continue
        mins = (rth["ts"].dt.hour * 60 + rth["ts"].dt.minute).to_numpy()
        per = (mins - RTH_START) // 30
        if mins[0] > RTH_START + 5 or (mins < RTH_START + 60).sum() < 30:
            dropped.append((r.date, len(rth), "missing the open or most of the IB"))
            continue
        if len(np.unique(per)) != per.max() + 1:
            dropped.append((r.date, len(rth), "a 30-minute period has no bars"))
            continue
        k = len(sess_rows)
        part = rth[["o", "h", "l", "c", "v", "off", "iid"]].copy()
        part["minute"] = mins
        part["session"] = k
        rth_parts.append(part)
        offs = rth["off"].unique()
        assert len(offs) == 1, f"contract changed inside RTH on {r.date}"
        sess_rows.append(dict(date=pd.Timestamp(r.date), early_close=bool(r.early_close),
                              end_minute=int(r.rth_end.hour * 60 + r.rth_end.minute), n_bars=len(rth),
                              offset_t=int(offs[0]), iid=int(rth["iid"].iloc[0]),
                              on_hi_t=int(eth["h"].max()) if len(eth) else np.nan,
                              on_lo_t=int(eth["l"].min()) if len(eth) else np.nan,
                              on_bars=len(eth)))
    bars = pd.concat(rth_parts, ignore_index=True)
    sessions = pd.DataFrame(sess_rows)
    b0 = np.searchsorted(bars["session"].to_numpy(), np.arange(len(sessions)), side="left")
    b1 = np.searchsorted(bars["session"].to_numpy(), np.arange(len(sessions)), side="right")
    sessions["b0"], sessions["b1"] = b0, b1
    sym_by_iid = dict(zip(rolls["old_id"], rolls["old_symbol"])) | dict(zip(rolls["new_id"], rolls["new_symbol"]))
    sessions["contract"] = sessions["iid"].map(sym_by_iid)
    bars.to_parquet(fb)
    sessions.to_parquet(fs)
    pd.DataFrame(dropped, columns=["date", "rth_bars", "reason"]).to_csv(ROOT / f"sessions_dropped_{sym}.csv", index=False)
    return Market(sym, tick, bars, sessions, rolls)
