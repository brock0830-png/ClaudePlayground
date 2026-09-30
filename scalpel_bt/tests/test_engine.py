"""Engine correctness tests on DEV data only. Run: python -m pytest -q tests"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scalpel.data import load_bars, COST_RT_PTS
from scalpel.features import build_frame
from scalpel.levels import level_frame
from scalpel.levelsets import coefficients, NAMES
from scalpel.strategies import run, build


@pytest.fixture(scope="module")
def fr():
    return build_frame(load_bars("dev"))


def test_coefficients_match_level_frame(fr):
    for tf in "DWM":
        for mode in ("fixed", "scaled"):
            po = pd.Series(fr.po[tf])
            vol = None if mode == "fixed" else pd.Series(fr.vol[(tf, mode)])
            lf = level_frame(po, tf, vol=vol)
            k = coefficients(tf)
            for n in NAMES:
                mine = po.values + fr.sigma[(tf, mode)] * k[n]
                ref = lf[f"{tf}_{n}"].values
                ok = ~np.isnan(ref)
                assert np.nanmax(np.abs(mine[ok] - ref[ok])) < 1e-9, (tf, mode, n)


def test_fixed_levels_match_export(fr):
    raw = pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "es_levels_CME_MINI_ES1_240.csv.gz",
                      usecols=["WRL", "DTH1", "M RB Top"], nrows=len(fr.o))
    k = coefficients("W")
    assert np.abs(fr.po["W"] + fr.sigma[("W", "fixed")] * k["RL"] - raw["WRL"].values).max() < 1e-9
    k = coefficients("D")
    assert np.abs(fr.po["D"] + fr.sigma[("D", "fixed")] * k["TH1"] - raw["DTH1"].values).max() < 1e-9
    k = coefficients("M")
    assert np.abs(fr.po["M"] + fr.sigma[("M", "fixed")] * k["RB_TOP"] - raw["M RB Top"].values).max() < 1e-9


def ref_sim(fr, spec):
    """Slow reference for next-open triggers (touch/reject/break) and limit entries."""
    (o, h, l, c), E, S, T, elig, tmode, r = build(fr, spec)
    pid, pend, ff = fr.pid[spec["tf"]], fr.pend[spec["tf"]], fr.force_flat
    n = len(o)
    trades = []
    done = set()
    i = 0
    below = {}
    while i < n:
        p = pid[i]
        if spec["trig"] == "break" and c[i] <= E[i]:
            below[p] = True
        if elig[i] and p not in done:
            sig = False
            if spec["trig"] == "touch" and l[i] <= E[i]:
                sig = True
            elif spec["trig"] == "reject" and l[i] <= E[i]:
                done.add(p)
                sig = c[i] > E[i]
            elif spec["trig"] == "break" and c[i] > E[i] and (below.get(p) or o[i] < E[i]):
                sig = True
            elif spec["trig"] == "limit" and l[i] <= E[i]:
                done.add(p)
                fill = min(E[i], o[i]); st = S[i]
                tg = T[i] if tmode == 0 else (fill + r * (fill - st) if tmode == 1 else np.inf)
                if fill > st and fill < tg:
                    j = i
                    if l[j] <= st:
                        trades.append((i, j, fill, min(st, o[j]))); i += 1; continue
                    if ff[j] or (spec["pend"] and pend[j]):
                        trades.append((i, j, fill, c[j])); i += 1; continue
                    j += 1
                    while j < n:
                        if l[j] <= st:
                            trades.append((i, j, fill, min(st, o[j]))); break
                        if h[j] >= tg:
                            trades.append((i, j, fill, max(tg, o[j]))); break
                        if ff[j] or (spec["pend"] and pend[j]):
                            trades.append((i, j, fill, c[j])); break
                        j += 1
                    i = j + 1
                    continue
            if sig:
                done.add(p)
                if c[i] > S[i] and i + 1 < n and not ff[i] and not (pend[i] and spec["pend"]):
                    j = i + 1
                    fill = o[j]; st = S[i]
                    tg = T[i] if tmode == 0 else (fill + r * (fill - st) if tmode == 1 else np.inf)
                    if fill > st and fill < tg:
                        while j < n:
                            if l[j] <= st:
                                trades.append((i + 1, j, fill, min(st, o[j]))); break
                            if h[j] >= tg:
                                trades.append((i + 1, j, fill, tg if j == i + 1 else max(tg, o[j]))); break
                            if ff[j] or (spec["pend"] and pend[j]):
                                trades.append((i + 1, j, fill, c[j])); break
                            j += 1
                        # next bar where a new signal may occur is the exit bar itself
                        i = j
                        if spec["trig"] == "break" and c[i] <= E[i]:
                            below[pid[i]] = True
                        i += 1
                        continue
        i += 1
    return trades


SPECS = [
    dict(tf="W", mode="fixed", side="long", level="RL", trig="reject", stop=("sig", 0.5), target=("lvl", "OPEN"), pend=True),
    dict(tf="W", mode="scaled", side="short", level="RH", trig="touch", stop=("sig", 0.25), target=("R", 2.0), pend=True),
    dict(tf="D", mode="fixed", side="long", level="TL1", trig="limit", stop=("sig", 0.5), target=("lvl", "OPEN"), pend=True),
    dict(tf="W", mode="fixed", side="long", level="RH", trig="break", stop=("lvl", "OPEN"), target=("lvl", "TH1"), pend=True),
    dict(tf="D", mode="ewma_rs", side="short", level="GP_T_IN", trig="reject", stop=("sig", 0.25), target=("none",), pend=True),
]


@pytest.mark.parametrize("spec", SPECS)
def test_numba_matches_reference(fr, spec):
    res = run(fr, spec, 0, len(fr.o))
    ref = ref_sim(fr, spec)
    got = list(zip(res["ei"], res["xi"], np.round(res["entry"], 6), np.round(res["exit"], 6)))
    exp = [(a, b, round(x, 6), round(y, 6)) for a, b, x, y in ref]
    assert len(got) == len(exp), (len(got), len(exp))
    assert got == exp
    assert np.allclose(res["net"], res["exit"] - res["entry"] - COST_RT_PTS)
