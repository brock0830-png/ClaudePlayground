"""Phase 2 engine checks (DEV data only)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scalpel.data import load_bars
from scalpel import p2
from p2_screen import grids, eval_es


@pytest.fixture(scope="module")
def ctx():
    return p2.es_context(load_bars("dev"))


def test_trades_sum_to_bar_pnl(ctx):
    rng = np.random.default_rng(0)
    for spec in grids()[::37]:
        if spec["kind"] == "session":
            tgt = p2.session_target(ctx, spec)
        else:
            td = p2.daily_target(ctx["D"], spec)
            if td is None:
                continue
            tgt = p2.bar_target_from_daily(ctx, td)
        res = p2.run_bars(ctx, tgt, 0, len(ctx["o"]))
        assert abs(res["trades"]["net"].sum() - res["pnl"].sum()) < 1e-6, spec
        ev = eval_es(ctx, tgt, 0, len(ctx["o"]), rng, range(2013, 2020))
        if ev["n"]:
            assert abs(ev["total"] - res["pnl"].sum()) < 1e-6, spec


def test_no_lookahead_daily(ctx):
    # a daily target must not change inside a session: it is decided at the session's last bar only
    td = p2.daily_target(ctx["D"], dict(kind="entry_exit", entry=["rsi2<10"], exit="close>ma5", filters=[], side="long"))
    tb = p2.bar_target_from_daily(ctx, td)
    chg = np.flatnonzero(np.diff(tb) != 0) + 1          # bars where the target changes
    assert ctx["last_of_day"][chg].all()


def test_turn_of_month_days(ctx):
    D = ctx["D"]
    td = p2.daily_target(D, dict(kind="calendar", cal=["tom", 1, 2], side="long"))
    held_next = np.r_[0.0, td[:-1]]                       # sessions actually held
    held = D.loc[held_next != 0, ["tdm", "tdm_rev"]]
    assert set(held["tdm"]) == {1, 2}


def test_session_hours(ctx):
    tgt = p2.session_target(ctx, dict(hours=[18, 22, 2, 6], side="long", filters=[]))
    hold = np.r_[0.0, tgt[:-1]]
    assert set(ctx["hour"][hold != 0]) == {18, 22, 2, 6}
