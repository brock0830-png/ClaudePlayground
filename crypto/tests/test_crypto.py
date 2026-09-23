import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import cdata  # noqa: E402
import events  # noqa: E402
import indicators as ind  # noqa: E402
import portfolio as pf  # noqa: E402

USER = Path(__file__).resolve().parents[1] / "data" / "user"


def _bars(n=300, seed=0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.005, n))
    l = np.minimum(o, c) * (1 - rng.uniform(0, 0.005, n))
    idx = pd.date_range("2025-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": rng.uniform(1, 2, n)}, idx)


@pytest.mark.parametrize("name", ["SOLBTC_30m", "AVAXBTC_30m", "ETHBTC_15m"])
def test_parity_with_client_exports(name):
    df = pd.read_parquet(USER / f"{name}.parquet")
    z = ind.zscore(df.close, 20)
    m = z.notna()
    assert (z[m] - df.scr_z[m]).abs().max() < 1e-6
    sc, bc = ind.td_setup_counts(df.close)
    assert ((bc == 9).astype(int) == df.scr_buy9).all() and ((sc == 9).astype(int) == df.scr_sell9).all()
    assert ((bc == 13).astype(int) == df.scr_buy13_consec).all()
    s13, b13 = ind.td_countdown(df.close, df.high, df.low)
    assert (b13.astype(int) == df.scr_buy13_countdown).all() and (s13.astype(int) == df.scr_sell13_countdown).all()
    up, dn = ind.ema_stack(df.close)
    assert (up.astype(int) == df.scr_stack_up).all() and (dn.astype(int) == df.scr_stack_dn).all()
    b, s = ind.tdz_signals(df, mode="export")
    assert (b.astype(int) == df.scr_conf_buy).all() and (s.astype(int) == df.scr_conf_sell).all()


def test_indicators_are_causal():
    df = _bars(400)
    cut = 250
    fns = [lambda d: ind.zscore(d.close, 20), lambda d: ind.sigmajanus_fast(d.close), lambda d: ind.ema(d.close, 50),
           lambda d: ind.capitulation(d, 2.0, 1.0).astype(float), lambda d: ind.donchian_trend(d.close, 20),
           lambda d: ind.tdz_signals(d, mode="export")[0].astype(float), lambda d: ind.td_countdown(d.close, d.high, d.low)[1].astype(float)]
    for f in fns:
        full = f(df).iloc[:cut]
        part = f(df.iloc[:cut])
        pd.testing.assert_series_equal(full, part, check_names=False)


def test_rsi_matches_wilder_reference():
    x = pd.Series([44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28,
                   46.28, 46.00, 46.03, 46.41, 46.22, 45.64])
    r = ind.rsi(x, 14)
    assert abs(r.iloc[14] - 70.46) < 0.1  # classic Wilder worked example


def test_event_fills_and_no_overlap():
    df = _bars(100)
    sig = pd.Series(False, df.index)
    sig.iloc[[10, 12, 30]] = True
    w = (df.index[0], df.index[-1])
    tr = events.trades(df, sig, 8, "long", w, 0.001)
    assert list(tr.entry_time) == [df.index[11], df.index[31]]  # the signal at 12 is skipped (still in trade)
    r0 = df.open.iloc[19] / df.open.iloc[11] - 1
    assert abs(tr.gross.iloc[0] - r0) < 1e-12 and abs(tr.net.iloc[0] - (r0 - 0.002)) < 1e-12
    tr_s = events.trades(df, sig, 8, "short", w, 0.0)
    assert abs(tr_s.gross.iloc[0] + r0) < 1e-12
    trd = events.trades(df, sig, 8, "long", w, 0.0, delay=1)
    assert trd.entry_time.iloc[0] == df.index[12]


def test_event_window_excludes_trades_exiting_after_end():
    df = _bars(100)
    sig = pd.Series(False, df.index)
    sig.iloc[90] = True
    tr = events.trades(df, sig, 8, "long", (df.index[0], df.index[95]), 0.0)
    assert len(tr) == 0


def test_portfolio_buy_and_hold_matches_price():
    idx = pd.date_range("2020-01-01", periods=50, freq="D", tz="UTC")
    c = pd.DataFrame({"A": np.linspace(100, 150, 50)}, idx)
    o = c.shift(1).fillna(100.0)
    W = pd.DataFrame({"A": 1.0}, idx)
    R = pd.Series(False, idx)
    R.iloc[0] = True
    res = pf.simulate(W, R, o, c, pd.Series({"A": 0.0}))
    assert abs(res["equity"].iloc[-1] - c.A.iloc[-1] / o.A.iloc[1]) < 1e-9
    res2 = pf.simulate(W, R, o, c, pd.Series({"A": 0.01}))
    assert abs(res2["equity"].iloc[-1] - 0.99 * c.A.iloc[-1] / o.A.iloc[1]) < 2e-4
    assert (res2["equity"] - res2["held"].sum(axis=1)).min() >= 0  # cash never negative


def test_holdout_lock():
    if cdata.UNLOCK.exists():
        pytest.skip("holdout already unlocked")
    with pytest.raises(RuntimeError):
        cdata.check_lock(cdata.DAILY_HOLDOUT[1], "1D")


def test_clustered_t_survives_object_dtype():
    df = _bars(200)
    sig = pd.Series(False, df.index)
    sig.iloc[[10, 40, 70, 100, 130]] = True
    tr = events.trades(df, sig, 4, "long", (df.index[0], df.index[-1]), 0.0, sym="A")
    empty = events.trades(df, pd.Series(False, df.index), 4, "long", (df.index[0], df.index[-1]), 0.0, sym="B")
    mixed = pd.concat([tr, empty], ignore_index=True)
    assert np.isfinite(events.clustered_t(mixed))
