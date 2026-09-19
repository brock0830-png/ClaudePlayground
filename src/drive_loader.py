"""Decode Norgate export chunks fetched through the Google Drive MCP tool.

The Drive tool returns file bytes as base64 inside a JSON envelope that the
harness writes to a tool-results file when the payload is large. This module
turns those envelopes into CSV/parquet on disk. It is the only Drive loading
route available in this environment (direct HTTPS to Google hosts is blocked
by the egress policy), and it only works for files up to roughly 6 MB.

Norgate export layout (verified on the files that could be loaded):
  daily_NNNN.csv   columns: ticker,date,o,h,l,c,v          (300 tickers per chunk, inferred)
  monthly_NNN.csv  columns: ticker,ym,o,h,l,c,n,v          (1000 tickers per chunk, verified)
Prices are total-return adjusted (dividends reinvested), verified against
test_TOTALRETURN.csv (exact match) and test_CAPITAL.csv (differs).
Delisted names carry a -YYYYMM suffix (delisting month).
Chunks are contiguous slices of the alphabetically sorted symbol manifest
(_done.txt), so data/norgate_chunk_map.csv says which chunk holds a ticker.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pandas as pd


def decode_envelope(path: str | Path) -> tuple[str, bytes]:
    """Return (title, raw_bytes) from a Drive download envelope on disk."""
    d = json.load(open(path))
    return d["title"], base64.b64decode(d["content"])


def load_norgate_csv(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw))
    datecol = "date" if "date" in df.columns else "ym"
    df[datecol] = pd.to_datetime(df[datecol])
    return df


def envelope_to_parquet(envelope_path: str | Path, out_dir: str | Path) -> Path:
    title, raw = decode_envelope(envelope_path)
    df = load_norgate_csv(raw)
    out = Path(out_dir) / (Path(title).stem + ".parquet")
    df.to_parquet(out, index=False)
    return out


def chunk_for(ticker: str, chunk_map_csv: str | Path = "data/norgate_chunk_map.csv") -> dict:
    cm = pd.read_csv(chunk_map_csv)
    row = cm.loc[cm.ticker == ticker]
    if row.empty:
        raise KeyError(ticker)
    return row.iloc[0].to_dict()
