"""Tape ingest on a synthetic Full Tape zip (no network)."""
import csv
import io
import sys
import zipfile
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import gn_config  # noqa: E402
import gn_store  # noqa: E402
import tape_ingest as ti  # noqa: E402

COLS = (
    "id", "underlying_symbol", "executed_at", "nbbo_bid", "nbbo_ask", "size",
    "price", "option_chain_id", "alert_score", "created_at", "report_flags",
    "tags", "expiry", "option_type", "open_interest", "strike", "premium",
    "aggregated_trade_id", "volume", "underlying_price", "ewma_nbbo_ask",
    "ewma_nbbo_bid", "implied_volatility", "delta", "theta", "gamma", "vega",
    "rho", "theo", "upstream_condition_detail", "market_center_locate",
    "canceled", "trade_id", "exchange", "ask_vol", "bid_vol", "no_side_vol",
    "mid_vol", "multi_vol", "stock_multi_vol",
)


def row(i, und, occ, expiry, **kw):
    r = {c: "" for c in COLS}
    r.update(id=str(i), underlying_symbol=und, option_chain_id=occ, expiry=expiry,
             executed_at="2026-10-01 14:00:00.123456+00", nbbo_bid="1.0", nbbo_ask="1.2",
             size="2", price="1.15", option_type="call", strike="7680", open_interest="100",
             volume="5", underlying_price="7650.5", implied_volatility="0.15", delta="0.3",
             gamma="0.004", canceled="f", ask_vol="3", bid_vol="1", no_side_vol="0",
             mid_vol="1", multi_vol="0", tags='{ask_side,bullish}', report_flags="{}")
    r.update(kw)
    return r


def make_zip(path: Path, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("full_tape_2026-10-01.csv", buf.getvalue())


@pytest.fixture
def rows():
    d0, d1 = "2026-10-01", "2026-10-02"
    return [
        row(1, "SPX", "SPXW261001C07680000", d0),
        row(2, "SPX", "SPXW261001P07600000", d0, option_type="put", strike="7600"),
        row(3, "SPX", "SPXW261002C07700000", d1),                      # next day: kept
        row(4, "SPX", "SPXW261005C07700000", "2026-10-05"),            # 2 days out: dropped
        row(5, "XSP", "XSP261001C00768000", d0, strike="768"),
        row(6, "AAPL", "AAPL261001C00250000", d0, strike="250"),       # other ticker: dropped
        row(7, "SPX", "SPXW261001C07690000", d0,
            upstream_condition_detail='multi\nline, "quoted"'),         # embedded newline
        row(8, "SPX", "SPXW261001C07695000", d0, gamma="", canceled="t"),  # empty numeric ok
    ]


def test_filter_and_independent_count(tmp_path, rows):
    z = tmp_path / "t.zip"
    make_zip(z, rows)
    exp = ("2026-10-01", "2026-10-02")
    tbl, total = ti.arrow_pass(z, exp)
    assert total == 8
    assert sorted(tbl.column("id").to_pylist()) == ["1", "2", "3", "5", "7", "8"]
    assert ti.csvmodule_pass(z, exp) == (8, 6)
    typed = ti.type_table(tbl)
    assert str(typed.schema.field("executed_at").type) == "timestamp[us, tz=UTC]"
    assert typed.column("gamma").null_count == 1


def test_bad_numeric_stops(tmp_path, rows):
    rows[0]["gamma"] = "abc"
    z = tmp_path / "t.zip"
    make_zip(z, rows)
    tbl, _ = ti.arrow_pass(z, ("2026-10-01", "2026-10-02"))
    with pytest.raises(ti.StopError, match="gamma"):
        ti.type_table(tbl)


def test_ingest_day_end_to_end(tmp_path, rows, monkeypatch):
    root = tmp_path / "drive"
    cfg = gn_config.Config(api_key="k", data_root=root, rclone_remote=None)
    root.mkdir()
    store = gn_store.Store(cfg)
    monkeypatch.setattr(ti, "WORK", tmp_path / "work")
    monkeypatch.setattr(ti, "MIN_SPXW_0DTE_ROWS", 3)
    monkeypatch.setattr(ti, "MIN_LOCAL_FREE_BYTES", 0)
    monkeypatch.setattr(ti, "download", lambda d, dest, key: (make_zip(dest, rows), dest.stat().st_size)[1])
    log = ti.ingest_day(date(2026, 10, 1), cfg, store)
    assert log["status"] == "ok" and log["kept_rows_arrow"] == 6 and log["spxw_0dte_rows"] == 4
    out = root / "tape" / "2026-10-01.parquet"
    assert pq.read_metadata(out).num_rows == 6
    man = store.manifest()
    assert man[0]["date"] == "2026-10-01" and man[0]["checksum"] == gn_store.sha256_file(out)
    assert not list((tmp_path / "work").rglob("*.zip"))           # raw zip deleted
    assert ti.ingest_day(date(2026, 10, 1), cfg, store)["status"] == "already in MANIFEST"
    with pytest.raises(FileExistsError):                          # never overwrite Drive
        store.put(out, "tape/2026-10-01.parquet")


def test_too_few_spxw_rows_stops(tmp_path, rows, monkeypatch):
    root = tmp_path / "drive"
    root.mkdir()
    cfg = gn_config.Config(api_key="k", data_root=root, rclone_remote=None)
    monkeypatch.setattr(ti, "WORK", tmp_path / "work")
    monkeypatch.setattr(ti, "MIN_LOCAL_FREE_BYTES", 0)
    monkeypatch.setattr(ti, "download", lambda d, dest, key: (make_zip(dest, rows), 1)[1])
    with pytest.raises(ti.StopError, match="SPXW same-day"):
        ti.ingest_day(date(2026, 10, 1), cfg, gn_store.Store(cfg))
    assert not (root / "tape").exists()
