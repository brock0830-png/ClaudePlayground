"""aggTrades parsing (Binance USD-M futures daily files)."""
from __future__ import annotations

import io
import zipfile

import numpy as np
import pyarrow as pa
import pyarrow.csv as pcsv

NAMES = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"]
TYPES = {"agg_trade_id": pa.int64(), "price": pa.float64(), "quantity": pa.float64(), "first_trade_id": pa.int64(),
         "last_trade_id": pa.int64(), "transact_time": pa.int64(), "is_buyer_maker": pa.bool_()}


def parse(path) -> dict:
    """Return dict of numpy arrays p, q, ts (ms), sell (True = aggressive SELL), sorted by time."""
    with zipfile.ZipFile(path) as z:
        raw = z.read(z.namelist()[0])
    has_hdr = raw[:1].isalpha()
    t = pcsv.read_csv(io.BytesIO(raw),
                      read_options=pcsv.ReadOptions(column_names=NAMES, skip_rows=1 if has_hdr else 0),
                      convert_options=pcsv.ConvertOptions(column_types=TYPES,
                                                          include_columns=["price", "quantity", "transact_time",
                                                                           "is_buyer_maker"]))
    ts = t.column("transact_time").to_numpy()
    if len(ts) and ts[0] > 10 ** 14:          # microseconds -> ms
        ts = ts // 1000
    o = np.argsort(ts, kind="stable")
    return dict(p=t.column("price").to_numpy()[o], q=t.column("quantity").to_numpy()[o], ts=ts[o],
                sell=t.column("is_buyer_maker").to_numpy(zero_copy_only=False)[o])


def window(days: list[dict], a_ms: int, b_ms: int) -> dict:
    """Trades with a_ms <= ts < b_ms from a list of parsed (time-ordered) days."""
    parts = {k: [] for k in ("p", "q", "ts", "sell")}
    for d in days:
        if d is None or len(d["ts"]) == 0:
            continue
        i, j = np.searchsorted(d["ts"], [a_ms, b_ms], side="left")
        for k in parts:
            parts[k].append(d[k][i:j])
    return {k: (np.concatenate(v) if v else np.array([])) for k, v in parts.items()}
