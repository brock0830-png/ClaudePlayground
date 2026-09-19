import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import numpy as np, pandas as pd, pytest
from engine import run, CostModel, BASE_LAG

rng = np.random.default_rng(0)
N = 400
idx = pd.bdate_range("2010-01-01", periods=N)
R = pd.DataFrame({"A": rng.normal(0, 0.01, N), "B": rng.normal(0, 0.02, N)}, idx)
CASH = pd.Series(0.0001, idx)
ZERO = CostModel(multiplier=0.0)


def test_base_lag_is_two_days():
    assert BASE_LAG == 2


def test_return_on_day_s_depends_only_on_weights_up_to_s_minus_2():
    w = pd.DataFrame({"A": rng.uniform(0, 0.5, N), "B": rng.uniform(0, 0.5, N)}, idx)
    base = run(w, R, CASH, ZERO).returns
    s = 200
    w2 = w.copy(); w2.iloc[s - 1] = [0.9, 0.1]; w2.iloc[s] = [0.1, 0.9]   # perturb t = s-1 and s
    pert = run(w2, R, CASH, ZERO).returns
    assert np.allclose(base.iloc[:s + 1], pert.iloc[:s + 1])              # day s (and before) unchanged
    assert not np.allclose(base.iloc[s + 1], pert.iloc[s + 1])            # day s+1 changed (w at s-1 executed at s)


def test_perfect_foresight_of_next_day_has_no_edge_at_base_lag():
    # weight decided at t using R[t+1] (illegal lookahead). With lag=1 it wins; with lag=2 it cannot.
    fut = R["A"].shift(-1)
    w = pd.DataFrame({"A": (fut > 0).astype(float), "B": 0.0}, idx)
    cheat = run(w, R, CASH, ZERO, lag=1).returns
    honest = run(w, R, CASH, ZERO, lag=2).returns
    assert (cheat > -1e-12).all()                      # never loses: proves lag=1 leaks the future
    assert (honest < -1e-12).sum() > 50                # base engine takes losses: the future is not usable


def test_buy_and_hold_matches_asset_exactly_with_zero_cost():
    w = pd.DataFrame({"A": 1.0, "B": 0.0}, idx)
    res = run(w, R, CASH, ZERO)
    # first held day is index 2 (decide 0, trade close 1, earn 2)
    assert np.allclose(res.returns.iloc[2:], R["A"].iloc[2:])
    assert np.allclose(res.returns.iloc[:1], CASH.iloc[:1])
    assert res.turnover.iloc[1] == pytest.approx(1.0)
    assert res.turnover.iloc[2:].sum() == pytest.approx(0.0, abs=1e-12)   # no drift trades for a single 100% asset


def test_all_cash_earns_cash_rate():
    w = pd.DataFrame({"A": 0.0, "B": 0.0}, idx)
    res = run(w, R, CASH, ZERO)
    assert np.allclose(res.returns, CASH)


def test_costs_reduce_return_by_turnover_times_rate():
    w = pd.DataFrame({"A": 0.5, "B": 0.5}, idx)
    cm = CostModel(commission_bp=2, default_half_spread_bp=1, multiplier=1)
    res0 = run(w, R, CASH, ZERO); res1 = run(w, R, CASH, cm)
    diff = res0.returns - res1.returns
    assert np.allclose(diff, res1.turnover * 3e-4)


def test_rejects_leverage_and_shorts():
    with pytest.raises(ValueError):
        run(pd.DataFrame({"A": 0.8, "B": 0.5}, idx), R, CASH, ZERO)
    with pytest.raises(ValueError):
        run(pd.DataFrame({"A": -0.1, "B": 0.5}, idx), R, CASH, ZERO)


def test_nan_return_in_future_does_not_affect_past():
    R2 = R.copy(); R2.iloc[300, 0] = np.nan
    w = pd.DataFrame({"A": 0.6, "B": 0.4}, idx)
    a = run(w, R, CASH, ZERO).returns; b = run(w, R2, CASH, ZERO).returns
    assert np.allclose(a.iloc[:300], b.iloc[:300])


def test_extra_delay_shifts_holdings_by_one_day():
    w = pd.DataFrame({"A": (np.arange(N) % 7 == 0).astype(float), "B": 0.0}, idx)
    r2 = run(w, R, CASH, ZERO, lag=2); r3 = run(w, R, CASH, ZERO, lag=3)
    assert np.allclose(r2.weights_held["A"].iloc[2:-1].to_numpy(), r3.weights_held["A"].iloc[3:].to_numpy())
