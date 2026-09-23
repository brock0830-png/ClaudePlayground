"""Trend-basket bot: runs the frozen H4 rule once per day, just after the 00:00 UTC daily close.

  python crypto/bot/trend_bot.py --config crypto/bot/configs/trend_basket.yaml            # paper (default)
  python crypto/bot/trend_bot.py --config ... --dry-run                                   # plan only, no fills
  python crypto/bot/trend_bot.py --config ... --replay 2024-01-01:2026-09-22              # replay research data

Live trading needs BOTH `mode: live` in the config AND the environment variable BOT_LIVE_CONFIRM=I_UNDERSTAND, plus
BOT_API_KEY / BOT_API_SECRET (and BOT_API_PASSWORD on venues that use one). Any other combination runs paper.
Halt: create the file named by `halt_file` (default crypto/bot/STOP) or set BOT_HALT=1, and the bot places no
orders. With `halt_action: flatten` it sells everything in the universe instead.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import strategy as st  # noqa: E402
import venues  # noqa: E402

DAY = pd.Timedelta(days=1)
TIER1, TIER2 = {"BTC", "ETH"}, {"BNB", "XRP", "SOL", "DOGE", "ADA", "LINK", "AVAX", "LTC", "TRX", "BCH", "DOT"}
MAX_STALE_DAYS = 3


def default_slippage(coin: str) -> float:
    return 2.0 if coin in TIER1 else 4.0 if coin in TIER2 else 6.0


def load_config(path: str) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    cfg.setdefault("strategy", {})
    cfg.setdefault("paper", {})
    cfg.setdefault("min_trade_usd", 10.0)
    cfg.setdefault("halt_file", "crypto/bot/STOP")
    cfg.setdefault("halt_action", "hold")
    cfg.setdefault("state_dir", f"crypto/bot/state/{cfg['name']}")
    cfg["exchange"] = os.environ.get("BOT_EXCHANGE", cfg.get("exchange", "binance"))
    cfg["quote"] = os.environ.get("BOT_QUOTE", cfg.get("quote", "USDT"))
    live_cfg = cfg.get("mode", "paper") == "live"
    live_env = os.environ.get("BOT_LIVE_CONFIRM") == "I_UNDERSTAND"
    forced_paper = os.environ.get("BOT_MODE") == "paper"
    cfg["live"] = bool(live_cfg and live_env and not forced_paper)
    if live_cfg and not cfg["live"]:
        print("config says live but BOT_LIVE_CONFIRM is not set (or BOT_MODE=paper): running PAPER")
    return cfg


def params(cfg) -> st.Params:
    return st.Params(**{k: v for k, v in cfg["strategy"].items() if k in st.Params.__dataclass_fields__})


def gather(cfg, provider, now: pd.Timestamp):
    """Closed daily bars for the universe. Stale coins are forward-filled to asof and frozen (not traded)."""
    asof = now.floor("D") - DAY
    closes, frozen, missing = {}, set(), []
    for coin in cfg["universe"]:
        try:
            c = provider.daily_closes(coin, now)
        except Exception as e:  # network or venue error: freeze the coin rather than guess
            print(f"  {coin}: data error {e!r}; frozen this run")
            c = None
            frozen.add(coin)
        if c is None or len(c) == 0:
            missing.append(coin)
            continue
        last = c.index[-1]
        if last < asof:
            if asof - last > pd.Timedelta(days=MAX_STALE_DAYS):
                missing.append(coin)
                continue
            c = pd.concat([c, pd.Series(c.iloc[-1], index=pd.date_range(last + DAY, asof, freq="D"))])
            frozen.add(coin)
        closes[coin] = c.loc[:asof]
    return asof, closes, frozen, missing


def plan(dec: st.Decision, qty: dict, prices: dict, book: float, prev_on: dict, frozen: set, rates: dict,
         min_trade: float, cash: float = float("inf")) -> list[tuple[str, float]]:
    """Signed USD deltas per coin, mirroring crypto/src/portfolio.simulate plus a self-heal for missed fills."""
    coins = [c for c in dec.weights if c in prices and c not in frozen]

    def deltas(b):
        out = {}
        for c in coins:
            cur = qty.get(c, 0.0) * prices[c]
            tgt = dec.weights[c] * b
            if dec.rebalance:
                d = tgt - cur
            elif tgt == 0 and cur > 0:
                d = -cur
            elif tgt > 0 and (dec.on[c] != prev_on.get(c) or cur < 0.05 * tgt):
                d = tgt - cur
            else:
                d = 0.0
            out[c] = d
        return out

    d0 = deltas(book)
    c0 = sum(abs(v) * rates[c] for c, v in d0.items())
    d1 = deltas(book - c0)
    # spot account: scale buys pro rata to cash plus sale proceeds (same rule as the research engine)
    need = sum(v * (1 + rates[c]) for c, v in d1.items() if v > 0)
    avail = cash + sum(-v * (1 - rates[c]) for c, v in d1.items() if v < 0)
    if need > 0 and need > avail:
        k = max(avail, 0.0) / need
        d1 = {c: (v * k if v > 0 else v) for c, v in d1.items()}
    orders = []
    for c, v in d1.items():
        full_exit = dec.weights[c] == 0 and v < 0
        if abs(v) > 1e-9 and (abs(v) >= min_trade or full_exit):
            orders.append((c, v))
    return sorted(orders, key=lambda x: x[1])  # sells first


def run_once(cfg, provider, broker, now: pd.Timestamp, price_fn=None, force=False, dry_run=False, log=print):
    p = params(cfg)
    halt = Path(REPO / cfg["halt_file"]).exists() or os.environ.get("BOT_HALT") == "1"
    asof, closes, frozen, missing = gather(cfg, provider, now)
    if p.gate_coin not in closes or p.gate_coin in frozen:
        log(f"{p.gate_coin} data unavailable or stale: no decision possible, no orders")
        return {"status": "no-data"}
    if broker.meta.get("last_run") == str(asof.date()) and not force:
        log(f"already ran for bar {asof.date()}; use --force to rerun")
        return {"status": "duplicate"}
    dec = st.decide(closes, asof, p)
    prices = price_fn(list(closes)) if price_fn else provider.prices(list(closes))
    cash, qty = broker.balances()
    qty = {c: q for c, q in qty.items() if c in cfg["universe"]}
    equity = cash + sum(q * prices.get(c, 0.0) for c, q in qty.items())
    book = min(equity, float(cfg["capital_usd"])) if cfg.get("capital_usd") else equity
    rates = {c: (cfg["paper"].get("fee_bp", 10.0) + cfg.get("slippage_bp", {}).get(c, default_slippage(c))) / 1e4
             for c in closes}
    if halt:
        log("HALT set: " + ("flattening universe" if cfg["halt_action"] == "flatten" else "no orders"))
        orders = [(c, -q * prices[c]) for c, q in qty.items() if c in prices] if cfg["halt_action"] == "flatten" else []
    else:
        # live market orders fill at a slightly different price than the ticker: keep a small cash buffer
        buf = float(cfg.get("live_cash_buffer", 0.005)) if cfg["live"] else 0.0
        orders = plan(dec, qty, prices, book, broker.meta.get("last_on", {}), frozen, rates, float(cfg["min_trade_usd"]),
                      cash=cash * (1 - buf))
    when = now.isoformat()
    fills, errors = [], []
    for coin, usd in orders:
        px = prices[coin]
        if dry_run:
            log(f"  DRY {'SELL' if usd < 0 else 'BUY '} {coin:<5} ${abs(usd):,.2f} @ {px:.6g}")
            continue
        try:
            if usd < 0:
                q = qty.get(coin, 0.0) if dec.weights.get(coin, 0) == 0 or halt else abs(usd) / px
                f = broker.sell(coin, q, px, when)
            else:
                f = broker.buy(coin, usd, px, when)
            if f is not None and f.qty > 0:
                fills.append(f)
        except Exception as e:
            errors.append(f"{coin}: {e!r}")
    cash2, qty2 = broker.balances()
    eq2 = cash2 + sum(q * prices.get(c, 0.0) for c, q in qty2.items() if c in cfg["universe"])
    if not dry_run:
        broker.meta.update({"last_run": str(asof.date()), "last_on": dec.on})
        broker.save()
        journal(cfg, asof, now, dec, fills, eq2, cash2, errors, frozen, missing)
    summary = {"status": "ok" if not errors else "errors", "bar": str(asof.date()), "mode": "live" if cfg["live"] else "paper",
               "equity": round(eq2, 2), "cash": round(cash2, 2), "gate_open": dec.gate_open, "rebalance": dec.rebalance,
               "holding": sorted(c for c, w in dec.weights.items() if w > 0), "orders": len(orders), "fills": len(fills),
               "errors": errors, "frozen": sorted(frozen), "missing": missing, "notes": dec.notes}
    return summary


def journal(cfg, asof, now, dec, fills, equity, cash, errors, frozen, missing):
    d = REPO / cfg["state_dir"]
    d.mkdir(parents=True, exist_ok=True)
    tf = d / "trades.csv"
    new = not tf.exists()
    with tf.open("a", newline="") as f:
        w = csv.DictWriter(f, ["time", "coin", "side", "qty", "price", "notional", "cost", "order_id"])
        if new:
            w.writeheader()
        for x in fills:
            w.writerow(asdict(x))
    ef = d / "equity.csv"
    new = not ef.exists()
    with ef.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["bar", "run_time", "equity", "cash", "gate_open", "rebalance", "n_holding", "errors"])
        w.writerow([asof.date(), now.isoformat(), round(equity, 4), round(cash, 4), dec.gate_open, dec.rebalance,
                    sum(1 for v in dec.weights.values() if v > 0), len(errors)])
    (d / "last_decision.json").write_text(json.dumps({"bar": str(asof.date()), "gate_open": dec.gate_open,
                                                      "rebalance": dec.rebalance, "weights": dec.weights,
                                                      "on": dec.on, "eligible": dec.eligible, "frozen": sorted(frozen),
                                                      "missing": missing, "notes": dec.notes}, indent=1))


def notify(summary: dict):
    url = os.environ.get("BOT_WEBHOOK_URL")
    if not url:
        return
    try:
        import urllib.request
        body = json.dumps({"content": f"trend bot {summary['mode']} {summary['bar']}: equity {summary['equity']}, "
                                      f"holding {len(summary['holding'])}, fills {summary['fills']}, "
                                      f"errors {len(summary['errors'])}"}).encode()
        urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}), timeout=10)
    except Exception as e:
        print(f"webhook failed: {e!r}")


def replay(cfg, start: str, end: str, state_dir: Path | None = None, log=lambda *_: None) -> pd.DataFrame:
    """Day-by-day paper replay on the research parquet data (fills at the next day's open)."""
    provider = venues.ParquetProvider(REPO / "crypto" / "data" / "tv", cfg["quote"])
    tmp = Path(state_dir or tempfile.mkdtemp())
    cfg = {**cfg, "state_dir": str(tmp.relative_to(REPO)) if tmp.is_relative_to(REPO) else str(tmp), "live": False}
    broker = venues.PaperBroker(tmp / "state.json", cfg["paper"].get("fee_bp", 10.0),
                                {c: cfg.get("slippage_bp", {}).get(c, default_slippage(c)) for c in cfg["universe"]},
                                cfg["paper"].get("start_cash", 10_000.0))
    rows = []
    for d in pd.date_range(start, end, freq="D", tz="UTC"):
        now = d + DAY
        s = run_once(cfg, provider, broker, now, price_fn=lambda cs, n=now: provider.prices(cs, n), log=log)
        if s.get("status") in ("ok", "errors"):
            cash, qty = broker.balances()
            closes = {c: provider.daily_closes(c, now + DAY) for c in qty}
            eq_close = cash + sum(q * float(closes[c].iloc[-1]) for c, q in qty.items() if closes[c] is not None and len(closes[c]))
            rows.append({"bar": now.normalize(), "equity_close": eq_close, "fills": s["fills"], "holding": len(s["holding"])})
    return pd.DataFrame(rows).set_index("bar")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--replay", help="START:END, paper replay on the research data")
    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.replay:
        s, e = a.replay.split(":")
        eq = replay(cfg, s, e, log=print if a.dry_run else (lambda *_: None))
        r = eq["equity_close"].pct_change().dropna()
        print(eq.tail())
        print(f"replay {s}..{e}: equity x{eq.equity_close.iloc[-1] / cfg['paper'].get('start_cash', 10_000.0):.3f}, "
              f"Sharpe {r.mean() / r.std() * (365 ** 0.5):.2f}, max DD {(eq.equity_close / eq.equity_close.cummax() - 1).min():.1%}")
        return
    now = pd.Timestamp.now(tz="UTC")
    provider = venues.CcxtProvider(cfg["exchange"], cfg["quote"])
    state = REPO / cfg["state_dir"] / "state.json"
    if cfg["live"]:
        broker = venues.LiveBroker(provider, state)
    else:
        broker = venues.PaperBroker(state, cfg["paper"].get("fee_bp", 10.0),
                                    {c: cfg.get("slippage_bp", {}).get(c, default_slippage(c)) for c in cfg["universe"]},
                                    cfg["paper"].get("start_cash", 10_000.0))
    print(f"{cfg['name']} [{'LIVE' if cfg['live'] else 'paper'}] on {cfg['exchange']} ({cfg['quote']}) at {now}")
    s = run_once(cfg, provider, broker, now, force=a.force, dry_run=a.dry_run)
    print(json.dumps(s, indent=1, default=str))
    notify(s) if s.get("status") in ("ok", "errors") and not a.dry_run else None
    sys.exit(1 if s.get("status") == "errors" else 0)


if __name__ == "__main__":
    main()
