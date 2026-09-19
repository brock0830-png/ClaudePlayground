"""Ingest FMP MCP tool results (JSON arrays saved by the harness) into parquet.

Usage: python src/fmp_ingest.py <tool-results-dir> <out-dir>

Routes each file by content:
  * price rows with a 'symbol' key  -> data/raw/fmp/<SYMBOL>.parquet (deduped by date)
  * treasury rows (have 'month3')   -> data/raw/fmp/TREASURY.parquet
  * indicator rows (have 'name')    -> data/raw/fmp/IND_<name>.parquet
Symbols with a leading caret are stored without it (e.g. ^GSPC -> GSPC).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


def _load(p: Path):
    txt = p.read_text()
    try:
        obj = json.loads(txt)
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict) and "content" in obj:  # Drive envelope, not FMP
        return None
    return obj if isinstance(obj, list) and obj and isinstance(obj[0], dict) else None


def ingest(tool_dir: str | Path, out_dir: str | Path) -> dict[str, int]:
    tool_dir, out_dir = Path(tool_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[str, list[pd.DataFrame]] = {}
    for p in sorted(tool_dir.glob("mcp-FMP-*.txt")):
        rows = _load(p)
        if rows is None:
            continue
        df = pd.DataFrame(rows)
        if "symbol" in df.columns:
            for sym, g in df.groupby("symbol"):
                frames.setdefault(sym.lstrip("^"), []).append(g)
        elif "month3" in df.columns:
            frames.setdefault("TREASURY", []).append(df)
        elif "name" in df.columns:
            for nm, g in df.groupby("name"):
                frames.setdefault(f"IND_{nm}", []).append(g)
    counts = {}
    for key, parts in frames.items():
        df = pd.concat(parts, ignore_index=True)
        df["date"] = pd.to_datetime(df["date"])
        df = df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
        target = out_dir / f"{key}.parquet"
        if target.exists():
            old = pd.read_parquet(target)
            df = pd.concat([old, df]).drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
        df.to_parquet(target, index=False)
        counts[key] = len(df)
    return counts


if __name__ == "__main__":
    c = ingest(sys.argv[1], sys.argv[2])
    for k in sorted(c):
        print(f"{k:14s} {c[k]:6d}")
