"""Design-window evaluation of every pre-registered cell (crypto/PREREG.md), with ledger and pass/fail verdicts.

Usage: python crypto/src/research.py design
Writes crypto/TRIAL_LEDGER.csv (appends) and crypto/reports/design/*.csv.
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

import cdata
import events
import indicators as ind
import portfolio as pf

ROOT = cdata.ROOT
LEDGER = ROOT / "TRIAL_LEDGER.csv"
OUT = ROOT / "reports"
FIELDS = ["trial_id", "timestamp", "phase", "hypothesis", "family", "cell", "params", "group", "window_start",
          "window_end", "delay", "cost_mult", "n", "mean_gross", "mean_net", "median_net", "win_rate",
          "profit_factor", "t_clust", "excess", "breadth", "breadth_syms", "avg_bars", "adverse", "adverse_uncond",
          "cagr", "vol", "sharpe", "sortino", "maxdd", "mar", "exposure", "turnover_ann", "trades_per_year", "note"]


def _next_id() -> int:
    if not LEDGER.exists():
        return 1
    with LEDGER.open() as f:
        return sum(1 for _ in f)  # header counts as row 0


def ledger(row: dict) -> dict:
    new = not LEDGER.exists()
    row = {**row, "trial_id": _next_id(), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with LEDGER.open("a", newline="") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()})
    return row


# ------------------------------------------------------------------ data + signal caches
@lru_cache(maxsize=None)
def data(sym: str, interval: str) -> pd.DataFrame:
    return cdata.load(sym, interval)


@lru_cache(maxsize=None)
def zser(sym: str, interval: str) -> pd.Series:
    return ind.zscore(data(sym, interval)["close"], 20)


@lru_cache(maxsize=None)
def signal(hyp: str, variant: str, side: str, sym: str, interval: str) -> pd.Series:
    df = data(sym, interval)
    if hyp == "H1":
        mode, zt = {"V1": ("client", 2.5), "V2": ("client", 2.0), "V3": ("td", 2.5), "V4": ("z", 2.5),
                    "V5": ("countdown", 2.5), "V6": ("export", 2.5)}[variant]
        b, s = ind.tdz_signals(df, z_thresh=zt, mode=mode)
        return b if side == "long" else s
    if hyp == "H2":
        return ind.sigmajanus_rerisk(df["close"], float(variant.split("=")[1]))
    if hyp == "H3":
        k, clvf = variant.split("|")
        return ind.capitulation(df, k=float(k.split("=")[1]), vol_mult=2.0, clv_filter=clvf == "clv=on")
    raise ValueError(hyp)


def eval_event(hyp, variant, side, grp, H, window, delay=0, cost_mult=1.0, fee_bp=None):
    interval, syms = cdata.group(grp)
    cdata.check_lock(window[1], interval)
    trs, unc, unc_adv = [], {}, {}
    for sym in syms:
        df = data(sym, interval)
        c = cdata.cost_per_side(sym, side, fee_bp) * cost_mult
        fb = cdata.funding_per_bar(sym, side, interval)
        tr = events.trades(df, signal(hyp, variant, side, sym, interval), H, side, window, c, fb, delay,
                           z=zser(sym, interval), sym=sym)
        h_u = H if H != "zexit" else (int(round(tr.bars.mean())) if len(tr) else 8)
        unc[sym], unc_adv[sym] = events.unconditional(df, h_u, side, window, delay)
        trs.append(tr)
    tr = pd.concat(trs, ignore_index=True)
    return events.summarize(tr, unc, unc_adv), tr


def event_row(phase, hyp, family, cell, params, grp, window, delay, cost_mult, s, note=""):
    return ledger({"phase": phase, "hypothesis": hyp, "family": family, "cell": cell, "params": json.dumps(params),
                   "group": grp, "window_start": str(window[0].date()), "window_end": str(window[1].date()),
                   "delay": delay, "cost_mult": cost_mult, **s, "note": note})


def event_families():
    fams = []
    for v in ["V1", "V2", "V3", "V4", "V5", "V6"]:
        for side in ["long", "short"]:
            for g in ["G30", "G4h"]:
                fams.append(("H1", v, side, g, [4, 8, 16, 32, "zexit"], 8))
    for os_ in ["os=15", "os=20"]:
        for g in ["G30", "G4h", "GD"]:
            fams.append(("H2", os_, "long", g, [4, 8, 16, 32], 8))
    for k in ["k=2.5", "k=3.0"]:
        for clvf in ["clv=off", "clv=on"]:
            for g in ["G30", "G4h", "GD"]:
                fams.append(("H3", f"{k}|{clvf}", "long", g, [3, 6, 12, 24], 6))
    return fams


def judge_event(cells: dict, ref, s_delay, s_cost2, grp) -> dict:
    s = cells[ref]
    fixed = [h for h in cells if h != "zexit"]
    e1 = s.get("n", 0) > 0 and s["mean_net"] > 0 and (s["t_clust"] or 0) >= 2.0
    e1_mean = s.get("n", 0) > 0 and s["mean_net"] > 0
    e2 = sum(1 for h in fixed if cells[h].get("n", 0) > 0 and cells[h]["mean_net"] > 0) >= 3
    e3 = s.get("n", 0) > 0 and s["excess"] > 0
    if grp == "G30":
        e4 = s.get("breadth_syms", 0) == 2 and s["breadth"] == 1.0
    else:
        e4 = s.get("breadth_syms", 0) < 3 or (s["breadth"] >= 0.6)
    e5 = s_delay.get("n", 0) > 0 and s_delay["mean_net"] > 0 and s_delay["mean_net"] >= 0.5 * s["mean_net"]
    e6 = s_cost2.get("n", 0) > 0 and s_cost2["mean_net"] > 0
    e7 = s.get("n", 0) >= 30
    flags = dict(E1=e1, E2=e2, E3=e3, E4=e4, E5=e5, E6=e6, E7=e7)
    passed = all(flags.values())
    promising = (not passed) and e1_mean and all(v for k, v in flags.items() if k != "E1")
    return {**flags, "PASS": passed, "promising": promising}


def run_event_design():
    rows = []
    for hyp, var, side, grp, Hs, ref in event_families():
        interval, _ = cdata.group(grp)
        w = cdata.design_window(interval)
        fam = f"{hyp}|{var}|{side}|{grp}"
        cells = {}
        for H in Hs:
            s, _ = eval_event(hyp, var, side, grp, H, w)
            cells[H] = s
            event_row("design", hyp, fam, f"H={H}", {"variant": var, "side": side, "H": H}, grp, w, 0, 1.0, s)
        sd, _ = eval_event(hyp, var, side, grp, ref, w, delay=1)
        event_row("design-delay", hyp, fam, f"H={ref}", {"variant": var, "side": side, "H": ref}, grp, w, 1, 1.0, sd)
        sc, _ = eval_event(hyp, var, side, grp, ref, w, cost_mult=2.0)
        event_row("design-cost2x", hyp, fam, f"H={ref}", {"variant": var, "side": side, "H": ref}, grp, w, 0, 2.0, sc)
        v = judge_event(cells, ref, sd, sc, grp)
        r = cells[ref]
        rows.append({"family": fam, "hyp": hyp, "variant": var, "side": side, "group": grp, "ref_H": ref,
                     "n": r.get("n", 0), "mean_net_bp": 1e4 * r.get("mean_net", np.nan),
                     "t": r.get("t_clust", np.nan), "excess_bp": 1e4 * r.get("excess", np.nan),
                     "win": r.get("win_rate", np.nan), "breadth": r.get("breadth", np.nan),
                     "delay_net_bp": 1e4 * sd.get("mean_net", np.nan), "cost2_net_bp": 1e4 * sc.get("mean_net", np.nan),
                     **{f"net_bp_H{h}": 1e4 * cells[h].get("mean_net", np.nan) for h in Hs},
                     "adverse_bp": 1e4 * r.get("adverse", np.nan), "adverse_uncond_bp": 1e4 * r.get("adverse_uncond", np.nan),
                     **v})
    out = pd.DataFrame(rows)
    (OUT / "design").mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / "design" / "event_families.csv", index=False)
    return out


# ------------------------------------------------------------------ daily portfolio
@lru_cache(maxsize=None)
def panel():
    syms = cdata.DAILY_UNIVERSE
    dfs = {c: data(c + "USDT", "1D") for c in syms}
    idx = sorted(set().union(*[d.index for d in dfs.values()]))
    idx = pd.DatetimeIndex(idx)
    O = pd.DataFrame({c: dfs[c]["open"] for c in syms}).reindex(idx)
    C = pd.DataFrame({c: dfs[c]["close"] for c in syms}).reindex(idx)
    first = {c: dfs[c].index[0] for c in syms}
    E = pd.DataFrame({c: idx >= first[c] + pd.Timedelta(days=200) for c in syms}, index=idx)
    E &= C.notna()
    cost = pd.Series({c: cdata.cost_per_side(c + "USDT") for c in syms})
    return O, C, E, cost


def month_start(idx):
    return pd.Series(idx.day == 1, index=idx)


def weights(rule: str, params: dict, C: pd.DataFrame, E: pd.DataFrame):
    idx = C.index
    nel = E.sum(axis=1).replace(0, np.nan)
    elig_change = (E != E.shift(1)).any(axis=1)
    if rule == "BM1":
        W = E.astype(float).div(nel, axis=0).fillna(0.0)
        return W, month_start(idx) | elig_change
    if rule == "BM2":
        W = pd.DataFrame(0.0, idx, C.columns)
        W["BTC"] = E["BTC"].astype(float)
        return W, elig_change
    if rule == "BM3":
        W = pd.DataFrame(0.0, idx, C.columns)
        W["BTC"] = (ind.sma_trend(C["BTC"], 100).fillna(0) * E["BTC"]).astype(float)
        return W, elig_change & False
    if rule in ("SMA", "DON"):
        N = params["N"]
        on = pd.DataFrame({c: (ind.sma_trend(C[c].dropna(), N) if rule == "SMA" else ind.donchian_trend(C[c].dropna(), N))
                           for c in C.columns}).reindex(idx).fillna(0.0)
        if params.get("btc_gate"):
            g = ind.sma_trend(C["BTC"], 100).fillna(0.0)
            for c in C.columns:
                if c != "BTC":
                    on[c] = on[c] * g
        W = (on * E).div(nel, axis=0).fillna(0.0)
        return W, month_start(idx) | elig_change
    if rule == "XSM":
        L, k, gate = params["L"], params["k"], params["gate"]
        mom = C / C.shift(L) - 1
        sun = pd.Series(idx.dayofweek == 6, index=idx)
        W = pd.DataFrame(np.nan, idx, C.columns)
        for d in idx[sun.to_numpy()]:
            m = mom.loc[d][E.loc[d]].dropna().sort_values(ascending=False)
            top = m.head(k)
            row = pd.Series(0.0, C.columns)
            for c, v in top.items():
                row[c] = 0.0 if (gate and v < 0) else 1.0 / k
            W.loc[d] = row
        W = W.ffill().fillna(0.0)
        return W, sun
    raise ValueError(rule)


def run_portfolio(rule, params, window, delay=0, cost_mult=1.0, fee_bp=None):
    cdata.check_lock(window[1], "1D")
    O, C, E, cost = panel()
    if fee_bp is not None:
        cost = pd.Series({c: (fee_bp + cdata.slippage_bp(c + "USDT")) / 1e4 for c in C.columns})
    keep = C.index <= window[1]
    O, C, E = O[keep], C[keep], E[keep]
    W, R = weights(rule, params, C, E)
    res = pf.simulate(W, R, O, C, cost, delay=delay, cost_mult=cost_mult)
    ret = res["equity"].pct_change()
    ret = ret[(ret.index >= window[0]) & (ret.index <= window[1])]
    return pf.metrics(ret, res["exposure"], res["turnover"], res["trades"]), ret, res


def port_row(phase, hyp, family, cell, params, window, delay, cost_mult, m, note=""):
    return ledger({"phase": phase, "hypothesis": hyp, "family": family, "cell": cell, "params": json.dumps(params),
                   "group": "GD-port", "window_start": str(window[0].date()), "window_end": str(window[1].date()),
                   "delay": delay, "cost_mult": cost_mult, **m, "note": note})


def portfolio_cells():
    cells = []
    for rule, Ns in (("SMA", [20, 50, 100, 200]), ("DON", [20, 50, 100])):
        for gate in (False, True):
            for N in Ns:
                cells.append(("H4", rule, {"N": N, "btc_gate": gate}))
    for gate in (False, True):
        for k in (3, 5):
            for L in (14, 28, 56):
                cells.append(("H5", "XSM", {"L": L, "k": k, "gate": gate}))
    return cells


def cell_name(rule, p):
    if rule == "XSM":
        return f"XSM L={p['L']} k={p['k']} gate={'on' if p['gate'] else 'off'}"
    return f"{rule}{p['N']} btcgate={'on' if p['btc_gate'] else 'off'}"


def neighbours(rule, p, all_cells):
    if rule == "XSM":
        Ls = [14, 28, 56]
        i = Ls.index(p["L"])
        return [(rule, {**p, "L": Ls[j]}) for j in (i - 1, i + 1) if 0 <= j < len(Ls)]
    Ns = [20, 50, 100, 200] if rule == "SMA" else [20, 50, 100]
    i = Ns.index(p["N"])
    return [(rule, {**p, "N": Ns[j]}) for j in (i - 1, i + 1) if 0 <= j < len(Ns)]


SUBPERIODS = [("2018-01-01", "2018-12-31"), ("2019-01-01", "2020-12-31"), ("2021-01-01", "2021-12-31"),
              ("2022-01-01", "2023-12-31")]


def run_portfolio_design():
    w = cdata.DAILY_DESIGN
    bm = {}
    for b in ("BM1", "BM2", "BM3"):
        m, r, _ = run_portfolio(b, {}, w)
        port_row("design", "BM", b, b, {}, w, 0, 1.0, m)
        bm[b] = (m, r)
    m1, r1 = bm["BM1"]
    res = {}
    for hyp, rule, p in portfolio_cells():
        m, r, _ = run_portfolio(rule, p, w)
        port_row("design", hyp, hyp, cell_name(rule, p), p, w, 0, 1.0, m)
        res[(rule, json.dumps(p, sort_keys=True))] = (hyp, m, r)

    def p1(m):
        return m["sharpe"] >= m1["sharpe"] + 0.20 and m["maxdd"] >= 0.75 * m1["maxdd"]

    rows, verdict = [], {}
    for hyp in ("H4", "H5"):
        fam = {k: v for k, v in res.items() if v[0] == hyp}
        sh = [v[1]["sharpe"] for v in fam.values()]
        P2 = np.median(sh) >= m1["sharpe"] + 0.10 and np.mean([s > m1["sharpe"] for s in sh]) >= 2 / 3
        elig = []
        for (rule, pj), (_, m, r) in fam.items():
            p = json.loads(pj)
            nb_ok = all(p1(res[(nr, json.dumps(np_, sort_keys=True))][1]) for nr, np_ in neighbours(rule, p, fam))
            if p1(m) and nb_ok:
                elig.append((m["sharpe"], rule, p))
        sel = max(elig, key=lambda x: x[0]) if elig else None
        v = {"hyp": hyp, "median_sharpe": float(np.median(sh)), "bm1_sharpe": m1["sharpe"], "bm1_maxdd": m1["maxdd"],
             "P2": bool(P2), "n_cells_P1": int(sum(p1(v_[1]) for v_ in fam.values())), "n_cells": len(fam)}
        if sel:
            _, rule, p = sel
            m, r = res[(rule, json.dumps(p, sort_keys=True))][1:]
            md, _, _ = run_portfolio(rule, p, w, delay=1)
            port_row("design-delay", hyp, hyp, cell_name(rule, p), p, w, 1, 1.0, md)
            mc, _, _ = run_portfolio(rule, p, w, cost_mult=2.0)
            port_row("design-cost2x", hyp, hyp, cell_name(rule, p), p, w, 0, 2.0, mc)
            P3 = (md["sharpe"] - m1["sharpe"]) >= 0.7 * (m["sharpe"] - m1["sharpe"])
            sub = {}
            for a, b in SUBPERIODS:
                sub[f"{a[:4]}-{b[:4]}"] = (pf.sharpe_excluding(r, a, b), pf.sharpe_excluding(r1, a, b))
            P4 = all(s >= s1 for s, s1 in sub.values())
            P5 = p1(mc)
            v.update({"selected": cell_name(rule, p), "sel_sharpe": m["sharpe"], "sel_maxdd": m["maxdd"],
                      "sel_cagr": m["cagr"], "P1": True, "P3": bool(P3), "delay_sharpe": md["sharpe"],
                      "P4": bool(P4), "sub": {k: [round(a, 3), round(b, 3)] for k, (a, b) in sub.items()},
                      "P5": bool(P5), "cost2_sharpe": mc["sharpe"], "cost2_maxdd": mc["maxdd"]})
            v["PASS"] = bool(P2 and P3 and P4 and P5)
        else:
            v.update({"selected": None, "P1": False, "PASS": False})
        verdict[hyp] = v
    table = []
    for (rule, pj), (hyp, m, _) in res.items():
        table.append({"hyp": hyp, "cell": cell_name(rule, json.loads(pj)), **{k: m[k] for k in
                      ("cagr", "vol", "sharpe", "sortino", "maxdd", "mar", "exposure", "turnover_ann", "trades_per_year")},
                      "P1": p1(m)})
    for b, (m, _) in bm.items():
        table.append({"hyp": "BM", "cell": b, **{k: m.get(k) for k in
                      ("cagr", "vol", "sharpe", "sortino", "maxdd", "mar", "exposure", "turnover_ann", "trades_per_year")}})
    (OUT / "design").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(table).to_csv(OUT / "design" / "portfolio_cells.csv", index=False)
    (OUT / "design" / "portfolio_verdict.json").write_text(json.dumps(verdict, indent=2, default=float))
    return pd.DataFrame(table), verdict


if __name__ == "__main__":
    if sys.argv[1:] == ["design"]:
        ev = run_event_design()
        pt, verdict = run_portfolio_design()
        pd.set_option("display.width", 250)
        print(ev[["family", "n", "mean_net_bp", "t", "excess_bp", "breadth", "delay_net_bp", "cost2_net_bp",
                  "E1", "E2", "E3", "E4", "E5", "E6", "E7", "PASS", "promising"]].to_string())
        print(pt.to_string())
        print(json.dumps(verdict, indent=2, default=float))
