"""
A1 (PROTOCOL_P4.md): forward paper-trade logger for the frozen P2A and P3B. Run after 17:00 ET on trading days:

    python scripts/p4_signal_logger.py                  # live: Yahoo Finance daily bars, appends today's rows
    python scripts/p4_signal_logger.py --dry-run        # print, do not write
    python scripts/p4_signal_logger.py --source local --date 2026-09-29 --dry-run   # repo data (tests)

For ES, SPX, SPY, DIA and IWM it computes IBS, VIX, the P3B score, and the P2A / P3B signal, replaying the
frozen rules over ~3 years of history to know whether a trade is already open. One row per (date, market,
system) is APPENDED to results/live/signals_log.csv. Existing rows are never rewritten or edited; a
(date, market, system) that is already logged is skipped.

Execution conventions (as tested): SPX/SPY/DIA/IWM market-on-close at 16:00 ET on the signal date (paper fill at
that close; SPX itself is not tradable, use SPY or ES), exit at the close 5 sessions later. ES: entry at the
18:00 ET open that evening, exit at the 18:00 ET open after the 5th session.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd

from scalpel import p3

LOG = ROOT / "results" / "live" / "signals_log.csv"
COLS = ["logged_utc", "date", "market", "system", "ibs", "vix", "score", "signal", "in_position",
        "planned_entry", "planned_exit", "source", "note"]
FROZEN = {c["name"]: c["spec"] for c in json.loads((ROOT / "results" / "p3" / "frozen_candidates.json").read_text())}
SYSTEMS = {"P2A": FROZEN["P2A_reference"], "P3B": FROZEN["P3B_oversold_score90"]}
YAHOO = {"ES": "ES=F", "SPX": "^GSPC", "SPY": "SPY", "DIA": "DIA", "IWM": "IWM", "VIX": "^VIX"}
ET = ZoneInfo("America/New_York")


# ------------------------------------------------------------------ data
def yahoo(symbol: str, years: int = 3) -> pd.DataFrame:
    import requests
    r = requests.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
                     params={"range": f"{years}y", "interval": "1d", "events": "div,splits"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    tz = ZoneInfo(res["meta"].get("exchangeTimezoneName", "America/New_York"))
    dates = [dt.datetime.fromtimestamp(t, tz).date() for t in res["timestamp"]]
    d = pd.DataFrame({"date": pd.to_datetime(dates), "open": q["open"], "high": q["high"], "low": q["low"],
                      "close": q["close"]})
    adj = res["indicators"].get("adjclose")
    if adj and symbol in ("SPY", "DIA", "IWM"):           # dividend-adjust OHLC like the backtests (IBS unchanged)
        f = np.asarray(adj[0]["adjclose"], float) / d["close"].values
        for c in ("open", "high", "low", "close"):
            d[c] = d[c] * f
    return d.dropna().drop_duplicates("date", keep="last").reset_index(drop=True)


def local(market: str) -> pd.DataFrame:
    """Repo data (for tests and backfill checks)."""
    from scalpel import p4
    if market == "VIX":
        v = p3.load_vix("VIX")
        return pd.DataFrame({"date": v.index, "close": v.values})
    if market == "SPX":
        return pd.read_csv(ROOT / "data" / "external" / "GSPC.csv.gz", parse_dates=["date"])
    if market == "ES":
        return p4.load_es("all")[["date", "open", "high", "low", "close"]]
    return p4.load_etf(market)[["date", "open", "high", "low", "close"]]


def complete(d: pd.DataFrame, market: str, now_et: dt.datetime) -> pd.DataFrame:
    """Drop today's bar unless the session has closed (ES 17:00 ET; cash markets and VIX 16:15 ET)."""
    cutoff = dt.time(17, 0) if market == "ES" else dt.time(16, 15)
    today = pd.Timestamp(now_et.date())
    if now_et.time() < cutoff:
        d = d[d["date"] < today]
    return d


# ------------------------------------------------------------------ signals
def nyse_sessions(after: pd.Timestamp, n: int) -> list[pd.Timestamp]:
    import pandas_market_calendars as mcal
    cal = mcal.get_calendar("NYSE")
    s = cal.schedule(start_date=after + pd.Timedelta(days=1), end_date=after + pd.Timedelta(days=20))
    return [pd.Timestamp(x) for x in s.index[:n]]


def evaluate(bars: pd.DataFrame, vix: pd.Series, market: str, date: pd.Timestamp) -> list[dict]:
    bars = bars[bars["date"] <= date].reset_index(drop=True)
    if len(bars) == 0 or bars["date"].iat[-1] != date:
        return []
    V = pd.DataFrame({"vix": vix})
    D = p3.add_features(bars, V)
    D["roll"] = False
    D["sym"] = "ES" if market == "ES" else market
    n = len(D)
    mode = "next_open" if market == "ES" else "close"
    vix_today = vix.get(date, np.nan)
    rows = []
    for name, spec in SYSTEMS.items():
        note = ""
        if "vix>20" in spec["entry"] and not np.isfinite(vix_today):
            note = "VIX close for this date missing: P2A not evaluated"
        t = p3.simulate(D, spec, mode, 0, n)
        dec = (t["exit"] - (1 if mode == "next_open" else 0)).where(t["why"] != "end", n - 1)
        in_pos = bool(((t["sig"] < n - 1) & (dec >= n - 1)).any())
        # today's signal: the frozen entry condition on the last bar while flat (the engine cannot record a
        # next-open trade before the next bar exists, so this is evaluated directly)
        cond_today = bool(p3.all_of(D, spec["entry"])[n - 1]) and np.isfinite(D["atr20"].iat[-1])
        sig = cond_today and not in_pos and not note
        if mode == "next_open":
            s = nyse_sessions(date, 5)
            entry = f"{date.date()} 18:00 ET (open of the {s[0].date()} session)"
            exit_ = f"{s[4].date()} 18:00 ET (open of the session after {s[4].date()})"
        else:
            s = nyse_sessions(date, 5)
            entry = f"{date.date()} 16:00 ET close (MOC)" + (" via SPY or ES" if market == "SPX" else "")
            exit_ = f"{s[4].date()} 16:00 ET close"
        rows.append(dict(date=str(date.date()), market=market, system=name,
                         ibs=round(float(D["ibs"].iat[-1]), 4), vix=round(float(vix_today), 2) if np.isfinite(vix_today) else "",
                         score=round(float(D["os_score"].iat[-1]), 4) if np.isfinite(D["os_score"].iat[-1]) else "",
                         signal=int(sig), in_position=int(in_pos),
                         planned_entry=entry if sig else "", planned_exit=exit_ if sig else "", note=note))
    return rows


# ------------------------------------------------------------------ append-only log
def logged_keys() -> set:
    if not LOG.exists():
        return set()
    with open(LOG, newline="") as fh:
        r = csv.reader(fh)
        hdr = next(r)
        if hdr != COLS:
            raise SystemExit(f"{LOG} header differs from the expected columns; refusing to append")
        i = [hdr.index(k) for k in ("date", "market", "system")]
        return {tuple(row[j] for j in i) for row in r}


def append(rows: list[dict]):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with open(LOG, "a", newline="") as fh:                  # append mode only: past rows are never touched
        w = csv.DictWriter(fh, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", choices=["yahoo", "local"], default="yahoo")
    ap.add_argument("--date", help="session date to evaluate (default: latest complete session)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    now_et = dt.datetime.now(ET)
    get = yahoo if a.source == "yahoo" else local
    vb = complete(get(YAHOO["VIX"] if a.source == "yahoo" else "VIX"), "VIX", now_et)
    vix = pd.Series(vb["close"].values, index=pd.DatetimeIndex(vb["date"]))
    have = logged_keys()
    out = []
    for market in ("ES", "SPX", "SPY", "DIA", "IWM"):
        bars = complete(get(YAHOO[market] if a.source == "yahoo" else market), market, now_et)
        date = pd.Timestamp(a.date) if a.date else bars["date"].iat[-1]
        for r in evaluate(bars, vix, market, date):
            if (r["date"], r["market"], r["system"]) in have:
                continue
            r.update(logged_utc=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
                     source=f"{a.source}:{YAHOO[market] if a.source == 'yahoo' else market}")
            out.append(r)
    for r in out:
        flag = "SIGNAL" if r["signal"] else ("in trade" if r["in_position"] else "-")
        print(f"{r['date']} {r['market']:4s} {r['system']}  IBS {r['ibs']}  VIX {r['vix']}  score {r['score']}  "
              f"{flag}  {r['planned_entry']}  {r['note']}")
    if not a.dry_run and out:
        append(out)
        print(f"appended {len(out)} rows to {LOG}")
    elif not out:
        print("nothing new to log")


if __name__ == "__main__":
    main()
