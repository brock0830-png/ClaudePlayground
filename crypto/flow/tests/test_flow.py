import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import flow_research as fr  # noqa: E402


def _panel(n=800, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="1h", tz="UTC")
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
    o = np.r_[c[0], c[:-1]]
    v = rng.uniform(100, 200, n)
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.001, "low": np.minimum(o, c) * 0.999, "close": c,
                         "volume": v, "quote_volume": v * c, "count": 1000, "taker_buy_volume": v * rng.uniform(0.3, 0.7, n),
                         "oi": 1e6, "top_pos": np.exp(rng.normal(0, 0.1, n)), "top_acc": 1.0,
                         "glob": np.exp(rng.normal(0, 0.1, n)), "taker_ratio": 1.0, "prem_open": -0.0001}, idx)


def test_signals_causal(monkeypatch):
    full = _panel()
    cut = 600
    for fam, p in (("F1", {"k": 2}), ("F2", {"k": 2}), ("F3", {"k": 1.5}), ("F4", {"N": 24}), ("F5", {"s": 1.5}), ("F6", {"g": 1.5})):
        for side in ("long", "short"):
            fr.feats.cache_clear()
            monkeypatch.setattr(fr, "load", lambda c, d=full: d)
            a = fr.signal(fam, p, side, "X").iloc[:cut]
            fr.feats.cache_clear()
            monkeypatch.setattr(fr, "load", lambda c, d=full.iloc[:cut]: d)
            b = fr.signal(fam, p, side, "X")
            assert (a.fillna(False) == b.fillna(False)).all(), (fam, side)
    fr.feats.cache_clear()


def test_panel_aggregates_15m_to_1h(tmp_path, monkeypatch):
    idx = pd.date_range("2024-01-01", periods=8, freq="15min", tz="UTC")
    k = pd.DataFrame({"open": np.arange(8.0), "high": np.arange(8.0) + 1, "low": np.arange(8.0) - 1, "close": np.arange(8.0) + 0.5,
                      "volume": 1.0, "quote_volume": 1.0, "count": 1.0, "taker_buy_volume": 0.25}, idx)
    m = pd.DataFrame({"sum_open_interest": np.arange(8.0), "sum_open_interest_value": 1.0, "count_toptrader_long_short_ratio": 1.0,
                      "sum_toptrader_long_short_ratio": 1.0, "count_long_short_ratio": 1.0, "sum_taker_long_short_vol_ratio": 1.0}, idx)
    k.to_parquet(tmp_path / "X_klines_15m.parquet")
    m.to_parquet(tmp_path / "X_metrics_15m.parquet")
    monkeypatch.setattr(fr, "BV", tmp_path)
    h = fr.build_panel("X")
    assert list(h["open"]) == [0.0, 4.0] and list(h["close"]) == [3.5, 7.5] and list(h["high"]) == [4.0, 8.0]
    assert list(h["volume"]) == [4.0, 4.0] and list(h["taker_buy_volume"]) == [1.0, 1.0]
    assert list(h["oi"]) == [3.0, 7.0]  # last print inside each hour


def test_carry_real_funding_accounting(tmp_path, monkeypatch):
    hours = pd.date_range("2023-01-01", periods=24 * 10, freq="1h", tz="UTC")
    f = pd.DataFrame({"funding_interval_hours": 8.0, "last_funding_rate": 0.0002},
                     index=pd.date_range("2023-01-01", periods=30, freq="8h", tz="UTC"))
    f.to_parquet(tmp_path / "X_funding.parquet")
    monkeypatch.setattr(fr, "BV", tmp_path)
    monkeypatch.setattr(fr, "load", lambda c: pd.DataFrame({"prem_open": 0.0}, index=hours))
    fr.funding.cache_clear()
    monkeypatch.setattr(fr, "check_lock", lambda e: None)
    r, n = fr.carry(0.01, (hours[0], hours[-1]), coins=["X"])
    notional = 1 / 1.5
    leg = fr.pr.spot_cost("X") + fr.pr.perp_cost("X")
    # enters at the first 8h decision with 6+ prints in the trailing 72h (t = 40h), then earns every later print
    prints_after_entry = sum(1 for t in f.index if t > hours[0] + pd.Timedelta(hours=40) and t <= hours[-1])
    assert n == 1
    assert abs(r.sum() - (prints_after_entry * 0.0002 * notional - leg * notional)) < 1e-12
