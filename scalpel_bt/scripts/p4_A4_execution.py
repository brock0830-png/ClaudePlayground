"""
A4 (PROTOCOL_P4.md): execution realism. P2A signals from SPY's own bar and from SPX (^GSPC) bars; each signal
is filled three ways on the SAME signal list:
  (i)  16:00 close, exit at the close 5 sessions later (SPY prices, 0.05%)
  (ii) next 09:30 open, exit at the open 5 sessions after entry (SPY prices, 0.05%)
  (iii) ES at 18:00 the same evening, exit at 18:00 after 5 sessions (ES points, 0.60 pt + rolls; % of the RAW
       traded ES price)
Windows: 3-way 2013-01 to 2026-09; (i) vs (ii) also from 1994. Paired differences with month-clustered CIs,
also for signals with VIX > 25.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from scalpel import p3, p4

TAG = "A4_execution"


def fills(sig_dates, vix, spy, es, raw):
    sd = pd.DatetimeIndex(spy["date"])
    ed = pd.DatetimeIndex(es["date"])
    O, C = spy["open"].values, spy["close"].values
    eO = es["open"].values
    rollcum = np.r_[0, np.cumsum(es["roll"].values.astype(int))]
    rows = []
    for d, v in zip(sig_dates, vix):
        i = sd.searchsorted(d)
        if i >= len(sd) or sd[i] != d or i + 6 >= len(sd):
            continue
        r_close = (C[i + 5] - C[i] - p3.ETF_RT_PCT * C[i]) / C[i]
        r_open = (O[i + 6] - O[i + 1] - p3.ETF_RT_PCT * O[i + 1]) / O[i + 1]
        j = ed.searchsorted(d, side="right")                    # ES session opening at 18:00 on date d
        r_es = np.nan
        if j + 5 < len(ed):
            rolls = rollcum[j + 5] - rollcum[j + 1]              # switches in sessions j+1..j+4
            pnl = eO[j + 5] - eO[j] - (p3.ES_RT_PTS + p3.ES_ROLL_PTS * rolls)
            r_es = pnl / raw["raw_open"].values[j]
        rows.append(dict(date=d, vix=v, close=r_close, open=r_open, es=r_es))
    return pd.DataFrame(rows)


def summarize(F, cols):
    out = {}
    for c in cols:
        m, lo, hi = p4.month_ci(F[c], F["date"])
        out[c] = dict(n=int(F[c].notna().sum()), mean_pct=m * 100, ci=[lo * 100, hi * 100])
    for a, b in (("open", "close"), ("es", "close"), ("es", "open")):
        if a in cols and b in cols:
            x = F.dropna(subset=[a, b])
            m, lo, hi = p4.month_ci(x[a] - x[b], x["date"])
            out[f"{a}-{b}"] = dict(n=len(x), mean_pct=m * 100, ci=[lo * 100, hi * 100])
    return out


def main():
    p4.check_lock()
    out = p4.OUT / TAG
    if (out / "results.json").exists():
        raise SystemExit("A4 already ran once")
    out.mkdir(parents=True, exist_ok=True)
    spy, spx = p4.load_etf("SPY"), p4.load_gspc()
    es, raw = p4.load_es("all"), p4.es_raw_prices("all")
    res, logrows = {}, []
    for src, D in (("SPY signals", spy), ("SPX signals", spx)):
        i0, i1 = p4.window(D, "1994-01-03")
        t = p4.trades(D, p4.P2A, "close", i0, i1)
        F = fills(pd.DatetimeIndex(t["date"]), t["vix"].values, spy, es, raw)
        F.to_csv(out / f"fills_{src.split()[0]}.csv", index=False)
        recent = F[F["date"] >= "2013-01-01"]
        for nm, X, cols in ((f"{src} 1994-2026", F, ["close", "open"]),
                            (f"{src} 2013-2026", recent, ["close", "open", "es"]),
                            (f"{src} 2013-2026 VIX>25", recent[recent["vix"] > 25], ["close", "open", "es"]),
                            (f"{src} 1994-2026 VIX>25", F[F["vix"] > 25], ["close", "open"])):
            res[nm] = summarize(X, cols)
            for c, s in res[nm].items():
                logrows.append(dict(test="A4", variant=f"{nm} | {c}", system="P2A", universe=src.split()[0],
                                    mode=c, cost_case="base", n=s["n"], mean_ret_pct=s["mean_pct"],
                                    ci_lo_pct=s["ci"][0], ci_hi_pct=s["ci"][1], verdict="descriptive"))
    agree = None
    S = p4.trades(spy, p4.P2A, "close", *p4.window(spy, "1994-01-03"))
    X = p4.trades(spx, p4.P2A, "close", *p4.window(spx, "1994-01-03"))
    a, b = set(pd.DatetimeIndex(S["date"])), set(pd.DatetimeIndex(X["date"]))
    agree = dict(spy_signals=len(a), spx_signals=len(b), both=len(a & b), jaccard=len(a & b) / len(a | b))
    res["signal_agreement_SPY_vs_SPX"] = agree
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    p4.log(logrows)
    for k, v in res.items():
        print(k, json.dumps(v, default=lambda x: round(x, 3) if isinstance(x, float) else str(x)))


if __name__ == "__main__":
    main()
