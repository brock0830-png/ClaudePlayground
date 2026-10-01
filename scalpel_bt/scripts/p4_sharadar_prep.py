"""
Phase 4 B4 data prep (PROTOCOL_P4.md): point-in-time S&P 500 membership, prices and earnings dates from the
client's Sharadar export (data/sharadar/, fetched by data/sharadar/fetch.sh; not committed).

Outputs (data/sharadar/):
  membership.parquet   ticker, start, end (end exclusive; NaT = still a member) from added/removed events
  prices.parquet       SEP rows for every ticker that was a member at any time from 2005-01-03, from 2003-01-01
  earnings.parquet     ticker, date for EVENTS rows containing code 22 (8-K Item 2.02)
  prep_report.json     membership-vs-snapshot validation, coverage of members by SEP prices
"""
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SH = ROOT / "data" / "sharadar"
TEST_START = pd.Timestamp("2005-01-03")
PRICE_START = "2003-01-01"


def membership(sp: pd.DataFrame) -> pd.DataFrame:
    ev = sp[sp.action.isin(["added", "removed"])].copy()
    ev["date"] = pd.to_datetime(ev["date"])
    ev = ev.sort_values(["date", "action"])            # 'added' before 'removed' on the same date
    rows, open_ = [], {}
    for r in ev.itertuples():
        if r.action == "added":
            if r.ticker not in open_:
                open_[r.ticker] = r.date
        else:
            s = open_.pop(r.ticker, None)
            rows.append((r.ticker, s if s is not None else pd.NaT, r.date))
    rows += [(tk, s, pd.NaT) for tk, s in open_.items()]
    return pd.DataFrame(rows, columns=["ticker", "start", "end"])


def members_on(M: pd.DataFrame, d: pd.Timestamp) -> set:
    st = M["start"].isna() | (M["start"] <= d)
    en = M["end"].isna() | (M["end"] > d)
    return set(M.loc[st & en, "ticker"])


def main():
    sp = pd.read_csv(SH / "sp500.csv")
    M = membership(sp)
    rep = {}
    # validation against the quarterly 'historical' snapshots
    snaps = sp[sp.action == "historical"].copy()
    snaps["date"] = pd.to_datetime(snaps["date"])
    val = []
    for d, g in snaps.groupby("date"):
        a, b = members_on(M, d), set(g["ticker"])
        val.append(dict(date=str(d.date()), snapshot=len(b), rebuilt=len(a), only_snapshot=len(b - a),
                        only_rebuilt=len(a - b), jaccard=len(a & b) / len(a | b)))
    V = pd.DataFrame(val)
    rep["snapshot_validation"] = {"snapshots": len(V), "min_jaccard": float(V.jaccard.min()),
                                  "mean_jaccard": float(V.jaccard.mean()),
                                  "worst": V.sort_values("jaccard").head(5).to_dict("records")}
    cur = set(sp.loc[sp.action == "current", "ticker"])
    last = members_on(M, pd.Timestamp(sp.loc[sp.action == "current", "date"].iat[0]))
    rep["current_check"] = {"current": len(cur), "rebuilt": len(last), "jaccard": len(cur & last) / len(cur | last)}
    M.to_parquet(SH / "membership.parquet", index=False)

    universe = set(M.loc[M["end"].isna() | (M["end"] > TEST_START), "ticker"])
    tk = pd.read_csv(zipfile.ZipFile(SH / "tickers.csv.zip").open("tickers.csv"))
    sep = tk[tk.table == "SEP"].drop_duplicates("ticker").set_index("ticker")
    rep["universe_members_since_2005"] = len(universe)
    rep["universe_without_SEP_ticker"] = sorted(universe - set(sep.index))
    rep["universe_categories"] = sep.reindex(sorted(universe & set(sep.index)))["category"].value_counts().to_dict()

    parts = []
    with zipfile.ZipFile(SH / "stocks.csv.zip") as z:
        with z.open("stocks.csv") as fh:
            for ch in pd.read_csv(fh, chunksize=4_000_000,
                                  usecols=["ticker", "date", "open", "high", "low", "close", "volume", "closeadj",
                                           "closeunadj"]):
                ch = ch[ch["ticker"].isin(universe) & (ch["date"] >= PRICE_START)]
                if len(ch):
                    parts.append(ch)
                print("chunk", sum(len(p) for p in parts), flush=True, file=sys.stderr)
    P = pd.concat(parts, ignore_index=True)
    P["date"] = pd.to_datetime(P["date"])
    P = P.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")
    P.to_parquet(SH / "prices.parquet", index=False)
    have = set(P["ticker"])
    rep["universe_with_prices"] = len(universe & have)
    rep["universe_without_prices"] = sorted(universe - have)
    # member-days covered by a price bar (a stock in the index on a day must have a price that day)
    cov = []
    for r in M[M["ticker"].isin(universe)].itertuples():
        s = max(r.start if pd.notna(r.start) else TEST_START, TEST_START)
        e = r.end if pd.notna(r.end) else P["date"].max() + pd.Timedelta(days=1)
        g = P.loc[P["ticker"] == r.ticker, "date"] if r.ticker in have else pd.Series(dtype="datetime64[ns]")
        bdays = len(pd.bdate_range(s, e - pd.Timedelta(days=1)))
        n = int(((g >= s) & (g < e)).sum())
        cov.append((r.ticker, bdays, n))
    C = pd.DataFrame(cov, columns=["ticker", "bdays", "bars"])
    rep["member_bday_coverage"] = float(C.bars.sum() / C.bdays.sum())
    rep["tickers_under_90pct_coverage"] = C[C.bars < 0.9 * C.bdays].ticker.tolist()

    e = pd.read_csv(zipfile.ZipFile(SH / "events.csv.zip").open("events.csv"))
    e = e[e["eventcodes"].astype(str).str.split("|").apply(lambda c: "22" in c)]
    E = e[["ticker", "date"]].assign(date=lambda x: pd.to_datetime(x["date"])).drop_duplicates()
    E.to_parquet(SH / "earnings.parquet", index=False)
    rep["earnings_rows"] = len(E)
    rep["universe_with_earnings"] = len(universe & set(E["ticker"]))
    rep["prices_rows"] = len(P)
    rep["prices_last_date"] = str(P["date"].max().date())
    (SH / "prep_report.json").write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps({k: v for k, v in rep.items() if k != "snapshot_validation"}, indent=1, default=str)[:3000])
    print("snapshot validation:", json.dumps(rep["snapshot_validation"], default=str)[:1500])


if __name__ == "__main__":
    main()
