"""
B4 (PROTOCOL_P4.md): frozen P3B on single stocks, point-in-time S&P 500 membership (Sharadar), 2005-01-03 to the
last SEP date. Entries only on days the stock is a member; seen names excluded. Market-on-close, 0.05%.
  (a) all P3B signals
  (b) excluding signals whose window [signal day .. exit day] contains an earnings date (EVENTS code 22)
Primary: pooled excess over random entries in the same stock (member days), month-clustered CI.
Pass (each variant): pooled excess > 0 with CI lower bound > 0.
Data: data/sharadar/{membership,prices,earnings}.parquet from scripts/p4_sharadar_prep.py.
"""
import json
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from scalpel import p3, p4

TAG = "B4_stocks"
SH = p4.ROOT / "data" / "sharadar"
START = pd.Timestamp("2005-01-03")
SEEN = {"AAPL", "AMZN", "NVDA", "MSFT", "GOOGL", "GOOG", "META", "FB", "TSLA", "JPM", "AVGO", "NFLX", "LLY", "AMD"}
_G = {}


def _init():
    _G["M"] = pd.read_parquet(SH / "membership.parquet")
    _G["E"] = pd.read_parquet(SH / "earnings.parquet")
    _G["V"] = p3.vix_features()


def stock_frame(tk, P):
    P = P.sort_values("date").reset_index(drop=True)
    f = (P["closeadj"] / P["close"]).replace([np.inf, -np.inf], np.nan).ffill().fillna(1.0)
    d = pd.DataFrame({"date": P["date"], "open": P["open"] * f, "high": P["high"] * f, "low": P["low"] * f,
                      "close": P["close"] * f, "volume": P["volume"]})
    D = p3.add_features(d, _G["V"])
    D["roll"] = False
    D["sym"] = tk
    D["unadj"] = P["closeunadj"].values
    dates = pd.DatetimeIndex(D["date"])
    mem = np.zeros(len(D), bool)
    for r in _G["M"][_G["M"]["ticker"] == tk].itertuples():
        s = r.start if pd.notna(r.start) else pd.Timestamp("1900-01-01")
        e = r.end if pd.notna(r.end) else pd.Timestamp("2100-01-01")
        mem |= (dates >= s) & (dates < e)
    D["member"] = mem.astype(float)
    ed = np.sort(_G["E"].loc[_G["E"]["ticker"] == tk, "date"].values)
    k = np.searchsorted(dates.values, ed)                  # bar index on/after each earnings date
    has = np.zeros(len(D) + 6, int)
    np.add.at(has, k[k < len(D)], 1)
    cum = np.r_[0, np.cumsum(has)]
    idx = np.arange(len(D))
    D["earn_free"] = ((cum[np.minimum(idx + 6, len(D))] - cum[idx]) == 0).astype(float)   # bars i..i+5
    D["earn_known"] = float(len(ed) > 0)
    return D


def run_one(args):
    tk, P = args
    try:
        D = stock_frame(tk, P)
    except Exception as e:                                 # report, never silently drop
        return tk, None, f"frame error: {e}"
    if len(D) < 300:
        return tk, None, "fewer than 300 bars"
    i0 = max(252, int(np.searchsorted(D["date"].values, np.datetime64(START))))
    i1 = len(D)
    if i0 >= i1 - 6:
        return tk, None, "no bars in window"
    rng = np.random.default_rng(zlib.crc32(tk.encode()))
    member = D["member"].values > 0.5
    out = {}
    for var, extra in (("a", ["member>0.5"]), ("b", ["member>0.5", "earn_free>0.5"])):
        spec = {"entry": list(p4.P3B["entry"]) + extra, "hold": p4.P3B["hold"]}
        t = p4.trades(D, spec, "close", i0, i1)
        if len(t) == 0:
            out[var] = None
            continue
        t, _ = p4.add_excess(D, t, "close", i0, i1, rng, eligible=member)
        t["ret_hv"] = p4.highvix_ret(D, t["sig"].values, t["px_in"].values, t["ret"].values,
                                     unadj_px=D["unadj"].values[t["sig"].values])
        hv = p4.random_entries(D, t, "close", i0, i1, rng, eligible=member, highvix=True, unadj=D["unadj"].values)
        t["excess_hv"] = t["ret_hv"] - float(np.nanmean(hv))
        if var == "b":
            draws_ef = p4.random_entries(D, t, "close", i0, i1, rng, eligible=member & (D["earn_free"].values > 0.5))
            t["excess_ef"] = t["ret"] - float(np.nanmean(draws_ef))
        t["delisted_exit"] = (t["why"] == "end") & (t["exit"] < len(D))
        out[var] = t.drop(columns=["entry", "exit"]).assign(earn_known=D["earn_known"].iat[0])
    return tk, out, "ok"


def summary(P, col="excess", raw="ret"):
    m, lo, hi = p4.month_ci(P[col], P["date"])
    per = P.groupby("sym")[col].mean()
    return dict(p4.basic(P[raw].values), excess_pct=m * 100, ci_lo_pct=lo * 100, ci_hi_pct=hi * 100,
                stocks=int(P["sym"].nunique()), share_stocks_pos=float((per > 0).mean()))


def main():
    p4.check_lock()
    out = p4.OUT / TAG
    if (out / "results.json").exists():
        raise SystemExit("B4 already ran once")
    out.mkdir(parents=True, exist_ok=True)
    M = pd.read_parquet(SH / "membership.parquet")
    univ = sorted(set(M.loc[M["end"].isna() | (M["end"] > START), "ticker"]) - SEEN)
    prices = pd.read_parquet(SH / "prices.parquet")
    groups = {tk: g for tk, g in prices[prices["ticker"].isin(univ)].groupby("ticker")}
    jobs = [(tk, groups[tk]) for tk in univ if tk in groups]
    status, A, B = {}, [], []
    with Pool(4, initializer=_init) as pool:
        for k, (tk, res, msg) in enumerate(pool.imap_unordered(run_one, jobs, chunksize=4), 1):
            status[tk] = msg
            if res:
                if res.get("a") is not None:
                    A.append(res["a"])
                if res.get("b") is not None:
                    B.append(res["b"])
            if k % 100 == 0:
                print(k, "stocks", flush=True)
    A, B = pd.concat(A, ignore_index=True), pd.concat(B, ignore_index=True)
    A.to_parquet(out / "trades_a.parquet", index=False)
    B.to_parquet(out / "trades_b.parquet", index=False)
    res = {"universe": len(univ), "with_prices": len(jobs), "status_counts": pd.Series(status).value_counts().to_dict(),
           "not_ok": {k: v for k, v in status.items() if v != "ok"}}
    for nm, P in (("a_all_signals", A), ("b_ex_earnings", B)):
        r = {"base": summary(P), "highvix": summary(P, "excess_hv", "ret_hv")}
        if nm.startswith("b"):
            r["vs_earnings_free_random"] = summary(P, "excess_ef")
        pre, post = P[P["date"] < "2020-01-01"], P[P["date"] >= "2020-01-01"]
        r["2005_2019"], r["2020_2026"] = summary(pre), summary(post)
        r["delisted_exits"] = int(P["delisted_exit"].sum())
        r["dsr_raw"], r["dsr_excess"] = p4.dsr(P["ret"].values), p4.dsr(P["excess"].values)
        r["PASS"] = bool(r["base"]["excess_pct"] > 0 and r["base"]["ci_lo_pct"] > 0)
        r["highvix_flips_verdict"] = bool((r["highvix"]["excess_pct"] > 0 and r["highvix"]["ci_lo_pct"] > 0) != r["PASS"])
        res[nm] = r
    tk = pd.read_csv(SH / "tickers.csv.zip", compression="zip")
    sec = tk[tk["table"] == "SEP"].drop_duplicates("ticker").set_index("ticker")["sector"]
    res["a_by_sector"] = {s: dict(n=int(len(g)), excess_pct=float(g["excess"].mean() * 100))
                          for s, g in A.assign(sector=A["sym"].map(sec).fillna("unknown")).groupby("sector")}
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    rows = []
    for nm, var in (("a_all_signals", "P3B all signals"), ("b_ex_earnings", "P3B ex-earnings windows")):
        r = res[nm]
        for case in ("base", "highvix"):
            s = r[case]
            rows.append(dict(test="B4", variant=var, system="P3B", universe="S&P500 PIT stocks 2005-2026",
                             mode="close", cost_case=case, n=s["n"], markets=s["stocks"], mean_ret_pct=s["mean_pct"],
                             excess_pct=s["excess_pct"], ci_lo_pct=s["ci_lo_pct"], ci_hi_pct=s["ci_hi_pct"],
                             share_markets_pos=s["share_stocks_pos"],
                             dsr=r["dsr_raw"].get("dsr") if case == "base" else None,
                             n_trials=r["dsr_raw"].get("n_trials") if case == "base" else None,
                             verdict=("PASS" if r["PASS"] else "FAIL") if case == "base" else "robustness"))
    p4.log(rows)
    print(json.dumps({k: v for k, v in res.items() if k not in ("not_ok",)}, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
