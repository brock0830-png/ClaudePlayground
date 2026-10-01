"""Full Tape ingest: download one day, keep SPX/SPXW/XSP rows expiring today or next
trading day, verify, store as DATA_ROOT/tape/YYYY-MM-DD.parquet, log in MANIFEST.csv.

Follows the endpoint behaviour documented in UW's uw-options-data-lake skill (Bearer
auth, Accept */*, zip sniff, historic-window 403 carrying the earliest date, 429 daily
quota resetting 20:00 ET). The zip's CSV is streamed straight out of the archive, so the
~6 GB CSV never touches disk; peak local disk is the zip (~2-2.6 GB) plus the small
filtered Parquet.

Gates (PROTOCOL D2), any failure stops the day and nothing is stored:
  - the CSV has every kept column;
  - total rows seen by the Arrow parser == rows seen by an independent csv-module pass;
  - rows matching the filter in the Arrow pass == rows matching in the csv-module pass;
  - at least MIN_SPXW_0DTE_ROWS SPXW same-day-expiry rows (catches a format change);
  - no non-empty timestamp or numeric value becomes null when typed;
  - the written Parquet re-reads with the same row count.

CLI (run from gamma_nodes/):
  python src/tape_ingest.py probe                     earliest available date
  python src/tape_ingest.py day 2026-10-01            one day
  python src/tape_ingest.py range START END [--confirm]
  python src/tape_ingest.py pilot [--confirm]         most recent 60 trading days
"""
from __future__ import annotations

import csv
import io
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gn_calendar as cal  # noqa: E402
from gn_config import WORK, Config, load  # noqa: E402
from gn_store import Store, sha256_file  # noqa: E402

API_BASE = "https://api.unusualwhales.com/api"
FULL_TAPE = "/option-trades/full-tape/"
ZIP_MAGIC = b"PK\x03\x04"
CHUNK = 1 << 20
ROOTS = ("SPX", "SPXW", "XSP")
ROOT_RE = r"^(SPX|SPXW|XSP)\d{6}[CP]\d{8}$"
MIN_SPXW_0DTE_ROWS = 10_000
MIN_LOCAL_FREE_BYTES = 6_000_000_000

KEEP = (
    "id", "executed_at", "underlying_symbol", "option_chain_id", "expiry", "option_type",
    "strike", "price", "size", "nbbo_bid", "nbbo_ask", "underlying_price",
    "implied_volatility", "delta", "gamma", "open_interest", "volume", "ask_vol",
    "bid_vol", "mid_vol", "no_side_vol", "multi_vol", "canceled", "tags", "report_flags",
)
FLOAT_COLS = ("strike", "price", "nbbo_bid", "nbbo_ask", "underlying_price",
              "implied_volatility", "delta", "gamma")
INT_COLS = ("size", "open_interest", "volume", "ask_vol", "bid_vol", "mid_vol",
            "no_side_vol", "multi_vol")
INGEST_LOG_FIELDS = ("date", "zip_bytes", "csv_rows_arrow", "csv_rows_csvmod", "kept_rows_arrow",
                     "kept_rows_csvmod", "spxw_0dte_rows", "parquet_bytes", "seconds",
                     "status", "note", "ingested_utc")


class StopError(Exception):
    """A data gate failed: stop and report, do not substitute."""


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------

def _headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "Accept": "*/*",
            "User-Agent": "gamma-nodes-ingest/1.0"}


def _explain(status: int, body: str, hdrs) -> str:
    low = body.lower()
    if "historic_data_access_missing" in low:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", body)
        return f"outside your history window (earliest {m.group(1) if m else '?'}): {body[:300]}"
    if status == 401:
        return "401: bad or missing UW_API_KEY"
    if status == 429:
        return (f"429: rate limit or daily quota ({hdrs.get('x-uw-daily-req-count')} of "
                f"{hdrs.get('x-uw-token-req-limit')}); the daily quota resets 20:00 ET")
    if status == 403 and ("host_not_allowed" in low or "egress" in low):
        return "403 from this environment's egress proxy, not from UW"
    return f"HTTP {status}: {body[:300]}"


def download(d: date, dest: Path, key: str, retries: int = 3) -> int:
    """Stream the day's zip to dest. Returns bytes written."""
    url = f"{API_BASE}{FULL_TAPE}{d.isoformat()}"
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=_headers(key))
            with urllib.request.urlopen(req, timeout=120) as r:
                first = r.read(CHUNK)
                if first[:4] != ZIP_MAGIC:
                    body = (first + r.read()).decode("utf-8", "replace")
                    raise StopError(_explain(r.status, body, r.headers))
                dest.parent.mkdir(parents=True, exist_ok=True)
                n = 0
                with open(dest, "wb") as f:
                    f.write(first)
                    n += len(first)
                    while True:
                        chunk = r.read(CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        n += len(chunk)
                expected = int(r.headers.get("content-length") or 0)
                if expected and n != expected:
                    raise ConnectionError(f"short download {n} of {expected} bytes")
                return n
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 404:
                raise StopError(f"no tape for {d} (404)")
            if e.code in (500, 502, 503, 504) and attempt < retries:
                time.sleep(10 * (attempt + 1))
                continue
            raise StopError(_explain(e.code, body, e.headers))
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            if attempt < retries:
                time.sleep(10 * (attempt + 1))
                continue
            raise StopError(f"download of {d} failed after {retries + 1} attempts: {e}")
    raise StopError("unreachable")


def probe(key: str) -> str:
    """Request a date before UW's 2022-01-01 data start; the 403 body states the
    caller's earliest date. Reads only the first chunk so a 200 never downloads a day."""
    url = f"{API_BASE}{FULL_TAPE}2021-12-31"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_headers(key)), timeout=60) as r:
            head = r.read(4096)
            return "200 zip: unlimited history" if head[:4] == ZIP_MAGIC else head.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return _explain(e.code, e.read().decode("utf-8", "replace"), e.headers)


# ----------------------------------------------------------------------------
# filter
# ----------------------------------------------------------------------------

def _csv_member(zf: zipfile.ZipFile) -> str:
    names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if len(names) != 1:
        raise StopError(f"expected one CSV in the zip, found {names}")
    return names[0]


def _match_mask(tbl: pa.Table | pa.RecordBatch, expiries: tuple[str, str]) -> pa.Array:
    und = pc.is_in(tbl.column("underlying_symbol"), value_set=pa.array(ROOTS))
    occ = pc.match_substring_regex(tbl.column("option_chain_id"), ROOT_RE)
    sym = pc.or_(pc.fill_null(und, False), pc.fill_null(occ, False))
    exp = pc.is_in(pc.utf8_slice_codeunits(tbl.column("expiry"), 0, 10),
                   value_set=pa.array(list(expiries)))
    return pc.and_(sym, pc.fill_null(exp, False))


def arrow_pass(zip_path: Path, expiries: tuple[str, str]) -> tuple[pa.Table, int]:
    """Stream the CSV with Arrow (all kept columns read as text), keep matching rows."""
    with zipfile.ZipFile(zip_path) as zf, zf.open(_csv_member(zf)) as fh:
        header = fh.readline().decode("utf-8-sig").strip()
    cols = next(csv.reader([header]))
    missing = [c for c in KEEP if c not in cols]
    if missing:
        raise StopError(f"tape CSV is missing columns {missing}")
    parts, total = [], 0
    with zipfile.ZipFile(zip_path) as zf, zf.open(_csv_member(zf)) as fh:
        reader = pacsv.open_csv(
            fh,
            read_options=pacsv.ReadOptions(block_size=64 << 20),
            parse_options=pacsv.ParseOptions(newlines_in_values=True),
            convert_options=pacsv.ConvertOptions(
                include_columns=list(KEEP),
                column_types={c: pa.string() for c in KEEP},
                strings_can_be_null=False,
            ),
        )
        for batch in reader:
            total += batch.num_rows
            m = _match_mask(batch, expiries)
            if pc.any(m).as_py():
                parts.append(pa.Table.from_batches([batch]).filter(m))
    schema = pa.schema([(c, pa.string()) for c in KEEP])
    tbl = pa.concat_tables(parts) if parts else schema.empty_table()
    return tbl.select(list(KEEP)), total


def csvmodule_pass(zip_path: Path, expiries: tuple[str, str]) -> tuple[int, int]:
    """Independent count with Python's csv module: (total rows, matching rows)."""
    rx = re.compile(ROOT_RE)
    exp = set(expiries)
    total = kept = 0
    with zipfile.ZipFile(zip_path) as zf, zf.open(_csv_member(zf)) as raw:
        rdr = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        hdr = next(rdr)
        iu, io_, ie = hdr.index("underlying_symbol"), hdr.index("option_chain_id"), hdr.index("expiry")
        for row in rdr:
            total += 1
            if (row[iu] in ROOTS or rx.match(row[io_])) and row[ie][:10] in exp:
                kept += 1
    return total, kept


def type_table(tbl: pa.Table) -> pa.Table:
    """Cast text columns to their types; raise if any non-empty value fails to parse."""
    import pandas as pd
    df = tbl.to_pandas()
    bad = {}
    ts = pd.to_datetime(df["executed_at"], utc=True, format="mixed", errors="coerce")
    bad["executed_at"] = int((ts.isna() & (df["executed_at"] != "")).sum())
    if (df["executed_at"] == "").any():
        bad["executed_at_empty"] = int((df["executed_at"] == "").sum())
    df["executed_at"] = ts.astype("datetime64[us, UTC]")
    for c in FLOAT_COLS + INT_COLS:
        v = pd.to_numeric(df[c].mask(df[c] == ""), errors="coerce")
        bad[c] = int((v.isna() & (df[c] != "")).sum())
        df[c] = v.astype("float64") if c in FLOAT_COLS else v.astype("Int64")
    df["expiry"] = pd.to_datetime(df["expiry"].str[:10], format="%Y-%m-%d", errors="coerce").dt.date
    bad["expiry"] = int(df["expiry"].isna().sum())
    df["canceled"] = df["canceled"].str.lower().map({"t": True, "true": True, "f": False, "false": False})
    bad["canceled"] = int(df["canceled"].isna().sum())
    df["canceled"] = df["canceled"].astype("boolean")
    failed = {k: v for k, v in bad.items() if v}
    if failed:
        raise StopError(f"values that failed to parse (count per column): {failed}")
    return pa.Table.from_pandas(df, preserve_index=False)


# ----------------------------------------------------------------------------
# one day
# ----------------------------------------------------------------------------

def ingest_day(d: date, cfg: Config, store: Store, keep_zip: bool = False) -> dict:
    rel = f"tape/{d.isoformat()}.parquet"
    if any(r["date"] == d.isoformat() and r["file"] == rel for r in store.manifest()):
        return {"date": d.isoformat(), "status": "already in MANIFEST"}
    if not cal.is_trading_day(d):
        raise StopError(f"{d} is not a trading day")
    work = WORK / d.isoformat()
    work.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(work).free < MIN_LOCAL_FREE_BYTES:
        raise StopError(f"less than {MIN_LOCAL_FREE_BYTES / 1e9:.0f} GB free locally for the zip")
    t0 = time.time()
    zpath = work / f"full_tape_{d.isoformat()}.zip"
    zbytes = zpath.stat().st_size if zpath.exists() else download(d, zpath, cfg.api_key)
    expiries = (d.isoformat(), cal.next_trading_day(d).isoformat())
    tbl, total_arrow = arrow_pass(zpath, expiries)
    total_csv, kept_csv = csvmodule_pass(zpath, expiries)
    log = {"date": d.isoformat(), "zip_bytes": zbytes, "csv_rows_arrow": total_arrow,
           "csv_rows_csvmod": total_csv, "kept_rows_arrow": tbl.num_rows, "kept_rows_csvmod": kept_csv}
    if total_arrow != total_csv or tbl.num_rows != kept_csv:
        raise StopError(f"row counts disagree: {log}")
    typed = type_table(tbl)
    root = pc.utf8_slice_codeunits(typed.column("option_chain_id"), 0, 4)
    spxw0 = pc.sum(pc.and_(pc.equal(root, "SPXW"),
                           pc.equal(typed.column("expiry"), pa.scalar(d)))).as_py() or 0
    log["spxw_0dte_rows"] = spxw0
    if spxw0 < MIN_SPXW_0DTE_ROWS:
        raise StopError(f"only {spxw0} SPXW same-day rows on {d}; filter or format problem: {log}")
    local = work / f"{d.isoformat()}.parquet"
    pq.write_table(typed, local, compression="zstd", compression_level=3)
    if pq.read_metadata(local).num_rows != typed.num_rows:
        raise StopError(f"parquet re-read row count mismatch on {d}")
    nbytes, checksum = local.stat().st_size, sha256_file(local)
    store.put(local, rel)
    store.manifest_add(d.isoformat(), rel, typed.num_rows, nbytes, checksum)
    log.update(parquet_bytes=nbytes, seconds=round(time.time() - t0, 1), status="ok", note="",
               ingested_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    store.append_csv("INGEST_LOG.csv", INGEST_LOG_FIELDS, log)
    if not keep_zip:
        zpath.unlink(missing_ok=True)
    local.unlink(missing_ok=True)
    return log


def run_days(days: list[date], cfg: Config, store: Store) -> int:
    for d in days:
        try:
            log = ingest_day(d, cfg, store)
            print(json.dumps(log))
        except StopError as e:
            print(f"STOP on {d}: {e}")
            store.append_csv("INGEST_LOG.csv", INGEST_LOG_FIELDS, {
                "date": d.isoformat(), "status": "failed", "note": str(e)[:500],
                "ingested_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            return 1
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    cfg = load()
    if cmd == "probe":
        print(probe(cfg.api_key))
        return 0
    store = Store(cfg)
    if cmd == "day":
        return run_days([date.fromisoformat(argv[1])], cfg, store)
    if cmd in ("range", "pilot"):
        if cmd == "pilot":
            days = cal.last_n_trading_days(date.fromisoformat("2026-10-01"), 60)
        else:
            days = cal.trading_days(date.fromisoformat(argv[1]), date.fromisoformat(argv[2]))
        done = {r["date"] for r in store.manifest()}
        todo = [d for d in days if d.isoformat() not in done]
        print(f"{len(days)} trading days, {len(todo)} not yet ingested: "
              f"{todo[0] if todo else '-'} .. {todo[-1] if todo else '-'}")
        if "--confirm" not in argv:
            print("dry run; add --confirm to download (about 2 GB per day, one day at a time)")
            return 0
        return run_days(todo, cfg, store)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
