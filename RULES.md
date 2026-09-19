# RULES.md — the final system in plain English

One decision per day, after the close, using adjusted closing prices. Orders are placed for the next day's close. Everything below can be computed by hand from closing prices.

**Instruments.** QQQ, SPY, IWM, TLT, GLD, IEF, and a cash sleeve (BIL or a money-market fund). For exposure above 1x the same positions are expressed with the 3x funds TQQQ, UPRO, TMF and the 2x funds UGL and UST, never with borrowing. No inverse funds: every inverse-fund variant tested lost money.

**Two sleeves, blended 70 / 30.**

1. **Equity core (70% of capital).** Each day compute the 200-day simple moving average of QQQ's close and the annualised volatility of QQQ's last 20 daily returns.
   - If QQQ closes above its 200-day average, hold QQQ with exposure equal to 10% divided by that volatility, capped at 100% of the sleeve. (Example: volatility 25% gives 40% of the sleeve in QQQ, the rest in cash.)
   - If QQQ closes below its 200-day average, hold nothing in QQQ. Instead, if IEF closes above its own 200-day average, hold the whole sleeve in IEF; otherwise hold cash.

2. **Momentum rotation (30% of capital).** On the last trading day of each month, for each of SPY, QQQ, IWM, TLT and GLD compute the total return over the last 126 trading days. Rank them. Take the top three. Any of the three whose 126-day return is below the 126-day return of cash is replaced by cash. Hold the survivors in equal thirds of the sleeve until the next month end.

**Rebalancing band.** Compare each instrument's target weight with its current drifted weight. Only trade an instrument when the difference exceeds 2% of account equity. This keeps trades to roughly 75 a year and next-day round trips to about 7 a year, so the system runs in a cash account without limited margin.

**Exposure multiplier (the only risk knob).** Multiply every target exposure by a single number. 1.0 is the base case. Above 1.0 the excess is carried in the 3x or 2x fund of the same underlying so that fund weights still sum to 100% or less. The design-window frontier was: multiplier 1.0 for a 15% drawdown tolerance, 2.5 for 25%, and 3.0 (the most the fund set allows) reaches only 27%.

**Costs assumed.** 2 bp commission plus half spread per trade, doubled on leveraged funds.

**The eight free parameters.** 200-day trend length (shared by the QQQ gate and the IEF gate), 10% volatility target, 20-day volatility window, 126-day momentum lookback, top-3 rotation count, 70% core weight, 2% rebalance band, exposure multiplier.

**What it does not do.** No intraday logic, no options, no shorting, no inverse funds, no VIX inputs, no drawdown-control overlay (tested: it raised MAR by about 0.02 at the cost of 0.5% CAGR and a ninth parameter).
