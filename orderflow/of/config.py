"""Universes, dates, costs and paths for the order-flow work (see SPEC_value_area_tests.md)."""
from __future__ import annotations

import os
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = pathlib.Path(os.environ.get("OF_DATA", ROOT / "data" / "binance"))   # raw zips + parquet (gitignored)
RAW = DATA / "raw"
PQ = DATA / "parquet"
RESULTS = ROOT / "orderflow" / "results"

BASE_URL = "https://data.binance.vision/data/futures/um"

DEV = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT", "DOGEUSDT", "LTCUSDT", "AVAXUSDT"]
HOLDOUT = [s + "USDT" for s in
           "AAVE UNI FIL ETC BCH ICP APT ARB OP SUI INJ SEI TIA WIF 1000PEPE 1000SHIB FET XLM HBAR ALGO "
           "SAND MANA AXS GALA CRV LDO".split()]
assert len(DEV) == 9 and len(HOLDOUT) == 26

START = pd.Timestamp("2022-01-01", tz="UTC")          # first signal bar allowed
END = pd.Timestamp("2026-09-01", tz="UTC")            # exclusive: last signal bar is in 2026-08
LOOKBACK_START = pd.Timestamp("2021-12-01", tz="UTC")  # data needed before START (24h changes, ATR, weekly profiles)
SPLIT = pd.Timestamp("2024-01-01", tz="UTC")          # dev 2022-23 | dev 2024-26

# base signal (SPEC background section)
PRICE_CHG = -0.046
OI_CHG = -0.018
HOLD_H = 24
COST_RT = 0.0014       # round trip, applied once per trade


def period(t: pd.Series) -> pd.Series:
    return pd.Series(["22-23" if x < SPLIT else "24-26" for x in t], index=t.index)
