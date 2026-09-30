"""
MODELED option screens on DEV (see scalpel/options.py for every assumption).
Weekly structures on W levels (sold Monday 10:00 ET, held to Friday expiry or closed when
the underlying closes through a short strike), legging on first touches, and same-day
(0DTE) structures on D levels on SPX expiry days. Baselines: the same structure with
strikes at the DEV-median model delta of the level strikes, and at 16-delta short /
10-delta long. All rows go to results/log.csv with modeled=True.
Usage: python scripts/screen_options.py
"""
import sys, json, itertools
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from scalpel.data import load_bars
from scalpel.features import build_frame
from scalpel.strategies import level_array
from scalpel import options as op
from scalpel.stats import summarize
from scalpel import screen

fr = build_frame(load_bars("dev"))
B = fr.bars
N = len(B)
adj = op.roll_adjusted_close(B)
vix9 = op.vix9d_prior(B)
hours = B.index.hour.values
times = B.index


def expiry_days():
    d = pd.DatetimeIndex(B["tday"].unique())
    dow = d.dayofweek
    ok = (dow == 4) | ((dow == 2) & (d >= "2016-02-24")) | ((dow == 0) & (d >= "2016-08-22"))
    return set(d[ok])


def leg_value(F, K, T, atm, cp, flat):
    p, dlt = op.price(F, np.array([K], float), T, atm, cp, flat)
    return float(p[0]), float(dlt[0])


def open_spread(F, Ks, Kl, T, atm, cp, flat):
    """Sell Ks, buy Kl. Returns net credit after costs, short-leg delta, long-leg delta."""
    ms, ds = leg_value(F, Ks, T, atm, cp, flat)
    ml, dl = leg_value(F, Kl, T, atm, cp, flat)
    credit = (ms - op.spread_cost(ms)) - (ml + op.spread_cost(ml)) - 2 * op.COMM_PTS
    return credit, ds, dl


def close_spread(F, Ks, Kl, T, atm, cp, flat):
    """Buy back Ks, sell Kl: cost to close (positive number)."""
    ms, _ = leg_value(F, Ks, T, atm, cp, flat)
    ml, _ = leg_value(F, Kl, T, atm, cp, flat)
    return (ms + op.spread_cost(ms)) - (ml - op.spread_cost(ml)) + 2 * op.COMM_PTS


def payoff(S, Ks, Kl, cp):
    if cp < 0:
        return -max(Ks - S, 0.0) + max(Kl - S, 0.0)
    return -max(S - Ks, 0.0) + max(S - Kl, 0.0)


def sim_spread(i_ent, i_exp, Ks, Kl, cp, flat, manage):
    """P&L (points per 1 spread) of a credit spread from bar i_ent open to expiry bar close."""
    F0 = fr.o[i_ent]
    exp_t = times[i_exp].normalize() + pd.Timedelta(hours=16)
    T0 = max((exp_t - times[i_ent]).total_seconds() / 3600.0, 0.5) / op.YEAR_H
    atm0 = op.ATM_RATIO * vix9[i_ent] / 100.0
    credit, ds, dl = open_spread(F0, Ks, Kl, T0, atm0, cp, flat)
    base_adj = adj[i_ent]
    if manage == "touch":
        for j in range(i_ent, i_exp):
            cj = fr.c[j] - (adj[j] - base_adj)
            if (cp < 0 and cj <= Ks) or (cp > 0 and cj >= Ks):
                k = j + 1
                Fk = fr.o[k] - (adj[k] - base_adj)
                Tk = max((exp_t - times[k]).total_seconds() / 3600.0, 0.5) / op.YEAR_H
                atmk = op.ATM_RATIO * vix9[k] / 100.0
                return credit - close_spread(Fk, Ks, Kl, Tk, atmk, cp, flat), credit, ds, dl
    S = fr.c[i_exp] - (adj[i_exp] - base_adj)
    return credit + payoff(S, Ks, Kl, cp), credit, ds, dl


def dm_strikes(F, T, atm, cp, d_s, d_l, flat):
    Ks = op.strike_for_delta(F, T, atm, cp, d_s, flat)
    Kl = op.strike_for_delta(F, T, atm, cp, d_l, flat)
    if cp < 0 and Kl >= Ks:
        Kl = Ks - 5
    if cp > 0 and Kl <= Ks:
        Kl = Ks + 5
    return float(Ks), float(Kl)


def entries_weekly(mode, roll):
    out = []
    for wid, g in B.groupby("week_id"):
        pos = np.flatnonzero(B["week_id"].values == wid)
        i10 = [p for p in pos if hours[p] == 10]
        if not i10:
            continue
        ie, ix = i10[0], pos[-1]
        if fr.no_signal["W"][ie] or np.isnan(vix9[ie]) or np.isnan(fr.sigma[("W", mode)][ie]):
            continue
        if roll == "excl" and B["roll_week"].values[ie]:
            continue
        if B.index[ix].hour != 14:
            continue
        out.append((ie, ix))
    return out


def entries_daily(mode):
    exp = expiry_days()
    out = []
    for did, pos in B.groupby("day_id").indices.items():
        td = B["tday"].values[pos[0]]
        if pd.Timestamp(td) not in exp:
            continue
        i10 = [p for p in pos if hours[p] == 10]
        if not i10 or hours[pos[-1]] != 14:
            continue
        ie, ix = i10[0], pos[-1]
        if fr.no_signal["D"][ie] or np.isnan(vix9[ie]) or np.isnan(fr.sigma[("D", mode)][ie]):
            continue
        out.append((ie, ix))
    return out


def structure_trades(tf, mode, legs_def, entries, flat, manage):
    """legs_def: list of (cp, short_level, long_level). Returns per-trade dicts."""
    L = {nm: level_array(fr, tf, mode, nm) for nm in {x for _, a, b in legs_def for x in (a, b)}}
    rows = []
    for ie, ix in entries:
        F0 = fr.o[ie]
        pnl = 0.0; risk_w = 0.0; cred = 0.0; dsl = []; ok = True; ks = []
        for cp, a, b in legs_def:
            Ks, Kl = float(op.round5(L[a][ie])), float(op.round5(L[b][ie]))
            if (cp < 0 and not (Kl < Ks < F0)) or (cp > 0 and not (Kl > Ks > F0)):
                ok = False; break
            ks.append((cp, Ks, Kl))
        if not ok:
            continue
        for cp, Ks, Kl in ks:
            p, c_, ds, dl = sim_spread(ie, ix, Ks, Kl, cp, flat, manage)
            pnl += p; cred += c_; risk_w = max(risk_w, abs(Kl - Ks)); dsl.append((ds, dl))
        rows.append(dict(ie=ie, ix=ix, pnl=pnl, credit=cred, risk=risk_w - cred, deltas=dsl))
    return rows


def dm_trades(entries, legs_cp, deltas, flat, manage):
    rows = []
    for ie, ix in entries:
        F0 = fr.o[ie]
        exp_t = times[ix].normalize() + pd.Timedelta(hours=16)
        T0 = max((exp_t - times[ie]).total_seconds() / 3600.0, 0.5) / op.YEAR_H
        atm0 = op.ATM_RATIO * vix9[ie] / 100.0
        pnl = 0.0; risk_w = 0.0; cred = 0.0
        for cp, (d_s, d_l) in zip(legs_cp, deltas):
            Ks, Kl = dm_strikes(F0, T0, atm0, cp, d_s, d_l, flat)
            p, c_, _, _ = sim_spread(ie, ix, Ks, Kl, cp, flat, manage)
            pnl += p; cred += c_; risk_w = max(risk_w, abs(Kl - Ks))
        rows.append(dict(ie=ie, ix=ix, pnl=pnl, credit=cred, risk=risk_w - cred))
    return rows


def to_frame(rows):
    t = pd.DataFrame(rows)
    if t.empty:
        return pd.DataFrame(columns=["net", "R", "tday", "year", "bars_held"])
    t["net"] = t["pnl"]; t["R"] = t["pnl"] / t["risk"]
    t["tday"] = B["tday"].values[t["ie"].values]
    t["year"] = pd.DatetimeIndex(t["tday"]).year
    t["bars_held"] = t["ix"] - t["ie"] + 1
    return t


def legging_trades(mode, roll, trig_lv, legs_map, flat, deltas=None):
    """First touch of trig level (per side) -> sell that side's spread at next bar open."""
    rows = []
    Lt = {s: level_array(fr, "W", mode, trig_lv[s]) for s in trig_lv}
    Ls = {nm: level_array(fr, "W", mode, nm) for s in legs_map for nm in legs_map[s]}
    for wid, pos in B.groupby("week_id").indices.items():
        ix = pos[-1]
        if hours[ix] != 14:
            continue
        if roll == "excl" and B["roll_week"].values[pos[0]]:
            continue
        for side, cp in (("put", -1), ("call", 1)):
            for p in pos[:-1]:
                if fr.no_signal["W"][p]:
                    continue
                touched = fr.l[p] <= Lt[side][p] if cp < 0 else fr.h[p] >= Lt[side][p]
                if touched:
                    ie = p + 1
                    if np.isnan(vix9[ie]):
                        break
                    F0 = fr.o[ie]
                    if deltas is None:
                        a, b = legs_map[side]
                        Ks, Kl = float(op.round5(Ls[a][p])), float(op.round5(Ls[b][p]))
                    else:
                        exp_t = times[ix].normalize() + pd.Timedelta(hours=16)
                        T0 = max((exp_t - times[ie]).total_seconds() / 3600.0, 0.5) / op.YEAR_H
                        Ks, Kl = dm_strikes(F0, T0, op.ATM_RATIO * vix9[ie] / 100.0, cp, *deltas[side], flat)
                    if (cp < 0 and not (Kl < Ks < F0)) or (cp > 0 and not (Kl > Ks > F0)):
                        break
                    pnl, cred, ds, dl = sim_spread(ie, ix, Ks, Kl, cp, flat, "hold")
                    rows.append(dict(ie=ie, ix=ix, pnl=pnl, credit=cred, risk=abs(Kl - Ks) - cred,
                                     deltas=[(ds, dl)], side=side))
                    break
    return rows


def row_for(name, tf, mode, roll, flat, manage, desc, t, extra):
    s = summarize(t) if len(t) else summarize(pd.DataFrame(columns=["net", "R", "tday", "year", "bars_held"]))
    r = {"spec": json.dumps(dict(family=name, tf=tf, mode=mode, roll=roll, skew="flat" if flat else "skew",
                                 manage=manage, structure=desc)),
         "key": "", "stage": "OPT", "family": name, "tf": tf, "mode": mode, "roll": roll, "side": "short_premium",
         "level": desc, "trig": "week_open" if tf == "W" else "expiry_day_10:00", "stop": manage,
         "target": "expiry", "filters": json.dumps({"skew": "flat" if flat else "skew"}), "modeled": True}
    r.update(s); r.update(extra)
    return r


def main():
    rows_out = []
    W_STRUCT = {
        "put_TL1_TL2": [(-1, "TL1", "TL2")], "put_TL2_RBBOT": [(-1, "TL2", "RB_BOT")],
        "put_RBTOP_TL2": [(-1, "RB_TOP", "TL2")], "put_RL_RBTOP": [(-1, "RL", "RB_TOP")],
        "call_TH1_TH2": [(1, "TH1", "TH2")], "call_TH2_GBTOP": [(1, "TH2", "GB_TOP")],
        "call_GBBOT_TH2": [(1, "GB_BOT", "TH2")], "call_RH_GBBOT": [(1, "RH", "GB_BOT")],
        "ic_inner_RBTOP_GBBOT": [(-1, "RB_TOP", "RB_BOT"), (1, "GB_BOT", "GB_TOP")],
        "ic_TL1_TH1_w2": [(-1, "TL1", "TL2"), (1, "TH1", "TH2")],
        "ic_TL1_TH1_wbox": [(-1, "TL1", "RB_BOT"), (1, "TH1", "GB_TOP")],
    }
    D_STRUCT = {
        "put_TL1_TL2": [(-1, "TL1", "TL2")], "put_RL_TL1": [(-1, "RL", "TL1")],
        "call_TH1_TH2": [(1, "TH1", "TH2")], "call_RH_TH1": [(1, "RH", "TH1")],
        "ic_TL1_TH1": [(-1, "TL1", "TL2"), (1, "TH1", "TH2")],
        "ic_RL_RH": [(-1, "RL", "TL1"), (1, "RH", "TH1")],
    }
    jobs = []
    for mode, roll, flat, manage in itertools.product(["fixed", "scaled"], ["incl", "excl"], [False, True], ["hold", "touch"]):
        for nm, lg in W_STRUCT.items():
            jobs.append(("opt_weekly", "W", mode, roll, flat, manage, nm, lg))
    for mode, flat in itertools.product(["fixed", "scaled", "ewma_rs"], [False, True]):
        for nm, lg in D_STRUCT.items():
            jobs.append(("opt_0dte", "D", mode, "incl", flat, "hold", nm, lg))
    ent_cache = {}
    for fam, tf, mode, roll, flat, manage, nm, lg in jobs:
        key = (tf, mode, roll)
        if key not in ent_cache:
            ent_cache[key] = entries_weekly(mode, roll) if tf == "W" else entries_daily(mode)
        ents = ent_cache[key]
        tr = structure_trades(tf, mode, lg, ents, flat, manage)
        t = to_frame(tr)
        extra = {}
        if len(tr):
            dmed = [(float(np.median([abs(x["deltas"][k][0]) for x in tr])), float(np.median([abs(x["deltas"][k][1]) for x in tr])))
                    for k in range(len(lg))]
            used = [(x["ie"], x["ix"]) for x in tr]
            b1 = to_frame(dm_trades(used, [c for c, _, _ in lg], dmed, flat, manage))
            b2 = to_frame(dm_trades(used, [c for c, _, _ in lg], [(0.16, 0.10)] * len(lg), flat, manage))
            extra = dict(dm_delta=json.dumps([[round(a, 3), round(b, 3)] for a, b in dmed]),
                         dm_ev=float(b1["net"].mean()), dm_evR=float(b1["R"].mean()),
                         dm_n=len(b1), d1610_ev=float(b2["net"].mean()), d1610_evR=float(b2["R"].mean()),
                         credit_mean=float(t["credit"].mean()) if "credit" in t else np.nan)
        rows_out.append(row_for(fam, tf, mode, roll, flat, manage, nm, t, extra))
        print(fam, tf, mode, roll, "flat" if flat else "skew", manage, nm, len(t),
              round(rows_out[-1].get("ev", np.nan), 3), round(extra.get("dm_ev", np.nan), 3),
              round(rows_out[-1].get("ev_R", np.nan), 4), round(extra.get("dm_evR", np.nan), 4), flush=True)
    # legging
    for mode, roll, flat, (nm, legs_map) in itertools.product(
            ["fixed", "scaled"], ["incl", "excl"], [False, True],
            [("leg_RL_RH_TL1TL2_TH1TH2", {"put": ("TL1", "TL2"), "call": ("TH1", "TH2")}),
             ("leg_RBTOP_GBBOT_TL2RBB_TH2GBT", {"put": ("TL2", "RB_BOT"), "call": ("TH2", "GB_TOP")})]):
        trig = {"put": "RL", "call": "RH"} if nm.startswith("leg_RL") else {"put": "RB_TOP", "call": "GB_BOT"}
        tr = legging_trades(mode, roll, trig, legs_map, flat)
        t = to_frame(tr)
        extra = {}
        if len(tr):
            dd = {}
            for side in ("put", "call"):
                xs = [x["deltas"][0] for x in tr if x["side"] == side]
                dd[side] = (float(np.median([abs(a) for a, _ in xs])), float(np.median([abs(b) for _, b in xs]))) if xs else (0.16, 0.10)
            b1 = to_frame(legging_trades(mode, roll, trig, legs_map, flat, deltas=dd))
            extra = dict(dm_delta=json.dumps(dd), dm_ev=float(b1["net"].mean()), dm_evR=float(b1["R"].mean()), dm_n=len(b1))
        rows_out.append(row_for("opt_legging", "W", mode, roll, flat, "hold", nm, t, extra))
        print("legging", mode, roll, flat, nm, len(t), round(rows_out[-1].get("ev", np.nan), 3), round(extra.get("dm_ev", np.nan), 3), flush=True)
    screen.append_log(rows_out, path=screen.RESULTS / "log_options_pending.csv")


if __name__ == "__main__":
    main()
