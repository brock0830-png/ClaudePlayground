import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sim import BOUNCE, BREAKOUT, simulate  # noqa: E402

TICK, PV, COMM, BUDGET = 0.25, 5.0, 4.5, 500.0
S = np.array([1.0])
T = np.array([1.0])


def run(bars, P=100.0, od=-1, side=BOUNCE, d=0.0, style=0, D=np.inf, slip=1.0, wo=None):
    b = np.array(bars, dtype=float)
    n = len(b)
    O, H, L, C = (b[:, i][None, :] for i in range(4))
    nb = np.array([n])
    one = lambda v: np.array([v], dtype=float)
    R, PN, EB, ET, XB = simulate(O, H, L, C, nb, one(P), one(1.0), one(wo if wo else b[0, 0]),
                                 one(np.nan), one(np.nan), np.ones(1, np.bool_), np.ones((1, n), np.bool_),
                                 od, side, d, style, D, S, T, TICK, slip, PV, COMM, BUDGET)
    return R[0, 0, 0], PN[0, 0, 0], EB[0], ET[0], XB[0, 0, 0]


def test_limit_needs_trade_through():
    # low 99.8 does not trade a tick through 100 -> no fill
    r = run([[102, 102.5, 101, 101.5], [101.5, 101.6, 99.8, 100.5], [100.5, 100.6, 100.2, 100.4]])
    assert np.isnan(r[0])


def test_limit_fill_then_target():
    r = run([[102, 102.5, 101, 101.5], [101.5, 101.6, 99.5, 100.5], [100.5, 101.5, 100.2, 101.2]])
    R, PN, EB, ET, XB = r
    assert EB == 1 and ET == 0 and XB == 2
    # fill 100 + 1 tick = 100.25; stop 99 -> risk 1.25pt = $6.25 -> 80 contracts
    assert abs(PN - 80 * ((101 - 100.25) * PV - COMM)) < 1e-9
    assert abs(R - PN / (80 * 6.25)) < 1e-12


def test_target_in_fill_bar_needs_close_beyond():
    # fill bar high reaches the target but closes below it: not counted, trade continues to time exit
    R, PN, EB, ET, XB = run([[102, 102.5, 101, 101.5], [101.5, 101.8, 99.5, 100.2], [100.2, 100.4, 100.0, 100.1]])
    assert XB == 2
    exitpx = 100.1 - TICK
    assert abs(PN - 80 * ((exitpx - 100.25) * PV - COMM)) < 1e-9


def test_stop_first_when_both_in_bar():
    R, PN, EB, ET, XB = run([[102, 102.5, 101, 101.5], [101.5, 101.6, 99.5, 100.5], [100.5, 101.5, 98.5, 100.0]])
    assert XB == 2
    # stop 99 filled with 1 tick slippage
    assert abs(PN - 80 * ((99 - TICK - 100.25) * PV - COMM)) < 1e-9
    assert R < -1.0


def test_reclaim_entry_next_open():
    # pierce 100 in bar 1 (low 99.4), close back above in bar 2, enter bar 3 open 100.5
    R, PN, EB, ET, XB = run([[102, 102, 101, 101], [101, 101, 99.4, 99.6], [99.6, 100.4, 99.5, 100.3],
                             [100.5, 101.9, 100.4, 101.8]], style=1, D=1.5)
    assert EB == 3 and ET == 1
    # target = 100.5 + 1 = 101.5; stop = 99 -> fill 100.75, risk 1.75pt
    n = int(np.floor(BUDGET / (1.75 * PV)))
    assert abs(PN - n * ((101.5 - 100.75) * PV - COMM)) < 1e-9


def test_reclaim_invalidated_by_max_pierce():
    R = run([[102, 102, 101, 101], [101, 101, 98.9, 99.6], [99.6, 100.4, 99.5, 100.3],
             [100.5, 101.9, 100.4, 101.8]], style=1, D=1.0)[0]
    assert np.isnan(R)


def test_reclaim_time_limit():
    bars = [[102, 102, 101, 101], [101, 101, 99.4, 99.6], [99.6, 99.9, 99.5, 99.7], [99.7, 100.4, 99.6, 100.3],
            [100.5, 101.9, 100.4, 101.8]]
    assert np.isnan(run(bars, style=2, D=1.5)[0])      # k=1: reclaim at lag 2 is too late
    assert np.isfinite(run(bars, style=3, D=1.5)[0])   # k=2 ok


def test_breakout_stop_entry_and_gap_stop():
    # long breakout through 100 (od=+1): trigger 100 + 1 tick; stop = 100 - 1 = 99
    bars = [[98, 99, 97.8, 98.8], [98.8, 100.6, 99.2, 100.4], [98.0, 98.2, 97.0, 97.5]]
    R, PN, EB, ET, XB = run(bars, od=1, side=BREAKOUT, wo=98.0)
    assert EB == 1 and ET == 2
    fill = 100.25 + TICK
    n = int(np.floor(BUDGET / ((fill - 99) * PV)))
    # bar 2 opens 98.0 below the stop 99 -> filled at the open minus slippage
    assert abs(PN - n * ((98.0 - TICK - fill) * PV - COMM)) < 1e-9
