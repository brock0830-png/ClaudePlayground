# Operational conventions for SPEC_market_profile_ES_v3.md

The spec is frozen and is not edited. Where it leaves a choice open, the choice made in code is
listed here and tagged `[C#]` in the source. This file is committed before the explore stage runs,
so none of these choices is tuned on results. Nothing here changes a definition, threshold or pass
rule that the spec states.

## Data and sessions

- **C6 Sessions.** RTH sessions are NYSE trading days, 09:30 to 16:15 ET (13:15 ET on NYSE
  early-close days). A session is dropped if it has fewer than 60 RTH bars, its first bar is after
  09:35, or it has fewer than 30 bars in the first hour. Overnight (ETH) for a session is every bar
  between the prior RTH close and this session's 09:30 open. This includes any exchange-holiday Globex
  trading in between.
- **C7 Roll and back-adjustment.** The front month is Databento `ES.v.0` / `NQ.v.0` (volume
  roll). At each roll, spread = new minus old, taken at the last RTH minute both contracts traded
  in the last RTH session fully on the old contract. The new contract's bars for that window are
  fetched separately. The adjustment is additive and anchored on the latest contract. Databento
  switches contracts at 00:00 UTC (evening ET), so an RTH session never straddles a roll. Roll
  dates, symbols and spreads are in `rolls_ES.csv` / `rolls_NQ.csv`.
- **C3 TPO rows.** Rows are binned on the traded contract's own (unadjusted) ticks, then shifted
  by the session's constant adjustment. With 2-tick rows: POC = the POC row's low tick, VAH = the
  top value-area row's high tick, VAL = the bottom row's low tick, clamped to the session range.
  The 1- vs 2-tick decision (more than 400 one-tick rows) is logged per session as `rs`.
- **C5 Volume value area** (robustness only). Each 1-minute bar's volume is spread evenly over
  the ticks it traded. Phase 1 has no tick data.

## Profile

- **C1 Value area.** Appendix 1 pairwise method. When a side has only one row left, that row is
  its "pair". When the two pairs are equal, both are added.
- **C2 POC ties.** Closest to the range center, then the lower row.
- **C4 Tails.** Count single-print rows inward from the extreme and stop at the first row printed
  by the session's last period. The tail is that run if it has at least 2 rows. If the extreme row
  itself was printed by the last period, there is no tail. A poor high/low needs at least 2 TPOs
  at the extreme row (each period prints at most once per row, so they come from different
  periods).
- Mid-profile single prints: a run of at least 3 single-TPO rows that touches neither the top nor
  the bottom row.
- TPO count excludes rows in qualifying tails.

## Session labels

- **C10 Opening types.** OR = the 09:30-09:34 bars. Precedence: Open-Drive, then Open-Test-Drive,
  then Open-Rejection-Reverse, then Open-Auction.
  - *Open-Drive*: after the OR, during A, price trades beyond one OR extreme and never beyond the
    other. The final label also requires no trade beyond the other extreme through the end of B.
  - *Open-Test-Drive*: the known references are the prior RTH high/low and the 3-session balance
    high/low as of the prior close. A reference counts only if the open is not already 2 ticks
    beyond it. The test (at least 2 ticks beyond) must come before any trade beyond the opposite
    OR extreme. Price must then trade beyond the opposite OR extreme and A must close beyond it
    (the "drive").
  - *Open-Rejection-Reverse*: take the first direction in A to move at least 0.25 x the median
    A-range of the prior 20 sessions away from the open. Price must then trade beyond the opposite
    OR extreme within A. The initial extreme is the most extreme price before the reversal.
  - Trades entering at or after 10:00 use the label known at 10:00 (`open_A`). The final label
    (`open_type`, which needs period B for Open-Drive) is for descriptive statistics and the
    parity print.
- **C11 Day types**, precedence where the spec's types overlap:
  - RE on both sides: Neutral-Extreme (close in the outer 15% of the range), else Neutral-Center.
  - RE on one side, first match wins: DD-Trend (narrow IB plus a mid-profile single-print run
    reaching beyond the IB on the RE side); Trend (open within 10% of either extreme and every row
    at most 5 TPOs wide); Normal-Variation (range at most 2x IB); otherwise `Other-RE1`.
  - No RE: Nontrend (narrow IB), Normal (wide IB), otherwise `Other-noRE`.
  - The spec's list does not cover the two `Other` cases. Labels are descriptive only.
- **C12 Value relationship.** Higher value means VAL and VAH are both at or above the prior
  session's, with at least one strictly higher (this includes overlapping-higher). Lower value is
  the mirror. Anything else is neither.
- **C13 Initiative vs responsive** (vs the prior VA):
  - Measured at the tail's midpoint for tails, at the midpoint between the IB extreme and the day
    extreme for RE, and at the POC for the TPO count.
  - Tail and RE directions exist only when exactly one side has a tail or an extension.
  - 3-to-I needs tail, RE and TPO count all initiative in one direction. 2I-1R is the same with
    a responsive tail.
- **C14 P-shape.** All of the following:
  - the POC row's midpoint is in the upper third of the range;
  - rows in the lower third hold at most 20% of TPOs;
  - the day's low was made in A, B or C;
  - by the end of C price had risen more than half the day's range above that low;
  - the two prior sessions each had lower value than the session before them.

  The b-shape is the mirror.
- **C9 Spike.** Both of the session's last two periods trade beyond the value area (pairwise, 70%)
  of all earlier periods, and the spike side's day extreme is made in them. Their combined range
  must cover at least 25% of the day's range. Spike range = the first of the two periods' open to
  the day extreme. If both sides qualify, there is no spike.
- Balance area: the longest run of sessions ending at the prior close whose value areas share a
  common overlap, with at least 3 sessions (5 as the logged variant). Its high/low are the RTH
  extremes of those sessions.
- Overnight inventory: RTH open at or above `ON high - 0.2 x ON range` and above the prior RTH
  close means long; the mirror means short.
- Acceptance: at least 2 consecutive 30-minute periods whose ranges overlap the area. Rejection
  otherwise.
- 20-day medians (IB, A-range, RTH range) use the 20 sessions before the current one. ATR(20)
  includes the current session. True range uses the prior RTH close.

## Execution

- **C8 Intrabar path.** Each 1-minute bar goes O, L, H, C (up bar) or O, H, L, C (down bar). A
  flat bar visits the extreme nearer the open first. A level crossed inside a bar fills at the
  level. A level crossed by the bar's open (a gap) fills at the open. Stops, targets and entries
  are ordered by this path.
- **C15 Clock-time entries.** "Enter at the end of a period" and "on a 30-minute close" both mean
  the open of the next bar. Time exits (10:30, 11:00) are the open of that bar. "The close" is the
  last RTH bar's close.
- **C17 "Back inside" / "beyond".** "Back inside" an IB or balance extreme means a trade 1 tick
  inside it. "Beyond" means at least 1 tick beyond unless the spec gives a number.
- Targets that are not whole ticks are rounded to the side that is harder to reach. A trade whose
  entry is already at or through its stop or target is skipped.
- Stops are monitored in RTH only. An overnight gap through a stop fills at the next RTH open.
- **C21 One position at a time.** Within each evaluation, a signal that arrives while a position
  is open is skipped. Intraday hypotheses take the first signal of the session.
- Costs: 1 tick slippage per side plus $5 per round turn = 2.4 ES ticks. Gross is also reported.
- Hypotheses without a stop in the spec (MP8, MP9, MP10, MP11, MP13, MP14, MP14b, MP15b, MP15c,
  MP16, MP19, MP20, MP21, MP26, MP27) exit only at their target, if any, or at their time exit.
  "Toward X" (MP10 rejected leg, MP28) gives a direction, not a target.

## Hypothesis details

- MP1: acceptance back inside the prior VA can complete in any period before the last. The stop
  is a later 30-minute close back beyond the edge the market opened outside. MP1c adds:
  - the open is inside the prior RTH range;
  - the prior VA width is at or below the 1/3 quantile of the 20 widths ending at the prior
    session;
  - the trade side equals sign(VA midpoint of the prior session minus VA midpoint 10 sessions
    before that).
- **C16 MP3**: enter on the first touch of the OR edge on the reversal side at or after 10:00. If
  price at 10:00 is already back through that edge, there is no trade. The stop is 1 tick beyond
  the initial extreme.
- **C22 MP5**: the developing profile is built from the completed periods and updated every 30
  minutes. Entry is the first touch from inside of the developing VAH or VAL from 11:00, one trade
  per session. The stop is the day's extreme so far plus or minus 4 ticks; the target is the
  developing POC at entry.
- MP6, MP7, MP25: the first period close beyond the IB from period C onward.
- MP8: the first touch of the IB high or low from 10:30. The target is the IB midpoint.
- MP9: the A/B tail comes from the profile of A and B only (both may form it). Entry is at 10:30.
- MP10: accepted = A and B both trade beyond the prior VA edge the market opened beyond. Rejected
  = not accepted, and A or B traded inside the prior VA. The rejected leg is taken only if price
  at 10:30 is still on the open's side of the prior POC.
- MP12/MP12b: the entry is a stop order 2 ticks beyond the balance extreme and fills at the open
  on a gap. MP12b is the opposite break after an MP12 stop-out in the same session, with the same
  rules.
- MP13/MP14/MP14b: entry at the RTH close, primary exit at the next session's 11:00 open.
- MP15: the open must be beyond the spike. Take the first touch of the spike edge from that side.
- MP15b: the first touch from inside of either spike extreme.
- MP15c: entry at 10:00 against the spike.
- MP17: the open must be on the inner side of the tail. MP18: the open must be outside the
  single-print run; take the first touch of any run's near edge.
- **C18 MP22**: the composite covers all RTH periods of the prior calendar week, with 1-tick rows
  and the pairwise 70% VA. Take the first touch of each level in the current week. The side price
  approaches from sets the fade direction. A week that opens exactly on a level skips it.
- **C19 MP23/MP24**: the auction point (AP) is the IB extreme plus or minus 1 tick.
  - MP23 is confirmed when the close is strictly beyond the AP. MP24 is a failed extension: RE on
    that side and a close at or inside the IB extreme.
  - Both look for the first touch in the next 5 RTH sessions: from the extension side for MP23,
    from the IB side for MP24.
- **C23 MP16**: "1 IB-width" is the prior session's IB width. The open must not have repaired the
  poor extreme yet. If both qualify, take the nearer one. Entry is at the open.
- **C24 MP26**: a range-expansion day has a range of at least 1.5x the prior-20 median. The
  composite is the sessions after the latest expansion day through today, capped at 10. The count
  is the most TPOs in any 1-tick row. The starting move's direction is sign(close - open) of the
  expansion day. Exit is at the close of the 3rd session.
- **C25 MP27**: at least 2 session lows within 0.25 x ATR(20) of the lowest low of the last 5
  sessions, none with a buying tail, means long at the next open. Highs are the mirror. If both
  qualify, there is no trade.
- MP28: a probe is the first trade at least 1 tick beyond a balance extreme. It is not accepted if
  price trades 1 tick back inside before the end of the next period, and that is the entry. The
  stop is the probe's most extreme price plus or minus 4 ticks.

## Statistics and the explore stage

- **C20 Matched baseline.** For each trade: excess = side x (trade move - mean move from the same
  clock time with the same exit rule over all explore sessions). The baseline has no stop or
  target, and costs cancel. t = mean(excess) / (sd / sqrt(n)).
  - Baseline sessions: those with the same open location (inside prior VA / outside VA inside
    range / outside range) for MP1, MP1c, MP5, MP6, MP9, MP10, MP19 and MP21, whose setups are
    defined by that location. All sessions for the rest.
  - The other baseline's t is logged as `t_vs_alt_baseline` but plays no part in any decision.
- Explore sample: the first usable RTH session (data start 2010-06-06) to 2016-12-30. Prices after
  2016-12-31 are cut off before any feature is computed. Trades that would need later data are
  dropped.
- Variants run in explore:
  - the spec's own definition;
  - the spec's named variants: 5-session balance (MP12, MP12b, MP28), the 3-session exit (MP12,
    MP12b) and the next-close exit (MP13, MP14, MP14b);
  - the two legs of MP10, each on its own;
  - the volume value area for MP1, MP1c, MP10 and MP19. These are robustness rows: logged, but
    they can never be frozen.

  No other thresholds or entry times were tried.
- Explore rule (spec section 6): an eligible variant with mean net ticks > 0 and t over the
  matched baseline of at least 2.0 (at least 2 trades). Every qualifying variant is frozen as its
  own candidate.
