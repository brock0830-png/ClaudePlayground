"""Portfolio view (K=10 open positions) on DISCOVERY and VALIDATION only. K=5/20 as sensitivity, not selection."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import pandas as pd
from of import explore as ex
from of.config import DEV, HOLDOUT, RESULTS
import run_explore as rx

E = rx.all_events(DEV + HOLDOUT)
A = E[E.event == "A9L_fade_accept_below_PDL"][["sym", "t", "net", "split"]]
T = pd.read_csv(RESULTS / "flush_signals.csv"); T["t"] = pd.to_datetime(T.t, utc=True)
T = T[["sym", "t", "net"]].assign(split=ex.split_of(T.sym, T.t))
rows = []
for name, X in [("A9L", A), ("flush", T), ("flush+A9L", pd.concat([T, A]))]:
    for sp in ["discovery", "validation"]:
        x = X[X.split == sp]
        if sp == "discovery":
            x = x[x.sym.isin(DEV)]
        for K in [5, 10, 20]:
            r = ex.pstats(ex.portfolio(x, K))
            rows.append(dict(strategy=name, split=sp, K=K, **r))
R = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(R.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
ex.log([dict(family="P", split=r["split"], id=f"P:{r['strategy']}:K{r['K']}", n=r["taken"], mean=r["CAGR"], t=r["t"],
             note=f"Sharpe {r['Sharpe']:.2f} MaxDD {r['MaxDD']:.3f}") for r in rows])
