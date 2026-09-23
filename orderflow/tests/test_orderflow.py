import io
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest

from of import aggtrades, profile, signals, va_features
from of.config import COST_RT

rng = np.random.default_rng(1)


# ---------- profiles ----------

def test_value_area_expands_one_row_toward_higher_side():
    h = np.array([1, 2, 10, 30, 8, 5, 1, 0, 0, 43], float)   # total 100, POC row 9 (43)
    va = profile.value_area(h, 0.0, 10.0)
    assert va.poc == pytest.approx(9.5)
    # from row 9 only downward: 43+0+0+1+5+8=57, +30=87 >= 70
    assert va.val == pytest.approx(3.0) and va.vah == pytest.approx(10.0)


def test_value_area_tie_goes_up_and_poc_tie_goes_to_middle():
    h = np.array([5, 20, 5, 5, 20, 5], float)
    va = profile.value_area(h, 0.0, 6.0)
    assert va.poc == pytest.approx(1.5) or va.poc == pytest.approx(4.5)
    # rows 1 and 4 are equidistant from the middle (2.5) -> lower row wins
    assert va.poc == pytest.approx(1.5)
    va = profile.value_area(np.array([0, 10, 40, 10, 0], float), 0, 5)   # target 42: 40, then tie -> up
    assert (va.val, va.vah) == (pytest.approx(2.0), pytest.approx(4.0))


def test_profile_rows_cover_range_and_top_trade_in_last_row():
    p = np.array([100.0, 100.5, 101.0, 105.0])
    r = profile.rows_of(p, 100.0, 105.0, 50)
    assert r.tolist() == [0, 5, 10, 49]
    va = profile.profile_from_trades(p, np.ones(4))
    assert va.lo == 100 and va.hi == 105 and va.hist.sum() == 4


def test_profile_from_bars_conserves_volume():
    l = rng.uniform(90, 100, 200); hgh = l + rng.uniform(0, 5, 200); v = rng.uniform(1, 10, 200)
    va = profile.profile_from_bars(l, hgh, v)
    assert va.hist.sum() == pytest.approx(v.sum())


# ---------- signal and trades ----------

def _hourly(n=24 * 40, drop_at=24 * 20):
    idx = pd.date_range("2022-01-01", periods=n, freq="1h", tz="UTC")
    c = np.full(n, 100.0); oi = np.full(n, 1e9)
    c[drop_at:] = 94.0; oi[drop_at:] = 0.97e9       # -6% price, -3% OI from bar drop_at on
    h = pd.DataFrame({"o": c, "h": c, "l": c, "c": c, "oi_usd": oi}, idx)
    h.loc[idx[drop_at + 1:], "o"] = 94.0
    h.loc[idx[drop_at + 25]:, ["o", "c"]] = 96.0     # price recovers at bar drop_at+25
    return h


def test_signal_fires_for_24_bars_and_nonoverlap_keeps_one():
    h = _hourly()
    cond = signals.flush_condition(h)
    fired = cond.index[cond.values]
    assert len(fired) == 24 and fired[0] == h.index[24 * 20]
    assert len(signals.dedup(fired, "nonoverlap")) == 1
    assert len(signals.dedup(fired, "episode")) == 1


def test_trade_entry_exit_costs_and_funding():
    h = _hourly()
    t0 = h.index[24 * 20]
    f = pd.Series([0.0001, 0.0002, 0.0003, 0.0004],
                  index=pd.DatetimeIndex([t0, t0 + pd.Timedelta("1h"), t0 + pd.Timedelta("9h"), t0 + pd.Timedelta("25h")]))
    tr = signals.trades("X", h, f)
    assert len(tr) == 1
    r = tr.iloc[0]
    assert r.entry_t == t0 + pd.Timedelta("1h") and r.exit_t == t0 + pd.Timedelta("25h")
    assert r.entry == 94.0 and r.exit == 96.0
    # funding stamps in [entry, exit): +1h and +9h only
    assert r.fund == pytest.approx(0.0005)
    assert r.net == pytest.approx(96 / 94 - 1 - COST_RT - 0.0005)


# ---------- aggTrades ----------

def _zip(csv: str) -> io.BytesIO:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x.csv", csv)
    b.seek(0)
    return b


@pytest.mark.parametrize("hdr", [True, False])
def test_aggtrades_parse_with_and_without_header(tmp_path, hdr):
    body = "1,10.5,2,1,1,1700000000200,true\n2,10.4,3,2,2,1700000000100,false\n"
    csv = ("agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n" if hdr else "") + body
    p = tmp_path / "a.zip"; p.write_bytes(_zip(csv).read())
    d = aggtrades.parse(p)
    assert d["ts"].tolist() == [1700000000100, 1700000000200]      # sorted by time
    assert d["sell"].tolist() == [False, True]                      # buyer-maker = aggressive sell
    assert d["p"].tolist() == [10.4, 10.5]


# ---------- features: no lookahead ----------

def _trades(t: pd.Timestamp, n=20000):
    a = int((t - pd.Timedelta("30h")).value // 1e6); b = int((t + pd.Timedelta("3h")).value // 1e6)
    ts = np.sort(rng.integers(a, b, n))
    p = 100 + np.cumsum(rng.normal(0, 0.05, n))
    return dict(p=p, q=rng.uniform(0.1, 2, n), ts=ts, sell=rng.random(n) < 0.5)


def test_features_ignore_trades_after_signal_close():
    t = pd.Timestamp("2023-05-05 12:00", tz="UTC")
    d = _trades(t)
    ms = lambda x: int(x.value // 1_000_000)
    def feats(dd):
        w0 = aggtrades.window([dd], ms(t - pd.Timedelta("29h")), ms(t - pd.Timedelta("5h")))
        w1 = aggtrades.window([dd], ms(t - pd.Timedelta("5h")), ms(t + pd.Timedelta("1h")))
        return va_features.features_for(w0, w1, 100.0, 1.0)
    base = feats(d)
    d2 = {k: v.copy() for k, v in d.items()}
    after = d2["ts"] >= ms(t + pd.Timedelta("1h"))
    assert after.sum() > 0
    d2["p"][after] = 1e6; d2["q"][after] = 1e6              # wreck everything after the close
    pert = feats(d2)
    for k in ["POC0", "VAL1", "POC1", "V1", "V2", "V3", "F1r"]:
        assert base[k] == pytest.approx(pert[k])


def test_f1r_zero_when_close_in_bottom_zone():
    w = dict(p=np.linspace(100, 110, 1000), q=np.ones(1000), ts=np.arange(1000), sell=np.ones(1000, bool))
    f = va_features.features_for(w, w, 100.5, 1.0)
    assert f["F1r"] == 0.0
    f = va_features.features_for(w, w, 105.0, 1.0)
    assert f["F1r"] == pytest.approx(0.1, abs=0.01)


# ---------- X1 exit ----------

def _m1(entry_t, path):
    idx = pd.date_range(entry_t, periods=len(path), freq="1min")
    p = np.asarray(path, float)
    return pd.DataFrame({"o": p, "h": p + 0.1, "l": p - 0.1, "c": p}, idx)


def test_x1_fills_at_first_touch_else_24h():
    e_t = pd.Timestamp("2023-01-01 01:00", tz="UTC"); x_t = e_t + pd.Timedelta("24h")
    path = np.full(24 * 60 + 5, 100.0); path[300] = 102.0
    m1 = _m1(e_t, path)
    f = pd.Series([0.001], index=pd.DatetimeIndex([e_t + pd.Timedelta("7h")]))
    row = pd.Series(dict(entry_t=e_t, exit_t=x_t, entry=100.0, POC0=101.5, net=-0.5))
    r = va_features.exit_x1(row, m1, f)
    assert r["x1_hit"] == 1 and r["x1_t"] == e_t + pd.Timedelta("300min")
    assert r["x1_net"] == pytest.approx(0.015 - COST_RT)            # funding at +7h not reached
    row["POC0"] = 105.0
    r = va_features.exit_x1(row, m1, f)
    assert r["x1_hit"] == 0 and r["x1_net"] == -0.5 and r["x1_t"] == x_t
    row["POC0"] = 99.0
    r = va_features.exit_x1(row, m1, f)
    assert r["x1_hit"] == 1 and r["x1_net"] == pytest.approx(-COST_RT)


# ---------- exploration events ----------

def _frame(n=72):
    from of import explore  # noqa: F401
    idx = pd.date_range("2023-03-06", periods=n, freq="1h", tz="UTC")      # a Monday
    X = pd.DataFrame(index=idx)
    X["c"] = 100.0; X["o"] = 100.0; X["h"] = 100.5; X["l"] = 99.5; X["delta"] = 0.0
    for k, v in dict(PDL=98.0, PDH=102.0, PDVAL=99.0, PDVAH=101.0, PWL=95.0, PWH=105.0, PWVAL=97.0, PWVAH=103.0,
                     dO=100.0, wO=100.0, dPOC=100.0).items():
        X[k] = v
    X["dL"] = X.l.groupby(idx.floor("D")).cummin(); X["dH"] = X.h.groupby(idx.floor("D")).cummax()
    X["wL"] = X.l.cummin(); X["wH"] = X.h.cummax()
    X["dVAH"] = 100.4; X["dVAL"] = 99.6
    for hd in (24,):
        X[f"L{hd}"] = 0.01; X[f"S{hd}"] = -0.01; X[f"fund{hd}"] = 0.0
    return X


def test_A1L_fires_once_on_first_reclaim_of_prior_day_low():
    from of import explore
    X = _frame()
    X.loc[X.index[5], "l"] = 97.0; X.loc[X.index[5], "c"] = 97.5          # trades and closes below PDL
    X.loc[X.index[6], "c"] = 98.5                                          # closes back above
    X.loc[X.index[8], "l"] = 97.2                                          # second dip same day: no new signal
    X["dL"] = X.l.groupby(X.index.floor("D")).cummin()
    trig, side, _ = explore.events(X)["A1L_fail_below_PDL"]
    fired = X.index[trig.values]
    assert side == 1 and list(fired) == [X.index[6]]


def test_A3S_needs_two_closes_below_in_same_day():
    from of import explore
    X = _frame()
    X.loc[X.index[23], "c"] = 97.0                     # last bar of day 1
    X.loc[X.index[24], "c"] = 97.0                     # first bar of day 2: different day -> no
    X.loc[X.index[30:32], "c"] = 97.0                  # two consecutive in day 2 -> fires at bar 31
    trig, side, _ = explore.events(X)["A3S_accept_below_PDL"]
    assert side == -1 and list(X.index[trig.values]) == [X.index[31]]


def test_tp_exit_hits_target_or_falls_back():
    from of import explore
    X = _frame()
    X.loc[X.index[10], "h"] = 101.2
    r = explore._tp_exit(X, 3, 1, 101.0, 24)
    assert r == pytest.approx(0.01 - COST_RT)
    assert explore._tp_exit(X, 3, 1, 150.0, 24) == pytest.approx(0.01)       # falls back to the 24h net
    assert explore._tp_exit(X, 3, 1, 99.0, 24) == pytest.approx(-COST_RT)     # target already through


def test_developing_profile_works_with_millisecond_index():
    from of import structure
    idx = pd.date_range("2024-01-01", periods=3 * 1440, freq="1min").as_unit("ms")    # pandas 3 keeps ms
    p = 100 + np.cumsum(rng.normal(0, 0.01, len(idx)))
    b = pd.DataFrame({"o": p, "h": p + 0.02, "l": p - 0.02, "c": p, "v": 1.0, "tbv": 0.5}, idx)
    hours = pd.date_range("2024-01-01", periods=72, freq="1h")
    D = structure._developing(b, pd.Series(hours.floor("D"), index=hours), hours, "d")
    assert len(D) == 72 and D.dL.notna().all() and D.dtypes.eq(float).all()
    assert D.dVOL.iloc[0] == pytest.approx(60) and D.dVOL.iloc[23] == pytest.approx(1440)
