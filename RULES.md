# RULES.md — TALOS v2 (configuration T7), the live system in plain English

Adopted 2026-09-19 at the client's request in place of the pre-registered TALOS v1 (whose rules are kept at the end). One decision per day, after the close, using adjusted closing prices. Orders are placed for the next day's close. Everything below can be computed by hand from closing prices.

**Instruments.** QQQ, SPY, IWM, TLT, GLD, IEF, and a cash sleeve (BIL or a same-day money-market fund). At the recommended 1.25x multiplier no leveraged fund is ever held (see the multiplier paragraph). The gold sleeve is never levered (no UGL). No inverse funds, never any borrowing.

**Three sleeves: 49% equity core, 21% momentum rotation, 30% gold.** (The v1 70/30 split scaled by 0.7, plus a 30% gold sleeve.)

1. **Equity core (49% of capital).** Each day compute the 250-day simple moving average of QQQ's close and the annualised volatility of QQQ's last 20 daily returns.
   - **Gate with a 1% band.** The gate turns ON when QQQ closes above 1.01 × its 250-day average and OFF when it closes below 0.99 × the average; in between it keeps yesterday's state.
   - Gate ON: hold QQQ with exposure equal to 10% divided by the 20-day volatility, capped at 100% of the sleeve; the rest of the sleeve in cash.
   - **Buy the dip.** If the gate is ON and today's close is the lowest close of the last 10 trading days, then for 5 trading days (today's signal and the next four) the QQQ exposure is doubled: min(100%, 2 × the vol-target size). The boost never applies while the gate is OFF.
   - Gate OFF: no QQQ. If IEF closes above its own 250-day average, hold the whole sleeve in IEF; otherwise cash.

2. **Momentum rotation (21% of capital).** On the last trading day of each month, for each of SPY, QQQ, IWM, TLT and GLD compute the total return over the last 126 trading days. Take the top three. Any of the three whose 126-day return is below the 126-day return of cash is replaced by cash. Hold the survivors in equal thirds of the sleeve until the next month end.

3. **Gold sleeve (30% of capital).** Each day: if GLD closes above its 250-day simple moving average, hold GLD with exposure equal to 10% divided by GLD's 20-day annualised volatility, capped at 100% of the sleeve; otherwise the sleeve is in cash.

**Rebalancing band.** Compare each instrument's target weight with its current drifted weight. Only trade an instrument when the difference exceeds 2% of account equity. At 1.25x this is about 100 trades a year and 9 next-day round trips a year; no limited margin is needed.

**Exposure multiplier: 1.25 (recommended).** Multiply every target exposure by 1.25. Because the gold sleeve scales the equity sleeves to 70%, no exposure ever exceeds 1x at this multiplier (the largest QQQ exposure over 1991-2026 was 70% of equity), so **no leveraged fund is ever held at 1.25x**: the multiplier only scales unlevered weights, and if the three sleeves together would exceed 100% they are scaled down proportionally. Leveraged funds (TQQQ etc.) would only enter above about 1.8x, which is not recommended. Use 1.0 for the lower-vol version (1991-2026: CAGR 10.2%, worst drawdown 11.3%, MAR 0.91).

**Costs assumed.** 2 bp commission plus half spread per trade, doubled on leveraged funds.

**The fourteen parameters.** 250-day trend length (QQQ gate, IEF gate, GLD gate), 1% gate band, 10% core volatility target, 20-day volatility window, 10-day dip lookback, 5-day dip hold, 2× dip multiplier, 126-day momentum lookback, top-3 rotation count, 70% core-to-rotation split, 30% gold weight, 10% gold volatility target, 2% rebalance band, 1.25 exposure multiplier.

**Record (net, next-close execution).** 1991-2026 at 1.25x: CAGR 11.7%, vol 11.1%, Sharpe 0.81, worst drawdown 14.0%, MAR 0.83. Design half 1991-2015: 11.1% / -13.9% / 0.79. Confirmation half 2016-2026: 13.1% / -13.2% / 1.00. TALOS v1 at 1x on the same windows: 10.3% / -15.5% / 0.67; 9.6% / -15.5% / 0.62; 11.8% / -14.4% / 0.82. Only v1 has a clean out-of-sample record (the one-shot 2016-2026 holdout); every v2 number is in-sample, because the dip, gold, band and 250-day choices were made after the holdout with the full 1991-2026 record in view.

**What it does not do.** No intraday logic, no options, no shorting, no inverse funds, no VIX inputs, no drawdown-control overlay, no silver, no levered gold, no bonds in the core's idle cash (all tested and rejected).

---

## TALOS v1 (pre-registered, one-shot holdout), for reference

Two sleeves, 70% core and 30% rotation, no gold sleeve. Core: QQQ sized 10%/vol20 while above its 200-day average (no band, no dip boost), else IEF if above its 200-day average, else cash. Rotation as above. 2% band. Eight parameters. 1998-2026 at 1x: CAGR 9.7%, Sharpe 0.75, worst drawdown 15.5%, MAR 0.63; locked holdout 2016-2026: 11.8%, 0.93, -14.4%, 0.82. `python daily_signal.py --v1` prints it.
