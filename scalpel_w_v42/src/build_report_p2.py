"""Writes REPORT_P2.md (phase 2: context / confluence / market profile) from stored outputs."""
import numpy as np
import pandas as pd

from common import LINEAGE, OUT, ROOT

FAM = OUT / "families"


def f(x, nd=3):
    if x is None or (isinstance(x, (float, np.floating)) and not np.isfinite(x)):
        return "inf" if (isinstance(x, (float, np.floating)) and x == np.inf) else "-"
    return f"{x:.{nd}f}"


def fam_table():
    rows = []
    for p in sorted(FAM.glob("p2round*_summary.csv")):
        d = pd.read_csv(p)
        d["round"] = p.stem.split("_")[0].replace("p2round", "P2-")
        rows.append(d)
    d = pd.concat(rows)
    L = ["| round | variant | real passers | placebo passers mean / max | real top-10 expR | placebo top-10 mean / max | beats placebo (count, top-10) | family screen |",
         "|---|---|---|---|---|---|---|---|"]
    for r in d.itertuples():
        st = "PASS" if r.family_pass else ("fail (b)" if r.screen_a else "fail (a)")
        L.append(f"| {r.round} | {r.variant} | {r.real_pass} | {r.plc_pass_mean:.0f} / {r.plc_pass_max} | {f(r.real_top10)} | "
                 f"{f(r.plc_top10_mean)} / {f(r.plc_top10_max)} | {r.beats_plc_pass}/4, {r.beats_plc_top10}/4 | {st} |")
    return "\n".join(L)


def meta_table():
    m = pd.read_csv(OUT / "meta_rank.csv")
    L = ["| searches | metric | families | real ranked 1st of 5 | share (chance = 0.20) | p (more often than chance) | mean rank (chance = 3.0) | p (better than chance) |",
         "|---|---|---|---|---|---|---|---|"]
    for r in m.itertuples():
        L.append(f"| {r.phase} | {'top-10 expectancy' if r.metric == 'rank_top10' else 'screen passers'} | {r.families} | "
                 f"{r.ranked_first} | {r.share_first:.2f} | {r.p_first_binom:.2f} | {r.mean_rank:.2f} | {r.p_mean_rank:.2f} |")
    return "\n".join(L)


def gate_table(g):
    ok = lambda b: "pass" if b else "**fail**"
    L = ["| id | tier | variant: config | IS n / PF / expR | 2021+ n / PF / expR | 2021+ placebo mean / max | LOTO | G1 | G3 2x slip | G4 x0.95/x1.05 | G5 placebo | G6 DSR | G7 | GC n / expR (placebo mean) | G8 GC | failed |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in g.itertuples():
        g4 = "n/a" if not np.isfinite(r.OOS2_expR_x095) else f"{f(r.OOS2_expR_x095)} / {f(r.OOS2_expR_x105)}"
        L.append(f"| {r.finalist} | {r.tier} | {r.variant}: `{r.config}` | {int(r.IS_n)} / {f(r.IS_pf, 2)} / {f(r.IS_expR)} | "
                 f"{int(r.OOS2_n)} / {f(r.OOS2_pf, 2)} / {f(r.OOS2_expR)} | {f(r.OOS2_plc_mean)} / {f(r.OOS2_plc_max)} | "
                 f"{r.LOTO_pos}/4 | {ok(r.G1_oos2)} | {ok(r.G3_slip2)} | {g4} {ok(r.G4_mult)} | {ok(r.G5_placebo)} | "
                 f"{ok(r.G6_dsr)} | {'needs 15m' if r.G7_needs_15m else 'ok'} | {int(r.GC_n)} / {f(r.GC_expR)} ({f(r.GC_plc_mean)}) | "
                 f"{ok(r.G8_gc)} | {r.failed} |")
    return "\n".join(L)


def scope_md(v, fid):
    q = v[(v.finalist == fid) & (v.run == "base")]
    L = ["| period | ticker | n | WR | PF | net expR | net $ | max DD $ |", "|---|---|---|---|---|---|---|---|"]
    for r in q.itertuples():
        L.append(f"| {r.period} | {r.scope} | {int(r.n)} | {f(r.wr, 2)} | {f(r.pf, 2)} | {f(r.expR)} | {r.usd:,.0f} | {r.maxdd_usd:,.0f} |")
    return "\n".join(L)


def year_md(tr, fid):
    t = tr[tr.finalist == fid]
    y = t.groupby(["period", "year"]).agg(n=("R", "size"), wr=("R", lambda x: (x > 0).mean()), expR=("R", "mean"),
                                           usd=("pnl_usd", "sum")).reset_index()
    L = ["| period | year | n | WR | net expR | net $ |", "|---|---|---|---|---|---|"]
    for r in y.itertuples():
        L.append(f"| {r.period} | {int(r.year)} | {r.n} | {r.wr:.2f} | {r.expR:+.3f} | {r.usd:,.0f} |")
    return "\n".join(L)


def ci(r, seed=1, n=5000):
    rng = np.random.default_rng(seed)
    bs = [rng.choice(r, len(r)).mean() for _ in range(n)]
    return np.percentile(bs, [2.5, 97.5])


def main():
    g = pd.read_csv(OUT / "validation_p2_gates.csv")
    v = pd.read_csv(OUT / "validation_p2_holdouts.csv")
    tr = pd.read_csv(OUT / "finalist_p2_trades_all.csv")
    dfl = pd.read_csv(OUT / "deflation_p2.csv", header=None, index_col=0)[1]
    meta = pd.read_csv(OUT / "meta_rank.csv").set_index(["phase", "metric"])
    G = g.set_index("finalist")
    p13, p02 = G.loc["P13"], G.loc["P02"]
    r13_is = tr[(tr.finalist == "P13") & (tr.period == "IS")].R.values
    r13_o = tr[(tr.finalist == "P13") & (tr.period == "OOS2")].R.values
    r02_o = tr[(tr.finalist == "P02") & (tr.period == "OOS2")].R.values
    c13_is, c13_o, c02_o = ci(r13_is), ci(r13_o), ci(r02_o)
    mp = pd.read_parquet(FAM / "screen_MPALONE.parquet")
    mir = mp[mp.config == "PVAH_DN|breakout|SIG|d0.00|c1|Dinf|s0.50|t2.00"].iloc[0]
    nb13 = mp[mp.config.str.startswith("PVAL_UP|breakout|SIG|d0.00") & mp.config.str.contains(r"\|c1\||\|c2\||\|b_reclaim\|")]
    nbm = mp[mp.config.str.startswith("PVAH_DN|breakout|SIG|d0.00") & mp.config.str.contains(r"\|c1\||\|c2\||\|b_reclaim\|")]
    gcm = v[(v.run == "base_min1") & (v.period == "GC_HOLDOUT")].set_index("finalist")
    p2m = meta.loc[("phase 2", "rank_top10")]
    p2p = meta.loc[("phase 2", "rank_pass")]
    idea = [("generalized uptrend (longs only above the 200-day SMA)", "P07"),
            ("avoid bullish setups in a strong bear market", "P08"),
            ("prior-week POC / value confluence (0.20 sigma)", "P09"),
            ("bullish / bearish RSI divergence (4h)", "P10"),
            ("basic S/R (prior-day high / low)", "P11"),
            ("stacked evidence (3 of 5 signals)", "P12"),
            ("market-profile levels alone, no v42", "P13")]
    idea_rows = ["| idea | finalist | IS n / PF / expR | 2021+ n / PF / expR | GC n / expR (min-one: n / expR) | LOTO | failed gates |",
                 "|---|---|---|---|---|---|---|"]
    for text, fid in idea:
        r = G.loc[fid]
        gm = gcm.loc[fid]
        idea_rows.append(f"| {text} | {fid} | {int(r.IS_n)} / {f(r.IS_pf, 2)} / {f(r.IS_expR)} | {int(r.OOS2_n)} / {f(r.OOS2_pf, 2)} / {f(r.OOS2_expR)} | "
                         f"{int(r.GC_n)} / {f(r.GC_expR)} ({int(gm.n)} / {f(gm.expR)}) | {r.LOTO_pos}/4 | {r.failed} |")
    md = f"""# REPORT_P2 - {LINEAGE} phase 2: context, confluence and market profile

Follow-up to [REPORT.md](REPORT.md). The question: do the weekly v42 levels work when a signal is taken only
with supporting evidence - trend regime, prior-week market profile (POC / value area), RSI divergence,
basic support / resistance - rather than on every touch? Same process as phase 1: full pierce grid under
each filter, the same filter on four placebo level sets, the family screen, EXPAND / REFINE rounds until
two rounds bring no new passing family, then frozen finalists, leave-one-ticker-out and holdouts.
Status tags: all numbers are **[NEW]** unless marked.

## 1. Verdict

**No rule passes every gate. [NEW]** The context filters named for the system do not turn the v42 levels
into an edge. Each was tested as a filter over the whole grid against placebo levels. The best rule for
each was frozen and tested on 2021-2026, and none held up there: uptrend, bear-market avoidance, RSI
divergence, prior-week POC, basic S/R, stacked evidence (Section 5).

Across the 56 phase 2 families, the real v42 levels rank first of five searches (real + four placebo
shifts) in {p2m.share_first:.0%} of families on top-10 expectancy and {p2p.share_first:.0%} on screen passers, where chance is
20% (p = {p2m.p_first_binom:.2f} and {p2p.p_first_binom:.2f}). Phase 1 was lower. Context does not make the v42 levels look
different from nearby arbitrary lines.

The in-sample favourite was a v42 level lying near prior value (0.20-0.30 sigma of the prior week's or
month's POC / VAH / VAL), traded as a long breakout. It passed the family screen across a whole range of
tolerances, which no phase 1 idea did. Out of sample it went flat or negative (P01, P03-P06, P09).

**One idea held up in 2021-2026, and the best version of it does not use v42 at all.** When the week
opens below the prior week's value area low, go long on a 4h close back above that VAL, with a stop
0.5 sigma below it, and hold to Friday (P13).
* In-sample: {f(p13.IS_expR)} R per trade [95% CI {c13_is[0]:.2f}, {c13_is[1]:.2f}], n = {int(p13.IS_n)}.
* 2021-2026: {f(p13.OOS2_expR)} R [{c13_o[0]:.2f}, {c13_o[1]:.2f}], n = {int(p13.OOS2_n)}, PF {f(p13.OOS2_pf, 2)}. That beats all four placebo
  level sets (max {f(p13.OOS2_plc_max)}), and 2022 was positive.
* The v42 version (P02) uses the RNG_T_HI breakout in weeks that open below prior value. It is weaker:
  {f(p02.OOS2_expR)} R [{c02_o[0]:.2f}, {c02_o[1]:.2f}], losing in 2022-2023.

P13 is still **not proven by the prompt's standard**. It has 84 trades from 2021 on (fewer than 100). Its
in-sample per-trade Sharpe ({f(p13.IS_SR_trade, 2)}) clears only the lenient deflation floor ({f(dfl['sr0_null_eff'], 2)}), not the strict
ones. The only clean holdout, GC, gives it {int(p13.GC_n)} trades under the $500 sizing rule ({int(gcm.loc['P13'].n)} with at
least one micro), at {f(p13.GC_expR, 2)} R. There the placebo levels did better ({f(p13.GC_plc_mean, 2)} R), though that is far
too few trades to mean anything either way. Its short mirror (sell a close back below the prior VAH in a week that
opened above it) loses in-sample: PF {f(mir.pf, 2)}, and every neighbouring config is negative. So the
effect is buying-side only.

What this means for the mission: whatever edge the people trading this system have is more likely in
the market profile they trade alongside than in the v42 levels. P13 is the one lead worth
forward-testing, and it needs fresh data before anyone trades it.

## 2. What was added

`src/features.py` builds every feature with no look-ahead (week-level values from the prior day, and
bar-level gates from the close before the entry bar):
* **Regime:** daily SMA50 / SMA200, strong bull or bear (price vs a rising or falling SMA200),
  drawdown from the 52-week high.
* **Market profile:** a TPO proxy built from the 4h bars. Each bar spreads its time over its range in
  0.02-sigma bins; POC plus a 70% value area are computed for the prior week, the prior two weeks, a
  4-week composite and the prior month. The developing weekly POC and TPO density (a thin/thick-node
  proxy) are also available. The exports have no volume, so this is time-at-price, not a volume profile.
* **RSI(14) divergence** on 4h and daily bars, using 2-bar confirmed pivots.
* **S/R:** prior-day high / low, daily swing pivots, prior-week high / low.

Families (`src/families_p2.py`): 64 variants in 5 rounds. Each is the full 229,068-config grid (MPALONE:
its own 1,416 cells) on the real levels and on four placebo shifts. Coverage is 100%, with 0 errors
(`coverage_summary.csv`).

## 3. Family results

{fam_table()}

Rounds 4 and 5 produced no new family that passed; their passes were refinements of the
profile-confluence region. That meets the stop rule.

## 4. Do the v42 levels beat nearby lines anywhere? (meta-test over every family)

{meta_table()}

## 5. Frozen finalists and gates

Frozen in commit `c3a4f31` (`FREEZE_P2.md`, `finalists_p2.csv`) from 2013-2020 only. Tier A is the six
best entry clusters from families that passed the screen; tier B is the best rule for each idea you
named, plus the market-profile levels alone. 2021+ is a **second look**: it was opened once in phase 1,
so it is weaker evidence than a first opening, although no phase 2 rule was chosen with it. GC
(COMEX:GC1! 4h, 2023-07 to 2026-09) was sealed on disk before phase 2 began and read once. G1-G7 are as
in phase 1, applied to 2021+. G8 needs >= 20 GC trades, a positive expectancy in R and $, and a result
above the placebo mean. DSR floors: {f(dfl['sr0_all'], 2)} (N = {int(dfl['n_all']):,}), {f(dfl['sr0_eff'], 2)} (N_eff = {int(dfl['n_eff']):,}), and
{f(dfl['sr0_null_eff'], 2)} for the lenient null-variance version with N_eff.

{gate_table(g)}

The ideas you named, answered directly:

{chr(10).join(idea_rows)}

![phase 2 finalists](outputs/finalists_p2_is_vs_oos2.png)

## 6. The lead: reclaim of prior value from below

**P13 (market profile only)**, `{p13.config}` on the prior-week value area low (VAL). The rule applies in
weeks whose open is at least 0.05 sigma below the prior VAL. After the first 4h bar trades above the
VAL, a 4h close above it (on that bar or the next) triggers a market buy at the next bar's open. The
stop is VAL - 0.50 sigma. The target is entry + 2.0 sigma, which is rarely reached, so most trades exit
at the week's final 4h close. sigma = WO x vol / sqrt(52), with the pine per-asset vol. Size: $500 /
planned stop distance, in micros.

{scope_md(v, 'P13')}

{year_md(tr, 'P13')}

In-sample neighbourhood (stop, target and entry-timing variants of the same trigger): {(nb13.expR > 0).mean():.0%} of
{len(nb13)} configs are positive, median {nb13.expR.median():+.3f} R. The short mirror's neighbourhood: {(nbm.expR > 0).mean():.0%} positive,
median {nbm.expR.median():+.3f} R. GC holdout: {int(p13.GC_n)} trades, {f(p13.GC_expR)} R under the sizing rule; with at least one micro,
{int(gcm.loc['P13'].n)} trades, {f(gcm.loc['P13'].expR)} R.

**P02 (the v42 version)**, `{p02.config}` in weeks that open below the prior VAL: the long breakout
through RNG_T_HI (WRH + 0.078 sigma). It passed G1 to G5 on 2021+, with PF {f(p02.OOS2_pf, 2)} and {f(p02.OOS2_expR)} R above a placebo max
of {f(p02.OOS2_plc_max)}. It failed G6 and G8 (GC {int(p02.GC_n)} trades), and it needs 15m path resolution (pierce 0.10 sigma).
Its round-2 refinements (open below POC, open far below value) did not pass in-sample, and 6J lost in
2021+.

{scope_md(v, 'P02')}

## 7. Integrity notes

* The first `evaluate` run crashed on a code error before writing or printing any result (an empty
  trade frame when every trade in a set is skipped by the $500 budget). The note and fix were committed
  before the single re-run (`1408579`). No rule, gate or selection changed. A secondary "min-one-micro"
  row was declared before the re-run as an edge check, because one MGC or MNQ often risks more than $500.
* 2021+ is a second look (see Section 5). GC is the clean holdout, but it covers only 3.2 years, and the
  sizing rule leaves most rules with fewer than 20 trades.
* The market profile is a 4h TPO proxy with no volume. A true volume profile or 30-minute TPO could
  place POC and value differently.
* N now counts {int(dfl['n_unique']):,} unique configs plus the phase 1 pre-fix run. N_eff is {int(dfl['n_eff']):,} entry-overlap clusters.

## 8. What would settle it

1. Freeze P13 and P02 as they are, and test them once on data neither phase has touched. Full-history
   TradingView 4h exports of the other calibrated tickers (YM, RTY, SI, 6E, ZN, and GC back to 2013)
   would give several hundred more trades.
2. Re-export with volume, so the value area can be built from a volume profile instead of the TPO
   proxy.
3. Paper-trade P13 forward, logging each week's prior VAL and the reclaim bar.
"""
    (ROOT / "REPORT_P2.md").write_text(md)
    print(md[:2500])


if __name__ == "__main__":
    main()
