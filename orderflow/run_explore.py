"""Exploration runner (EXPLORATION_PROTOCOL.md).

    python orderflow/run_explore.py discovery              # families A, B, C on DISCOVERY only
    python orderflow/run_explore.py validate ID [ID ...]   # named candidates on VALIDATION
    python orderflow/run_explore.py vault ID [ID ...]      # finalists, once

Candidate IDs:  A:<event>[:tp]   B:<feature>:<hi|lo>   C:<feature>:<hi|lo>
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import numpy as np                                     # noqa: E402
import pandas as pd                                    # noqa: E402

from of import explore as ex                           # noqa: E402
from of.config import DEV, HOLDOUT, RESULTS            # noqa: E402

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 500)
SIG = RESULTS / "flush_signals.csv"


def panel(syms):
    """Per coin: structure frame X and its screen features F (both hourly)."""
    for s in syms:
        X = ex.load_structure(s)
        yield s, X, ex.screen_features(X)


def all_events(syms):
    rows = []
    for s, X, _ in panel(syms):
        for name, (trig, side, tgt) in ex.events(X).items():
            E = ex.event_trades(s, X, trig, side, target=tgt)
            if len(E):
                E["event"] = name
                rows.append(E)
    E = pd.concat(rows, ignore_index=True)
    E["split"] = ex.split_of(E.sym, E.t)
    return E


def screen_panel(syms, hours=(0, 12)):
    rows = []
    for s, X, F in panel(syms):
        m = np.isin(X.index.hour, hours)
        D = F[m].copy()
        D["L24"] = X.L24[m]
        D["sym"] = s
        D["t"] = D.index
        rows.append(D.reset_index(drop=True))
    D = pd.concat(rows, ignore_index=True).dropna(subset=["L24"])
    D["split"] = ex.split_of(D.sym, D.t)
    return D


def flush_panel(syms):
    T = pd.read_csv(SIG)
    T["t"] = pd.to_datetime(T.t, utc=True)
    rows = []
    for s, X, F in panel(syms):
        tr = T[T.sym == s]
        if len(tr) == 0:
            continue
        G = F.reindex(tr.t)
        G.index = tr.index
        rows.append(pd.concat([tr, G], axis=1))
    D = pd.concat(rows, ignore_index=True)
    D["split"] = ex.split_of(D.sym, D.t)
    return D


def discovery():
    syms = DEV
    led = []
    # ---- A: events
    E = all_events(syms)
    E = E[E.split == "discovery"]
    print("\n=== A: event trades, DISCOVERY (9 dev coins, 2022-23), 24h hold, net of costs+funding ===")
    rows = []
    for name, g in E.groupby("event"):
        r = ex.summarize(g)
        rows.append(dict(id=f"A:{name}", **r))
        if "net_tp" in g and g.net_tp.notna().any():
            r2 = ex.summarize(g, "net_tp")
            rows.append(dict(id=f"A:{name}:tp", **r2))
    A = pd.DataFrame(rows)
    print(A.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    led += [dict(family="A", split="discovery", **r) for r in rows]

    # ---- C: structure screen (decision at 00:00 and 12:00 UTC bars)
    D = screen_panel(syms)
    Dd = D[D.split == "discovery"]
    feats = [c for c in D.columns if c not in ("L24", "sym", "t", "split")]
    print("\n=== C: screen, DISCOVERY; top-third minus bottom-third of next-24h LONG net ===")
    rows = [ex.tercile_spread(Dd, f, "L24", Dd) for f in feats]
    C = pd.DataFrame(rows).sort_values("t")
    print(C.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    led += [dict(family="C", split="discovery", id=f"C:{r['feature']}", n=r["n_top"] + r["n_bot"],
                 mean=r["spread"], t=r["t"], note=r["compare"]) for r in rows]

    # ---- B: flush filters
    if SIG.exists():
        B = flush_panel(syms)
        Bd = B[B.split == "discovery"]
        print(f"\n=== B: flush-signal filters, DISCOVERY (n={len(Bd)}, base mean net {Bd.net.mean():.4f}) ===")
        rows = [ex.tercile_spread(Bd, f, "net", Bd) for f in feats]
        Bt = pd.DataFrame(rows).sort_values("t")
        print(Bt.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        led += [dict(family="B", split="discovery", id=f"B:{r['feature']}", n=r["n_top"] + r["n_bot"],
                     mean=r["spread"], t=r["t"], note=r["compare"]) for r in rows]
    ex.log(led)


def _part(D):
    return np.where(D.sym.isin(DEV), "dev coins 2024-25H1", "new coins 2022-25H1")


def evaluate(ids, split):
    """Evaluate named candidates on `split` with cutoffs frozen from DISCOVERY."""
    syms = DEV + HOLDOUT
    need = {i.split(":")[0] for i in ids}
    E = all_events(syms) if "A" in need else None
    S = screen_panel(syms) if "C" in need else None
    B = flush_panel(syms) if "B" in need else None
    led, out = [], []
    for cid in ids:
        fam, rest = cid.split(":", 1)
        if fam == "A":
            name, _, tp = rest.partition(":")
            g = E[(E.event == name) & (E.split == split)]
            col = "net_tp" if tp else "net"
            parts = [("pooled", g)] + ([(p, g[_part(g) == p]) for p in sorted(set(_part(g)))] if split == "validation" else [])
            for pn, x in parts:
                r = ex.summarize(x, col)
                out.append(dict(id=cid, part=pn, **r))
                led.append(dict(family=fam, split=f"{split}/{pn}", id=cid, **r))
        else:
            feat, side = rest.split(":")
            P = S if fam == "C" else B
            ret = "L24" if fam == "C" else "net"
            disc = P[P.split == "discovery"]
            q1, q2 = disc[feat].quantile([1 / 3, 2 / 3])
            x = P[P.split == split]
            parts = [("pooled", x)] + ([(p, x[_part(x) == p]) for p in sorted(set(_part(x)))] if split == "validation" else [])
            for pn, y in parts:
                if feat in ex.BINARY:
                    hi, lo = y[y[feat] == 1], y[y[feat] == 0]
                else:
                    hi, lo = y[y[feat] > q2], y[y[feat] <= q1]
                good, bad = (hi, lo) if side == "hi" else (lo, hi)
                sp = good[ret].mean() - bad[ret].mean()
                t = ex.diff_day_t(good[ret], good.t, bad[ret], bad.t)
                gs = ex.summarize(good, ret)
                out.append(dict(id=cid, part=pn, n=len(good) + len(bad), spread=sp, t_spread=t, good_n=gs["n"],
                                good_mean=gs["mean"], good_t=gs["t"], all_mean=y[ret].mean()))
                led.append(dict(family=fam, split=f"{split}/{pn}", id=cid, n=len(good) + len(bad), mean=sp, t=t,
                                note=f"good-group mean {gs['mean']:.5f} t {gs['t']:.2f} n {gs['n']}"))
    ex.log(led)
    R = pd.DataFrame(out)
    print(R.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    return R


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "discovery":
        discovery()
    elif cmd == "validate":
        evaluate(sys.argv[2:], "validation")
    elif cmd == "vault":
        flag = RESULTS / "VAULT_OPENED.txt"
        done = set(flag.read_text().split()) if flag.exists() else set()
        again = [i for i in sys.argv[2:] if i in done]
        if again:
            sys.exit(f"vault already opened for {again}; refusing")
        R = evaluate(sys.argv[2:], "vault")
        with open(flag, "a") as fh:
            fh.write("\n".join(sys.argv[2:]) + "\n")
        R.to_csv(RESULTS / f"vault_{pd.Timestamp.now():%Y%m%d_%H%M}.csv", index=False)
