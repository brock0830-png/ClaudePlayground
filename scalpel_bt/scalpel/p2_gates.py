"""PROTOCOL_P2 section 6 gates from results/p2/log.csv."""
import numpy as np
import pandas as pd


def add_gates(log: pd.DataFrame) -> pd.DataFrame:
    g = log.copy()
    g["P1"] = (g["ev"] > 0) & (g["total"] > 0)
    g["P2"] = (g["n"] >= 30) & (g["sessions_in"] >= 100)
    g["P3"] = (g["rand_pct"] >= 90) & (g["excess"] > 0)
    g["P4"] = g["ci_lo"] > 0
    g["P5"] = (g["pos_years"] >= 5) & (g["ex_best"] > 0)
    spx_ok = (g["spx_excess_pct"] > 0) & (g["spx_ev_pct"] > 0)
    halves_ok = (g["half1_excess"] > 0) & (g["half2_excess"] > 0)
    g["P6"] = np.where(g["robust_mode"] == "spx", spx_ok, halves_ok)
    g["ALL"] = g[["P1", "P2", "P3", "P4", "P5", "P6"]].all(axis=1)
    return g
