"""
Gate 1: the Python port must reproduce the TradingView export before any backtest.
Usage: python validate_export.py data/<your_export>.csv
Checks every D/W/M level column present in the file (v37 Full-mode weekly export or
the docs_scalpel_export_es.pine export), then checks weekly-open derivation.
"""
import sys
import pandas as pd
from scalpel.levels import level_frame, weekly_open

path = sys.argv[1] if len(sys.argv) > 1 else "data/es_levels_CME_MINI_ES1_240.csv.gz"
df = pd.read_csv(path)
df.index = pd.to_datetime(df["time"], utc=True).dt.tz_convert("America/New_York")

def export_names(tf):
    return {
        f"{tf}_GB_TOP": f"{tf} GB Top", f"{tf}_TH2": f"{tf}TH2", f"{tf}_TH1": f"{tf}TH1",
        f"{tf}_GB_BOT": f"{tf} GB Bot", f"{tf}_RH": f"{tf}RH", f"{tf}_RL": f"{tf}RL",
        f"{tf}_RB_TOP": f"{tf} RB Top", f"{tf}_TL1": f"{tf}TL1", f"{tf}_TL2": f"{tf}TL2",
        f"{tf}_RB_BOT": f"{tf} RB Bot", f"{tf}_GP_T_OUT": f"{tf} GP T Out",
        f"{tf}_GP_T_IN": f"{tf} GP T In", f"{tf}_GP_B_OUT": f"{tf} GP B Out",
        f"{tf}_GP_B_IN": f"{tf} GP B In", f"{tf}_RNG_T_HI": f"{tf} Rng T Hi",
        f"{tf}_RNG_T_LO": f"{tf} Rng T Lo", f"{tf}_RNG_B_HI": f"{tf} Rng B Hi",
        f"{tf}_RNG_B_LO": f"{tf} Rng B Lo",
    }

ok = True
for tf, open_col in [("D", "DO"), ("W", "WO"), ("M", "MO")]:
    if open_col not in df:
        print(f"{tf}: no {open_col} column, skipped")
        continue
    lv = level_frame(df[open_col], tf)
    cols = {k: c for k, c in export_names(tf).items() if c in df}
    err = max((lv[k] - df[c]).abs().max() for k, c in cols.items())
    print(f"{tf}: {len(cols)} levels checked, max error {err:.2e} pts")
    ok &= err < 0.01

wo = weekly_open(df)
bad = (wo - df["WO"]).abs() > 0.01
print(f"derived WO mismatches: {bad.sum()} of {len(df)} bars "
      "(first partial week + rare data quirks are expected)")
print(df.loc[bad, ["open", "WO"]].assign(derived=wo[bad]).drop_duplicates("WO").head(20).to_string())
assert ok, "Level port does not match TradingView — stop and fix before backtesting."
