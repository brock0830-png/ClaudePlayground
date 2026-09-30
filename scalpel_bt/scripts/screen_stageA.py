"""
Stage A screen (DEV only): bounce, break-and-go, reclaim and confluence families over
D/W/M levels, every vol mode, with/without roll weeks (W/M). Appends to results/log.csv.
Usage: python scripts/screen_stageA.py [n_procs]
"""
import sys, time, itertools
from pathlib import Path
from multiprocessing import Pool
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from scalpel.data import load_bars
from scalpel.features import build_frame
from scalpel import screen

MODES = {"D": ["fixed", "scaled", "ewma_rs"], "W": ["fixed", "scaled"], "M": ["fixed", "scaled"]}
ROLLS = {"D": ["incl"], "W": ["incl", "excl"], "M": ["incl", "excl"]}
BOUNCE = [("long", x) for x in ["RL", "RB_TOP", "TL1", "TL2", "GP_B_OUT", "GP_B_IN"]] + \
         [("short", x) for x in ["RH", "GB_BOT", "TH1", "TH2", "GP_T_OUT", "GP_T_IN"]]
BREAK = [("long", "GP_T_IN", "RH"), ("long", "RH", "GB_BOT"), ("long", "GB_BOT", "TH1"), ("long", "TH1", "TH2"),
         ("short", "GP_B_IN", "RL"), ("short", "RL", "RB_TOP"), ("short", "RB_TOP", "TL1"), ("short", "TL1", "TL2")]
RECLAIM = [("long", x) for x in ["RL", "RB_TOP", "TL1", "GP_B_IN"]] + [("short", x) for x in ["RH", "GB_BOT", "TH1", "GP_T_IN"]]
STOPS = [("sig", 0.25), ("sig", 0.5), ("sig", 1.0)]
TGTS = [("lvl", "OPEN"), ("R", 1.0), ("R", 2.0), ("none",)]


def specs():
    out = []
    for tf in "DWM":
        for mode, roll in itertools.product(MODES[tf], ROLLS[tf]):
            base = dict(tf=tf, mode=mode, roll=roll, pend=True, max_bars=0, stage="A")
            for (side, lvl), trig, st, tg in itertools.product(BOUNCE, ["reject", "touch", "limit"], STOPS, TGTS):
                out.append({**base, "family": "bounce", "side": side, "level": lvl, "trig": trig, "stop": st, "target": tg})
            for (side, lvl, nxt), trig, st, tg in itertools.product(BREAK, ["break", "stopin"],
                                                                    [("sig", 0.25), ("sig", 0.5), ("lvl", "OPEN")],
                                                                    [("lvl", None), ("R", 1.0), ("R", 2.0), ("none",)]):
                tg2 = ("lvl", nxt) if tg[0] == "lvl" else tg
                out.append({**base, "family": "break", "side": side, "level": lvl, "trig": trig, "stop": st, "target": tg2})
            for (side, lvl), st, tg in itertools.product(RECLAIM, STOPS, TGTS):
                out.append({**base, "family": "reclaim", "side": side, "level": lvl, "trig": "reclaim", "stop": st, "target": tg})
    # confluence: D levels near W/M levels, W levels near M levels (fixed and scaled only, roll incl)
    for tf, pcts, tfs in [("D", [0.05, 0.10, 0.20], ["W", "M"]), ("W", [0.10, 0.20, 0.40], ["M"])]:
        for mode in ["fixed", "scaled"]:
            base = dict(tf=tf, mode=mode, roll="incl", pend=True, max_bars=0, stage="A")
            for (side, lvl), trig, st, tg, pct in itertools.product(BOUNCE, ["reject", "limit"], [("sig", 0.5), ("sig", 1.0)],
                                                                    [("lvl", "OPEN"), ("R", 2.0), ("none",)], pcts):
                out.append({**base, "family": f"confluence_{tf}", "side": side, "level": lvl, "trig": trig, "stop": st,
                            "target": tg, "filters": {"conf": [pct, tfs]}})
    return out


def init():
    screen.set_frame(build_frame(load_bars("dev")))


def work(spec):
    fr = screen._FR
    return screen.evaluate(spec, 0, len(fr.o))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    sp = specs()
    print("variants:", len(sp), flush=True)
    t0 = time.time()
    rows = []
    with Pool(n, initializer=init) as pool:
        for i, r in enumerate(pool.imap(work, sp, chunksize=8)):
            rows.append(r)
            if (i + 1) % 500 == 0:
                print(i + 1, round(time.time() - t0), "s", flush=True)
    screen.append_log(rows)
    print("done", len(rows), round(time.time() - t0), "s")
