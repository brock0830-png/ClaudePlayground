import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import perp_research as pr  # noqa: E402

H4 = pd.Timedelta("4h")


def _df(n=400, prem=-0.02, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="4h", tz="UTC")
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.002, "low": np.minimum(o, c) * 0.998, "close": c,
                         "volume": rng.uniform(1, 2, n), "oi": 1000 * np.exp(np.cumsum(rng.normal(0, 0.01, n))),
                         "prem": prem, "prem_open": prem, "prem_mid": prem}, idx)


def test_funding_formula_matches_binance_clamp():
    for p, want in ((-0.02, 0.0001), (0.10, 0.0005), (-0.08, -0.0003), (0.0, 0.0001), (2.0, 0.0075)):
        s = pd.Series(p, pd.date_range("2025-01-01", periods=12, freq="4h", tz="UTC"))
        f = pr.funding_from_premium(s, H4)
        assert len(f) and np.allclose(f.to_numpy(), want), (p, f.iloc[0])
        assert set(f.index.hour) <= {0, 8, 16}


def test_funding_charged_only_between_entry_and_exit():
    df = _df(20)
    sig = pd.Series(False, df.index)
    sig.iloc[0] = True  # signal on the 00:00 bar -> entry 04:00, H=2 -> exit 12:00: only the 08:00 print applies
    fund = pd.Series(0.001, pd.date_range("2025-01-01", periods=10, freq="8h", tz="UTC"))
    tr = pr.trades(df, sig, 2, "long", (df.index[0], df.index[-1]), 0.0, fund)
    assert abs(tr.funding.iloc[0] - 0.001) < 1e-12
    assert abs(tr.net.iloc[0] - (tr.gross.iloc[0] - 0.001)) < 1e-12
    ts = pr.trades(df, sig, 2, "short", (df.index[0], df.index[-1]), 0.0, fund)
    assert abs(ts.net.iloc[0] - (ts.gross.iloc[0] + 0.001)) < 1e-12


def test_signals_are_causal():
    df = _df(500)
    cut = 350
    for hyp, p in (("P1", {"k": 2, "m": 1.5}), ("P2", {"z0": 1.5, "z1": 1}), ("P3", {"N": 20, "filter": True}), ("P4", {"N": 20})):
        for side in ("long", "short"):
            a = pr.signal(hyp, p, side, df).iloc[:cut]
            b = pr.signal(hyp, p, side, df.iloc[:cut])
            assert (a.fillna(False) == b.fillna(False)).all(), (hyp, side)


def test_carry_constant_funding(monkeypatch):
    df = _df(600, prem=-0.02)  # funding 0.01% per 8h, flat basis
    monkeypatch.setattr(pr, "load", lambda c, iv="4h": df)
    monkeypatch.setattr(pr, "funding", lambda c, iv="4h": pr.funding_from_premium(df["prem_mid"], H4))
    w = (df.index[0], df.index[-1])
    r, n = pr.carry(0.01, w, coins=["BTC"])
    assert n == 1
    notional = 1 / 1.5
    leg = pr.spot_cost("BTC") + pr.perp_cost("BTC")
    held = (r > 0).sum()
    assert abs(r.sum() - (held * 0.0001 * notional - leg * notional)) < 1e-12
