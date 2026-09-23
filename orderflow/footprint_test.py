"""
FOOTPRINT FILTER TEST for the OI-flush signal  (pre-registered; written before any results)

Base signal: USD-mode OI flush on 1h Binance USDT perps (24h price <= -4.6%, 24h OI <= -1.8%),
entry next bar open, 24h hold, net of 0.14% costs and funding. Universe: the 9 Kraken US coins.

Input: a pickle/table of signals with columns sym (e.g. SOLUSDT), t (signal bar open time, UTC),
net (trade return). Pass its path as the first argument.

Footprints are rebuilt from Binance futures aggTrades (price, qty, aggressor side), using
only trades up to the signal bar's close (no lookahead). Window W = the 6 hourly bars
ending at the signal bar. "Low bar" = the hourly bar in W containing W's lowest trade.

Features (direction stated in advance):
  F1 trapped_sellers  share of W's aggressive-sell volume printed in the bottom 10% of W's
                      range, set to 0 if the signal close is still inside that zone.  good = HIGH
  F2 absorption       low bar has delta/volume <= -0.05 AND closes in the upper half of
                      its range (binary).                                              good = 1
  F3 thin_low         volume density in the bottom 5% of the low bar's range, relative
                      to the bar average (1.0 = average).                              good = LOW
  F4 stacked_sell_imb in the bottom third of the low bar (20 equal rows), >= 3 consecutive
                      rows where sell[r] >= 3 x buy[r+1] (diagonal imbalance) (binary). good = 1

Protocol: continuous features split into terciles with cutoffs from 2022-23 signals only;
binary features compared present vs absent. Judge on 2022-23 and 2024-26 separately.
PASS = good-minus-bad > 0 in BOTH periods AND pooled day-clustered t >= 2.5 (strict because
4 features are tested). Anything else is reported as a fail, whatever it looks like.

RESULT (Sept 2026, 1,968 signals): all four FAILED. F1 was worse in both periods (t = -1.7).
"""
import io, os, sys, time, zipfile, threading, queue
import numpy as np, pandas as pd, requests
from concurrent.futures import ThreadPoolExecutor

TR = pd.read_pickle(sys.argv[1] if len(sys.argv) > 1 else "scan/H1_trades.pkl")
KRAKEN = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT", "DOGEUSDT", "LTCUSDT", "AVAXUSDT"]
TR = TR[TR.sym.isin(KRAKEN)].sort_values(["sym", "t"]).reset_index(drop=True)
OUT = "footprint_features.pkl"
URL = "https://data.binance.vision/data/futures/um/daily/aggTrades/{s}/{s}-aggTrades-{d}.zip"

def fetch(s, d):
    for _ in range(3):
        try:
            r = requests.get(URL.format(s=s, d=d), timeout=120)
            if r.status_code == 200:
                return r.content
            if r.status_code == 404:
                return None
        except Exception:
            time.sleep(3)
    return None

def parse(blob):
    z = zipfile.ZipFile(io.BytesIO(blob))
    raw = z.open(z.namelist()[0]).read()
    hdr = 0 if raw[:3].isalpha() or raw[:1].isalpha() else None
    d = pd.read_csv(io.BytesIO(raw), header=hdr, usecols=[1, 2, 5, 6])
    d.columns = ["p", "q", "ts", "m"]
    if d.m.dtype != bool:                               # True = buyer is maker -> aggressive SELL
        d["m"] = d.m.astype(str).str.lower().eq("true")
    return d.sort_values("ts", kind="stable").reset_index(drop=True)

def features(w, sig_close):
    """w: trades in the 6h window (sorted). Returns F1..F4."""
    L, H = w.p.min(), w.p.max()
    rng = H - L if H > L else np.nan
    sell = w[w.m]; tot_sell = sell.q.sum()
    zone_top = L + 0.1 * rng
    f1 = (sell.q[sell.p <= zone_top].sum() / tot_sell) if tot_sell > 0 else np.nan
    if sig_close <= zone_top:
        f1 = 0.0
    w = w.assign(hr=(w.ts // 3_600_000))
    low_hr = w.loc[w.p.idxmin(), "hr"]
    b = w[w.hr == low_hr]
    bl, bh = b.p.min(), b.p.max(); brng = bh - bl
    buy_v = b.q[~b.m].sum(); sell_v = b.q[b.m].sum(); vol = buy_v + sell_v
    close_b = b.p.iloc[-1]
    f2 = int(vol > 0 and brng > 0 and (buy_v - sell_v) / vol <= -0.05 and (close_b - bl) / brng >= 0.5)
    f3 = (b.q[b.p <= bl + 0.05 * brng].sum() / (0.05 * vol)) if (vol > 0 and brng > 0) else np.nan
    f4 = 0
    if brng > 0:
        rows = np.minimum(((b.p - bl) / brng * 20).astype(int), 19)
        sv = np.bincount(rows[b.m], weights=b.q[b.m], minlength=20)
        bv = np.bincount(rows[~b.m], weights=b.q[~b.m], minlength=20)
        imb = [(sv[r] > 0 and sv[r] >= 3 * bv[r + 1]) for r in range(19)]
        run = 0
        for r in range(7):                                   # bottom third (rows 0..6)
            run = run + 1 if imb[r] else 0
            if run >= 3:
                f4 = 1; break
    return f1, f2, f3, f4

def main():
    jobs = []; need = {}
    for r in TR.itertuples():
        end = r.t + pd.Timedelta("1h"); start = end - pd.Timedelta("6h")
        ds = [d.date() for d in pd.date_range(start.floor("D"), end.floor("D"), freq="D")]
        need[r.Index] = (r.sym, ds, int(start.value // 1_000_000), int(end.value // 1_000_000))
        for d in ds:
            if (r.sym, d) not in jobs: jobs.append((r.sym, d))
    done = pd.read_pickle(OUT) if os.path.exists(OUT) else pd.DataFrame()
    done_idx = set(done.idx) if len(done) else set()
    results = done.to_dict("records") if len(done) else []

    q = queue.Queue(maxsize=4)
    pending_all = {i: v for i, v in need.items() if i not in done_idx}
    todo = [k for k in jobs if any(k[0] == v[0] and k[1] in v[1] for v in pending_all.values())]
    def producer():
        from collections import deque
        with ThreadPoolExecutor(5) as ex:
            win = deque()
            for k in todo:                       # bounded prefetch: at most 8 files in flight
                win.append((k, ex.submit(fetch, *k)))
                if len(win) >= 8:
                    kk, f = win.popleft(); q.put((kk, f.result()))
            while win:
                kk, f = win.popleft(); q.put((kk, f.result()))
        q.put(None)
    threading.Thread(target=producer, daemon=True).start()

    cache = {}
    pending = dict(pending_all)
    n_done = 0; t0 = time.time()
    while True:
        item = q.get()
        if item is None: break
        (s, d), blob = item
        cache[(s, d)] = parse(blob) if blob else None
        for k in [k for k in cache if k[0] == s and k[1] < d - pd.Timedelta(days=1).to_pytimedelta()]:
            del cache[k]
        ready = [i for i, (sym, ds, a, b) in pending.items() if sym == s and all((sym, x) in cache for x in ds)]
        for i in ready:
            sym, ds, a, b = pending.pop(i)
            parts = []
            for x in ds:
                dd = cache.get((sym, x))
                if dd is None: continue
                lo, hi = np.searchsorted(dd.ts.values, [a, b])
                parts.append(dd.iloc[lo:hi])
            if not parts: continue
            w = pd.concat(parts)
            if len(w) < 100: continue
            f = features(w, w.p.iloc[-1])
            r = TR.loc[i]
            results.append(dict(idx=i, sym=sym, t=r.t, net=r.net, F1_trapped=f[0], F2_absorb=f[1], F3_thin=f[2], F4_stacked=f[3]))
            n_done += 1
        if n_done and n_done % 50 == 0:
            pd.DataFrame(results).to_pickle(OUT)
            print(f"{len(results)} signals done, {time.time()-t0:.0f}s", flush=True)
    pd.DataFrame(results).to_pickle(OUT)
    print("finished", len(results), flush=True)

if __name__ == "__main__":
    main()
