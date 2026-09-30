"""
Date TradingView's ES1! contract switches from the ES-SPX basis.

basis(t) = ES 4h-bar open at 10:00 and 14:00 ET minus the SPX 1-minute open at the same
minute (SPX 1-min from the public HF dataset thillsss/SPX-MES-VIX-data, CT timestamps).
Between switches the basis drifts slowly (carry decays); at a switch it jumps by the
calendar spread. In each Mar/Jun/Sep/Dec (days 8-20) we take the largest day-over-day jump in the
median daily basis as the switch day and require it to be >2.5x the robust noise.
Output: data/roll_dates.csv  (switch_tday = first ES trading day on the new contract).
Usage: python scripts/detect_rolls.py <spx_1min_ct.parquet>
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from scalpel.data import read_export, DATA

spx = pd.read_parquet(sys.argv[1])
spx.index = spx.index.tz_localize("America/Chicago", ambiguous="NaT", nonexistent="NaT").tz_convert("America/New_York")
spx = spx[spx.index.notna()]
es = read_export()[["open"]]
es = es[es.index.hour.isin([10, 14])]
j = es.join(spx["open"].rename("spx"), how="inner")
j["basis"] = j["open"] - j["spx"]
j["date"] = j.index.tz_localize(None).normalize()
d = j.groupby("date")["basis"].median()
jump = d.diff()
noise = jump.abs().rolling(60, min_periods=20).median()
rows = []
for (y, m), g in jump.groupby([jump.index.year, jump.index.month]):
    if m not in (3, 6, 9, 12):
        continue
    g = g.dropna()
    g = g[(g.index.day >= 8) & (g.index.day <= 20)]   # switch is always mid-month, before expiry
    if g.empty:
        continue
    k = g.abs().idxmax()
    rows.append(dict(year=y, month=m, switch_tday=k.date(), jump=round(g[k], 2),
                     noise=round(noise.get(k, np.nan), 2),
                     ok=abs(g[k]) > 2.5 * noise.get(k, np.nan)))
out = pd.DataFrame(rows)
print(out.to_string())
out.to_csv(DATA / "roll_dates.csv", index=False)
