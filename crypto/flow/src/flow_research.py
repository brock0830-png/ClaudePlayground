"""Phase 3: order flow, positioning, book depth, footprint and real-funding carry (crypto/flow/PREREG_FLOW.md).

  python crypto/flow/src/flow_research.py panels    # build 1h panels from the condensed archive data
  python crypto/flow/src/flow_research.py design    # every pre-registered cell on the design window
"""
from __future__ import annotations

import csv
import json
import sys
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

FLOW = Path(__file__).resolve().parents[1]
CRYPTO = FLOW.parent
sys.path.insert(0, str(CRYPTO / "src"))
sys.path.insert(0, str(CRYPTO / "perp" / "src"))
import events as ev  # noqa: E402
import perp_research as pr  # noqa: E402  (trades with funding, costs, judge)

BV = CRYPTO / "data" / "bv"
PANEL = BV / "1h"
LEDGER = FLOW / "TRIAL_LEDGER.csv"
OUT = FLOW / "reports"
UNLOCK = FLOW / "HOLDOUT_UNLOCKED"
U16 = pr.U16
BOOK5 = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
FOOT3 = ["BTC", "ETH", "SOL"]
DESIGN = (pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2024-12-31 23:59:59", tz="UTC"))
HOLDOUT = (pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2026-09-22 23:59:59", tz="UTC"))
Z = 168


def check_lock(end):
    if end > DESIGN[1] and not UNLOCK.exists():
        raise RuntimeError("flow holdout locked until crypto/flow/HOLDOUT_UNLOCKED exists")


# ------------------------------------------------------------------ panels
def build_panel(c: str) -> pd.DataFrame:
    k = pd.read_parquet(BV / f"{c}_klines_15m.parquet")
    h = k.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
                              "quote_volume": "sum", "count": "sum", "taker_buy_volume": "sum"}).dropna(subset=["close"])
    m = pd.read_parquet(BV / f"{c}_metrics_15m.parquet").resample("1h").last()  # last 5-min print inside the hour
    h = h.join(m.rename(columns={"sum_open_interest": "oi", "sum_toptrader_long_short_ratio": "top_pos",
                                 "count_toptrader_long_short_ratio": "top_acc", "count_long_short_ratio": "glob",
                                 "sum_taker_long_short_vol_ratio": "taker_ratio"})[["oi", "top_pos", "top_acc", "glob", "taker_ratio"]])
    bp = BV / f"{c}_book_15m.parquet"
    if bp.exists():
        h = h.join(pd.read_parquet(bp)[["imb1", "imb2", "depth1"]].resample("1h").mean())
    fp = BV / f"{c}_footprint_1h.parquet"
    if fp.exists():
        f = pd.read_parquet(fp)
        f.index = pd.to_datetime(f.index, utc=True)
        h = h.join(f.add_prefix("fp_"))
    pm = BV / f"{c}_premium_1h.parquet"
    if pm.exists():
        h = h.join(pd.read_parquet(pm)["open"].rename("prem_open"))
    return h


def panels():
    PANEL.mkdir(parents=True, exist_ok=True)
    for c in U16:
        p = build_panel(c)
        p.to_parquet(PANEL / f"{c}.parquet")
        print(c, len(p), p.index[0], p.index[-1], p.columns.tolist() if c == "BTC" else "")


@lru_cache(maxsize=None)
def load(c: str) -> pd.DataFrame:
    return pd.read_parquet(PANEL / f"{c}.parquet")


@lru_cache(maxsize=None)
def funding(c: str) -> pd.Series:
    f = pd.read_parquet(BV / f"{c}_funding.parquet")
    return f["last_funding_rate"]


@lru_cache(maxsize=None)
def funding_interval(c: str) -> pd.Series:
    return pd.read_parquet(BV / f"{c}_funding.parquet")["funding_interval_hours"]


# ------------------------------------------------------------------ features and signals (causal)
def z(x: pd.Series, n: int = Z) -> pd.Series:
    mu = x.shift(1).rolling(n, min_periods=n).mean()
    sd = x.shift(1).rolling(n, min_periods=n).std()
    return (x - mu) / sd


@lru_cache(maxsize=None)
def feats(c: str) -> pd.DataFrame:
    d = load(c)
    f = pd.DataFrame(index=d.index)
    delta = 2 * d["taker_buy_volume"] - d["volume"]
    f["ret"] = d["close"].pct_change()
    f["r_z"] = f["ret"] / f["ret"].shift(1).rolling(Z, min_periods=Z).std()
    f["imb_z"] = z(delta / d["volume"])
    f["flow4_z"] = z(delta.rolling(4).sum() / d["volume"].rolling(4).sum())
    f["cvd"] = delta.cumsum()
    f["spread_z"] = z(np.log(d["top_pos"])) - z(np.log(d["glob"]))
    f["glob_z"] = z(np.log(d["glob"]))
    if "imb1" in d:
        f["book_z"] = z(d["imb1"])
    if "fp_vol" in d:
        v = d["fp_vol"].replace(0, np.nan)
        f["sellbot_z"] = z(d["fp_sell_bot"] / v)
        f["buytop_z"] = z(d["fp_buy_top"] / v)
    rng = (d["high"] - d["low"]).replace(0, np.nan)
    f["clv"] = ((2 * d["close"] - d["high"] - d["low"]) / rng).fillna(0.0)
    return f


def signal(fam: str, p: dict, side: str, c: str) -> pd.Series:
    f, d = feats(c), load(c)
    L = side == "long"
    if fam == "F1":
        k = p["k"]
        return (f.imb_z <= -k) & (f.ret >= 0) if L else (f.imb_z >= k) & (f.ret <= 0)
    if fam == "F2":
        k = p["k"]
        return (f.imb_z <= -k) & (f.r_z <= -k) if L else (f.imb_z >= k) & (f.r_z >= k)
    if fam == "F3":
        k = p["k"]
        return (f.flow4_z >= k) if L else (f.flow4_z <= -k)
    if fam == "F4":
        N, cl, cvd = p["N"], d["close"], f["cvd"]
        if L:
            return (cl < cl.shift(1).rolling(N, min_periods=N).min()) & (cvd > cvd.shift(1).rolling(N, min_periods=N).min())
        return (cl > cl.shift(1).rolling(N, min_periods=N).max()) & (cvd < cvd.shift(1).rolling(N, min_periods=N).max())
    if fam == "F5":
        return (f.spread_z >= p["s"]) if L else (f.spread_z <= -p["s"])
    if fam == "F6":
        return (f.glob_z <= -p["g"]) if L else (f.glob_z >= p["g"])
    if fam == "F7":
        return (f.book_z >= p["b"]) if L else (f.book_z <= -p["b"])
    if fam == "F8":
        return (f.sellbot_z >= p["f"]) & (f.clv >= 0) if L else (f.buytop_z >= p["f"]) & (f.clv <= 0)
    raise ValueError(fam)


GRIDS = {
    "F1": ([{"k": 2}, {"k": 3}], [1, 4, 12, 24], ({"k": 2}, 4), U16),
    "F2": ([{"k": 2}, {"k": 3}], [1, 4, 12, 24], ({"k": 2}, 4), U16),
    "F3": ([{"k": 1.5}, {"k": 2.5}], [1, 4, 12, 24], ({"k": 1.5}, 4), U16),
    "F4": ([{"N": 24}, {"N": 72}], [1, 4, 12, 24], ({"N": 24}, 4), U16),
    "F5": ([{"s": 1.5}, {"s": 2.5}], [4, 12, 24, 48], ({"s": 1.5}, 12), U16),
    "F6": ([{"g": 1.5}, {"g": 2.5}], [4, 12, 24, 48], ({"g": 1.5}, 12), U16),
    "F7": ([{"b": 1.5}, {"b": 2.5}], [1, 4, 12, 24], ({"b": 1.5}, 4), BOOK5),
    "F8": ([{"f": 1.5}, {"f": 2.5}], [1, 4, 12, 24], ({"f": 1.5}, 4), FOOT3),
}


def eval_event(fam, p, side, H, window, coins, delay=0, cost_mult=1.0):
    check_lock(window[1])
    trs, unc, unc_adv, span = [], {}, {}, []
    for c in coins:
        d = load(c)
        s = signal(fam, p, side, c)
        valid = s.index[feats(c).get({"F7": "book_z", "F8": "sellbot_z"}.get(fam, "imb_z")).notna()]
        if len(valid) == 0:
            continue
        a, b = max(window[0], valid[0]), min(window[1], valid[-1])
        if a >= b:
            continue
        span.append((b - a).days / 7)
        tr = pr.trades(d, s, H, side, (a, b), pr.perp_cost(c, cost_mult), funding(c), delay, c)
        unc[c], unc_adv[c] = ev.unconditional(d, H, side, (a, b), delay)
        if len(tr):
            trs.append(tr)
    tr = pd.concat(trs, ignore_index=True) if trs else pd.DataFrame(columns=["sym", "entry_time", "gross", "net", "bars", "adverse", "funding"])
    s = ev.summarize(tr, unc, unc_adv) if len(tr) else {"n": 0}
    s["per_week"] = s.get("n", 0) / (max(span) if span else np.nan)
    return s, tr


# ------------------------------------------------------------------ real-funding carry
def carry(theta: float, window, coins=U16, cost_mult=1.0):
    """Hourly clock. Each coin has 1/len(coins) of capital; an active slot is spot-long / perp-short with notional =
    slot / 1.5. Decisions at 00/08/16 UTC on the trailing 72h mean of prints normalised to 8h. Returns daily returns."""
    check_lock(window[1])
    hours = pd.date_range(window[0], window[1], freq="1h", tz="UTC")
    pnl = pd.Series(0.0, index=hours)
    entries = 0
    for c in coins:
        raw = pd.read_parquet(BV / f"{c}_funding.parquet")
        raw.index = raw.index.floor("h")
        raw = raw[~raw.index.duplicated()]
        F = raw["last_funding_rate"]
        norm = F * 8.0 / raw["funding_interval_hours"]  # threshold compares per-8h equivalents
        prem = load(c).get("prem_open")
        if prem is None:
            continue
        prem = prem.reindex(hours).ffill()
        fh = F.reindex(hours).fillna(0.0).to_numpy()
        decide = pd.Series(hours.hour % 8 == 0, index=hours)
        notional = 1.0 / len(coins) / 1.5
        leg = pr.spot_cost(c, cost_mult) + pr.perp_cost(c, cost_mult)
        pv = prem.to_numpy()
        on, out = False, np.zeros(len(hours))
        for i, t in enumerate(hours):
            if on:
                out[i] += fh[i] * notional  # print at t accrues to a position held into t
                if i and np.isfinite(pv[i]) and np.isfinite(pv[i - 1]):
                    out[i] -= (pv[i] - pv[i - 1]) * notional
            if decide.iat[i]:
                w = norm[(norm.index > t - pd.Timedelta(hours=72)) & (norm.index <= t)]
                if len(w) >= 6 and np.isfinite(pv[i]):
                    m3 = float(w.mean())
                    if not on and m3 >= theta / 100 - 1e-10:
                        on, entries = True, entries + 1
                        out[i] -= leg * notional
                    elif on and m3 < theta / 200 - 1e-10:
                        on = False
                        out[i] -= leg * notional
        pnl += out
    daily = pnl.groupby(pnl.index.floor("D")).sum()
    return daily, entries


def carry_metrics(r: pd.Series, entries: int) -> dict:
    eq = (1 + r).cumprod()
    yrs = len(r) / 365
    sd = r.std(ddof=1)
    return {"cagr": float(eq.iloc[-1] ** (1 / yrs) - 1), "vol": float(sd * np.sqrt(365)),
            "sharpe": float(r.mean() / sd * np.sqrt(365)) if sd > 0 else np.nan,
            "maxdd": float((eq / eq.cummax() - 1).min()), "n": entries, "per_week": entries / (len(r) / 7)}


# ------------------------------------------------------------------ ledger + design run
FIELDS = pr.FIELDS


def ledger(row: dict):
    new = not LEDGER.exists()
    tid = 1 if new else sum(1 for _ in LEDGER.open())
    with LEDGER.open("a", newline="") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({**{k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()},
                    "trial_id": tid, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")})


def row(phase, fam, famname, cell, p, w, delay, cm, s, note=""):
    ledger({"phase": phase, "hypothesis": fam, "family": famname, "cell": cell, "params": json.dumps(p),
            "window_start": str(w[0].date()), "window_end": str(w[1].date()), "delay": delay, "cost_mult": cm, **s, "note": note})


def run_design(fams=None, do_carry=True):
    """fams: subset of GRIDS keys (families are independent; F7/F8 wait for their data). Results append to CSVs."""
    w = DESIGN
    rows = []
    for fam, (plist, Hs, (ref_p, ref_H), coins) in GRIDS.items():
        if fams is not None and fam not in fams:
            continue
        for p in plist:
            for side in ("long", "short"):
                name = f"{fam}|{json.dumps(p, sort_keys=True)}|{side}"
                cells = {}
                for H in Hs:
                    s, _ = eval_event(fam, p, side, H, w, coins)
                    cells[H] = s
                    row("design", fam, name, f"H={H}", p, w, 0, 1.0, s)
                sd, _ = eval_event(fam, p, side, ref_H, w, coins, delay=1)
                row("design-delay", fam, name, f"H={ref_H}", p, w, 1, 1.0, sd)
                sc, _ = eval_event(fam, p, side, ref_H, w, coins, cost_mult=2.0)
                row("design-cost2x", fam, name, f"H={ref_H}", p, w, 0, 2.0, sc)
                v = pr.judge(cells, ref_H, sd, sc)
                r = cells[ref_H]
                rows.append({"family": name, "fam": fam, "side": side, "is_ref_params": p == ref_p, "ref_H": ref_H,
                             "n": r.get("n", 0), "per_week": r.get("per_week", 0), "gross_bp": 1e4 * r.get("mean_gross", np.nan),
                             "net_bp": 1e4 * r.get("mean_net", np.nan), "t": r.get("t_clust", np.nan),
                             "excess_bp": 1e4 * r.get("excess", np.nan), "win": r.get("win_rate", np.nan),
                             "breadth": r.get("breadth", np.nan), "delay_net_bp": 1e4 * sd.get("mean_net", np.nan),
                             "cost2_net_bp": 1e4 * sc.get("mean_net", np.nan),
                             **{f"net_bp_H{h}": 1e4 * cells[h].get("mean_net", np.nan) for h in Hs}, **v})
                print(name, round(rows[-1]["net_bp"], 1), round(rows[-1]["t"], 2) if pd.notna(rows[-1]["t"]) else None, v["PASS"], flush=True)
    evt = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    if len(evt):
        pe = OUT / "design_events.csv"
        evt = pd.concat([pd.read_csv(pe), evt]) if pe.exists() else evt
        evt.to_csv(pe, index=False)
    if not do_carry:
        return evt, None
    crow = []
    for th in (0.01, 0.02, 0.03):
        r, n = carry(th, w)
        m = carry_metrics(r, n)
        row("design", "P5R", "P5R", f"theta={th}", {"theta": th}, w, 0, 1.0, m)
        rc, _ = carry(th, w, cost_mult=2.0)
        mc = carry_metrics(rc, n)
        row("design-cost2x", "P5R", "P5R", f"theta={th}", {"theta": th}, w, 0, 2.0, mc)
        ok = m["cagr"] >= 0.03 and m["sharpe"] >= 2 and m["maxdd"] >= -0.03 and mc["cagr"] > 0
        crow.append({"theta": th, **m, "cost2_cagr": mc["cagr"], "cost2_sharpe": mc["sharpe"], "PASS": ok, "is_ref": th == 0.01})
    car = pd.DataFrame(crow)
    car.to_csv(OUT / "design_carry.csv", index=False)
    return evt, car


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    if sys.argv[1:] == ["panels"]:
        panels()
    elif sys.argv[1] == "design":
        args = sys.argv[2:]
        fams = [a for a in args if a in GRIDS] or (None if not args else [])
        evt, car = run_design(fams, do_carry=(not args) or "carry" in args)
        print(evt[["family", "n", "per_week", "gross_bp", "net_bp", "t", "excess_bp", "win", "breadth", "delay_net_bp",
                   "cost2_net_bp", "PASS"]].round(2).to_string())
        if car is not None:
            print(car.round(4).to_string())
