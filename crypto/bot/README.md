# Trend-basket bot: runbook

The bot trades one rule, the only candidate that passed both the pre-registered design stage and the one-shot holdout (`crypto/REPORT.md`):

> Split the book into equal slots, one per eligible coin (28-coin universe, 200+ days of history). Hold a coin's slot while its daily close is above its 50-day SMA. Alts are held only while BTC's daily close is above BTC's 100-day SMA. Otherwise the slot sits in USDT/USD. Reset every slot to equal size on the 1st of each month (UTC). On other days, only coins that switch on or off trade.

It runs once a day, just after the 00:00 UTC daily close, and places spot market orders only. It never uses leverage, never shorts and never borrows. Replayed on the research data, it reproduces the backtest to machine precision (`crypto/tests/test_bot.py::test_replay_matches_research_engine`).

## What to expect (net of 10 bp fee + 2-6 bp slippage per side)

| Window | CAGR | Sharpe | Max drawdown | Time invested |
|---|---|---|---|---|
| Design 2018-2023 | 70.5% | 1.38 | -39.5% | 36% |
| Holdout 2024-01 to 2026-09 (one shot) | 31.9% | 0.90 | -39.5% | 35% |
| Holdout, 40 bp fee per side (US retail) | 23.5% | 0.73 | -44.4% | 35% |
| Holdout, BTC buy and hold | 29.8% | 0.79 | -53.0% | 100% |
| Holdout, BTC above SMA100 else cash | 28.0% | 0.91 | -36.4% | 56% |

A 40% peak-to-trough drawdown has happened in both windows, and should be expected again. The holdout's drawdown ran from December 2024 to April 2026, and on 2026-09-22 the rule was still 5% below that peak. Losing years happened too: 2018 -25%, 2022 -19%, 2025 -10%. Across the basket the bot places about 690 orders a year (entries, exits and monthly trims). That works out to about 310 new positions a year, held about 11 days each on average.

## 1. Paper trade first (default)

```bash
pip install -r crypto/bot/requirements.txt
python crypto/bot/trend_bot.py --config crypto/bot/configs/trend_basket.yaml --dry-run   # show today's orders
python crypto/bot/trend_bot.py --config crypto/bot/configs/trend_basket.yaml             # paper fill, $10k start
```

Paper state lives in `crypto/bot/state/trend_basket/`: `state.json` (cash, quantities, last signal), `trades.csv`, `equity.csv` and `last_decision.json`. Running it twice for the same daily bar is refused; `--force` overrides that.

Replay the research data to see what the bot would have done: `--replay 2024-01-01:2026-09-21`.

## 2. Pick a venue

`exchange` and `quote` in the config (or the env vars `BOT_EXCHANGE` / `BOT_QUOTE`) accept any ccxt spot venue.

- **Binance.com** (`binance`, `USDT`) is what the research used: fee 10 bp, all 28 coins listed. It is not available to US residents, and it refuses connections from US IP addresses, including GitHub's runners.
- **US options:** `binanceus` (`USDT` or `USD`), `kraken` (`USD`), `coinbase` (`USD`/`USDC`). Taker fees at the lowest tier are much higher (Kraken Pro 40 bp, Coinbase Advanced 60 bp). The 40 bp row in the table above shows what that costs: about 8 points of CAGR a year. Qualify for a lower fee tier where you can.
- The bot skips coins the venue does not list and splits the book across the rest. That is a small departure from the tested 28-coin universe, and the log lists every skipped coin.
- Minimum order sizes are about $5-10 on most venues. With 28 slots, fund at least about $1,000 (roughly $35 a slot), or the monthly trims will be skipped as dust.

## 3. Schedule it

**GitHub Actions (free, no server):** `.github/workflows/crypto-trend-bot.yml` runs daily at 00:07 UTC and commits the paper state back to the repo. GitHub only runs scheduled workflows from the repository's default branch, so merge this work there to activate it. You can also run it by hand from the Actions tab (it has a dry-run switch). The workflow defaults to `kraken` / `USD`, because the runners are in the US. Override that with the repository variables `BOT_EXCHANGE` and `BOT_QUOTE`.

**Your own machine or a VPS (use this for Binance.com from a supported country):**

```cron
7 0 * * *  cd /path/to/ClaudePlayground && /usr/bin/python3 crypto/bot/trend_bot.py --config crypto/bot/configs/trend_basket.yaml >> crypto/bot/state/cron.log 2>&1
```

## 4. Going live (only after a few weeks of paper runs that look right)

Live mode needs **all three** of the following. Any other combination runs paper and prints a notice.

1. `mode: live` in the config.
2. The environment variable `BOT_LIVE_CONFIRM=I_UNDERSTAND`. On GitHub, set it as a repository **variable**.
3. API keys in the environment: `BOT_API_KEY`, `BOT_API_SECRET`, and `BOT_API_PASSWORD` on venues that use one. On GitHub, set them as repository **secrets**. Never put keys in the config file.

Set up the API key like this: **spot trading only, withdrawals disabled**, and IP-restricted if you run from a fixed server. Use a dedicated sub-account or a separate account for the bot. The bot treats all quote cash plus any universe coins in the account as its book, unless `capital_usd` caps it. Do not run two live bots on the same account.

On the first live run, the bot buys every coin whose slot is on. Right now that is all 28: on the 2026-09-22 bar the BTC gate is open and every coin is above its SMA(50). If you would rather not go all-in on day one, start with a smaller `capital_usd` and raise it later.

## 5. Stopping it

- `touch crypto/bot/STOP` (or `BOT_HALT=1`): no orders on the next run. Positions are kept.
- `halt_action: flatten` in the config plus the STOP file: the next run sells the whole universe to cash.
- Disable the workflow in the Actions tab to stop the schedule itself.

## 6. Monitoring

- Set `BOT_WEBHOOK_URL` (a Discord-compatible webhook) to get one message per run.
- The process exits non-zero when any order errors, so a GitHub run shows red.
- Coins with missing or stale data are frozen (never traded on a guess). If BTC data is missing, the whole run places no orders, because the gate is unknown.

## 7. What not to change

The strategy block (50 / 100 / 200) is the tested rule. Other settings were tested too. Some did better than the frozen rule on the holdout (Donchian-20 with the gate: Sharpe 1.21) and some did worse (SMA100 with the gate: 0.74). Switching to one of them now would be choosing on the holdout, which is exactly the overfitting the protocol exists to prevent. Changing the block makes it an untested strategy. The TradingView version for charts and alerts is `crypto/pine/trend_basket.pine`.
