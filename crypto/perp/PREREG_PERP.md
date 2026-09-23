# crypto/perp/PREREG_PERP.md: Phase 2 pre-registration, perpetual-futures signals (OI, funding, OBV)

Written 2026-09-23 before any Phase 2 backtest. Committed before the first row of `crypto/perp/TRIAL_LEDGER.csv`. The only things looked at so far: bar counts, date ranges, alignment, and one column-range check of the premium index to confirm its units (the median across coins is about -0.04%, 1st-99th percentile -0.18% to +0.10%). No forward return has been computed.

**The brief.** Using perp data (open interest, funding, OBV, order flow), find something positive-EV that trades several times a week across several major coins and could help fund the Phase 1 trend basket.

## 0. What the data can and cannot do

| Wanted | Available here? | Source used |
|---|---|---|
| Open interest | yes | TradingView `BINANCE:<X>USDT.P_OI` (OHLC of OI in coin units) |
| Funding rate | reconstructed | TradingView `BINANCE:<X>USDT_PREMIUM` (premium index, in %). Funding per 8h = mean premium over the interval + clamp(0.01% - mean premium, -0.05%, +0.05%), capped at ±0.75%. This is Binance's published formula applied to TradingView's premium bars. It has not been checked against Binance's actual funding prints, because `data.binance.vision` and `fapi.binance.com` are blocked here |
| OBV | yes | from perp OHLCV |
| Aggressive vs passive flow (taker buy/sell), CVD, footprint | **no** | needs taker volume or tick trades from `data.binance.vision`, which is blocked. Not tested in this phase |

Universe **U16** (4h): BTC ETH SOL XRP DOGE BNB ADA AVAX LINK LTC DOT TRX BCH SUI NEAR APT, USDT-margined perps, 2024-06-12 to 2026-09-23. Confirmation set **C9** (1h, holdout only): BTC ETH SOL XRP DOGE BNB AVAX LINK ADA, 2026-02-27 to 2026-09-23.

## 1. Fixed protocol

| Item | Setting |
|---|---|
| Split | 4h design 2024-06-12 to 2025-09-30; 4h holdout 2025-10-01 to 2026-09-23; 1h used only at the holdout stage |
| Holdout contamination, disclosed | The same calendar holdout was used in Phase 1 for spot event tests, where capitulation dip-buying lost 35 bp per trade. It also contains the widely reported 10 Oct 2025 liquidation cascade. Both facts are known before any Phase 2 test |
| Lock | `crypto/perp/src/perp_research.py` refuses windows past 2025-09-30 until `crypto/perp/HOLDOUT_UNLOCKED` exists. The holdout runs once |
| Execution | Signal on the close of 4h bar t, fill at the open of t+1, exit at the open of t+1+H. Robustness check: one extra bar of delay |
| Costs per side | Perp taker fee 5 bp (Binance USD-M VIP0) plus slippage: BTC and ETH 1 bp; SOL XRP DOGE BNB 2 bp; the rest 3 bp. A round trip is 12-16 bp. Stress check: 2x. Spot leg (carry only): 10 bp fee plus the Phase 1 spot slippage tiers |
| Funding | Charged at 00:00, 08:00 and 16:00 UTC on positions open across those times: longs pay the reconstructed rate, shorts receive it. Some Binance alts settle every 4h; they are modelled on 8h intervals |
| Frequency requirement | The reference cell must average at least 3 trades a week, pooled over U16, in the design window |
| Ledger | every cell and robustness row goes to `crypto/perp/TRIAL_LEDGER.csv` |

Definitions (all on 4h bars, using data up to bar t only):
- r_t = close/close[1] - 1; **r_z** = r_t / stdev(r, 50 prior bars).
- dOI_t = OI_close/OI_close[1] - 1; **oi_z** = dOI_t / stdev(dOI, 50 prior bars).
- **oi6_z** = (OI/OI[6] - 1) / stdev(6-bar OI change, 180 prior bars).
- **prem_z** = (premium close - mean(premium, 180 prior bars)) / stdev(premium, 180 prior bars).
- **OBV** = cumulative sign(close - close[1]) x volume.

## 2. Hypotheses

| ID | Rationale | Long signal | Short signal | Grid | Reference cell |
|---|---|---|---|---|---|
| **P1 OI flush** | forced liquidations overshoot; once the leverage is flushed, price mean-reverts | r_z <= -k and oi_z <= -m (price dump while OI collapses) | r_z >= +k and oi_z <= -m (squeeze while shorts are liquidated) | k {2, 3} x m {1.5, 2.5} x H {1, 3, 6, 12} x side | k 2, m 1.5, H 3 |
| **P2 crowding fade** | crowded leverage (premium stretched, OI building) unwinds against the crowd | prem_z <= -z0 and oi6_z >= z1 (shorts piling in) | prem_z >= +z0 and oi6_z >= z1 (longs piling in) | z0 {1.5, 2.5} x z1 {1, 2} x H {3, 6, 12, 24} x side | z0 1.5, z1 1, H 6 |
| **P3 OI-confirmed breakout** | a breakout backed by new positions continues; OI filter off is the pure-breakout ablation | close > max(close, N prior bars) and (filter: OI/OI[6] > 1) | close < min(close, N prior) and (filter: OI rising) | N {20, 60} x filter {on, off} x H {3, 6, 12, 24} x side | N 20, on, H 6 |
| **P4 OBV divergence** | a new price low on weaker selling volume marks absorption | close < min(close, N prior) and OBV > min(OBV, N prior) | close > max(close, N prior) and OBV < max(OBV, N prior) | N {20, 60} x H {3, 6, 12, 24} x side | N 20, H 6 |
| **P5 funding carry** | leveraged longs pay shorts; a spot-long / perp-short pair collects that with no price exposure | enter a coin when the trailing 3-day mean funding >= θ; exit when it falls below θ/2 | (the pair is delta-neutral) | θ {0.01%, 0.02%, 0.03%} per 8h | θ 0.01% |

P1-P4 are event families: (hypothesis, parameters other than H, side). One trade per signal, no pyramiding per symbol.

P5 is a portfolio. Each of the 16 coins has a slot of 1/16 of capital. An active slot holds a spot-long and perp-short pair of equal notional, with capital = 1.5x notional (perp margin at 2x). P&L comes from funding received, minus the basis change (premium at exit minus premium at entry), minus four legs of costs at entry and exit. An idle slot earns 0. Signals are checked at each 00:00/08:00/16:00 UTC funding time.

**Cell count:** P1 32 + P2 32 + P3 32 + P4 16 + P5 3 = 115, plus delay, cost and bias rows.

## 3. Pass rules (design window)

**Event families (P1-P4):** all of E1-E8 at the reference cell, base costs.
- E1: pooled mean net > 0 with day-clustered t >= 2.0.
- E2: mean net > 0 in at least 3 of the 4 horizons.
- E3: excess over unconditional drift > 0 (for shorts, drift is the negative of the long drift).
- E4: mean net > 0 in at least 60% of the symbols with 5+ trades.
- E5: one bar of delay keeps mean net > 0 and at least 50% of the base value.
- E6: mean net > 0 at 2x costs.
- E7: at least 30 trades.
- E8: at least 3 trades a week pooled.

**P5 carry:** annualised return on capital >= 3% net, Sharpe >= 2, max drawdown no deeper than -3%, and still >= 0% return when every reconstructed funding print is lowered by 0.003% (funding-model bias check).

**Holdout (families that pass only, reference cell, run once):**
- Events: mean net > 0, t >= 1.0, breadth >= 50% on the 4h holdout. C9 at 1h is reported but has no veto.
- Carry: return > 0 and Sharpe >= 1.

Nothing that fails can be deployed. Anything that passes goes to a paper bot first, and its funding assumption must be checked against real funding prints before any live capital.
