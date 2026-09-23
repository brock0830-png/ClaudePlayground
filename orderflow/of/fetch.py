"""Cached downloader for data.binance.vision (USD-M futures).

Every file is kept under data/binance/raw/<same path as the URL>, so a coin-day is downloaded
once and reused. Missing files (404: before listing, or not yet published) are remembered in
a .missing marker so they are not requested again.
"""
from __future__ import annotations

import datetime as dt
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from .config import BASE_URL, RAW

_session = None


def _sess():
    global _session
    if _session is None:
        s = requests.Session()
        a = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32)
        s.mount("https://", a)
        _session = s
    return _session


def local(rel: str):
    return RAW / rel


def get(rel: str, retries: int = 5):
    """Download BASE_URL/rel to the cache if needed. Returns the local path, or None on 404."""
    p = local(rel)
    miss = p.with_suffix(p.suffix + ".missing")
    if p.exists():
        return p
    if miss.exists():
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    url = f"{BASE_URL}/{rel}"
    err = None
    for k in range(retries):
        try:
            r = _sess().get(url, timeout=180)
            if r.status_code == 404:
                miss.touch()
                return None
            r.raise_for_status()
            tmp = p.with_suffix(p.suffix + ".part")
            tmp.write_bytes(r.content)
            with zipfile.ZipFile(tmp) as z:          # integrity check before it enters the cache
                if z.testzip() is not None:
                    raise IOError("corrupt zip")
            tmp.rename(p)
            return p
        except Exception as e:                      # network hiccup: back off and retry
            err = e
            time.sleep(2 ** k)
    raise RuntimeError(f"failed {url}: {err}")


def get_bytes(rel: str, retries: int = 6):
    """Fetch BASE_URL/rel into memory without caching (for the large aggTrades files).
    Uses the disk cache if the file happens to be there. Returns bytes, or None on 404."""
    p = local(rel)
    if p.exists():
        return p.read_bytes()
    url = f"{BASE_URL}/{rel}"
    err = None
    for k in range(retries):
        try:
            r = _sess().get(url, timeout=300)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except Exception as e:
            err = e
            time.sleep(2 ** k)
    raise RuntimeError(f"failed {url}: {err}")


def get_many(rels, workers: int = 8, label: str = ""):
    """Fetch many files with at most `workers` in flight. Returns {rel: path|None}."""
    rels = list(dict.fromkeys(rels))
    todo = [r for r in rels if not local(r).exists() and not local(r).with_suffix(".zip.missing").exists()]
    out = {r: (local(r) if local(r).exists() else None) for r in rels if r not in set(todo)}
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(get, r): r for r in todo}
        for i, f in enumerate(as_completed(futs), 1):
            out[futs[f]] = f.result()
            if i % 200 == 0 or i == len(todo):
                print(f"  {label} {i}/{len(todo)} files, {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    return out


# ---------- URL builders ----------

def months(a: pd.Timestamp, b: pd.Timestamp):
    return [m.strftime("%Y-%m") for m in pd.period_range(a.tz_localize(None), b.tz_localize(None), freq="M")]


def days(a, b):
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(pd.Timestamp(a).tz_localize(None).normalize(),
                                                           pd.Timestamp(b).tz_localize(None).normalize(), freq="D")]


def klines_rel(sym, interval, key, monthly=True):
    f = "monthly" if monthly else "daily"
    return f"{f}/klines/{sym}/{interval}/{sym}-{interval}-{key}.zip"


def metrics_rel(sym, day):
    return f"daily/metrics/{sym}/{sym}-metrics-{day}.zip"


def funding_rel(sym, month):
    return f"monthly/fundingRate/{sym}/{sym}-fundingRate-{month}.zip"


def aggtrades_rel(sym, day):
    return f"daily/aggTrades/{sym}/{sym}-aggTrades-{day}.zip"


def read_zip_csv(path, **kw) -> pd.DataFrame:
    """Binance CSVs sometimes have a header row and sometimes not; handle both."""
    with zipfile.ZipFile(path) as z:
        with z.open(z.namelist()[0]) as fh:
            head = fh.read(64)
    has_hdr = head[:1].isalpha()
    with zipfile.ZipFile(path) as z:
        with z.open(z.namelist()[0]) as fh:
            return pd.read_csv(fh, header=0 if has_hdr else None, **kw)


def today():
    return dt.datetime.now(dt.timezone.utc).date()
