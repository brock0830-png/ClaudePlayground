# Vault finalists (frozen before the vault was opened)

Vault = all 35 coins, signal bars 2025-07-01 to 2026-08-31. It is opened once, and every result is reported.

| ID | Why it is here | Vault metric |
|---|---|---|
| A:A9L_fade_accept_below_PDL | passed validation on both parts (+0.28% and +0.21% per trade, day-t 3.5 and 5.8) | per-trade and per-day mean net, day-t; also the K=10 causal portfolio (Sharpe, CAGR, MaxDD) |
| A:A6L_newlow_pos_delta | the only order-flow (delta) event that passed validation, formally (+0.02% per trade) | per-trade mean net, day-t |
| C:pos_d:lo | screen: location in the developing day range (validation spread t 4.8, both parts) | top-bottom spread, day-t |
| C:below_pdval:hi | screen: close below the previous-day VAL (validation t 4.5, both parts) | spread, day-t |
| C:x_PDVAL:lo | screen: distance to the previous-day VAL (validation t 5.4, both parts) | spread, day-t |

Not advanced:
- A9L_mkt (BTC filter): per-trade mean 0.00% in validation.
- A9S and A6S: per-trade mean < 0.
- The other screen features: they were redundant or their per-trade spread had the wrong sign.

The flush signal is not a vault finalist because its 2025-07 to 2026-08 trades already sit inside the spec's cells.
Its vault-period numbers are printed for information and labelled as not clean.
