"""Phase 3 engine checks."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scalpel.data import load_bars
from scalpel import p3


def synth(rows):
    D = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    D["date"] = pd.date_range("2000-01-03", periods=len(D), freq="B")
    D["atr20"] = 10.0
    D["sig"] = [1.0] + [0.0] * (len(D) - 1)
    D["zero"] = 0.0
    D["roll"] = False
    D["sym"] = "X"
    return D


def test_reproduces_p2a_on_es_dev():
    D = p3.es_daily(load_bars("dev"))
    t = p3.simulate(D, dict(entry=["ibs<0.3", "vix>20"], hold=5), "next_open")
    assert len(t) == 42 and abs(t["pnl"].mean() - 27.483) < 1e-3


def test_stop_fills_first_when_both_hit():
    # entry at close 100; next day high 120 (target 110) and low 85 (stop 90): stop wins
    D = synth([[100, 101, 99, 100], [100, 120, 85, 100], [100, 101, 99, 100]])
    t = p3.simulate(D, dict(entry=["sig>0.5"], tgt=1.0, stop=1.0, hold=5), "close")
    assert t["why"].iat[0] == "stop" and t["px_out"].iat[0] == 90


def test_gap_through_stop_fills_at_open():
    D = synth([[100, 101, 99, 100], [80, 82, 78, 81], [81, 82, 80, 81]])
    t = p3.simulate(D, dict(entry=["sig>0.5"], stop=1.0, hold=5), "close")
    assert t["px_out"].iat[0] == 80


def test_time_exit_next_open_counts_sessions():
    D = synth([[100, 101, 99, 100]] + [[100 + i, 101 + i, 99 + i, 100 + i] for i in range(1, 10)])
    t = p3.simulate(D, dict(entry=["sig>0.5"], hold=3), "next_open")
    # signal close 0 -> entry open 1 -> holds sessions 1,2,3 -> exit at open 4
    assert (t["entry"].iat[0], t["exit"].iat[0]) == (1, 4) and t["px_out"].iat[0] == 104


def test_test_markets_locked():
    if p3.TEST_LOCK.exists():
        pytest.skip("already unlocked")
    with pytest.raises(PermissionError):
        p3.etf_daily("QQQ")
