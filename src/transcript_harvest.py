"""Recover small (inline) FMP tool results from the session transcript JSONL.

Inline results are not written to the tool-results directory, but the CLI
transcript stores every tool_result block. This scans those blocks, parses any
JSON array of records, and writes them through fmp_ingest's routing so that
quarterly Treasury pages land in data/raw/fmp/TREASURY.parquet.
"""
import json, sys
from pathlib import Path
import pandas as pd

def harvest(transcript: str):
    rows_by_key = {}
    for line in open(transcript):
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = o.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            c = block.get("content")
            texts = []
            if isinstance(c, str):
                texts = [c]
            elif isinstance(c, list):
                texts = [x.get("text", "") for x in c if isinstance(x, dict)]
            for t in texts:
                t = t.strip()
                if not t.startswith("["):
                    continue
                try:
                    arr = json.loads(t)
                except json.JSONDecodeError:
                    continue
                if not arr or not isinstance(arr[0], dict):
                    continue
                if "month3" in arr[0]:
                    rows_by_key.setdefault("TREASURY", []).extend(arr)
                elif "symbol" in arr[0]:
                    for r in arr:
                        rows_by_key.setdefault(r["symbol"].lstrip("^"), []).append(r)
                elif "name" in arr[0]:
                    for r in arr:
                        rows_by_key.setdefault("IND_" + r["name"], []).append(r)
    return rows_by_key

if __name__ == "__main__":
    out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    for key, rows in harvest(sys.argv[1]).items():
        df = pd.DataFrame(rows); df["date"] = pd.to_datetime(df["date"])
        target = out / f"{key}.parquet"
        if target.exists():
            old = pd.read_parquet(target); old["date"] = pd.to_datetime(old["date"])
            df = pd.concat([old, df])
        # merge rows for the same date field-by-field: the last non-null value wins, so a row from an unadjusted
        # endpoint never blanks out adjClose captured from the adjusted endpoint
        df = df.groupby("date", sort=True).last().reset_index()
        df.to_parquet(target, index=False)
        print(key, len(df), df.date.min().date(), df.date.max().date())
