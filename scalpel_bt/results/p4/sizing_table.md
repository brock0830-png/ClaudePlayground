# A2 sizing table (99th-percentile drawdown, block bootstrap by calendar month, 10,000 paths)

Daily mark-to-market drawdown, fixed size (no compounding), 2013-01 to 2026-09. ES figures are points per
contract with MES costs (0.84 pt per round trip and per roll); 1 MES = $5 per point. SPY figures are
% of the position. P2A+P3B = one unit of each, held independently (up to 2 units at once).

## Drawdown and losing streaks

| System | Trades | Hist. max DD | DD p50 | DD p95 | DD p99 | Worst month | Longest losing streak p50 / p95 / p99 (hist.) |
|---|---|---|---|---|---|---|---|
| ES P2A | 153 | 676 pt | 721 pt | 1060 pt | 1284 pt | -280 pt | 4 / 7 / 8 (4) |
| SPY P2A | 149 | 15.1% | 16.4% | 26.6% | 32.7% | -11.3% | 4 / 7 / 9 (4) |
| ES P3B | 111 | 821 pt | 739 pt | 1241 pt | 1562 pt | -243 pt | 4 / 7 / 8 (5) |
| SPY P3B | 115 | 23.1% | 21.1% | 36.7% | 46.0% | -9.0% | 4 / 6 / 8 (3) |
| ES P2A+P3B | 264 | 1332 pt | 1333 pt | 1984 pt | 2389 pt | -454 pt | 6 / 9 / 12 (7) |
| SPY P2A+P3B | 264 | 32.7% | 28.4% | 46.4% | 57.6% | -17.1% | 5 / 8 / 10 (5) |

## MES sizing (drawdown tolerance at the 99th percentile)

| System | Tolerance | Account $ per MES | MES at $25k | $50k | $100k | $250k |
|---|---|---|---|---|---|---|
| P2A | 15% | $42,787 | 0 | 1 | 2 | 5 |
| P2A | 20% | $32,090 | 0 | 1 | 3 | 7 |
| P2A | 25% | $25,672 | 0 | 1 | 3 | 9 |
| P3B | 15% | $52,067 | 0 | 0 | 1 | 4 |
| P3B | 20% | $39,050 | 0 | 1 | 2 | 6 |
| P3B | 25% | $31,240 | 0 | 1 | 3 | 8 |
| P2A+P3B | 15% | $79,640 | 0 | 0 | 1 | 3 |
| P2A+P3B | 20% | $59,730 | 0 | 0 | 1 | 4 |
| P2A+P3B | 25% | $47,784 | 0 | 1 | 2 | 5 |

For P2A+P3B the count is MES per system (each system trades that many contracts).

## SPY sizing (dollars of SPY per $1 of account)

| System | 15% | 20% | 25% |
|---|---|---|---|
| P2A | 0.46 | 0.61 | 0.77 |
| P3B | 0.33 | 0.43 | 0.54 |
| P2A+P3B | 0.26 | 0.35 | 0.43 |

A value above 1.00 means the tolerance allows more than 1x the account in SPY, which needs margin (see A5). Reg T caps overnight stock leverage at 2x.

## ADDENDUM (after the run): MES sizing from % drawdowns at today's ES price

The pre-registered MES table above uses point drawdowns from 2013-2026, when ES was much lower. Measured in % of notional and converted at ES 7,750 (close of 2026-09-30), 1 MES is $38,750 of notional. Percent drawdowns use the raw traded entry price. **Use this table, not the one above.**

| System | DD p99 (% of notional) | Tolerance | Account $ per MES | MES at $25k | $50k | $100k | $250k |
|---|---|---|---|---|---|---|---|
| P2A | 31.5% | 15% | $81,325 | 0 | 0 | 1 | 3 |
| P2A | 31.5% | 20% | $60,994 | 0 | 0 | 1 | 4 |
| P2A | 31.5% | 25% | $48,795 | 0 | 1 | 2 | 5 |
| P3B | 42.9% | 15% | $110,783 | 0 | 0 | 0 | 2 |
| P3B | 42.9% | 20% | $83,087 | 0 | 0 | 1 | 3 |
| P3B | 42.9% | 25% | $66,470 | 0 | 0 | 1 | 3 |
| P2A+P3B | 57.5% | 15% | $148,648 | 0 | 0 | 0 | 1 |
| P2A+P3B | 57.5% | 20% | $111,486 | 0 | 0 | 0 | 2 |
| P2A+P3B | 57.5% | 25% | $89,189 | 0 | 0 | 1 | 2 |

For P2A+P3B the count is MES per system.
