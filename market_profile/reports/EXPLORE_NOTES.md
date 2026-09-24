# Explore stage: observations

Written after the explore run. Nothing here changes a frozen definition or the candidate list. Points that
suggest a different definition belong in a future spec (v4), tested on fresh data (spec section 7).

## Candidates

- **MP10 rejected leg** (open outside the prior VA, back inside it in the first hour, 10:30 toward the prior POC):
  32 trades in 6.5 years, mean +14.8 net ticks, t 2.58 over the open-location baseline. The three best trades are 63%
  of the total, and 2010 and 2013 were negative. The combined MP10 hypothesis (both legs, 1,061 trades) and the
  accepted leg (1,029 trades) were net-negative.
- **MP16 poor high/low** (prior-day poor extreme within one prior IB width of the open, trade toward it at the open):
  111 trades, mean +2.5 net ticks, t 2.26, target reached on 73% of trades. Positive in 5 of 7 years (2013 about flat,
  2016 negative).
- 45 eligible evaluations at t >= 2.0 would produce about one false positive by chance. Finding two is consistent with
  chance, and that is what the confirm stage (t >= 2.5 on 2017-2021) is for.

## Near misses (not frozen)

- **MP1 Value-Area Rule**: t over the baseline 2.44, but net-negative (-0.46 ticks per trade). The rule needs both.
  The volume-VA robustness row agreed (t 2.56, net -0.46).
- MP4 Open-Test-Drive (+15.5 net, t 1.63, 26 trades), MP20 P/b shapes (+10.3, t 1.65, 49 trades), MP21 gap
  (+2.1, t 1.69) and MP15b (+0.9, t 1.76) were net-positive but under t 2.0.

## Definitions that behaved differently from the book

- **Open-Drive is very common under this translation.** With a 5-minute OR, "breaks one side of the OR and never the
  other" is met by 65% of sessions at 10:00 and still by 49% after period B. Because Open-Drive takes precedence, few
  days are left for Open-Test-Drive (26) and Open-Auction (58 at 10:00). Dalton describes Open-Drive as the rarest,
  highest-conviction open. A minimum drive distance would be a v4 change.
- Book statistics in modern ES (explore period):
  - MP3 Open-Rejection-Reverse: the initial extreme held on 21% of 497 days (book: under 50%). Same direction as the book.
  - MP13 Neutral-Extreme: next day traded beyond the prior VA in the closing direction within 90 minutes on 83% of
    178 days (book 64%), yet the trade lost 6.2 net ticks on average. Probing beyond value did not mean follow-through.
  - MP14 3-to-I: 60% traded beyond the VA in the first 90 minutes (book 94%); 74% closed within or beyond (book 97%).
  - MP14b 2I-1R: 73% / 79% (book 71% / 82%), close to the book.
  - MP25 narrow-range days: the next day's range exceeded the 20-day median 22% of the time, against 49% on all days.
    That is the opposite of "narrow days come before big days". Volatility clustering dominates.
  - MP26 timeslots: after a count of 43+, price moved against the composite's starting move over the next 3 sessions
    39% of the time (36 cases). After a count of 18 or less it moved with it 45% of the time (580 cases). Neither
    matches the book's matrix.

## Data notes

- 1,650 explore sessions. One 2-tick-row day (2015-08-24, 119.75-point range). Six sessions have no RTH bars in the
  Databento file (2014-06-12, 06-13, 09-23 to 09-25, 12-31; Databento flags them as degraded). Details in
  `sessions_dropped_ES.csv`.
