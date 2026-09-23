"""Ingest TradingView get_ohlcv tool results (JSON saved by the harness) and the user's CSV exports into parquet.

Usage:
  python crypto/src/ingest.py tv <tool-results-dir>     -> crypto/data/tv/<TICKER>_<interval>.parquet
  python crypto/src/ingest.py user <csv> [<csv> ...]    -> crypto/data/user/<TICKER>_<interval>.parquet

Bars are indexed by bar-open time in UTC. A file for the same symbol+interval is merged (union, later pull wins).
The last bar of a pull may still be forming; it is dropped when its close time is after the pull time.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TV_DIR = ROOT / "data" / "tv"
USER_DIR = ROOT / "data" / "user"
BAR_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1D": 86400, "1W": 604800}


def _merge_write(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    if path.exists():
        old = pd.read_parquet(path)
        df = pd.concat([old, df])
        df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df


def ingest_tv(tool_dir: str | Path) -> list[tuple[str, int, str, str]]:
    out = []
    for p in sorted(Path(tool_dir).glob("mcp-Tradingview_Remix-get_ohlcv-*.txt")):
        try:
            obj = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        if not obj.get("success") or not obj.get("bars"):
            continue
        sym, iv = obj["symbol"], obj["interval"]
        bars = pd.DataFrame(obj["bars"]).rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        bars["time"] = pd.to_datetime(bars["t"], unit="s", utc=True)
        bars = bars.set_index("time")[["open", "high", "low", "close", "volume"]].astype(float)
        # drop a still-forming last bar: pull time is the file's mtime (ms epoch in the filename)
        m = re.search(r"-(\d{13})\.txt$", p.name)
        if m:
            pulled = pd.Timestamp(int(m.group(1)), unit="ms", tz="UTC")
            bars = bars[bars.index + pd.Timedelta(seconds=BAR_SECONDS[iv]) <= pulled]
        ticker = sym.split(":")[1]
        df = _merge_write(bars, TV_DIR / f"{ticker}_{iv}.parquet")
        out.append((f"{ticker}_{iv}", len(df), str(df.index[0]), str(df.index[-1])))
    return out


def ingest_user(paths: list[str]) -> list[tuple[str, int, str, str]]:
    out = []
    for p in paths:
        m = re.search(r"BINANCE_([A-Z0-9]+)_(\d+)\.csv$", p)
        if not m:
            continue
        ticker, minutes = m.group(1), int(m.group(2))
        iv = {15: "15m", 30: "30m", 60: "1h", 240: "4h"}[minutes]
        df = pd.read_csv(p)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time").rename(columns={"Volume": "volume"})
        df.columns = [c.strip().replace(" ", "_") for c in df.columns]
        df = _merge_write(df, USER_DIR / f"{ticker}_{iv}.parquet")
        out.append((f"{ticker}_{iv}", len(df), str(df.index[0]), str(df.index[-1])))
    return out


if __name__ == "__main__":
    mode = sys.argv[1]
    rows = ingest_tv(sys.argv[2]) if mode == "tv" else ingest_user(sys.argv[2:])
    for r in rows:
        print(*r, sep="\t")
