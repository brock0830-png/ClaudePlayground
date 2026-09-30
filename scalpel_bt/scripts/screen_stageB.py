"""
Stage B screen (DEV only): the filter hypotheses (trend, VIX regime, higher-TF position,
day of week) on a fixed set of simple base shapes and on the Stage-A all-gate shapes;
multi-level portfolios; holding past the level period. Appends to results/log.csv.
Usage: python scripts/screen_stageB.py [n_procs]
"""
import sys, time, json, itertools
from pathlib import Path
from multiprocessing import Pool
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from scalpel.data import load_bars, RESULTS
from scalpel.features import build_frame
from scalpel.gates import add_gates
from scalpel import screen

MODES = {"D": ["fixed", "scaled", "ewma_rs"], "W": ["fixed", "scaled"]}
ROLLS = {"D": ["incl"], "W": ["incl", "excl"]}
FILTERS = {
    "D": [{"trend": t} for t in ["up20", "dn20", "up50", "dn50"]]
         + [{"vix": v} for v in ["lt15", "15_20", "gt20", "below_mean", "above_mean"]]
         + [{"htf": ["W", w]} for w in ["above", "below"]]
         + [{"dow": d} for d in range(5)],
    "W": [{"trend": t} for t in ["up20", "dn20", "up50", "dn50"]]
         + [{"vix": v} for v in ["lt15", "15_20", "gt20", "below_mean", "above_mean"]]
         + [{"htf": ["M", w]} for w in ["above", "below"]],
}


def bases(tf):
    out = []
    for side, lv in [("long", x) for x in ["GP_B_IN", "RL", "RB_TOP", "TL1"]] + [("short", x) for x in ["GP_T_IN", "RH", "GB_BOT", "TH1"]]:
        for tg in [("lvl", "OPEN"), ("none",)]:
            out.append(dict(family="bounce", tf=tf, side=side, level=lv, trig="reject", stop=("sig", 0.5), target=tg))
    for side, lv in [("long", "GP_T_IN"), ("long", "RH"), ("short", "GP_B_IN"), ("short", "RL")]:
        out.append(dict(family="break", tf=tf, side=side, level=lv, trig="break", stop=("sig", 0.5), target=("none",)))
    return out


def stageA_winner_shapes():
    log = pd.read_csv(RESULTS / "log.csv")
    g = add_gates(log[log["stage"] == "A"])
    w = g[g["ALL"]]
    shapes = {}
    for s in w["spec"]:
        d = json.loads(s)
        d.pop("mode"); d.pop("stage", None)
        d["stop"] = tuple(d["stop"]); d["target"] = tuple(d["target"])
        shapes[json.dumps(d, sort_keys=True)] = d
    return list(shapes.values())


def specs():
    out = []
    # B1: filters on simple bases
    for tf in "DW":
        for b, f, mode, roll in itertools.product(bases(tf), FILTERS[tf], MODES[tf], ROLLS[tf]):
            out.append({**b, "mode": mode, "roll": roll, "pend": True, "max_bars": 0, "filters": f, "stage": "B"})
    # B2: filters on Stage-A all-gate shapes (every vol mode, for the G1 twin)
    for sh in stageA_winner_shapes():
        tf = sh["tf"]
        for f, mode in itertools.product(FILTERS[tf], MODES[tf]):
            out.append({**sh, "mode": mode, "filters": f, "stage": "B", "family": sh["family"] + "_Awin"})
    # B3: multi-level portfolios
    lad_l = ["GP_B_IN", "RL", "RB_TOP", "TL1"]; lad_s = ["GP_T_IN", "RH", "GB_BOT", "TH1"]
    for tf in "DW":
        for mode, roll in itertools.product(MODES[tf], ROLLS[tf]):
            mk = lambda side, lv, trig: dict(tf=tf, side=side, level=lv, trig=trig, stop=("sig", 0.5), target=("none",),
                                            pend=True, max_bars=0, roll=roll)
            for name, legs in [("ladder_long_reject", [mk("long", x, "reject") for x in lad_l]),
                               ("ladder_short_reject", [mk("short", x, "reject") for x in lad_s]),
                               ("ladder_both_reject", [mk("long", x, "reject") for x in lad_l] + [mk("short", x, "reject") for x in lad_s]),
                               ("ladder_long_limit", [mk("long", x, "limit") for x in lad_l])]:
                out.append({"family": "portfolio", "note": name, "tf": tf, "mode": mode, "roll": roll, "legs": legs,
                            "stage": "B", "level": name, "side": "long" if "long" in name else ("short" if "short" in name else "both")})
    # B4: hold past the level period
    for tf, mbs in [("D", [6, 30]), ("W", [30, 60])]:
        for b, mb, mode, roll in itertools.product(bases(tf), mbs, MODES[tf], ROLLS[tf]):
            out.append({**b, "family": b["family"] + "_hold", "mode": mode, "roll": roll, "pend": False, "max_bars": mb, "stage": "B"})
    return out


def init():
    screen.set_frame(build_frame(load_bars("dev")))


def work(spec):
    return screen.evaluate(spec, 0, len(screen._FR.o))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    sp = specs()
    print("variants:", len(sp), flush=True)
    t0 = time.time(); rows = []
    with Pool(n, initializer=init) as pool:
        for i, r in enumerate(pool.imap(work, sp, chunksize=8)):
            rows.append(r)
            if (i + 1) % 250 == 0:
                print(i + 1, round(time.time() - t0), "s", flush=True)
    screen.append_log(rows)
    print("done", len(rows), round(time.time() - t0), "s")
