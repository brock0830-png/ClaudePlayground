# Market Profile + footprint test plan (ES / NQ futures), v3

**v3.** v2 was checked against the full text of *Mind Over Markets* (updated edition, chapters 2-4 and
Appendix 1). v3 adds testable concepts from *Markets in Profile* (Dalton, Dalton & Jones, 2007) and
*Steidlmayer on Markets* (2nd ed.), in section 4b. Supersedes v1 and v2. Page references without a
prefix are to *Mind Over Markets*; "MiP" = *Markets in Profile*; "SoM" = *Steidlmayer on Markets*. Definitions are operational translations of Dalton's concepts. Where the book is
qualitative, a concrete threshold is chosen here and frozen. Page references are to the book, so
anyone can check the translation.

Rules for whoever runs this (Claude Code):
1. Commit this file before loading any price data.
2. Log every evaluation (pass or fail) to a ledger with a fixed schema.
3. Never change a frozen definition after seeing confirm-stage or final-stage data.

The book's own statistics (3-to-I and Neutral-Extreme studies) come from Treasury bonds, 1986-87,
one market. Part of the point here is to see whether they survive modern ES.

---

## 0. Why ES and not crypto

Market Profile is built on a session: the open, the Initial Balance, the close, and overnight
inventory. Crypto trades 24/7 with an arbitrary UTC day, and classic MP rules already failed there
(orderflow report, Sept 2026). ES/NQ is the market these concepts were written for.

## 1. Data

| Need | Source (get a cost estimate first) | Used for |
|---|---|---|
| 1-minute OHLCV, ES and NQ, continuous front month, full available history | Databento, CME Globex (`GLBX.MDP3`, `ohlcv-1m`) | Everything in Phase 1 |
| Trades with aggressor side, ES only, **event windows only** | Databento `trades` schema | Phase 2 footprint features |

- **Session:** RTH 09:30-16:15 ET, in 30-minute periods A, B, C... (last period is 15 minutes).
  Overnight (ETH) is kept separately for overnight-inventory tests.
- **Opening range (OR):** the first 5 minutes of RTH.
- **Roll:** on volume switch, back-adjusted for profiles. Record roll dates.
- **TPO row size:** 1 tick (0.25). If a day's profile exceeds 400 rows, use 2 ticks for that day and log it.
- **Costs:** 1 tick slippage per side plus $5 commission per round turn. Report gross and net.

## 2. Sample split (fixed now)

| Stage | Period | Use |
|---|---|---|
| Explore | first available date (confirm, likely mid-2010) to 2016-12 | Variants allowed within the families below. Every look is logged. |
| Confirm | 2017-01 to 2021-12 | Frozen candidates only |
| Final | 2022-01 to 2026-08 | **One** look at confirm-stage survivors |
| Second market | NQ, all years | Frozen survivors only, judged like the final stage |

## 3. Profile definitions

**Core structure**

- **Initial Balance (IB):** RTH range of periods A+B. IB ratio = IB / median IB of the prior 20 sessions. Narrow < 0.7, wide > 1.3. (Book p.11-13, 19)
- **Range extension (RE):** any trade beyond the IB. Record side, order and period. (p.13)
- **POC:** the row with the most TPOs, closest to the range center on ties. (p.14-15)
- **Value area (VA):** 70% of TPOs. Start at the POC and repeatedly add whichever *pair* of adjacent rows (above vs below) has more TPOs. (Appendix 1) Also compute a volume VA as a robustness check only.
- **Tail:** at least 2 consecutive single-print rows at a day extreme, not formed in the last period. (p.14, 40)
- **Poor high/low:** no tail, and at least 2 TPOs from different periods at the extreme row.
- **Single prints (mid-profile) / low-volume area:** at least 3 consecutive single-TPO rows not at an extreme. (p.25-26, 138-139)
- **TPO count:** TPOs above vs below the POC, excluding single-print tails. More below = buyers favored. (p.41-45)
- **Rotation Factor (RF):** for each period after A: +1 if its high > the prior period's high, -1 if lower, 0 if equal; same for lows; sum. Recorded as a descriptive feature only. The book says it answers direction only, not strength, so it is not a trade signal. (p.112-113)
- **Initiative vs responsive (vs prior-day VA):** buying at or above prior VAL = initiative; buying below prior VAL = responsive. Mirror for selling. Applies to tails, RE and TPO count. (p.45-48)

**Open and acceptance**

- **Open location:** inside prior VA / outside VA but inside prior range / outside prior range. (p.74-85)
- **Acceptance** of an area: price trades in it for at least 2 consecutive periods (about one hour, "double TPO prints"). **Rejection:** fails to do so. (p.75, 244)
- **Opening types**, classified from the first 30 minutes (p.63-73):
  - *Open-Drive:* after the OR, price auctions one way and does **not** trade back through the OR during A and B.
  - *Open-Test-Drive:* in A, price first trades at least 2 ticks beyond a known reference (prior-day high/low or bracket high/low), then reverses back through the OR and drives the other way.
  - *Open-Rejection-Reverse:* in A, price trades one way at least 0.25x the 20-day median A-range, then reverses back through the OR, with no reference test required.
  - *Open-Auction:* none of the above. Split into **in range** (open inside prior range) and **out of range** (open outside prior range).

**Day type** (labels at close, for descriptive stats and next-day tests only; p.19-31)

- *Nontrend:* narrow IB, no RE.
- *Normal:* wide IB, no RE.
- *Normal Variation:* RE on one side, range at most 2x IB.
- *Trend:* RE on one side, open within 10% of a day extreme, and the profile is no more than 5 TPOs wide at any row.
- *Double-Distribution Trend:* narrow IB, then RE that forms a second distribution separated by mid-profile single prints.
- *Neutral:* RE on both sides. *Neutral-Extreme* if the close is in the outer 15% of the range, else *Neutral-Center*.

**Multi-day and special structures**

- **Balance area:** at least 3 consecutive sessions with overlapping VAs. Balance high/low = extremes of those sessions. 5 days is a logged variant. (p.252-259)
- **Spike:** the last 2 periods of the session trade beyond the VA of the session's earlier periods and cover at least 25% of the day's range. Spike range runs from the breakout period's start price to the day extreme. (p.247-252)
- **Overnight inventory:** RTH open in the top or bottom 20% of the overnight range, and on the same side of the prior close, is inventory long or short.
- **3-to-I day:** tail, TPO count and RE all initiative and all in the same direction. **2I-1R:** same, but with a responsive tail. (p.239-241)
- **P-shape (short covering):** POC in the upper third of the range, the lower third holding no more than 20% of TPOs, most of the rally in periods A-C, after at least 2 sessions of lower value. **b-shape (long liquidation)** is the mirror, after at least 2 sessions of higher value. (p.123-128)

## 4. Phase 1 hypotheses (direction fixed now)

Unless stated, the time exit is at the RTH close. Each hypothesis is compared with a **matched
baseline**: same entry time and side, on all days or on days with the same open location. The
expected result comes from the book.

| ID | Setup (book page) | Trade | Expected |
|---|---|---|---|
| MP1 | **Value-Area Rule** (p.244-246): open outside prior VA, then accepted back inside (2 periods) | Enter at end of 2nd period toward the far VA edge. Target = far edge. Stop = 30-min close back outside. | Book: about a coin flip alone |
| MP1c | MP1 with all three of the book's conditions: open inside prior range; prior VA narrow (bottom third of 20-day VA widths); trade in the direction of the 10-day value migration | same | Beats MP1 and baseline |
| MP2 | **Open-Drive** (p.63-65) | Enter at 10:00 in drive direction. Stop = trade back through the OR. | Continuation; the opening extreme holds |
| MP3 | **Open-Rejection-Reverse** (p.68-69) | After the reversal, do **not** chase. Enter on the first retest of the OR, in the reversal direction. Stop = the initial extreme. | Book says low conviction, a two-sided day, likely return to the OR. Also record: does the initial extreme hold < 50% of the time? |
| MP4 | **Open-Test-Drive** (p.65-67) | Enter at 10:00 in drive direction. Stop = back through the OR. | Continuation, slightly weaker than MP2 |
| MP5 | **Open-Auction in range** (p.70) | From 11:00, fade touches of the developing VAH/VAL toward the developing POC. Stop 4 ticks beyond the day's extreme. | Rotational day; fades work |
| MP6 | **Open-Auction out of range** (p.71-73) | Enter on the first 30-min close beyond the IB, in that direction. Stop = back inside the IB. | Bigger range; more double-distribution days |
| MP7 | **Narrow IB** (<0.7) (p.19, 25) | Same entry as MP6 | Range extension and trend days more likely |
| MP8 | **Wide IB** (>1.3) (p.19-21, Normal day) | Fade the first touch of IB high/low. Target IB midpoint. | IB extremes tend to hold |
| MP9 | **Range estimation** (p.75-79): open inside prior VA and accepted, then an A or B tail forms at one extreme | Enter toward the other side. Target = tail extreme ± 0.9 x prior day range. | Day's range is about the prior range (±10%) |
| MP10 | **Initiative vs responsive at open**: open above (below) prior VA (p.45-48, 79-85) | Accepted outside in the first hour: enter at 10:30 with it. Rejected back into VA: enter at 10:30 toward prior POC. | Accepted continues; rejected rotates |
| MP11 | **Overnight inventory** long (short) | Enter against the inventory at the open, exit 10:30 | First-hour inventory correction |
| MP12 | **Balance-area breakout** (p.252-259) | Enter when price trades 2+ ticks beyond the balance extreme. Stop 4 ticks back inside. Primary exit: close. Secondary exit: 3 sessions. | Go with the breakout |
| MP12b | **Failed breakout**: MP12 stopped out the same session (p.257-259) | Enter the opposite balance-extreme break, same rules | "Break to rally" |
| MP13 | **Neutral-Extreme** day (p.241-243) | Enter at the close in the closing direction. Primary exit: next day 11:00 (first 90 min). Secondary: next close. | Book (T-bonds 86-87): next day traded beyond prior VA in first 90 min 64% of the time |
| MP14 | **3-to-I day** (p.239-241) | Same as MP13 | Book: 94% traded beyond prior VA in first 90 min next day; 97% closed within or beyond |
| MP14b | **2I-1R day** | Same | Book: weaker, 71% / 82% |
| MP15 | **Spike**, next-day open beyond the spike in its direction (p.249-252) | Buy (sell) the first test of the spike edge. Stop 4 ticks inside the spike. | Acceptance: continuation |
| MP15b | Open inside the spike (p.247-249) | Fade the spike extremes. Target spike midpoint. | Balancing day inside the spike |
| MP15c | Open against the spike (rejection) (p.249-252) | Enter at 10:00 against the spike direction | Rejection continues |
| MP16 | **Poor high/low**, prior day | Next day, if the open is within 1 IB-width of it, trade toward it. Target = the level. | Revisited more often than a same-distance high/low that has a tail |
| MP17 | **Tail** (excess), prior day (p.40, 110-112) | Fade the first test of the tail's inner edge. Stop beyond the tail extreme. | Tail holds |
| MP18 | **Mid-profile single prints / low-volume area**, prior day (p.138-139) | Fade the first test. Stop 4 ticks through the far side of the single prints. | Low-volume area holds like excess; once pierced, price moves fast |
| MP19 | **Value placement**: 2+ sessions of higher (lower) VA, and the open inside/above (below) the prior VA (p.54, 159-169) | Enter at the open in trend direction | Continuation |
| MP20 | **P-shape** after lower value (short covering) (p.123-127; MiP ch.8 "Trend Traders' Trap") | Short at next open. Mirror b-shape: long at next open. | The prior trend resumes. MiP: long liquidation drains selling potential and sets up a rally |
| MP21 | **Gap**: open outside prior range, not filled in the first hour (p.260-265) | Enter at 10:30 in gap direction | Continuation |
| MP22 | **Prior-week composite VAH/VAL**, first test in the week | Fade the first touch. Stop 8 ticks beyond. | Holds |

In the explore stage, variants of these definitions are allowed (thresholds, entry timing) but every
variant is logged, and nothing outside these families can advance.

## 4b. Additions from *Markets in Profile* and *Steidlmayer on Markets* (direction fixed now)

Same rules as section 4: one entry, one exit, a matched baseline, and the same stages and pass rule.

| ID | Setup (source) | Trade | Expected |
|---|---|---|---|
| MP23 | **Confirmed auction point** (SoM ch.11, p.168-170). The auction point is 1 tick beyond the IB high (low). It is confirmed when the session **closes** beyond it. | In the next 5 sessions, go with it on the first retest from the extension side: buy at an upside auction point, sell at a downside one. Stop 4 ticks through. Exit at close. | Level holds as support (resistance). Participants who were rewarded there act again. |
| MP24 | **Failed range extension** (SoM ch.11). Range extends beyond the IB but the close is back inside it. | In the next 5 sessions, fade the first return to the auction point. Stop 4 ticks beyond. Exit at close. | Level acts as resistance (support). Participants who were burned there fade it. |
| MP25 | **Narrow-range day** (SoM ch.4, p.41-42): RTH range <= 0.6x the 20-day median | Next day: enter on the first 30-min close beyond the IB, in that direction. Stop = back inside the IB. Exit at close. Also record whether the next day's range exceeds the median. | Narrow days come before big days and new directional moves |
| MP26 | **Timeslots-used** (SoM ch.6, p.75-81). Composite = sessions since the last range-expansion day (range >= 1.5x the 20-day median), capped at 10. Count the 30-min TPOs at the composite's widest row. | Count >= 43: enter next open **against** the direction of the move that started the composite, hold 3 sessions. Count <= 18: enter **with** it, hold 3 sessions. | SoM's matrix: 0-18 = trend continuation; 43+ = overdevelopment, price should move opposite. The composite start is this spec's own translation of SoM's "market time" and is the weakest definition here. |
| MP27 | **Repeated lows (highs) without excess** (MiP ch.8, "Correction of Inventory Imbalances"): 2+ session lows in the last 5 sessions within 0.25x the 20-day ATR of each other, none with a tail | Long at next open, hold 3 sessions. Mirror for highs. | Market too short to go lower, so it needs a short-covering rally |
| MP28 | **Bracket-extreme fade** (MiP ch.7, "Fade the Extremes, Go with Breakouts"). Inside a balance area (section 3), price probes beyond a balance extreme but is **not** accepted (back inside within the same or the next period). | Fade toward the balance midpoint. Stop 4 ticks beyond the probe's extreme. Exit at close. | Failed probes of a balance extreme reverse. This pairs with MP12 (go with accepted breakouts). |

Concepts from these books **not** turned into hypotheses (and why):
- Steidlmayer's *four steps of market activity* is a way of seeing any market move. It is already
  covered by MP12 (step 1, the directional move), MP15 (step 2, the stop) and MP26 (step 3,
  development).
- Steidlmayer's *minimum trend* is a charting method, not a signal.
- Most of *Markets in Profile* is about longer-term context and trading psychology.

## 5. Phase 2: footprint confirmation (only for Phase 1 survivors)

Market Profile gives the location and context. The footprint shows what happened when price got
there. That matches the book's order: logic starts the trade, time triggers it, structure confirms
it (p.37-38). Pull trades only for the minutes around each event. Measure on the 5-minute bar where
the MP trigger fires.

| ID | Feature | Good side (long; mirror for shorts) |
|---|---|---|
| FP1 absorption at level | Delta over the trigger bar is negative, but the bar closes in its upper half and holds the reference | Present |
| FP2 initiative aggression | Delta over the trigger bar is in the top third of its 20-day distribution, in trade direction | High |
| FP3 stacked imbalances | 3+ consecutive rows where buy >= 3x the diagonal sell, in the lower half of the trigger bar | Present |

Each is judged "with vs without" inside that survivor's trades, same stages and pass rule.

## 6. Pass rule (fixed now)

A hypothesis moves from explore to confirm if it is net-positive with t >= 2.0 over baseline in
the explore period.

It **passes** only if it is also:
- net-positive and beats baseline with t >= 2.5 in 2017-2021, **and**
- net-positive in the one-time 2022-2026 look, **and**
- net-positive on NQ over all years.

Report for each stage: trades, win rate, mean and median net ticks, t, and max drawdown in ticks.
Put the ledger count at the top of the report. For MP3, MP13, MP14, MP25 and MP26, also report the books'
descriptive statistics (extreme-hold rate, next-day location, next-day range) so they can be
compared with the books' claims directly. A fail is an acceptable result.

## 7. What not to do

- No tuning definitions on 2017+ data.
- No new hypotheses after seeing results. New ideas go in a new spec, tested on fresh data or
  going forward.
- Day-type labels are only known at the close. They're used only for next-day tests (MP13, MP14,
  MP20, MP25) or descriptive statistics, never as same-day entry signals.
