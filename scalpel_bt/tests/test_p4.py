import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest

from scalpel import p3, p4


def _frame(n=600, drift=0.001, sym="TEST", seed=0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.01, n)))
    o = c * (1 + rng.normal(0, 0.002, n))
    h = np.maximum(o, c) * 1.003
    l = np.minimum(o, c) * 0.997
    D = pd.DataFrame({"date": pd.bdate_range("2010-01-01", periods=n), "open": o, "high": h, "low": l, "close": c,
                      "vix": 22.0, "roll": False, "sym": sym})
    D["atr20"] = (D.high - D.low).rolling(20).mean()
    D["ibs"] = (D.close - D.low) / (D.high - D.low)
    return D


def test_random_entries_match_drift_minus_cost():
    D = _frame(drift=0.002, seed=1)
    t = pd.DataFrame({"sessions": [5] * 200})
    rng = np.random.default_rng(0)
    draws = p4.random_entries(D, t, "close", 0, 590, rng, n_draws=300)
    C = D.close.values
    exact = np.mean([(C[s + 5] - C[s] - p3.ETF_RT_PCT * C[s]) / C[s] for s in range(0, 590) if s + 5 < 600])
    assert abs(draws.mean() - exact) < 0.0015
    assert draws.std() > 0


def test_random_entries_respect_eligible_mask():
    D = _frame(seed=2)
    C = D.close.values
    elig = np.zeros(len(D), bool)
    elig[100] = True                                      # only one possible entry day
    t = pd.DataFrame({"sessions": [5, 5, 5]})
    draws = p4.random_entries(D, t, "close", 0, len(D), np.random.default_rng(0), n_draws=50, eligible=elig)
    one = (C[105] - C[100] - p3.ETF_RT_PCT * C[100]) / C[100]
    assert np.allclose(draws, one)


def test_highvix_adds_two_ticks_only_when_vix_above_25():
    D = _frame(seed=3)
    D.loc[:299, "vix"] = 30.0
    t = pd.DataFrame({"sessions": [5] * 50})
    base = p4.random_entries(D, t, "close", 0, 300, np.random.default_rng(5), n_draws=40)
    hv = p4.random_entries(D, t, "close", 0, 300, np.random.default_rng(5), n_draws=40, highvix=True)
    assert np.all(hv < base)
    lo = p4.random_entries(D, t, "close", 320, 590, np.random.default_rng(5), n_draws=40)
    lo_hv = p4.random_entries(D, t, "close", 320, 590, np.random.default_rng(5), n_draws=40, highvix=True)
    assert np.allclose(lo, lo_hv)


@pytest.mark.parametrize("mode", ["close", "next_open"])
def test_daily_mtm_sums_to_trade_pnl(mode):
    D = _frame(seed=4)
    spec = {"entry": ["ibs<0.3"], "hold": 5}
    t = p3.simulate(D, spec, mode, 30, 580)
    assert len(t) > 5
    m = p4.daily_mtm(D, t, mode, unit="pts")
    assert m.sum() == pytest.approx(t["pnl"].sum())
    mp = p4.daily_mtm(D, t, mode, unit="pct")
    assert mp.sum() == pytest.approx((t["pnl"] / t["px_in"]).sum())


def test_month_ci_point_is_pooled_mean_and_paired_zero_for_identical_arms():
    d = pd.Series(pd.date_range("2015-01-01", periods=300, freq="3D"))
    x = pd.Series(np.random.default_rng(1).normal(0.01, 0.02, 300))
    m, lo, hi = p4.month_ci(x, d)
    assert m == pytest.approx(x.mean()) and lo < m < hi
    a = pd.DataFrame({"date": d, "excess": x})
    pt, plo, phi = p4.paired_month_ci(a, a)
    assert pt == 0 and plo == 0 and phi == 0


def test_p4_trades_reproduce_phase3_p2a_on_qqq():
    old = pd.read_csv(p4.RESULTS / "p3" / "test_trades_P2A_reference.csv", parse_dates=["date"])
    old = old[old.sym == "QQQ"].reset_index(drop=True)
    D = p4.load_etf("QQQ")
    i0, i1 = 252, int(np.searchsorted(D["date"].values, np.datetime64("2026-09-19")))
    t = p4.trades(D, p4.P2A, "close", i0, i1)
    k = min(len(t), len(old)) - 1                         # the last trade may differ (data end)
    assert np.allclose(t["ret"].values[:k], old["ret"].values[:k])


def test_logger_signal_then_in_position_and_append_only(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import p4_signal_logger as lg
    es = p4.load_es("all")
    t = p4.trades(es, p4.P2A, "next_open", 0, len(es) - 10)
    sig_date = pd.Timestamp(es["date"].iat[int(t["sig"].iat[-1])])
    bars = es[["date", "open", "high", "low", "close"]]
    v = p3.load_vix("VIX")
    r0 = {r["system"]: r for r in lg.evaluate(bars, v, "ES", sig_date)}
    assert r0["P2A"]["signal"] == 1 and r0["P2A"]["in_position"] == 0
    nxt = pd.Timestamp(es["date"].iat[int(t["sig"].iat[-1]) + 1])
    r1 = {r["system"]: r for r in lg.evaluate(bars, v, "ES", nxt)}
    assert r1["P2A"]["in_position"] == 1 and r1["P2A"]["signal"] == 0
    monkeypatch.setattr(lg, "LOG", tmp_path / "log.csv")
    row = dict(r0["P2A"], logged_utc="x", source="test")
    lg.append([row])
    before = (tmp_path / "log.csv").read_text()
    assert (row["date"], "ES", "P2A") in lg.logged_keys()
    lg.append([dict(r1["P2A"], logged_utc="y", source="test")])
    after = (tmp_path / "log.csv").read_text()
    assert after.startswith(before)                        # earlier rows untouched
