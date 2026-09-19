"""Phase 6c: metals sleeve with silver. Builds an in-memory SLV proxy (SIUSD spot + carry calibrated on the first 5y of
SLV overlap, spliced to SLV) on the extension panel; nothing is written to data/. Compares gold-only vs gold+silver
sleeves, with and without the vol-scaled dip, across the exposure multiplier. Logged as P6 'METALS'."""
from __future__ import annotations
import sys, itertools
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import load_close
from proxies import splice, ER
from trials import cost_model, log, consecutive_roundtrips
from engine import run, BASE_LAG
from metrics import summary
from strategies import ALL_COLS, LEVERAGE
import system2 as S2

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "reports" / "phase6"
R = pd.read_parquet(ROOT / "data/proxies_ext/returns.parquet").copy(); L = pd.read_parquet(ROOT / "data/proxies_ext/levels.parquet").copy()
cal = R.index
si = load_close("SIUSD").reindex(cal).ffill(limit=3).pct_change()
slv = load_close("SLV").reindex(cal).pct_change()
both = pd.concat([slv, si], axis=1, keys=["live", "idx"]).dropna(); early = both.iloc[:5 * 252]
carry = float((early.live - early.idx).mean())
h = len(both) // 2; c1 = float((both.live - both.idx).iloc[:h].mean()); c2 = float((both.live - both.idx).iloc[h:].mean())
print(f"SLV proxy: carry {carry*252:+.4f}/yr (first 5y), first-half {c1*252:+.4f}, second-half {c2*252:+.4f}, corr {both.live.corr(both.idx):.3f}, live from {slv.first_valid_index().date()}")
R["SLV_X"] = splice(si + carry, slv); L["SLV_X"] = (1 + R["SLV_X"].fillna(0)).cumprod(); L.loc[R["SLV_X"].isna() & R["SLV_X"].ffill().isna(), "SLV_X"] = np.nan
COLS = ALL_COLS + ["SLV_X"]; LEV = dict(LEVERAGE, SLV_X=1)
WIN = ("1991-01-04", "2026-09-18"); PERIODS = {"design": ("1991-01-04", "2015-12-31"), "confirm": ("2016-01-04", "2026-09-18"), "full": WIN}
BAND = 0.02
led = pd.read_csv(ROOT / "TRIAL_LEDGER.csv"); led["note"] = led["note"].fillna("")
already = set(led[(led.phase == "P6") & ~led.note.str.startswith("duplicate")].cell)


def full_run(w):
    idx = R.index[(R.index >= WIN[0]) & (R.index <= WIN[1])]
    return run(w.reindex(R.index).reindex(columns=COLS).fillna(0.0).loc[idx], R[COLS], R["CASH"], cost_model(1.0), lag=BASE_LAG, leverage=LEV, rebalance_threshold=BAND)


def slice_metrics(res, a, b):
    keep = (res.returns.index >= a) & (res.returns.index <= b); ret = res.returns[keep]
    m = summary(ret, rf=R["CASH"], spy=R["SPY_X"], weights_held=res.weights_held[keep], gross_leverage=res.gross_leverage.abs()[keep], turnover=res.turnover[keep], trades=res.trades[keep])
    m["ConsecRoundTripsPerYear"] = consecutive_roundtrips(res.deltas[keep]) / (len(ret) / 252); m["T"] = int(len(ret)); return m


P0 = dict(S2.PARAMS2, lever=1.0)
V = {"gold0.3": dict(P0, w_gold=0.3, gold_vt=0.10),
     "gold+silver0.3": dict(P0, w_gold=0.3, gold_vt=0.10, gold_assets=("GLD", "SLV")),
     "dipvol+gold0.3": dict(P0, dip_n=10, dip_hold=5, dip_mult=2.0, w_gold=0.3, gold_vt=0.10),
     "dipvol+gold+silver0.3": dict(P0, dip_n=10, dip_hold=5, dip_mult=2.0, w_gold=0.3, gold_vt=0.10, gold_assets=("GLD", "SLV")),
     "dipvol+gold+silver0.2": dict(P0, dip_n=10, dip_hold=5, dip_mult=2.0, w_gold=0.2, gold_vt=0.10, gold_assets=("GLD", "SLV"))}
rows = []; curves = {}
for name, p in V.items():
    for lev in [1.0, 1.25, 1.5]:
        pp = dict(p, lever=lev); res = full_run(S2.build2(R, L, pp)); curves[f"{name} lever={lev}"] = res
        for per, (a, b) in PERIODS.items():
            m = slice_metrics(res, a, b); cell = f"METALS {name} lever={lev} [{per}]"
            tid = None if cell in already else log("P6", "METALS", cell, {k: (list(v) if isinstance(v, tuple) else v) for k, v in pp.items()}, (a, b), BASE_LAG, 1.0, m, "P6 metals sleeve with in-memory SLV proxy")
            rows.append({"variant": name, "lever": lev, "period": per, **{k: m[k] for k in ("CAGR", "Vol", "Sharpe", "MaxDD", "MAR", "AvgLeverage", "TradesPerYear")}, "MaxDD_trough": m["MaxDD_trough"]})
df = pd.DataFrame(rows); df.to_csv(OUT / "metals.csv", index=False)
for per in ("full", "design", "confirm"):
    print("\n==", per); print(df[df.period == per].pivot(index="lever", columns="variant", values=["CAGR", "MaxDD", "MAR"]).round(3).to_string())
pd.DataFrame({k: v.returns for k, v in curves.items()}).to_parquet(OUT / "metals_daily_returns.parquet")
