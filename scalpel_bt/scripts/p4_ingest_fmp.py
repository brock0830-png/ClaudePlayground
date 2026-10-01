"""
Phase 4 data ingest: FMP MCP tool results (JSON arrays the harness saved to disk) -> data/external/.

  python scripts/p4_ingest_fmp.py <tool-results-dir>

Writes data/external/etf/<SYM>.csv.gz (date,open,high,low,close,volume; dividend-adjusted) for the fresh
ETFs and data/external/GSPC.csv.gz (S&P 500 index OHLC). Existing Phase 2-3 ETF files are never touched.
Checks: no page at FMP's 5,000-row cap (= possibly truncated), no duplicate dates with different prices,
and no business-day gap longer than 7 calendar days inside a series.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ETF_DIR = ROOT / "data" / "external" / "etf"
FRESH = ["XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "EWZ", "EWA", "EWC", "EWY", "EWT", "FXI", "INDA", "EWW"]
SEEN_ETF = {"SPY", "QQQ", "IWM", "DIA", "EFA", "EWG", "EWJ", "EWU"}


def pages(tool_dir: Path):
    for p in sorted(tool_dir.glob("mcp-FMP-*.txt")):
        try:
            rows = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "symbol" in rows[0]:
            yield p.name, rows


def main(tool_dir):
    frames, report = {}, []
    for name, rows in pages(Path(tool_dir)):
        df = pd.DataFrame(rows)
        sym = str(df["symbol"].iat[0]).lstrip("^")
        if len(df) >= 5000:
            raise SystemExit(f"{name}: {len(df)} rows = FMP cap, page may be truncated")
        if "adjClose" in df:
            df = df.rename(columns={"adjOpen": "open", "adjHigh": "high", "adjLow": "low", "adjClose": "close"})
        df = df[["date", "open", "high", "low", "close", "volume"]]
        frames.setdefault(sym, []).append(df)
        report.append((sym, name, len(df), df["date"].min(), df["date"].max()))
    out = {}
    for sym, parts in frames.items():
        d = pd.concat(parts, ignore_index=True)
        d["date"] = pd.to_datetime(d["date"])
        dup = d[d.duplicated("date", keep=False)]
        if len(dup) and dup.groupby("date")["close"].nunique().max() > 1:
            raise SystemExit(f"{sym}: conflicting duplicate dates")
        d = d.drop_duplicates("date").sort_values("date").reset_index(drop=True)
        gap = d["date"].diff().dt.days.max()
        if gap and gap > 7:
            g = d.loc[d["date"].diff().dt.days.idxmax(), "date"]
            raise SystemExit(f"{sym}: {gap}-day gap ending {g.date()}")
        out[sym] = d
    for sym, d in out.items():
        if sym in FRESH:
            d.to_csv(ETF_DIR / f"{sym}.csv.gz", index=False)
        elif sym == "GSPC":
            d.to_csv(ROOT / "data" / "external" / "GSPC.csv.gz", index=False)
        elif sym in SEEN_ETF:
            # top-up rows after the Phase 3 file's last date, kept in a separate file
            old = pd.read_csv(ETF_DIR / f"{sym}.csv.gz", parse_dates=["date"])
            new = d[d["date"] > old["date"].max()]
            new.to_csv(ROOT / "data" / "external" / "etf_update" / f"{sym}.csv", index=False)
        print(f"{sym:6s} {len(d):5d} rows {d['date'].iat[0].date()} .. {d['date'].iat[-1].date()}")
    missing = [s for s in FRESH if s not in out]
    print("pages:", len(report), "| fresh missing:", missing)


if __name__ == "__main__":
    main(sys.argv[1])
