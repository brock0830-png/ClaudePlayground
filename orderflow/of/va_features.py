"""Pre-registered value-area features V1, V2, V3, F1r and exit X1 for each flush signal
(SPEC_value_area_tests.md; implementation choices in SPEC_implementation_notes.md).

Windows, with t = signal bar open time and the signal bar closing at t+1h:
  P0 (pre-flush value) = trades in [t-29h, t-5h)   the 24 hourly bars ending 6h before the close
  P1 (flush window)    = trades in [t-5h,  t+1h)   the 6 hourly bars ending at the close
Only trades before t+1h are used for features (no lookahead).

The earlier footprint features F1..F4 (footprint_test.py) are recomputed on P1 as a replication
check against the claude.ai run; they are not part of this pass rule.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import aggtrades, fetch
from .profile import atr_wilder, profile_from_trades, rows_of
from .signals import funding_between
from .config import COST_RT

H = pd.Timedelta("1h")


def days_needed(t: pd.Timestamp) -> list[str]:
    a, b = t - 29 * H, t + H - pd.Timedelta("1ms")
    return fetch.days(a, b)


def old_footprint(w: dict, sig_close: float):
    """F1..F4 exactly as in footprint_test.py (window w = P1)."""
    p, q, sell, ts = w["p"], w["q"], w["sell"], w["ts"]
    L, Hh = p.min(), p.max()
    rng = Hh - L if Hh > L else np.nan
    tot_sell = q[sell].sum()
    zone_top = L + 0.1 * rng
    f1 = (q[sell & (p <= zone_top)].sum() / tot_sell) if tot_sell > 0 else np.nan
    if sig_close <= zone_top:
        f1 = 0.0
    hr = ts // 3_600_000
    low_hr = hr[np.argmin(p)]
    m = hr == low_hr
    bp, bq, bs = p[m], q[m], sell[m]
    bl, bh = bp.min(), bp.max(); brng = bh - bl
    buy_v, sell_v = bq[~bs].sum(), bq[bs].sum(); vol = buy_v + sell_v
    close_b = bp[-1]
    f2 = int(vol > 0 and brng > 0 and (buy_v - sell_v) / vol <= -0.05 and (close_b - bl) / brng >= 0.5)
    f3 = (bq[bp <= bl + 0.05 * brng].sum() / (0.05 * vol)) if (vol > 0 and brng > 0) else np.nan
    f4 = 0
    if brng > 0:
        rows = np.minimum(((bp - bl) / brng * 20).astype(int), 19)
        sv = np.bincount(rows[bs], weights=bq[bs], minlength=20)
        bv = np.bincount(rows[~bs], weights=bq[~bs], minlength=20)
        imb = [(sv[r] > 0 and sv[r] >= 3 * bv[r + 1]) for r in range(19)]
        run = 0
        for r in range(7):
            run = run + 1 if imb[r] else 0
            if run >= 3:
                f4 = 1; break
    return f1, f2, f3, f4


def features_for(w0: dict, w1: dict, close: float, atr: float) -> dict:
    P0 = profile_from_trades(w0["p"], w0["q"])
    P1 = profile_from_trades(w1["p"], w1["q"])
    L1, H1 = P1.lo, P1.hi
    zone_top = L1 + 0.1 * (H1 - L1)
    sell = w1["sell"]
    tot_sell = w1["q"][sell].sum()
    f1r = (w1["q"][sell & (w1["p"] <= zone_top)].sum() / tot_sell) if tot_sell > 0 else np.nan
    if close <= zone_top:
        f1r = 0.0
    # buy/sell rows of both profiles are kept for later ideas (50 rows each)
    r0 = rows_of(w0["p"], P0.lo, P0.hi, 50); r1 = rows_of(w1["p"], P1.lo, P1.hi, 50)
    s0 = w0["sell"]
    return dict(
        atr=atr,
        L0=P0.lo, H0=P0.hi, POC0=P0.poc, VAL0=P0.val, VAH0=P0.vah,
        L1=P1.lo, H1=P1.hi, POC1=P1.poc, VAL1=P1.val, VAH1=P1.vah,
        V1=int(close >= P1.val),
        V2=(P0.poc - close) / atr,
        V3=(P0.poc - P1.poc) / atr,
        F1r=f1r,
        prof0_buy=np.bincount(r0[~s0], weights=w0["q"][~s0], minlength=50).astype("float32"),
        prof0_sell=np.bincount(r0[s0], weights=w0["q"][s0], minlength=50).astype("float32"),
        prof1_buy=np.bincount(r1[~sell], weights=w1["q"][~sell], minlength=50).astype("float32"),
        prof1_sell=np.bincount(r1[sell], weights=w1["q"][sell], minlength=50).astype("float32"),
        n_tr0=len(w0["p"]), n_tr1=len(w1["p"]),
    )


def exit_x1(row, m1: pd.DataFrame, f: pd.Series) -> dict:
    """X1: limit sell at POC0 placed at entry; filled at the first 1m bar with high >= POC0 within
    [entry, entry+24h); else the plain 24h exit. POC0 at or below the entry price fills at entry."""
    e_t, x_t, e = row.entry_t, row.exit_t, row.entry
    tp = row.POC0
    if not np.isfinite(tp):
        return dict(x1_hit=np.nan, x1_t=pd.NaT, x1_net=np.nan)
    if tp <= e:
        fill_t, px = e_t, e
    else:
        seg = m1.loc[e_t: x_t - pd.Timedelta("1min")]
        hit = np.flatnonzero(seg.h.values >= tp)
        if len(hit) == 0:
            return dict(x1_hit=0, x1_t=x_t, x1_net=row.net)
        fill_t, px = seg.index[hit[0]], tp
    fund = funding_between(f, e_t, fill_t)
    return dict(x1_hit=1, x1_t=fill_t, x1_net=px / e - 1 - COST_RT - fund)


def _prefetched(sym: str, days: list[str], inflight: int = 8):
    """Yield (day, zip bytes | None) in order, with at most `inflight` downloads outstanding."""
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(inflight) as ex:
        win = deque()
        for d in days:
            win.append((d, ex.submit(fetch.get_bytes, fetch.aggtrades_rel(sym, d))))
            if len(win) >= inflight:
                dd, f = win.popleft(); yield dd, f.result()
        while win:
            dd, f = win.popleft(); yield dd, f.result()


def coin_features(sym: str, tr: pd.DataFrame, h: pd.DataFrame, m1: pd.DataFrame, f: pd.Series,
                  inflight: int = 8) -> pd.DataFrame:
    """Features for all signals of one coin. aggTrades days are streamed through memory in time
    order (bounded prefetch) and never written to disk."""
    if len(tr) == 0:
        return pd.DataFrame()
    tr = tr.sort_values("t").reset_index(drop=True)
    atr = atr_wilder(h)
    sig_days = {r.Index: days_needed(r.t) for r in tr.itertuples()}
    by_last = {}
    for i, ds in sig_days.items():
        by_last.setdefault(ds[-1], []).append(i)
    need = sorted({d for ds in sig_days.values() for d in ds})
    cache: dict[str, dict | None] = {}
    ms = lambda x: int(x.value // 1_000_000)
    out = []
    for d, blob in _prefetched(sym, need, inflight):
        cache[d] = aggtrades.parse(blob) if blob is not None else None
        for k in [k for k in cache if pd.Timestamp(k) < pd.Timestamp(d) - pd.Timedelta(days=2)]:
            del cache[k]
        for i in by_last.get(d, []):
            r = tr.loc[i]
            parsed = [cache.get(x) for x in sig_days[i]]
            rec = dict(sym=sym, t=r.t)
            if any(p is None for p in parsed):
                rec["missing"] = 1; out.append(rec); continue
            w0 = aggtrades.window(parsed, ms(r.t - 29 * H), ms(r.t - 5 * H))
            w1 = aggtrades.window(parsed, ms(r.t - 5 * H), ms(r.t + H))
            if len(w0["p"]) < 100 or len(w1["p"]) < 100:
                rec["missing"] = 1; out.append(rec); continue
            c = float(h.at[r.t, "c"])
            rec.update(features_for(w0, w1, c, float(atr.at[r.t])))
            f1, f2, f3, f4 = old_footprint(w1, c)
            rec.update(F1_trapped=f1, F2_absorb=f2, F3_thin=f3, F4_stacked=f4, missing=0)
            out.append(rec)
    F = tr.merge(pd.DataFrame(out), on=["sym", "t"], how="left")
    F["missing"] = F["missing"].fillna(1).astype(int)
    x1 = [exit_x1(r, m1, f) if r.missing == 0 else dict(x1_hit=np.nan, x1_t=pd.NaT, x1_net=np.nan)
          for r in F.itertuples()]
    return pd.concat([F, pd.DataFrame(x1, index=F.index)], axis=1)
