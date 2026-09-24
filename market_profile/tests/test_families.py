"""Every hypothesis generator on a synthetic market: runs, produces sane trades, and never uses
information from after its own exit (changing later prices leaves earlier trades untouched)."""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from mp.engine import Ctx, Baseline, run_trades, evaluate, simulate, Trade  # noqa: E402
from mp.features import session_features, cross_session  # noqa: E402
from mp.families import FAMILIES  # noqa: E402

N_SESS = 160


def synth(seed=0, n=N_SESS, shock_from=None):
    rng = np.random.default_rng(seed)
    parts, rows, px, b = [], [], 16000, 0
    for d in range(n):
        drift = rng.normal(0, 0.15)
        steps = np.rint(rng.normal(drift, 2.2, 405)).astype(int)
        if shock_from is not None and d >= shock_from:
            steps = steps + rng.integers(-2, 3, 405)
        path = px + np.concatenate([[0], np.cumsum(steps)])
        o, c = path[:-1], path[1:]
        h = np.maximum(o, c) + rng.integers(0, 2, 405)
        l = np.minimum(o, c) - rng.integers(0, 2, 405)
        parts.append(pd.DataFrame({"o": o, "h": h, "l": l, "c": c, "v": rng.integers(50, 500, 405),
                                   "minute": 570 + np.arange(405), "session": d}))
        on = px + np.sort(rng.integers(-40, 40, 2))
        rows.append(dict(date=pd.Timestamp("2012-01-02") + pd.tseries.offsets.BDay(d), early_close=False,
                         b0=b, b1=b + 405, offset_t=0, on_lo_t=float(min(on[0], o[0])), on_hi_t=float(max(on[1], o[0]))))
        b += 405
        px = int(c[-1]) + int(rng.integers(-20, 21))
    bars = pd.concat(parts, ignore_index=True)
    S = pd.DataFrame(rows)
    feats = [session_features(*(bars.iloc[r.b0:r.b1][k] for k in ("o", "h", "l", "c", "v", "minute")))
             for r in S.itertuples()]
    return Ctx("ES", bars, S, cross_session(S, bars, feats), feats)


@pytest.fixture(scope="module")
def ctx():
    return synth()


@pytest.mark.parametrize("fam,gen,btype,variants", FAMILIES, ids=[f[0] for f in FAMILIES])
def test_family_runs_and_trades_are_sane(ctx, fam, gen, btype, variants):
    base = Baseline(ctx)
    for v in variants:
        tr = run_trades(ctx, gen(ctx, v))
        st = evaluate(ctx, base, tr, btype)
        if tr.empty:
            continue
        assert set(tr["side"]) <= {-1, 1}
        assert (tr["k_exit"] >= tr["k_entry"]).all()
        assert (tr["k_entry"].iloc[1:].to_numpy() >= tr["k_exit"].iloc[:-1].to_numpy()).all()   # one at a time
        assert np.isclose(tr["net"], tr["gross"] - 2.4).all()
        assert st["n_trades"] == len(tr)


def test_most_families_fire_on_a_random_walk(ctx):
    fired = [fam for fam, gen, _, vs in FAMILIES if len(gen(ctx, vs[0]))]
    assert len(fired) >= 25, sorted(set(f[0] for f in FAMILIES) - set(fired))


@pytest.mark.parametrize("fam,gen,btype,variants", FAMILIES, ids=[f[0] for f in FAMILIES])
def test_no_lookahead(fam, gen, btype, variants):
    cut = 110
    a, b = synth(seed=3), synth(seed=3, shock_from=cut)
    kcut = a.k_start(cut)
    assert (a.P[:kcut] == b.P[:kcut]).all() and not (a.P[kcut:] == b.P[kcut:]).all()
    for v in variants:
        ta = run_trades(a, gen(a, v))
        tb = run_trades(b, gen(b, v))
        ea = ta[ta["k_exit"] < kcut] if len(ta) else ta
        eb = tb[tb["k_exit"] < kcut] if len(tb) else tb
        cols = ["k_entry", "k_exit", "side", "entry", "exit", "why"]
        assert len(ea) == len(eb)
        if len(ea):
            pd.testing.assert_frame_equal(ea[cols].reset_index(drop=True), eb[cols].reset_index(drop=True))


# ---------------------------------------------------------------- fill mechanics
def test_stop_fills_at_level_inside_a_bar_and_at_open_on_a_gap(ctx):
    d = 5
    k = ctx.k_open(d, 600)
    px = int(ctx.P[k])
    seg = ctx.P[k + 1:ctx.k_close(d) + 1]
    stop = px - 3
    r = simulate(ctx, Trade(d=d, k=k, px=px, side=1, tau=600, exit=("close", 0), stop=stop))
    hit = np.flatnonzero(seg <= stop)
    if len(hit):
        kk = k + 1 + hit[0]
        assert r["why"] == "stop" and r["k_exit"] == kk
        assert r["exit"] == (ctx.P[kk] if ctx.jump[kk] else stop)
    else:
        assert r["why"] == "time"


def test_bar_path_order():
    from mp.path import bar_points
    assert list(bar_points([10], [12], [9], [11])) == [10, 9, 12, 11]      # up bar: low first
    assert list(bar_points([10], [12], [9], [9])) == [10, 12, 9, 9]       # down bar: high first


# ---------------------------------------------------------------- hand-built trades
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from helpers import bars_from_path, bars_from_periods  # noqa: E402
from mp import families as fm  # noqa: E402


def ctx_from(bars_list):
    parts, rows, b = [], [], 0
    for i, bs in enumerate(bars_list):
        bs = bs.copy(); bs["session"] = i
        parts.append(bs)
        rows.append(dict(date=pd.Timestamp("2015-01-05") + pd.tseries.offsets.BDay(i), early_close=False,
                         b0=b, b1=b + len(bs), offset_t=0, on_hi_t=np.nan, on_lo_t=np.nan))
        b += len(bs)
    bars = pd.concat(parts, ignore_index=True)
    S = pd.DataFrame(rows)
    feats = [session_features(*(bars.iloc[r.b0:r.b1][k] for k in ("o", "h", "l", "c", "v", "minute"))) for r in S.itertuples()]
    return Ctx("ES", bars, S, cross_session(S, bars, feats), feats)


def flat(lo, hi):
    return bars_from_periods([(lo, lo, hi, lo)] * 14)


def test_mp12_breakout_then_mp12b_failed_breakout():
    day = bars_from_path([(0, 110), (30, 125), (60, 115), (120, 95), (405, 97)])
    c = ctx_from([flat(100, 120)] * 3 + [day])
    assert (c.D["bal3_lo"].iloc[2], c.D["bal3_hi"].iloc[2]) == (100, 120)
    t12 = run_trades(c, fm.mp12(c, dict(bal=3)))
    assert len(t12) == 1 and t12["side"].iloc[0] == 1 and t12["entry"].iloc[0] == 122
    assert t12["why"].iloc[0] == "stop" and t12["exit"].iloc[0] == 116
    t12b = run_trades(c, fm.mp12b(c, dict(bal=3)))
    assert len(t12b) == 1 and t12b["side"].iloc[0] == -1 and t12b["entry"].iloc[0] == 98
    assert t12b["why"].iloc[0] == "time" and t12b["exit"].iloc[0] == 97


def test_mp1_value_area_rule():
    prior = flat(100, 140)
    va = ctx_from([prior, prior]).D[["val", "vah"]].iloc[0]
    # opens 10 ticks above VAH, A and B trade back inside, then falls to VAL
    day = bars_from_path([(0, va.vah + 10), (20, va.vah - 2), (60, va.vah - 3), (200, va.val - 1), (405, va.val)])
    c = ctx_from([prior, day])
    t = run_trades(c, fm.mp1(c, dict(va="tpo")))
    assert len(t) == 1 and t["side"].iloc[0] == -1 and t["tau"].iloc[0] == 630     # end of B
    assert t["why"].iloc[0] == "target" and t["exit"].iloc[0] == va.val


def test_mp2_open_drive_long_from_ten():
    day = bars_from_path([(0, 1000), (5, 1004), (60, 1040), (405, 1060)])
    c = ctx_from([flat(900, 1100), day])
    t = run_trades(c, fm.mp2(c, {}))
    assert len(t) == 1 and t["side"].iloc[0] == 1 and t["tau"].iloc[0] == 600
    assert t["exit"].iloc[0] == 1060 and t["net"].iloc[0] == 1060 - t["entry"].iloc[0] - 2.4


def test_mp13_neutral_extreme_close_to_next_eleven():
    ne = bars_from_periods([(110, 100, 120, 110), (110, 104, 116, 110), (110, 95, 112, 110), (110, 106, 118, 112)]
                           + [(112, 108, 116, 112)] * 8 + [(112, 110, 125, 124), (124, 122, 125, 125)])
    nxt = bars_from_path([(0, 126), (90, 140), (405, 130)])
    c = ctx_from([flat(100, 120), ne, nxt])
    t = run_trades(c, fm.mp13(c, {}))
    assert len(t) == 1 and t["side"].iloc[0] == 1 and t["entry"].iloc[0] == 125
    assert t["exit"].iloc[0] == 140                       # next day 11:00 open


def test_mp23_confirmed_auction_point_retest():
    # IB 100-120, extends to 130 and closes 128 (> AP 121). Next day dips to 121 from above -> long at 121.
    d0 = bars_from_periods([(110, 100, 120, 118), (118, 104, 118, 118), (118, 118, 130, 128)] + [(128, 124, 130, 128)] * 11)
    d1 = bars_from_path([(0, 126), (60, 121), (405, 131)])
    c = ctx_from([flat(90, 130), d0, d1])
    t = run_trades(c, fm.mp23(c, {}))
    assert len(t) == 1 and t["side"].iloc[0] == 1 and t["entry"].iloc[0] == 121 and t["d"].iloc[0] == 2
    assert t["exit"].iloc[0] == 131


def test_drive05_threshold_is_half_the_median_a_range():
    D = pd.DataFrame({"med20_arange": [40.0, 40.0, np.nan], "od_dist": [20.0, 19.0, 30.0]})
    v = dict(drive_min=0.5)
    assert fm._drive_ok(D, 0, "od_dist", v) and not fm._drive_ok(D, 1, "od_dist", v)
    assert not fm._drive_ok(D, 2, "od_dist", v)                  # no 20-session history
    assert fm._drive_ok(D, 1, "od_dist", {})                     # primary definition unaffected


def test_drive05_is_a_subset_of_the_primary(ctx):
    for gen in (fm.mp2, fm.mp4):
        base = {t.d for t in gen(ctx, {})}
        var = {t.d for t in gen(ctx, fm.DRIVE05)}
        assert var <= base
