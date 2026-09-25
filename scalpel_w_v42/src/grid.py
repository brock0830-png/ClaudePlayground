"""STEP 2B pierce grid: every level x side x unit x pierce x entry style x max-pierce x stop x
target, per ticker and pooled, in-sample only. Writes results_all (one row per config x scope),
coverage.csv and a packed trade-week bitmap for the overfitting guard."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from common import COMMISSION_RT, EQUITY, LEVELS, LINEAGE, OUT, RISK_FRAC, ROOT, SPEC, TICKERS, UPPER
from data import load_all
from sim import BOUNCE, BREAKOUT, simulate

D_PIERCE = [0.0, 0.10, 0.25, 0.40, 0.50, 0.75, 1.00]
S_VALS = np.array([0.10, 0.25, 0.40, 0.50, 0.75, 1.00])
T_VALS = np.array([0.25, 0.50, 0.75, 1.00, 1.50, 2.00])
D_MAX = [0.5, 1.0, 1.5]
STYLES = {0: "a_limit", 1: "b_reclaim", 2: "c1", 3: "c2", 4: "c3"}
STOP_NAMES = [f"s{v:.2f}" for v in S_VALS] + ["STRUCT"]
TGT_NAMES = [f"t{v:.2f}" for v in T_VALS] + ["NEXT", "WO"]
LADDER = ["GB_TOP", "WTH2", "WTH1", "GB_BOT", "WRH", "GP_T_IN", "GP_T_OUT", "WO",
          "GP_B_OUT", "GP_B_IN", "WRL", "RB_TOP", "WTL1", "WTL2", "RB_BOT"]
MIN_GAP = 0.10   # sigma; ladder neighbours closer than this are skipped


def signed_dist(b, name, scale=1.0):
    if name == "WO":
        return 0.0
    lv = b.level_matrix(scale)[name]
    return float(np.median((lv - b.wo) / b.sigma))


def struct_prices(b, name, side, scale=1.0, shift=0.0):
    """(S_struct, T_next) price arrays for a level. shift (sigma) moves the whole ladder outward
    on the level's side (used for matched placebos)."""
    od = 1 if name in UPPER else -1
    sd = {n: signed_dist(b, n, scale) for n in LADDER}
    x = signed_dist(b, name, scale)
    outs = [sd[n] for n in LADDER if od * (sd[n] - x) >= MIN_GAP]
    ins = [sd[n] for n in LADDER if od * (x - sd[n]) >= MIN_GAP and od * sd[n] >= 0]
    nxt_out = (min(outs, key=lambda v: od * (v - x)) if outs else np.nan)
    nxt_in = (max(ins, key=lambda v: od * (v - x)) if ins else 0.0)

    def price(v):
        if not np.isfinite(v):
            return np.full(len(b.wo), np.nan)
        extra = od * shift if v != 0.0 else 0.0
        return b.wo + (v + extra) * b.sigma

    if side == BOUNCE:
        return price(nxt_out), price(nxt_in)
    return price(nxt_in), price(nxt_out)


def cells():
    out = []
    for name in LEVELS:
        for side in (BOUNCE, BREAKOUT):
            for unit in ("ATR", "SIG"):
                for d in D_PIERCE:
                    for style in STYLES:
                        if side == BOUNCE and style > 0:
                            for D in D_MAX:
                                if D >= d:
                                    out.append((name, side, unit, d, style, D))
                        else:
                            out.append((name, side, unit, d, style, np.inf))
    return out


def ticker_arrays(b):
    nW = len(b.wo)
    allow = np.ones(nW, np.bool_)
    bar_ok = np.ones(b.O.shape, np.bool_)
    return allow, bar_ok


def global_weeks(B):
    allw = sorted(set().union(*[set(b.weeks.index) for b in B.values()]))
    gi = {w: i for i, w in enumerate(allw)}
    return allw, {tk: np.array([gi[w] for w in b.weeks.index]) for tk, b in B.items()}


def metrics_block(Rg, Pg, years=None):
    """Rg, Pg: [nWeeks, nS, nT] with nan = no trade. Returns dict of [nS, nT] arrays."""
    tr = np.isfinite(Rg)
    n = tr.sum(0)
    Rz = np.where(tr, Rg, 0.0)
    Pz = np.where(tr, Pg, 0.0)
    wins = (Rz > 0).sum(0)
    sR = Rz.sum(0)
    sR2 = (Rz ** 2).sum(0)
    gp = np.where(Pz > 0, Pz, 0).sum(0)
    gl = -np.where(Pz < 0, Pz, 0).sum(0)
    cum = np.cumsum(Pz, 0)
    dd = (np.maximum.accumulate(np.maximum(cum, 0), 0) - cum).max(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = sR / n
        sd = np.sqrt(np.maximum(sR2 / n - mean ** 2, 0) * n / np.maximum(n - 1, 1))
        pf = np.where(gl > 0, gp / gl, np.where(gp > 0, np.inf, np.nan))
        wr = wins / n
    return dict(n=n, wr=wr, pf=pf, expR=mean, sdR=sd, sumR=sR, usd=Pz.sum(0),
                exp_usd=np.where(n > 0, Pz.sum(0) / np.maximum(n, 1), np.nan), maxdd_usd=dd)


def run_grid(B=None, family="F0_pierce_grid", cell_list=None, slip=1.0, scale=1.0, shift=0.0,
             masks=None, tag=None, keep_bits=True, verbose=True, flip=False, t_vals=None, t_names=None,
             be_R=0.0, so_t=0.0):
    """Sweep cells. masks: optional fn(b, cell) -> (allow, bar_ok) for filter families."""
    B = B or load_all()
    allw, gmap = global_weeks(B)
    nG = len(allw)
    budget = EQUITY * RISK_FRAC
    rows, bits, cov = [], [], []
    cl = cell_list or cells()
    t0 = time.time()
    struct_cache = {}
    tv = T_VALS if t_vals is None else np.asarray(t_vals, float)
    tnames = TGT_NAMES if t_names is None else list(t_names) + ["NEXT", "WO"]
    for ci, cell in enumerate(cl):
        name, side, unit, d, style, D = cell
        od_nat = 1 if name in UPPER else -1
        od = -od_nat if flip else od_nat
        per_tk = {}
        for tk, b in B.items():
            sp = SPEC[tk]
            lv = b.level_matrix(scale)[name]
            P = lv if shift == 0.0 else b.wo + (lv - b.wo) + od_nat * shift * b.sigma
            if shift != 0.0:
                P = np.where(od_nat * (P - b.wo) / b.sigma < 0.05, np.nan, P)   # placebo on/over WO: dropped
            U = b.atr if unit == "ATR" else b.sigma
            sside = (BREAKOUT if side == BOUNCE else BOUNCE) if flip else side
            key = (tk, name, sside, scale, shift)
            if key not in struct_cache:
                struct_cache[key] = struct_prices(b, name, sside, scale, shift)
            S_struct, T_next = struct_cache[key]
            SB = None
            if masks is None:
                allow, bar_ok = ticker_arrays(b)
            else:
                allow, bar_ok, SB = masks(b, cell, P, od_nat)
            try:
                R, PN, EB, ET, XB = simulate(b.O, b.H, b.L, b.C, b.nb, P, U, b.wo, S_struct, T_next,
                                             allow, bar_ok, od, side, d, style, D, S_VALS, tv,
                                             sp["tick"], slip, sp["pv"], COMMISSION_RT, budget, SB, be_R, so_t)
                status = "done"
            except Exception as e:  # pragma: no cover
                status = f"error:{e}"
                R = PN = None
            per_tk[tk] = (R, PN)
            cov.append(dict(lineage=LINEAGE, family=family, level=name, side="bounce" if side == BOUNCE else "breakout",
                            unit=unit, d=d, style=STYLES[style], D=D, ticker=tk, status=status,
                            n_entries=int((EB >= 0).sum()) if R is not None else 0))
        # ---- map to global weeks and compute metrics
        nS, nT = len(S_VALS) + 1, len(tv) + 2
        Rg_all = np.full((len(B), nG, nS, nT), np.nan)
        Pg_all = np.full((len(B), nG, nS, nT), np.nan)
        for k, (tk, (R, PN)) in enumerate(per_tk.items()):
            if R is None:
                continue
            Rg_all[k, gmap[tk]] = R
            Pg_all[k, gmap[tk]] = PN
        scopes = {tk: (Rg_all[k], Pg_all[k]) for k, tk in enumerate(B)}
        # pooled: weekly $ summed across tickers (for DD); R pooled as a trade list
        Pw = np.nansum(Pg_all, 0)
        Pw[np.all(~np.isfinite(Pg_all), 0)] = np.nan
        mets = {tk: metrics_block(*scopes[tk]) for tk in scopes}
        # pooled trade-level stats
        Rcat = Rg_all.reshape(-1, nS, nT)
        Pcat = Pg_all.reshape(-1, nS, nT)
        mp = metrics_block(Rcat, Pcat)
        mw = metrics_block(Pw / budget, Pw)             # weekly-summed series for pooled DD
        mp["maxdd_usd"] = mw["maxdd_usd"]
        mets["POOLED"] = mp
        base = dict(lineage=LINEAGE, family=family, level=name, side="bounce" if side == BOUNCE else "breakout",
                    unit=unit, d=d, style=STYLES[style], D=D if np.isfinite(D) else np.nan)
        if tag:
            base["variant"] = tag
        for si in range(nS):
            for ti in range(nT):
                if side == BREAKOUT and tnames[ti] == "WO":
                    continue
                cid = f"{name}|{base['side']}|{unit}|d{d:.2f}|{STYLES[style]}|D{D:.1f}|{STOP_NAMES[si]}|{tnames[ti]}"
                for sc, m in mets.items():
                    r = dict(base, config=cid, stop=STOP_NAMES[si], target=tnames[ti], scope=sc)
                    for k2, v in m.items():
                        r[k2] = v[si, ti]
                    rows.append(r)
                if keep_bits:
                    bits.append((cid, np.packbits(np.isfinite(Rg_all[:, :, si, ti]).ravel())))
        if verbose and (ci % 200 == 0 or ci == len(cl) - 1):
            print(f"  {family} cell {ci + 1}/{len(cl)}  {time.time() - t0:.0f}s", flush=True)
    res = pd.DataFrame(rows)
    return res, bits, pd.DataFrame(cov)


if __name__ == "__main__":
    import sys
    OUT.mkdir(exist_ok=True)
    B = load_all()
    cl = cells()
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"
    print("cells:", len(cl), "mode:", mode)
    if mode == "real":
        res, bits, cov = run_grid(B, cell_list=cl)
        res.to_parquet(OUT / "grid_F0.parquet", index=False)
        cov.to_csv(OUT / "coverage_F0.csv", index=False)
        ids = [c for c, _ in bits]
        np.save(OUT / "bits_F0.npy", np.stack([b for _, b in bits]))
        pd.Series(ids).to_csv(OUT / "bits_F0_ids.csv", index=False, header=False)
    elif mode.startswith("shift"):
        sh = float(mode[5:])
        res, _, _ = run_grid(B, cell_list=cl, shift=sh, family=f"F0_placebo_{sh:+.2f}", keep_bits=False, verbose=False)
        res.to_parquet(OUT / f"grid_F0_shift{sh:+.2f}.parquet", index=False)
    elif mode.startswith("scale"):
        sc = float(mode[5:])
        res, _, _ = run_grid(B, cell_list=cl, scale=sc, family=f"F0_scale_{sc:.2f}", keep_bits=False, verbose=False)
        res.to_parquet(OUT / f"grid_F0_scale{sc:.2f}.parquet", index=False)
    elif mode.startswith("slip"):
        sl = float(mode[4:])
        res, _, _ = run_grid(B, cell_list=cl, slip=sl, family=f"F0_slip_{sl:.0f}", keep_bits=False, verbose=False)
        res.to_parquet(OUT / f"grid_F0_slip{sl:.0f}.parquet", index=False)
    print(res.shape)
