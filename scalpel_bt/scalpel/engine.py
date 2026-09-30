"""
Numba trade simulator on 4h bars. Long-only logic; shorts are run on negated prices
(o,h,l,c -> -o,-l,-h,-c and levels negated), which mirrors every rule exactly.

Triggers (evaluated on bars where `elig` is True, first event per period only):
  0 TOUCH   : low <= E                     -> signal at close, fill next bar open
  1 REJECT  : low <= E and close > E       -> signal at close, fill next bar open
  2 LIMIT   : resting buy limit at E (known before the period): fill at min(E, open)
  3 BREAK   : close > E (first close above E in the period, period opened below E)
                                           -> signal at close, fill next bar open
  4 STOPIN  : resting buy stop at E: fill at max(E, open) when high >= E
  5 RECLAIM : after a close < E in the period, first close > E -> next bar open

Exits: stop S (stop-market; gap -> open), target T (limit; touch), stop first when a bar
hits both. On a next-open entry both are checked in the entry bar; on a LIMIT/STOPIN
entry bar only the stop is checked (the target may have printed before the fill).
Time exits (scheduled, fill at that bar's close): end of the level period if
`exit_period_end`, after `max_bars` bars, before a contract switch (`force_flat`).
target_mode: 0 = level array T, 1 = R multiple of (fill - S), 2 = no target.
Costs are applied outside (COST_RT_PTS per round trip).
"""
from __future__ import annotations
import numpy as np
from numba import njit

TOUCH, REJECT, LIMIT, BREAK, STOPIN, RECLAIM = 0, 1, 2, 3, 4, 5
TRIG = {"touch": TOUCH, "reject": REJECT, "limit": LIMIT, "break": BREAK, "stopin": STOPIN,
        "reclaim": RECLAIM}
TGT_LEVEL, TGT_R, TGT_NONE = 0, 1, 2
# exit reasons
X_STOP, X_TARGET, X_TIME, X_PEND, X_FORCE = 0, 1, 2, 3, 4


@njit(cache=True)
def simulate(o, h, l, c, E, S, T, elig, pid, pend, force_flat, trig, target_mode, r_mult,
             max_bars, exit_period_end, trade_start, trade_end):
    n = o.shape[0]
    cap = 4096
    e_i = np.empty(cap, np.int64); x_i = np.empty(cap, np.int64)
    e_p = np.empty(cap, np.float64); x_p = np.empty(cap, np.float64)
    s_p = np.empty(cap, np.float64); reason = np.empty(cap, np.int64)
    k = 0
    in_pos = False
    pending = False          # signal given at close of previous bar
    done_period = -1         # period id in which the first event already happened
    cur_p = -1
    below_seen = False       # for RECLAIM / BREAK state within the period
    ent_price = 0.0; stop = 0.0; tgt = 0.0; ent_bar = 0; lvl_S = 0.0; lvl_T = 0.0
    sig_S = 0.0; sig_T = 0.0; sig_pid = -1
    for i in range(trade_start, trade_end):
        if pid[i] != cur_p:
            cur_p = pid[i]
            below_seen = False
        # ---------------- fill a pending next-open entry ----------------
        if pending and not in_pos:
            pending = False
            fill = o[i]
            st = sig_S
            if target_mode == TGT_LEVEL:
                tg = sig_T
            elif target_mode == TGT_R:
                tg = fill + r_mult * (fill - st)
            else:
                tg = np.inf
            if fill > st and fill < tg:
                in_pos = True
                ent_price = fill; stop = st; tgt = tg; ent_bar = i
                # check the entry bar: stop first
                if l[i] <= stop:
                    x = stop if o[i] > stop else o[i]
                    e_i[k] = ent_bar; x_i[k] = i; e_p[k] = ent_price; x_p[k] = x
                    s_p[k] = stop; reason[k] = X_STOP; k += 1
                    in_pos = False
                elif h[i] >= tgt:
                    e_i[k] = ent_bar; x_i[k] = i; e_p[k] = ent_price; x_p[k] = tgt
                    s_p[k] = stop; reason[k] = X_TARGET; k += 1
                    in_pos = False
        elif in_pos:
            # ---------------- manage an open position ----------------
            if l[i] <= stop:
                x = stop if o[i] > stop else o[i]
                e_i[k] = ent_bar; x_i[k] = i; e_p[k] = ent_price; x_p[k] = x
                s_p[k] = stop; reason[k] = X_STOP; k += 1
                in_pos = False
            elif h[i] >= tgt:
                x = tgt if o[i] < tgt else o[i]
                e_i[k] = ent_bar; x_i[k] = i; e_p[k] = ent_price; x_p[k] = x
                s_p[k] = stop; reason[k] = X_TARGET; k += 1
                in_pos = False
        # ---------------- new entries (resting orders fill intrabar) ----------------
        if (not in_pos) and (not pending) and elig[i] and done_period != pid[i] and not np.isnan(E[i]):
            if trig == LIMIT or trig == STOPIN:
                hit = l[i] <= E[i] if trig == LIMIT else h[i] >= E[i]
                if hit:
                    done_period = pid[i]
                    if trig == LIMIT:
                        fill = E[i] if o[i] > E[i] else o[i]
                    else:
                        fill = E[i] if o[i] < E[i] else o[i]
                    st = S[i]
                    if target_mode == TGT_LEVEL:
                        tg = T[i]
                    elif target_mode == TGT_R:
                        tg = fill + r_mult * (fill - st)
                    else:
                        tg = np.inf
                    if fill > st and fill < tg:
                        in_pos = True
                        ent_price = fill; stop = st; tgt = tg; ent_bar = i
                        if l[i] <= stop:   # entry bar: stop only
                            e_i[k] = ent_bar; x_i[k] = i; e_p[k] = ent_price; x_p[k] = stop if o[i] > stop else o[i]
                            s_p[k] = stop; reason[k] = X_STOP; k += 1
                            in_pos = False
            else:
                fire = False
                if trig == TOUCH:
                    fire = l[i] <= E[i]
                elif trig == REJECT:
                    if l[i] <= E[i]:
                        done_period = pid[i]          # first touch consumed either way
                        fire = c[i] > E[i]
                elif trig == BREAK:
                    if c[i] <= E[i]:
                        below_seen = True
                    elif below_seen or o[i] < E[i]:
                        fire = True
                elif trig == RECLAIM:
                    if c[i] < E[i]:
                        below_seen = True
                    elif below_seen and c[i] > E[i]:
                        fire = True
                if fire:
                    done_period = pid[i]
                    if c[i] > S[i] and i + 1 < trade_end and not force_flat[i] and not pend_skip(pend[i], exit_period_end):
                        pending = True
                        sig_S = S[i]; sig_T = T[i]; sig_pid = pid[i]
        elif trig == BREAK or trig == RECLAIM:
            if (not np.isnan(E[i])) and c[i] <= E[i]:
                below_seen = True
        # ---------------- scheduled exits at this bar's close ----------------
        if in_pos:
            tx = False
            rsn = X_TIME
            if force_flat[i]:
                tx = True; rsn = X_FORCE
            elif exit_period_end and pend[i]:
                tx = True; rsn = X_PEND
            elif max_bars > 0 and (i - ent_bar + 1) >= max_bars:
                tx = True; rsn = X_TIME
            if tx:
                e_i[k] = ent_bar; x_i[k] = i; e_p[k] = ent_price; x_p[k] = c[i]
                s_p[k] = stop; reason[k] = rsn; k += 1
                in_pos = False
        if pending and force_flat[i]:
            pending = False
        if k >= cap - 2:
            break
    return e_i[:k], x_i[:k], e_p[:k], x_p[:k], s_p[:k], reason[:k]


@njit(cache=True)
def pend_skip(is_pend, exit_period_end):
    # a signal on the last bar of a period cannot be traded if we must exit at period end
    return is_pend and exit_period_end
