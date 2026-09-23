"""Datasets, windows, costs and the holdout lock for the crypto research (all fixed by crypto/PREREG.md)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TV = ROOT / "data" / "tv"
USER = ROOT / "data" / "user"
UNLOCK = ROOT / "HOLDOUT_UNLOCKED"

DAILY_DESIGN = (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2023-12-31 23:59:59", tz="UTC"))
DAILY_HOLDOUT = (pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2026-09-22 23:59:59", tz="UTC"))
INTRA_DESIGN = (pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2025-09-30 23:59:59", tz="UTC"))
INTRA_HOLDOUT = (pd.Timestamp("2025-10-01", tz="UTC"), pd.Timestamp("2026-09-23 23:59:59", tz="UTC"))

DAILY_UNIVERSE = ["BTC", "ETH", "BNB", "XRP", "ADA", "DOGE", "SOL", "LINK", "AVAX", "DOT", "LTC", "TRX", "BCH", "ATOM",
                  "NEAR", "ETC", "XLM", "FIL", "UNI", "NEO", "XTZ", "ALGO", "IOTA", "ZEC", "DASH", "VET", "QTUM", "HBAR"]
G4H = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT",
       "DOTUSDT", "TRXUSDT", "BCHUSDT", "ETHBTC", "SOLBTC", "AVAXBTC"]
# PREREG says "12 USDT pairs + 3 BTC pairs = 15"; the pull has 13 USDT pairs (BCH too), so G4h is all 16 (logged in REPORT)
C1H = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT"]
G30 = ["SOLBTC", "AVAXBTC"]
C15 = ["ETHBTC"]

TIER1 = {"BTC", "ETH"}
TIER2 = {"BNB", "XRP", "SOL", "DOGE", "ADA", "LINK", "AVAX", "LTC", "TRX", "BCH", "DOT"}
FEE_SPOT = 10.0
FEE_PERP = 5.0
FUNDING_BP_PER_8H = 1.0
BAR_HOURS = {"15m": 0.25, "30m": 0.5, "1h": 1.0, "4h": 4.0, "1D": 24.0}


def slippage_bp(sym: str) -> float:
    if sym.endswith("BTC") and sym != "BTC":
        return 5.0
    base = sym[:-4] if sym.endswith("USDT") else sym
    if base in TIER1:
        return 2.0
    if base in TIER2:
        return 4.0
    return 6.0


def cost_per_side(sym: str, side: str = "long", fee_bp: float | None = None) -> float:
    """Fraction of notional per side. Shorts on USDT pairs are costed as perps (funding added separately)."""
    perp_short = side == "short" and sym.endswith("USDT")
    fee = fee_bp if fee_bp is not None else (FEE_PERP if perp_short else FEE_SPOT)
    return (fee + slippage_bp(sym)) / 1e4


def funding_per_bar(sym: str, side: str, interval: str) -> float:
    if side == "short" and sym.endswith("USDT"):
        return FUNDING_BP_PER_8H / 1e4 * BAR_HOURS[interval] / 8.0
    return 0.0


def load(sym: str, interval: str) -> pd.DataFrame:
    p = (USER if interval in ("15m", "30m") else TV) / f"{sym}_{interval}.parquet"
    df = pd.read_parquet(p)
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def group(name: str) -> tuple[str, list[str]]:
    return {"G30": ("30m", G30), "G4h": ("4h", G4H), "GD": ("1D", [c + "USDT" for c in DAILY_UNIVERSE]),
            "C1h": ("1h", C1H), "C15": ("15m", C15)}[name]


def design_window(interval: str):
    return DAILY_DESIGN if interval == "1D" else INTRA_DESIGN


def holdout_window(interval: str):
    return DAILY_HOLDOUT if interval == "1D" else INTRA_HOLDOUT


def check_lock(window_end: pd.Timestamp, interval: str) -> None:
    if window_end > design_window(interval)[1] and not UNLOCK.exists():
        raise RuntimeError(f"holdout locked: evaluation past {design_window(interval)[1]} refused until freeze")
