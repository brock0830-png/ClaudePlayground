import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "bot"))
import cdata  # noqa: E402
import portfolio as pf  # noqa: E402
import research as R  # noqa: E402
import strategy as st  # noqa: E402
import trend_bot as tb  # noqa: E402
import venues  # noqa: E402

CFG = ROOT / "bot" / "configs" / "trend_basket.yaml"


def _closes():
    return {c: cdata.load(c + "USDT", "1D")["close"] for c in cdata.DAILY_UNIVERSE}


def test_strategy_module_matches_research_weights():
    O, C, E, _ = R.panel()
    W_r, R_r = R.weights("SMA", {"N": 50, "btc_gate": True}, C, E)
    W_b, R_b = st.decide_history(_closes())
    W_b = W_b.reindex(W_r.index)[W_r.columns]
    assert (W_r - W_b).abs().max().max() < 1e-12
    assert (R_r == R_b.reindex(R_r.index)).all()


def test_decide_matches_vectorised_on_sample_days():
    closes = _closes()
    W, Rf = st.decide_history(closes)
    for d in ["2019-06-30", "2021-05-19", "2022-06-18", "2024-03-01", "2025-04-07", "2026-09-22"]:
        t = pd.Timestamp(d, tz="UTC")
        dec = st.decide(closes, t)
        assert max(abs(dec.weights[c] - W.at[t, c]) for c in closes) < 1e-12
        assert dec.rebalance == bool(Rf.at[t])


def test_replay_matches_research_engine():
    cfg = tb.load_config(CFG)
    cfg["min_trade_usd"] = 0.0
    start, end = "2024-01-01", "2024-12-31"
    eq = tb.replay(cfg, "2023-12-31", end)  # first decision at the 2023-12-31 close, first fill 2024-01-01 open
    O, C, E, cost = R.panel()
    W, Rf = R.weights("SMA", {"N": 50, "btc_gate": True}, C, E)
    s = pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=1)
    e = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    sl = lambda x: x.loc[s:e]
    res = pf.simulate(sl(W), sl(Rf).copy().where(sl(Rf).index > s, False), sl(O), sl(C), cost)
    eng = res["equity"]
    both = pd.concat([eq["equity_close"] / 10_000.0, eng], axis=1, join="inner").dropna()
    both.columns = ["bot", "engine"]
    assert len(both) > 300
    assert (both.bot / both.engine - 1).abs().max() < 1e-9  # the bot is the backtest, to machine precision


def test_live_needs_both_gates(monkeypatch):
    monkeypatch.delenv("BOT_LIVE_CONFIRM", raising=False)
    cfg = tb.load_config(CFG)
    assert cfg["live"] is False
    p = Path(CFG).read_text().replace("mode: paper", "mode: live")
    tmp = ROOT / "bot" / "configs" / "_tmp_live.yaml"
    tmp.write_text(p)
    try:
        assert tb.load_config(tmp)["live"] is False
        monkeypatch.setenv("BOT_LIVE_CONFIRM", "I_UNDERSTAND")
        assert tb.load_config(tmp)["live"] is True
        monkeypatch.setenv("BOT_MODE", "paper")
        assert tb.load_config(tmp)["live"] is False
    finally:
        tmp.unlink()


def test_halt_places_no_orders_and_duplicate_guard(tmp_path, monkeypatch):
    cfg = tb.load_config(CFG)
    cfg["state_dir"] = str(tmp_path)
    prov = venues.ParquetProvider(ROOT / "data" / "tv")
    br = venues.PaperBroker(tmp_path / "state.json", 10.0, {}, 10_000.0)
    now = pd.Timestamp("2024-03-02", tz="UTC")
    monkeypatch.setenv("BOT_HALT", "1")
    s = tb.run_once(cfg, prov, br, now, price_fn=lambda cs: prov.prices(cs, now))
    assert s["fills"] == 0 and br.cash == 10_000.0
    monkeypatch.delenv("BOT_HALT")
    s = tb.run_once(cfg, prov, br, now, price_fn=lambda cs: prov.prices(cs, now), force=True)
    assert s["fills"] > 0
    s2 = tb.run_once(cfg, prov, br, now, price_fn=lambda cs: prov.prices(cs, now))
    assert s2["status"] == "duplicate"


def test_missing_gate_coin_blocks_trading(tmp_path):
    cfg = tb.load_config(CFG)
    cfg["state_dir"] = str(tmp_path)
    cfg["universe"] = [c for c in cfg["universe"] if c != "BTC"]
    prov = venues.ParquetProvider(ROOT / "data" / "tv")
    br = venues.PaperBroker(tmp_path / "state.json", 10.0, {}, 10_000.0)
    now = pd.Timestamp("2024-03-02", tz="UTC")
    assert tb.run_once(cfg, prov, br, now, price_fn=lambda cs: prov.prices(cs, now))["status"] == "no-data"


class FakeExchange:
    """Minimal ccxt stand-in serving the research parquet bars; records orders."""

    def __init__(self, now, cash=5_000.0, holdings=None, unlisted=("NEO",)):
        self.now = now
        self.markets = {}
        self.orders = []
        self.bal = {"USDT": cash, **(holdings or {})}
        self.unlisted = set(unlisted)
        self.apiKey = self.secret = self.password = None
        self.prov = venues.ParquetProvider(ROOT / "data" / "tv")

    def load_markets(self):
        for c in cdata.DAILY_UNIVERSE:
            if c not in self.unlisted:
                self.markets[f"{c}/USDT"] = {"active": True, "spot": True,
                                             "limits": {"amount": {"min": 1e-8}, "cost": {"min": 5.0}}}
        return self.markets

    def market(self, s):
        return self.markets[s]

    def fetch_ohlcv(self, s, tf, limit=400):
        df = self.prov._df(s.split("/")[0])
        df = df[df.index <= self.now].tail(limit)  # includes the forming bar, like a real venue
        return [[int(t.value // 10**6), r.open, r.high, r.low, r.close, r.volume] for t, r in df.iterrows()]

    def fetch_ticker(self, s):
        c = s.split("/")[0]
        return {"last": self.prov.prices([c], self.now.floor("D"))[c]}

    def fetch_balance(self):
        return {"free": dict(self.bal), "total": dict(self.bal)}

    def amount_to_precision(self, s, a):
        return f"{float(a):.6f}"

    def _px(self, s):
        return self.fetch_ticker(s)["last"]

    def create_market_buy_order(self, s, amt):
        c, px = s.split("/")[0], self._px(s)
        cost = float(amt) * px * 1.001
        assert cost <= self.bal["USDT"] + 1e-6, f"insufficient funds buying {s}"
        self.bal["USDT"] -= cost
        self.bal[c] = self.bal.get(c, 0.0) + float(amt)
        self.orders.append(("buy", s, float(amt)))
        return {"id": str(len(self.orders)), "status": "closed", "filled": float(amt), "average": px,
                "fee": {"cost": float(amt) * px * 0.001}}

    def create_market_sell_order(self, s, amt):
        c, px = s.split("/")[0], self._px(s)
        assert float(amt) <= self.bal.get(c, 0.0) + 1e-9
        self.bal[c] -= float(amt)
        self.bal["USDT"] += float(amt) * px * 0.999
        self.orders.append(("sell", s, float(amt)))
        return {"id": str(len(self.orders)), "status": "closed", "filled": float(amt), "average": px,
                "fee": {"cost": float(amt) * px * 0.001}}

    def fetch_order(self, oid, s):
        raise AssertionError("orders fill immediately in the fake")


def test_live_path_against_fake_exchange(tmp_path, monkeypatch):
    now = pd.Timestamp("2024-03-02 00:07", tz="UTC")
    fx = FakeExchange(now, cash=5_000.0, holdings={"DOGE": 1000.0})
    prov = venues.CcxtProvider("binance", "USDT", exchange=fx)
    monkeypatch.setenv("BOT_API_KEY", "k")
    monkeypatch.setenv("BOT_API_SECRET", "s")
    cfg = tb.load_config(CFG)
    cfg.update(state_dir=str(tmp_path), live=True, capital_usd=None)
    br = venues.LiveBroker(prov, tmp_path / "state.json")
    s = tb.run_once(cfg, prov, br, now)
    assert s["status"] == "ok", s
    assert "NEO" in s["missing"]
    dec = st.decide({c: prov.daily_closes(c, now) for c in cdata.DAILY_UNIVERSE if c != "NEO"},
                    pd.Timestamp("2024-03-01", tz="UTC"))
    held = {c for c, w in dec.weights.items() if w > 0}
    bought = {o[1].split("/")[0] for o in fx.orders if o[0] == "buy"}
    sold = {o[1].split("/")[0] for o in fx.orders if o[0] == "sell"}
    assert bought == held - {"DOGE"} or bought == held  # DOGE may be topped up or trimmed on a rebalance day
    assert ("DOGE" in sold) == ("DOGE" not in held) or "DOGE" in sold
    assert fx.bal["USDT"] >= 0
    eq = fx.bal["USDT"] + sum(q * fx._px(f"{c}/USDT") for c, q in fx.bal.items() if c != "USDT")
    invested = sum(q * fx._px(f"{c}/USDT") for c, q in fx.bal.items() if c != "USDT" and c in held)
    assert invested / eq > 0.97 * len(held) / len(dec.weights)
    # second run the same day is refused; a run the next day trades only switches
    assert tb.run_once(cfg, prov, br, now)["status"] == "duplicate"
