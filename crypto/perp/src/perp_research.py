"""Phase 2: perpetual-futures signals (crypto/perp/PREREG_PERP.md).

  python crypto/perp/src/perp_research.py design     # every pre-registered cell on the design window
  python crypto/perp/src/perp_research.py holdout    # once, after the freeze (needs crypto/perp/HOLDOUT_UNLOCKED)
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

PERP = Path(__file__).resolve().parents[1]
CRYPTO = PERP.parent
sys.path.insert(0, str(CRYPTO / "src"))
import events as ev  # noqa: E402  (Phase 1 pooled statistics: summarize, clustered_t)

DATA = CRYPTO / "data" / "perp"
LEDGER = PERP / "TRIAL_LEDGER.csv"
OUT = PERP / "reports"
UNLOCK = PERP / "HOLDOUT_UNLOCKED"
U16 = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "ADA", "AVAX", "LINK", "LTC", "DOT", "TRX", "BCH", "SUI", "NEAR", "APT"]
C9 = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "AVAX", "LINK", "ADA"]
DESIGN = (pd.Timestamp("2024-06-12", tz="UTC"), pd.Timestamp("2025-09-30 23:59:59", tz="UTC"))
HOLDOUT = (pd.Timestamp("2025-10-01", tz="UTC"), pd.Timestamp("2026-09-23 23:59:59", tz="UTC"))
PERP_FEE, SPOT_FEE = 5.0, 10.0
SLIP_PERP = {"BTC": 1.0, "ETH": 1.0, "SOL": 2.0, "XRP": 2.0, "DOGE": 2.0, "BNB": 2.0}
SLIP_SPOT = {"BTC": 2.0, "ETH": 2.0, "SOL": 4.0, "XRP": 4.0, "DOGE": 4.0, "BNB": 4.0, "ADA": 4.0, "AVAX": 4.0,
             "LINK": 4.0, "LTC": 4.0, "DOT": 4.0, "TRX": 4.0, "BCH": 4.0}
INTEREST, CLAMP, CAP = 0.01, 0.05, 0.75  # % per 8h


def perp_cost(c, mult=1.0):
    return (PERP_FEE + SLIP_PERP.get(c, 3.0)) / 1e4 * mult


def spot_cost(c, mult=1.0):
    return (SPOT_FEE + SLIP_SPOT.get(c, 6.0)) / 1e4 * mult


def check_lock(end):
    if end > DESIGN[1] and not UNLOCK.exists():
        raise RuntimeError("perp holdout locked until crypto/perp/HOLDOUT_UNLOCKED exists")


# ------------------------------------------------------------------ data
@lru_cache(maxsize=None)
def load(coin: str, iv: str = "4h") -> pd.DataFrame:
    p = pd.read_parquet(DATA / f"{coin}USDT_PERP_{iv}.parquet")[["open", "high", "low", "close", "volume"]]
    oi = pd.read_parquet(DATA / f"{coin}USDT_OI_{iv}.parquet")["close"].rename("oi")
    pr = pd.read_parquet(DATA / f"{coin}USDT_PREMIUM_{iv}.parquet")
    df = p.join(oi, how="inner").join(pr[["open", "close"]].rename(columns={"open": "prem_open", "close": "prem"}), how="inner")
    df["prem_mid"] = pr[["open", "high", "low", "close"]].mean(axis=1).reindex(df.index)
    return df.astype(float)


def funding_from_premium(prem_mid: pd.Series, bar: pd.Timedelta) -> pd.Series:
    """Reconstructed funding (fraction) at each 00/08/16 UTC settlement from the mean premium of the prior 8h."""
    s = prem_mid.dropna()
    t0 = s.index[0].ceil("8h")
    times = pd.date_range(t0, s.index[-1] + bar, freq="8h")
    out = {}
    for tau in times:
        w = s[(s.index >= tau - pd.Timedelta(hours=8)) & (s.index < tau)]
        if len(w) < round(pd.Timedelta(hours=8) / bar):
            continue
        p = float(w.mean())
        f = p + np.clip(INTEREST - p, -CLAMP, CLAMP)
        out[tau] = round(float(np.clip(f, -CAP, CAP)) / 100.0, 10)  # Binance prints funding to 8 decimals
    return pd.Series(out, dtype=float)


@lru_cache(maxsize=None)
def funding(coin: str, iv: str = "4h") -> pd.Series:
    return funding_from_premium(load(coin, iv)["prem_mid"], pd.Timedelta(iv))


# ------------------------------------------------------------------ features and signals (causal)
def feats(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    r = df["close"].pct_change()
    f["r_z"] = r / r.shift(1).rolling(50, min_periods=50).std()
    d = df["oi"].pct_change()
    f["oi_z"] = d / d.shift(1).rolling(50, min_periods=50).std()
    d6 = df["oi"] / df["oi"].shift(6) - 1
    f["oi6_z"] = d6 / d6.shift(1).rolling(180, min_periods=180).std()
    f["oi6"] = d6
    p = df["prem"]
    f["prem_z"] = (p - p.shift(1).rolling(180, min_periods=180).mean()) / p.shift(1).rolling(180, min_periods=180).std()
    f["obv"] = (np.sign(df["close"].diff()).fillna(0) * df["volume"]).cumsum()
    return f


def signal(hyp: str, params: dict, side: str, df: pd.DataFrame) -> pd.Series:
    f = feats(df)
    c = df["close"]
    if hyp == "P1":
        k, m = params["k"], params["m"]
        return ((f.r_z <= -k) if side == "long" else (f.r_z >= k)) & (f.oi_z <= -m)
    if hyp == "P2":
        z0, z1 = params["z0"], params["z1"]
        return ((f.prem_z <= -z0) if side == "long" else (f.prem_z >= z0)) & (f.oi6_z >= z1)
    if hyp == "P3":
        N = params["N"]
        brk = (c > c.shift(1).rolling(N, min_periods=N).max()) if side == "long" else (c < c.shift(1).rolling(N, min_periods=N).min())
        return brk & (f.oi6 > 0) if params["filter"] else brk
    if hyp == "P4":
        N = params["N"]
        if side == "long":
            return (c < c.shift(1).rolling(N, min_periods=N).min()) & (f.obv > f.obv.shift(1).rolling(N, min_periods=N).min())
        return (c > c.shift(1).rolling(N, min_periods=N).max()) & (f.obv < f.obv.shift(1).rolling(N, min_periods=N).max())
    raise ValueError(hyp)


# ------------------------------------------------------------------ event engine with funding
def trades(df, sig, H, side, window, cost, fund: pd.Series, delay=0, sym=""):
    o, lo, hi, idx = df["open"].to_numpy(), df["low"].to_numpy(), df["high"].to_numpy(), df.index
    n = len(o)
    ft, fv = fund.index, fund.to_numpy()
    rows, free = [], 0
    for t in np.flatnonzero(sig.reindex(idx).fillna(False).to_numpy(bool)):
        if idx[t] < window[0] or idx[t] > window[1]:
            continue
        e = t + 1 + delay
        x = e + H
        if e < free or x >= n or idx[x] > window[1]:
            continue
        te, tx = idx[e], idx[x]
        fsum = float(fv[(ft > te) & (ft <= tx)].sum())
        ratio = o[x] / o[e]
        gross = ratio - 1 if side == "long" else 1 - ratio
        net = gross - 2 * cost - (fsum if side == "long" else -fsum)
        adverse = (lo[e:x].min() / o[e] - 1) if side == "long" else (1 - hi[e:x].max() / o[e])
        rows.append((sym, idx[t], te, tx, H, gross, net, adverse, fsum))
        free = x
    return pd.DataFrame(rows, columns=["sym", "signal_time", "entry_time", "exit_time", "bars", "gross", "net", "adverse", "funding"])


def eval_event(hyp, params, side, H, window, coins=U16, iv="4h", delay=0, cost_mult=1.0):
    check_lock(window[1])
    trs, unc, unc_adv = [], {}, {}
    for c in coins:
        df = load(c, iv)
        tr = trades(df, signal(hyp, params, side, df), H, side, window, perp_cost(c, cost_mult), funding(c, iv), delay, c)
        u, ua = ev.unconditional(df, H, side, window, delay)
        unc[c], unc_adv[c] = u, ua
        if len(tr):
            trs.append(tr)
    tr = pd.concat(trs, ignore_index=True) if trs else pd.DataFrame(columns=["sym", "entry_time", "gross", "net", "bars", "adverse"])
    s = ev.summarize(tr, unc, unc_adv) if len(tr) else {"n": 0}
    weeks = (min(window[1], load(coins[0], iv).index[-1]) - max(window[0], load(coins[0], iv).index[0])).days / 7
    s["per_week"] = s.get("n", 0) / weeks
    s["mean_funding"] = float(tr["funding"].mean()) if len(tr) else np.nan
    return s, tr


# ------------------------------------------------------------------ carry portfolio (P5)
def carry(theta: float, window, coins=U16, cost_mult=1.0, bias=0.0, iv="4h"):
    """Per 8h period returns on total capital. Each coin has 1/len(coins) of capital; an active slot holds spot-long /
    perp-short of notional = slot / 1.5. theta, bias in % per 8h."""
    check_lock(window[1])
    per, trades_n = {}, 0
    for c in coins:
        F = funding(c, iv) + bias / 100.0
        P = load(c, iv)["prem_open"] / 100.0
        m3 = F.rolling(9, min_periods=9).mean()
        on = False
        notional = 1.0 / len(coins) / 1.5
        leg = spot_cost(c, cost_mult) + perp_cost(c, cost_mult)
        prev_p = None
        for tau in F.index:
            if tau < window[0] or tau > window[1]:
                continue
            pnl = 0.0
            p_now = P.get(tau, np.nan)
            if on:
                pnl += F[tau] * notional  # held through this settlement
                if prev_p is not None and np.isfinite(p_now):
                    pnl -= (p_now - prev_p) * notional  # basis mark: short perp loses when premium rises
            sig = m3.get(tau, np.nan)
            if not on and np.isfinite(sig) and sig >= theta / 100.0 - 1e-10:  # funding often sits exactly at 0.01%
                on = True
                pnl -= leg * notional
                trades_n += 1
            elif on and np.isfinite(sig) and sig < theta / 200.0 - 1e-10:
                on = False
                pnl -= leg * notional
            if np.isfinite(p_now):
                prev_p = p_now
            per.setdefault(tau, 0.0)
            per[tau] += pnl
    r = pd.Series(per).sort_index()
    return r, trades_n


def carry_metrics(r: pd.Series, n_entries: int) -> dict:
    eq = (1 + r).cumprod()
    yrs = len(r) / 1095
    ann = float(eq.iloc[-1] ** (1 / yrs) - 1) if len(r) else np.nan
    sd = r.std(ddof=1)
    return {"cagr": ann, "vol": float(sd * np.sqrt(1095)), "sharpe": float(r.mean() / sd * np.sqrt(1095)) if sd > 0 else np.nan,
            "maxdd": float((eq / eq.cummax() - 1).min()), "n": n_entries, "per_week": n_entries / (len(r) / 21)}


# ------------------------------------------------------------------ ledger
FIELDS = ["trial_id", "timestamp", "phase", "hypothesis", "family", "cell", "params", "window_start", "window_end",
          "delay", "cost_mult", "n", "per_week", "mean_gross", "mean_net", "median_net", "win_rate", "profit_factor",
          "t_clust", "excess", "breadth", "breadth_syms", "mean_funding", "cagr", "vol", "sharpe", "maxdd", "note"]


def ledger(row: dict):
    new = not LEDGER.exists()
    tid = 1 if new else sum(1 for _ in LEDGER.open())
    with LEDGER.open("a", newline="") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({**{k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()},
                    "trial_id": tid, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")})


GRIDS = {
    "P1": ([{"k": k, "m": m} for k in (2, 3) for m in (1.5, 2.5)], [1, 3, 6, 12], ({"k": 2, "m": 1.5}, 3)),
    "P2": ([{"z0": a, "z1": b} for a in (1.5, 2.5) for b in (1, 2)], [3, 6, 12, 24], ({"z0": 1.5, "z1": 1}, 6)),
    "P3": ([{"N": N, "filter": f} for N in (20, 60) for f in (True, False)], [3, 6, 12, 24], ({"N": 20, "filter": True}, 6)),
    "P4": ([{"N": N} for N in (20, 60)], [3, 6, 12, 24], ({"N": 20}, 6)),
}


def judge(cells, ref_H, sd, sc):
    s = cells[ref_H]
    ok = lambda x: x.get("n", 0) > 0 and x["mean_net"] > 0  # noqa: E731
    fl = {
        "E1": ok(s) and (s.get("t_clust") or 0) >= 2.0,
        "E2": sum(ok(cells[h]) for h in cells) >= 3,
        "E3": s.get("n", 0) > 0 and s["excess"] > 0,
        "E4": s.get("breadth_syms", 0) < 3 or (s.get("breadth") or 0) >= 0.6,
        "E5": ok(sd) and sd["mean_net"] >= 0.5 * s["mean_net"],
        "E6": ok(sc),
        "E7": s.get("n", 0) >= 30,
        "E8": s.get("per_week", 0) >= 3.0,
    }
    fl["PASS"] = all(fl.values())
    return fl


def run_design():
    w = DESIGN
    rows = []
    for hyp, (plist, Hs, (ref_p, ref_H)) in GRIDS.items():
        for p in plist:
            for side in ("long", "short"):
                fam = f"{hyp}|{json.dumps(p, sort_keys=True)}|{side}"
                cells = {}
                for H in Hs:
                    s, _ = eval_event(hyp, p, side, H, w)
                    cells[H] = s
                    ledger({"phase": "design", "hypothesis": hyp, "family": fam, "cell": f"H={H}", "params": json.dumps(p),
                            "window_start": str(w[0].date()), "window_end": str(w[1].date()), "delay": 0, "cost_mult": 1.0, **s})
                sd, _ = eval_event(hyp, p, side, ref_H, w, delay=1)
                ledger({"phase": "design-delay", "hypothesis": hyp, "family": fam, "cell": f"H={ref_H}", "params": json.dumps(p),
                        "window_start": str(w[0].date()), "window_end": str(w[1].date()), "delay": 1, "cost_mult": 1.0, **sd})
                sc, _ = eval_event(hyp, p, side, ref_H, w, cost_mult=2.0)
                ledger({"phase": "design-cost2x", "hypothesis": hyp, "family": fam, "cell": f"H={ref_H}", "params": json.dumps(p),
                        "window_start": str(w[0].date()), "window_end": str(w[1].date()), "delay": 0, "cost_mult": 2.0, **sc})
                v = judge(cells, ref_H, sd, sc)
                r = cells[ref_H]
                rows.append({"family": fam, "hyp": hyp, "side": side, "is_ref_params": p == ref_p, "ref_H": ref_H,
                             "n": r.get("n", 0), "per_week": r.get("per_week", 0), "gross_bp": 1e4 * r.get("mean_gross", np.nan),
                             "net_bp": 1e4 * r.get("mean_net", np.nan), "t": r.get("t_clust", np.nan),
                             "excess_bp": 1e4 * r.get("excess", np.nan), "win": r.get("win_rate", np.nan),
                             "breadth": r.get("breadth", np.nan), "delay_net_bp": 1e4 * sd.get("mean_net", np.nan),
                             "cost2_net_bp": 1e4 * sc.get("mean_net", np.nan),
                             **{f"net_bp_H{h}": 1e4 * cells[h].get("mean_net", np.nan) for h in Hs}, **v})
    evt = pd.DataFrame(rows)
    crow = []
    for th in (0.01, 0.02, 0.03):
        r, n = carry(th, w)
        m = carry_metrics(r, n)
        ledger({"phase": "design", "hypothesis": "P5", "family": "P5", "cell": f"theta={th}", "params": json.dumps({"theta": th}),
                "window_start": str(w[0].date()), "window_end": str(w[1].date()), "delay": 0, "cost_mult": 1.0, **m})
        rb, _ = carry(th, w, bias=-0.003)
        mb = carry_metrics(rb, n)
        ledger({"phase": "design-bias", "hypothesis": "P5", "family": "P5", "cell": f"theta={th}", "params": json.dumps({"theta": th, "bias": -0.003}),
                "window_start": str(w[0].date()), "window_end": str(w[1].date()), "delay": 0, "cost_mult": 1.0, **mb})
        rc, _ = carry(th, w, cost_mult=2.0)
        mc = carry_metrics(rc, n)
        ledger({"phase": "design-cost2x", "hypothesis": "P5", "family": "P5", "cell": f"theta={th}", "params": json.dumps({"theta": th}),
                "window_start": str(w[0].date()), "window_end": str(w[1].date()), "delay": 0, "cost_mult": 2.0, **mc})
        passed = m["cagr"] >= 0.03 and m["sharpe"] >= 2 and m["maxdd"] >= -0.03 and mb["cagr"] >= 0
        crow.append({"theta": th, **{k: m[k] for k in ("cagr", "vol", "sharpe", "maxdd", "n", "per_week")},
                     "bias_cagr": mb["cagr"], "cost2_cagr": mc["cagr"], "cost2_sharpe": mc["sharpe"], "PASS": passed,
                     "is_ref": th == 0.01})
    car = pd.DataFrame(crow)
    OUT.mkdir(parents=True, exist_ok=True)
    evt.to_csv(OUT / "design_events.csv", index=False)
    car.to_csv(OUT / "design_carry.csv", index=False)
    return evt, car


INFO_ONLY = [("P1", {"k": 2, "m": 1.5}, "long", 3), ("P3", {"N": 60, "filter": True}, "long", 6)]


def run_holdout_info():
    """Declared at the Phase 2 freeze: nothing passed the design stage, so no family is eligible. These near-misses
    and the best carry cell are run once on the holdout for information only; no result can make them deployable."""
    once = OUT / "HOLDOUT_RAN_ONCE"
    if not UNLOCK.exists() or once.exists():
        sys.exit("locked or already ran")
    rows = []
    for hyp, p, side, H in INFO_ONLY:
        fam = f"{hyp}|{json.dumps(p, sort_keys=True)}|{side}"
        for label, coins, iv in (("4h U16", U16, "4h"), ("1h C9", C9, "1h")):
            Hh = H if iv == "4h" else H * 4  # same clock time on 1h bars
            s_, _ = eval_event(hyp, p, side, Hh, HOLDOUT, coins=coins, iv=iv)
            ledger({"phase": "holdout-info", "hypothesis": hyp, "family": fam, "cell": f"H={Hh} {label}", "params": json.dumps(p),
                    "window_start": str(HOLDOUT[0].date()), "window_end": str(HOLDOUT[1].date()), "delay": 0, "cost_mult": 1.0,
                    **s_, "note": "information only; failed design"})
            rows.append({"family": fam, "set": label, "H": Hh, **{k: s_.get(k) for k in ("n", "per_week", "mean_gross", "mean_net",
                         "t_clust", "excess", "win_rate", "breadth")}})
    r, n = carry(0.02, HOLDOUT)
    m = carry_metrics(r, n)
    ledger({"phase": "holdout-info", "hypothesis": "P5", "family": "P5", "cell": "theta=0.02", "params": json.dumps({"theta": 0.02}),
            "window_start": str(HOLDOUT[0].date()), "window_end": str(HOLDOUT[1].date()), "delay": 0, "cost_mult": 1.0, **m,
            "note": "information only; failed design"})
    rows.append({"family": "P5 carry theta=0.02", "set": "4h U16", **m})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "holdout_info.csv", index=False)
    once.write_text("ran once\n")
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    if sys.argv[1:] == ["design"]:
        evt, car = run_design()
        print(evt[["family", "n", "per_week", "gross_bp", "net_bp", "t", "excess_bp", "breadth", "delay_net_bp",
                   "cost2_net_bp", "PASS"]].round(2).to_string())
        print(car.round(4).to_string())
    if sys.argv[1:] == ["holdout"]:
        print(run_holdout_info().round(4).to_string())
