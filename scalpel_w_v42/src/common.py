"""Shared constants for the SCALPEL-W-v42 lineage.

Everything here is copied from docs_scalpel_v42.pine (WEEKLY engine) or from
CME contract specs for the micro contracts named in the prompt. Nothing is fitted.
"""
from pathlib import Path

LINEAGE = "SCALPEL-W-v42"
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"
SEAL_FILE = ROOT / "OOS_UNSEALED"          # written once, by validate_oos.py only

TICKERS = ["ES", "NQ", "CL", "6J"]
IS_END = "2021-01-01"                      # design window: weeks starting before this
OOS_START = "2021-01-01"

# ---------------------------------------------------------------- level math (pine v42)
LK_VOL = {"ES": 18.54, "NQ": 23.03, "CL": 39.83, "6J": 13.14, "GC": 22.58}
LK_BIAS = {"ES": 0.481, "NQ": 0.516, "CL": 0.489, "6J": 0.458, "GC": 0.588}

W_MULT = {  # wrh, wth1, wth2, gbtop, wrl, wtl1, wtl2, rbbot
    "ES": dict(wrh=0.550, wth1=1.202, wth2=1.654, gbtop=1.826, wrl=0.551, wtl1=1.171, wtl2=1.638, rbbot=1.704),
    "NQ": dict(wrh=0.551, wth1=1.133, wth2=1.556, gbtop=1.612, wrl=0.522, wtl1=1.120, wtl2=1.577, rbbot=1.685),
    "CL": dict(wrh=0.601, wth1=1.095, wth2=1.331, gbtop=1.506, wrl=0.584, wtl1=1.248, wtl2=1.969, rbbot=2.053),
    "6J": dict(wrh=0.498, wth1=1.208, wth2=1.653, gbtop=1.806, wrl=0.506, wtl1=1.072, wtl2=1.227, rbbot=1.280),
    "GC": dict(wrh=0.597, wth1=1.091, wth2=1.476, gbtop=1.558, wrl=0.483, wtl1=1.161, wtl2=1.549, rbbot=1.757),
}
W_RNG_HALF = 0.078
GP_OUTER, GP_INNER = 0.618, 0.650

# Monthly engine (used only by the monthly-confluence family). ES/NQ calibrated; CL/6J fall back
# to lk_vol/lk_bias and the weekly multipliers exactly as the pine does.
M_VOL = {"ES": 17.37, "NQ": 25.05}
M_BIAS = {"ES": 0.531, "NQ": 0.449}
M_MULT = {
    "ES": dict(wrh=0.511, wth1=1.013, wth2=1.197, gbtop=1.217, wrl=0.491, wtl1=1.127, wtl2=1.539, rbbot=1.598),
    "NQ": dict(wrh=0.590, wth1=1.073, wth2=1.319, gbtop=1.374, wrl=0.540, wtl1=1.163, wtl2=1.581, rbbot=1.610),
}

# Level names in price order (top to bottom). Upper = above WO, lower = below WO.
UPPER = ["GB_TOP", "WTH2", "WTH1", "GB_BOT", "RNG_T_HI", "WRH", "RNG_T_LO", "GP_T_IN", "GP_T_OUT"]
LOWER = ["GP_B_OUT", "GP_B_IN", "RNG_B_HI", "WRL", "RNG_B_LO", "RB_TOP", "WTL1", "WTL2", "RB_BOT"]
LEVELS = UPPER + LOWER

# ---------------------------------------------------------------- execution (micros)
# tick = micro contract tick, tick_usd = $ per tick, pv = $ per 1.0 price unit
SPEC = {
    "ES": dict(micro="MES", tick=0.25, tick_usd=1.25, pv=5.0),
    "NQ": dict(micro="MNQ", tick=0.25, tick_usd=0.50, pv=2.0),
    "CL": dict(micro="MCL", tick=0.01, tick_usd=1.00, pv=100.0),
    "6J": dict(micro="MJY", tick=0.000001, tick_usd=1.25, pv=1_250_000.0),
    "GC": dict(micro="MGC", tick=0.10, tick_usd=1.00, pv=10.0),       # sealed holdout (phase 2)
}
COMMISSION_RT = 4.50          # $ per contract per round turn
EQUITY = 100_000.0            # notional account for sizing (non-compounding)
RISK_FRAC = 0.005             # 0.5% of equity per trade
