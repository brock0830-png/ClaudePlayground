# DATA_AUDIT.md — Phase 0

Date: 2026-09-19. Session environment: remote container, 4 cores, 15 GB RAM, ~30 GB writable disk, Python 3.11 with pandas 3.0 / numpy 2.4 / pyarrow / scipy / matplotlib / pytest installed.

Blindness rules were followed. Only the Drive folders `norgate_export` and `norgate_export/norgate_daily` were listed or opened. Nothing under `RESEARCH_LIBRARY` and no file with a forbidden name was listed, opened, or searched for. No past chats were consulted.

## 1. What is in the allowed folders

### `norgate_export/` (top level)

| Item | Count | Size each | Notes |
|---|---|---|---|
| `monthly_000.csv` … `monthly_041.csv` | 42 | 5.5 MB to 9.8 MB | Monthly bars, 1,000 tickers per chunk (verified on chunk 041: exactly manifest positions 41000 to 41869) |
| `test_TOTALRETURN.csv` | 1 | 3.9 MB | 138 tickers, monthly, 1990-01 to 2026-08, total-return adjusted |
| `test_CAPITAL.csv` | 1 | 3.3 MB | Same 138 tickers, monthly, capital (split-only) adjusted |
| `norgate_daily/` | folder | | see below |

### `norgate_export/norgate_daily/`

| Item | Count | Size | Notes |
|---|---|---|---|
| `daily_0000.csv` … `daily_0139.csv` | 140 | 20 MB to 58 MB, total 6.37 GB | Daily bars. From the chunk count and manifest size, 300 tickers per chunk (inferred, not verified: no daily chunk could be loaded, see section 3) |
| `_done.txt` | 1 | 0.4 MB | Symbol manifest: 41,870 symbols, alphabetically sorted, CRLF line endings |

### File layout and columns (verified from file snippets and the one monthly chunk that loaded)

- Daily: `ticker,date,o,h,l,c,v`. Example first row of `daily_0000.csv`: `A,1999-11-18,27.074335,29.752016,23.801613,25.437973,7.517742e+07`.
- Monthly: `ticker,ym,o,h,l,c,n,v` where `ym` is the first day of the month, `n` is the number of trading days in the month, `v` is summed share volume.
- Chunks are contiguous slices of the sorted manifest. `data/norgate_chunk_map.csv` maps every ticker to its monthly chunk (verified) and inferred daily chunk.

### Symbol coverage (from the manifest)

| | Count |
|---|---|
| Total symbols | 41,870 |
| Live symbols (no suffix) | 14,645 |
| Delisted symbols (`-YYYYMM` suffix = delisting month) | 27,225 |

Delisted securities are present, so single-stock work would be free of survivorship bias at the price level. However, there is no index-membership file anywhere in the allowed folders, so historical index constituency is not available. Consequence: a single-stock system cannot be built without survivorship bias in the universe definition. This audit therefore recommends an ETF-only system, which the brief already prefers.

There are no index series (no `$SPX`, `$SPXTR`, `$NDX` or similar) in the manifest. The Norgate export is equities and ETFs only.

Key ETFs present (live): SPY, QQQ, IWM, DIA, MDY, IJR, RSP, VTI, EFA, EEM, VNQ, all nine original sector SPDRs, TLT, IEF, SHY, SHV, BIL, TIP, LQD, HYG, AGG, GOVT, VGLT, VGIT, EDV, ZROZ, SPTL, SPTS, GLD, SLV, GDX, DBC, USO, and the leveraged/inverse set SSO, QLD, UPRO, TQQQ, SPXL, UDOW, TNA, UGL, UST, UBT, TMF, TYD, SH, SQQQ, SPXU, TBT, TMV, plus VXX, VIXY, UVXY, SVXY. Several of these tickers also have unrelated delisted namesakes (for example `GLD-196209`, `TMF-199212`, `UPRO-200103`); the chunk map keeps them separate.

### Date ranges (verified on what loaded)

- `monthly_041.csv`: 84,198 rows, 870 tickers (WYNN to ZZ-201303), months from 1950-01 to 2026-08.
- Test files: 1990-01 to 2026-08 for every ticker that existed in 1990.
- Daily chunks: first rows for ticker A begin 1999-11-18 (Agilent's IPO), which says nothing about the start of the daily set as a whole. The end date of the daily set could not be verified.

### Adjustment type (verified)

The export is total-return adjusted. On the two tickers common to `monthly_041.csv` and the test files (XOM, ZBH), the export close equals `test_TOTALRETURN.csv` exactly (max relative difference 0.0 over 440 and 302 months) and differs from `test_CAPITAL.csv` by up to 71% (XOM) and 14% (ZBH). This means:

- Closes can be used directly as total-return indexes.
- Early prices are scaled down (XOM 1990-01 export close 3.44 versus capital-adjusted 11.75), so any rule that uses absolute price levels, round-number thresholds, or unadjusted dollar volume must be avoided or must reconstruct capital prices.
- Dollar-volume liquidity screens need capital-adjusted prices. Those exist only for the 138 single stocks in `test_CAPITAL.csv`, so ETF liquidity flags will be taken from FMP unadjusted closes and volumes.

## 2. Public and alternative sources reachable from this environment

The container's egress policy blocks most public data hosts. Verified blocked (HTTP 403 on CONNECT, also blocked through the WebFetch tool): fred.stlouisfed.org, mba.tuck.dartmouth.edu (Ken French), cdn.cboe.com, stooq.com, finance.yahoo.com, spglobal.com, drive.google.com, docs.google.com, financialmodelingprep.com (direct), data.nasdaq.com, home.treasury.gov, federalreserve.gov. Verified reachable: api.github.com and raw.githubusercontent.com. pip works.

Reachable through MCP connectors:

| Source | What was verified | Limits |
|---|---|---|
| FMP `economics/treasury-rates` | Daily constant-maturity Treasury curve (3m, 6m, 1y, 2y, 3y, 5y, 7y, 10y, 20y, 30y) from at least 1990-01-02. 1m and 2m are null before their series start; 20y is null in 1990 | This is the same data FRED publishes as DGS series. Suitable for building Treasury total-return proxies and the T-bill cash sleeve |
| FMP `economics/economics-indicators name=federalFunds` | Monthly effective fed funds (verified for 2006) | Monthly only. Daily financing rate for leveraged-ETF simulation will use the 3-month bill (or 1-month bill from 2001) from the curve above |
| FMP `chart/historical-price-eod-dividend-adjusted` | ETF dividend-adjusted OHLC and volume from listing date: SPY from 1993-01-29, QQQ from 1999-03-10, TLT from 2002-07-30, SSO from 2006-06-21, TQQQ from 2010-02-11 | Maximum 5,000 rows per call, so multi-decade histories are fetched in date-paged calls |
| FMP `chart/historical-price-eod-full` | Unadjusted close and volume (for liquidity screens) | Same 5,000-row cap |
| FMP `chart/historical-price-eod-light` on index symbols | `^GSPC` (S&P 500 price) from at least 1990-01-02, `^RUT` (Russell 2000 price) from at least 1990-01-02, `NDX` (Nasdaq-100 price) from 1985-10-01, `^VIX` from 1990-01-02, `GCUSD` (gold, continuous front-month) from 1980-01-02 | Price indexes only, no total return. `^NDX` and `^SP500TR` are plan-locked. The `volume` field on `^RUT` is a copy of the `^GSPC` volume and must be ignored |
| TradingView `get_ohlcv` | Reaches back only about 10 years (SPX daily from 2016-07) | Not useful for this project |
| Sharadar | No path or access method was given in the brief | Treated as unavailable |

Cross-check of FMP against Norgate (the only Norgate ETF data that could be loaded, chunk 041): month-end FMP dividend-adjusted closes versus Norgate total-return monthly closes, 238 overlapping months from 2006-11 to 2026-08.

| ETF | Mean monthly return difference | Std of difference | Max abs difference | Cumulative drift over 19.8 years |
|---|---|---|---|---|
| XLK | 0.2 bp | 5.2 bp | 46 bp (2026-08) | +0.34% total, 1.7 bp/yr |
| XLU | -0.5 bp | 8.5 bp | 113 bp (2026-08) | -1.25% total, -6.4 bp/yr |

Outside the final partial month the two sources agree at the level of a few basis points per month. FMP's dividend adjustment is therefore an acceptable stand-in for the Norgate total-return series where Norgate cannot be loaded, with the caveat that this was checked on two ETFs only.

## 3. Loading: what works and what does not

The only route to Drive from this container is the Google Drive MCP connector, which returns file bytes base64-encoded. Verified behaviour:

| File size | Result |
|---|---|
| 0.4 MB, 3.3 MB, 3.9 MB, 5.5 MB | Downloaded and decoded correctly |
| 7.9 MB, 8.7 MB (four attempts) | Connector session expires mid-transfer every time |
| 47.7 MB (a daily chunk) | Refused outright: "File too large for download, over limit of 10 MB" |

So of the Norgate export I can load: the manifest, the two test files, and exactly one of the 42 monthly chunks (`monthly_041.csv`, 5.5 MB). I cannot load any daily chunk or the other 41 monthly chunks. That means the Norgate daily data the brief is built around is not usable in this environment as exported.

This is a stop-point blocker. Three ways to unblock, in order of preference:

1. Commit a Norgate daily subset to this repository. A daily export of the roughly 80 ETFs and ETNs listed in section 1 (total-return adjusted, same columns) would be about 30 to 50 MB as CSV, which fits GitHub's per-file limit, and GitHub is reachable from here. Add a second file with the capital-adjusted closes and volume for the same tickers so liquidity can be screened. This keeps Norgate as the primary source, as the brief intends.
2. Re-chunk the Drive export so every file is at most 5 MB (gzip is fine, since the connector delivers raw bytes). For the ETF subset that is one or two gzipped files. For the full daily set it is about 1,300 files, which is impractical but possible.
3. Proceed on FMP as the primary daily source for ETFs and indexes, validated against Norgate only where Norgate can be loaded (the sector SPDRs and ZROZ in chunk 041, plus the 138 test-file stocks at monthly frequency). This is available now and the cross-check above supports it, but it puts a third-party adjusted series at the centre of a project that was specified around Norgate.

My recommendation is option 1, and to let me build Phase 1 on option 3 in the meantime so that the engine, proxies and tests are ready the moment the Norgate subset lands. Swapping the source is a one-line change in the loader.

## 4. Gaps that need a public source or a synthetic proxy

Backtest start is 1998-01-02; warmup lookbacks need data from 1997 or earlier.

| Need | Native history | Gap | Proxy plan | Source |
|---|---|---|---|---|
| S&P 500 total return | SPY from 1993-01 | None for a 1998 start | SPY itself; `^GSPC` price plus a dividend-yield accrual only if pre-1993 warmup is ever needed | FMP |
| Nasdaq-100 total return | QQQ from 1999-03 | 1998-01 to 1999-03 (14 months) plus warmup | `NDX` price index plus an assumed dividend yield, spliced to QQQ | FMP |
| Russell 2000 total return | IWM from 2000-05 | 1998-01 to 2000-05 | `^RUT` price plus dividend accrual, spliced to IWM | FMP |
| 20+ year Treasuries | TLT from 2002-07 | 1998 to 2002-07 | Constant-maturity bond total return from the 20y and 30y yields (duration and convexity approximation, coupon accrual), spliced to TLT | FMP treasury curve |
| 7 to 10 year Treasuries | IEF from 2002-07 | 1998 to 2002-07 | Same method from the 7y and 10y yields, spliced to IEF | FMP treasury curve |
| 1 to 3 year Treasuries | SHY from 2002-07 | 1998 to 2002-07 | Same method from the 2y yield, spliced to SHY | FMP treasury curve |
| Cash | BIL from 2007-05 | 1998 to 2007 | 3-month bill yield accrued daily | FMP treasury curve |
| Gold | GLD from 2004-11 | 1998 to 2004-11 | `GCUSD` front-month futures minus GLD expense ratio, spliced to GLD | FMP |
| Broad commodities | DBC from 2006-02 | 1998 to 2006 | No clean public proxy reachable from here. Candidate: `GCUSD` and crude only. Likely excluded from the tradable set unless a source appears | none |
| Leveraged equity ETFs | SSO 2006-06, QLD 2006-06, UPRO/SPXL 2009, TQQQ 2010 | 1998 to 2006/2010 | Daily simulation: L × index return minus (L-1) × (bill rate + calibrated spread) minus expense ratio / 252. Calibrate on the live period, report tracking error and annual drift, reject if drift over 1% per year | FMP for the live funds, proxies above for the index |
| Leveraged Treasury ETFs | UBT/TMF 2009-2010, UST/TYD 2009-2010 | 1998 to 2009 | Same simulation on the Treasury proxies | as above |
| VIX level (signal only) | `^VIX` from 1990 | None | Direct | FMP |
| VIX term structure, VIX ETPs | VXX 2009, VIX futures not reachable | Cannot span both recessions | Any vol sleeve is a separately flagged short-history component, as the brief requires | FMP for the ETPs |
| Financing rate | Fed funds monthly from FMP; 3m bill daily from 1990; 1m bill daily from 2001 | None | 3-month bill daily, checked against monthly fed funds | FMP |
| Risk-free rate for Sharpe | 3-month bill | None | Direct | FMP |

Public sources named in the brief that are not reachable and whose absence matters: Ken French daily factors (would have given a pre-1993 market total return; not needed for a 1998 start), FRED (replaced by the FMP Treasury curve, which is the same underlying data), CBOE VIX history (replaced by FMP `^VIX`; VIX futures term structure is not available at all).

## 5. Assumptions taken for unfilled brackets in the brief

| Bracket | Value used | Reason |
|---|---|---|
| Account size | $1,000,000 | Midpoint of the $500k to $2M example range. Liquidity flag at 1% of median daily dollar volume, so any ETF with median daily dollar volume under $100M gets flagged |
| Sharadar path | none | Not provided; treated as unavailable |
| Simulated-fund drift tolerance | 1% per year | As bracketed |
| Hypothesis cap | 12 | As bracketed |
| Commission-equivalent | 2 bp per trade plus half spread, doubled for leveraged ETFs | As bracketed |
| Free-parameter cap | 8 | As bracketed |
| Drawdown frontier | 15%, 25%, 35% | As bracketed |

## 6. Files produced in this phase

- `data/norgate_symbol_manifest.txt`: the 41,870-symbol manifest with line endings normalised.
- `data/norgate_chunk_map.csv`: ticker to monthly chunk (verified) and daily chunk (inferred).
- `src/drive_loader.py`: decodes Drive connector envelopes into DataFrames and parquet; documents the layout.
- `data/raw/` (git-ignored): `monthly_041.csv`, the two test files, and the FMP XLK and XLU pulls used for the cross-check.
