"""Download and condense Binance's public data archive (data.binance.vision) for the Phase 3 order-flow study.

data.binance.vision is served from the public S3 bucket of the same name; this environment reaches it through the
bucket's S3 endpoint. Raw zips go to crypto/data/cache/bv (git-ignored). Condensed parquet goes to crypto/data/bv.

  python crypto/src/binance_vision.py klines      # 15m USD-M perp klines with taker buy volume, 16 coins, 2022-01 on
  python crypto/src/binance_vision.py funding     # actual funding prints
  python crypto/src/binance_vision.py metrics     # 5-min OI, top-trader / global long-short ratios, taker ratio
  python crypto/src/binance_vision.py bookdepth   # order-book depth at +-1..5%, 5 majors, 2023-01 on -> 15m imbalance
  python crypto/src/binance_vision.py footprint   # aggTrades -> 1h footprint features, BTC ETH SOL, 2024-01 on
"""
from __future__ import annotations

import io
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "bv"
OUT = ROOT / "data" / "bv"
BASE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um"
U16 = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "ADA", "AVAX", "LINK", "LTC", "DOT", "TRX", "BCH", "SUI", "NEAR", "APT"]
BOOK5 = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
FOOT3 = ["BTC", "ETH", "SOL"]
START, END = pd.Timestamp("2022-01-01"), pd.Timestamp("2026-09-22")


def fetch(url: str, dest: Path, tries: int = 4) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    for _ in range(tries):
        r = subprocess.run(["curl", "-s", "-f", "--max-time", "300", "-o", str(tmp), url])
        if r.returncode == 0:
            tmp.replace(dest)
            return True
        if r.returncode == 22:  # HTTP error (404: not listed yet / no file)
            return False
    return False


def read_zip_csv(path: Path, names=None) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        raw = z.read(z.namelist()[0])
    first = raw[:200].decode(errors="ignore").split("\n")[0]
    has_header = any(c.isalpha() for c in first.split(",")[0])
    return pd.read_csv(io.BytesIO(raw), header=0 if has_header else None, names=None if has_header else names)


def months(a=START, b=END):
    return pd.period_range(a.to_period("M"), b.to_period("M") - 1, freq="M")  # complete months only


def days(a, b):
    return pd.date_range(a, b, freq="D")


def pull(jobs, workers=24):
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda j: fetch(*j), jobs))


# ------------------------------------------------------------------ klines 15m
KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count",
         "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def klines(iv="15m"):
    for c in U16:
        s = f"{c}USDT"
        jobs = [(f"{BASE}/monthly/klines/{s}/{iv}/{s}-{iv}-{m}.zip", CACHE / "klines" / s / f"{m}.zip") for m in months()]
        last_month_end = months()[-1].to_timestamp(how="end").normalize() + pd.Timedelta(days=1)
        jobs += [(f"{BASE}/daily/klines/{s}/{iv}/{s}-{iv}-{d.date()}.zip", CACHE / "klines" / s / f"{d.date()}.zip")
                 for d in days(last_month_end, END)]
        ok = pull(jobs)
        frames = [read_zip_csv(p, KCOLS) for (_, p), o in zip(jobs, ok) if o]
        if not frames:
            print(c, "no data")
            continue
        df = pd.concat(frames)
        df["time"] = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True)
        df = df.drop_duplicates("time").set_index("time").sort_index()
        df = df[["open", "high", "low", "close", "volume", "quote_volume", "count", "taker_buy_volume"]].astype(float)
        OUT.mkdir(parents=True, exist_ok=True)
        df.to_parquet(OUT / f"{c}_klines_{iv}.parquet")
        print(c, len(df), df.index[0], df.index[-1], f"{sum(ok)}/{len(ok)} files")


def funding():
    for c in U16:
        s = f"{c}USDT"
        jobs = [(f"{BASE}/monthly/fundingRate/{s}/{s}-fundingRate-{m}.zip", CACHE / "funding" / s / f"{m}.zip") for m in months()]
        ok = pull(jobs)
        frames = [read_zip_csv(p, ["calc_time", "funding_interval_hours", "last_funding_rate"]) for (_, p), o in zip(jobs, ok) if o]
        if not frames:
            continue
        df = pd.concat(frames)
        df["time"] = pd.to_datetime(df["calc_time"].astype("int64"), unit="ms", utc=True).dt.floor("min")
        df = df.drop_duplicates("time").set_index("time").sort_index()[["funding_interval_hours", "last_funding_rate"]].astype(float)
        df.to_parquet(OUT / f"{c}_funding.parquet")
        print(c, len(df), df.index[0], df.index[-1])


MCOLS = ["create_time", "symbol", "sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio",
         "sum_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]


def metrics():
    for c in U16:
        s = f"{c}USDT"
        jobs = [(f"{BASE}/daily/metrics/{s}/{s}-metrics-{d.date()}.zip", CACHE / "metrics" / s / f"{d.date()}.zip")
                for d in days(START, END)]
        ok = pull(jobs, workers=32)
        frames = []
        for (_, p), o in zip(jobs, ok):
            if o:
                try:
                    frames.append(read_zip_csv(p, MCOLS))
                except Exception as e:  # a handful of archive days are corrupt or empty
                    print("  bad", p.name, e)
        df = pd.concat(frames)
        df["time"] = pd.to_datetime(df["create_time"], utc=True)
        df = df.drop_duplicates("time").set_index("time").sort_index().drop(columns=["create_time", "symbol"]).astype(float)
        # value at the end of each 15m bar (the last 5-min print inside it), aligned to bar open time
        q = df.resample("15min", label="left", closed="left").last()
        q.to_parquet(OUT / f"{c}_metrics_15m.parquet")
        print(c, len(q), q.index[0], q.index[-1], f"{sum(ok)}/{len(ok)} files")


def _book_day(p: Path) -> pd.DataFrame:
    d = read_zip_csv(p, ["timestamp", "percentage", "depth", "notional"])
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
    w = d.pivot_table(index="timestamp", columns="percentage", values="notional", aggfunc="last")
    out = pd.DataFrame(index=w.index)
    for k in (1, 2, 5):
        bid, ask = w.get(-k), w.get(k)
        if bid is not None and ask is not None:
            out[f"imb{k}"] = (bid - ask) / (bid + ask)
    out["depth1"] = w.get(-1, np.nan) + w.get(1, np.nan)
    return out.resample("15min").mean()


def bookdepth():
    for c in BOOK5:
        s = f"{c}USDT"
        jobs = [(f"{BASE}/daily/bookDepth/{s}/{s}-bookDepth-{d.date()}.zip", CACHE / "book" / s / f"{d.date()}.zip")
                for d in days(pd.Timestamp("2023-01-01"), END)]
        ok = pull(jobs, workers=32)
        frames = []
        for (_, p), o in zip(jobs, ok):
            if o:
                try:
                    frames.append(_book_day(p))
                except Exception as e:
                    print("  bad", p.name, e)
                p.unlink(missing_ok=True)  # keep disk small
        df = pd.concat(frames).sort_index()
        df = df[~df.index.duplicated()]
        df.to_parquet(OUT / f"{c}_book_15m.parquet")
        print(c, len(df), df.index[0], df.index[-1], f"{sum(ok)}/{len(ok)} files")


def _foot_day(p: Path) -> pd.DataFrame:
    """1h footprint features from aggTrades: aggressive volume by side in the bottom/top 20% of each hour's range."""
    t = read_zip_csv(p, ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time",
                         "is_buyer_maker"])
    t["time"] = pd.to_datetime(t["transact_time"].astype("int64"), unit="ms", utc=True)
    t["hour"] = t["time"].dt.floor("h")
    sell = t["is_buyer_maker"].astype(str).str.lower().eq("true")  # buyer is maker -> the aggressor sold
    t["buy_q"] = np.where(sell, 0.0, t["quantity"])
    t["sell_q"] = np.where(sell, t["quantity"], 0.0)
    g = t.groupby("hour")["price"]
    lo, hi = g.transform("min"), g.transform("max")
    pos = (t["price"] - lo) / (hi - lo).replace(0, np.nan)
    t["bot"] = pos <= 0.2
    t["top"] = pos >= 0.8
    agg = t.groupby("hour").agg(vol=("quantity", "sum"), buy=("buy_q", "sum"), sell=("sell_q", "sum"))
    agg["sell_bot"] = t[t["bot"]].groupby("hour")["sell_q"].sum()
    agg["buy_bot"] = t[t["bot"]].groupby("hour")["buy_q"].sum()
    agg["buy_top"] = t[t["top"]].groupby("hour")["buy_q"].sum()
    agg["sell_top"] = t[t["top"]].groupby("hour")["sell_q"].sum()
    # point of control: price bucket (20 buckets of the hour's range) with the most volume, as a 0..1 position
    b = (pos.clip(0, 1) * 19.999).fillna(10).astype(int)
    vp = t.assign(b=b).groupby(["hour", "b"])["quantity"].sum()
    agg["poc"] = vp.groupby(level=0).idxmax().map(lambda x: (x[1] + 0.5) / 20.0)
    return agg.fillna(0.0)


def footprint(start="2024-01-01"):
    for c in FOOT3:
        s = f"{c}USDT"
        frames = []
        ds = days(pd.Timestamp(start), END)
        for i in range(0, len(ds), 16):  # 16 days at a time: download in parallel, condense, delete
            chunk = ds[i:i + 16]
            jobs = [(f"{BASE}/daily/aggTrades/{s}/{s}-aggTrades-{d.date()}.zip", CACHE / "agg" / s / f"{d.date()}.zip")
                    for d in chunk]
            ok = pull(jobs, workers=16)
            for (_, p), o in zip(jobs, ok):
                if o:
                    try:
                        frames.append(_foot_day(p))
                    except Exception as e:
                        print("  bad", p.name, e)
                    p.unlink(missing_ok=True)
            print(c, chunk[-1].date(), flush=True)
        df = pd.concat(frames).sort_index()
        df = df[~df.index.duplicated()]
        df.to_parquet(OUT / f"{c}_footprint_1h.parquet")
        print(c, len(df), df.index[0], df.index[-1])


if __name__ == "__main__":
    {"klines": klines, "funding": funding, "metrics": metrics, "bookdepth": bookdepth, "footprint": footprint}[sys.argv[1]]()
