"""Market data providers and brokers.

Providers return closed daily bars. Brokers hold positions and execute orders:
  * PaperBroker keeps a simulated account in state.json and fills at a supplied price, with fee and slippage;
  * LiveBroker sends market orders through ccxt, only when the runner has passed both live gates.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

DAY = pd.Timedelta(days=1)


# ------------------------------------------------------------------ providers
class CcxtProvider:
    def __init__(self, exchange_id: str, quote: str, exchange=None):
        import ccxt
        self.ex = exchange or getattr(ccxt, exchange_id)({"enableRateLimit": True})
        self.quote = quote
        self.ex.load_markets()

    def symbol(self, coin: str) -> str | None:
        s = f"{coin}/{self.quote}"
        m = self.ex.markets.get(s)
        return s if m and m.get("active", True) and m.get("spot", True) else None

    def daily_closes(self, coin: str, now: pd.Timestamp, bars: int = 400) -> pd.Series | None:
        s = self.symbol(coin)
        if s is None:
            return None
        raw = self.ex.fetch_ohlcv(s, "1d", limit=bars + 1)
        df = pd.DataFrame(raw, columns=["t", "o", "h", "l", "c", "v"])
        df.index = pd.to_datetime(df["t"], unit="ms", utc=True)
        df = df[df.index + DAY <= now]  # drop the still-forming bar
        return df["c"].astype(float)

    def prices(self, coins: list[str]) -> dict[str, float]:
        out = {}
        for c in coins:
            s = self.symbol(c)
            if s:
                t = self.ex.fetch_ticker(s)
                p = t.get("last") or t.get("close")
                if p:
                    out[c] = float(p)
        return out


class ParquetProvider:
    """Replays the research data: decision at the close of `asof`, fills at the open of the next day."""

    def __init__(self, data_dir: Path, quote: str = "USDT"):
        self.dir = Path(data_dir)
        self.quote = quote
        self._cache: dict[str, pd.DataFrame] = {}

    def _df(self, coin):
        if coin not in self._cache:
            p = self.dir / f"{coin}{self.quote}_1D.parquet"
            self._cache[coin] = pd.read_parquet(p) if p.exists() else None
        return self._cache[coin]

    def daily_closes(self, coin: str, now: pd.Timestamp, bars: int = 400) -> pd.Series | None:
        df = self._df(coin)
        if df is None:
            return None
        return df.loc[df.index + DAY <= now, "close"]

    def prices(self, coins: list[str], now: pd.Timestamp | None = None) -> dict[str, float]:
        out = {}
        for c in coins:
            df = self._df(c)
            if df is not None and now in df.index:
                out[c] = float(df.at[now, "open"])
        return out


# ------------------------------------------------------------------ brokers
@dataclass
class Fill:
    time: str
    coin: str
    side: str
    qty: float
    price: float
    notional: float
    cost: float
    order_id: str = ""


@dataclass
class PaperBroker:
    state_path: Path
    fee_bp: float
    slippage_bp: dict[str, float]
    start_cash: float = 10_000.0
    cash: float = field(init=False, default=0.0)
    qty: dict[str, float] = field(init=False, default_factory=dict)
    meta: dict = field(init=False, default_factory=dict)

    def __post_init__(self):
        self.state_path = Path(self.state_path)
        if self.state_path.exists():
            s = json.loads(self.state_path.read_text())
            self.cash, self.qty, self.meta = s["cash"], s["qty"], s.get("meta", {})
        else:
            self.cash, self.qty, self.meta = self.start_cash, {}, {}

    def balances(self) -> tuple[float, dict[str, float]]:
        return self.cash, {k: v for k, v in self.qty.items() if v > 0}

    def _cost_rate(self, coin):
        return (self.fee_bp + self.slippage_bp.get(coin, 6.0)) / 1e4

    def sell(self, coin: str, qty: float, price: float, when: str) -> Fill:
        qty = min(qty, self.qty.get(coin, 0.0))
        notional = qty * price
        cost = notional * self._cost_rate(coin)
        self.qty[coin] = self.qty.get(coin, 0.0) - qty
        if self.qty[coin] <= 1e-15:
            self.qty.pop(coin)
        self.cash += notional - cost
        return Fill(when, coin, "sell", qty, price, notional, cost)

    def buy(self, coin: str, notional: float, price: float, when: str) -> Fill:
        cost = notional * self._cost_rate(coin)
        if notional + cost > self.cash:
            notional = max(self.cash / (1 + self._cost_rate(coin)), 0.0)
            cost = notional * self._cost_rate(coin)
        qty = notional / price
        self.qty[coin] = self.qty.get(coin, 0.0) + qty
        self.cash -= notional + cost
        return Fill(when, coin, "buy", qty, price, notional, cost)

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"cash": self.cash, "qty": self.qty, "meta": self.meta}, indent=2))
        tmp.replace(self.state_path)


class LiveBroker:
    """Spot market orders via ccxt. Keys come only from environment variables, never from config files."""

    def __init__(self, provider: CcxtProvider, state_path: Path):
        ex = provider.ex
        ex.apiKey = os.environ["BOT_API_KEY"]
        ex.secret = os.environ["BOT_API_SECRET"]
        if os.environ.get("BOT_API_PASSWORD"):
            ex.password = os.environ["BOT_API_PASSWORD"]
        self.ex, self.p = ex, provider
        self.state_path = Path(state_path)
        self.meta = json.loads(self.state_path.read_text()).get("meta", {}) if self.state_path.exists() else {}

    def balances(self) -> tuple[float, dict[str, float]]:
        b = self.ex.fetch_balance()
        free = b.get("free", {})  # a bot-only account has no open orders, so free == total; sells need free
        return float(free.get(self.p.quote, 0.0) or 0.0), {k: float(v) for k, v in free.items()
                                                         if v and k != self.p.quote}

    def _limits(self, coin):
        m = self.ex.market(self.p.symbol(coin))
        lim = m.get("limits", {})
        return (lim.get("amount", {}) or {}).get("min") or 0.0, (lim.get("cost", {}) or {}).get("min") or 0.0

    def sell(self, coin: str, qty: float, price: float, when: str) -> Fill | None:
        s = self.p.symbol(coin)
        amt = float(self.ex.amount_to_precision(s, qty))
        amin, cmin = self._limits(coin)
        if amt <= 0 or amt < amin or amt * price < cmin:
            return None
        o = self.ex.create_market_sell_order(s, amt)
        return self._fill(o, coin, "sell", when, price)

    def buy(self, coin: str, notional: float, price: float, when: str) -> Fill | None:
        s = self.p.symbol(coin)
        amt = float(self.ex.amount_to_precision(s, notional / price))
        amin, cmin = self._limits(coin)
        if amt <= 0 or amt < amin or notional < cmin:
            return None
        o = self.ex.create_market_buy_order(s, amt)
        return self._fill(o, coin, "buy", when, price)

    def _fill(self, o, coin, side, when, ref_price):
        oid = o.get("id", "")
        for _ in range(10):  # some venues return the order before it is filled
            if o.get("status") in ("closed", "canceled") or o.get("filled"):
                break
            time.sleep(1)
            o = self.ex.fetch_order(oid, self.p.symbol(coin))
        filled = float(o.get("filled") or 0.0)
        avg = float(o.get("average") or o.get("price") or ref_price)
        fee = o.get("fee") or {}
        return Fill(when, coin, side, filled, avg, filled * avg, float(fee.get("cost") or 0.0), str(oid))

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"live": True, "meta": self.meta}, indent=2))
