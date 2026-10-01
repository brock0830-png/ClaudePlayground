"""Rebuild UW's 0DTE strike profile every 5 minutes from the Full Tape (PROTOCOL §3).

For snapshot t only non-canceled trades with executed_at <= t are used. Dollar gamma
is gamma x contracts x 100 x S^2 x 0.01 (= gamma x contracts x S^2).

Variants (17):
  D (directionalized): side in {tag, quote} x mid in {exclude, split} x gamma in {G1, G2, G3}
  O (open interest):   gamma in {G2, G3}
  V (volume):          gamma in {G1, G2, G3}
G1 = gamma and spot at trade time; G2 = Black-Scholes gamma at t from S(t), the
contract's latest IV (strike-interpolated when the contract has not traded yet);
G3 = the contract's latest observed tape gamma at t, with S(t)^2.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

ET = "America/New_York"
BAND_KEEP = 0.03          # store strikes within +-3% of spot
QUOTE_ASK_X = 0.75
QUOTE_BID_X = 0.25

# Dealer-perspective sign per directionalized bucket and per view leg. Confirmed (or
# corrected, with a logged amendment) against UW's live response; see validate.py.
BUCKET_SIGN = {"call_ask": -1.0, "call_bid": 1.0, "put_ask": -1.0, "put_bid": 1.0}
LEG_SIGN = {"call": 1.0, "put": -1.0}


@dataclass(frozen=True)
class Variant:
    view: str            # D, O, V
    gamma: str           # G1, G2, G3
    side: str = ""       # tag, quote (D only)
    mid: str = ""        # exclude, split (D only)

    @property
    def id(self) -> str:
        return "-".join(x for x in (self.view, self.side, self.mid, self.gamma) if x)


VARIANTS = (
    [Variant("D", g, s, m) for s in ("tag", "quote") for m in ("exclude", "split") for g in ("G1", "G2", "G3")]
    + [Variant("O", g) for g in ("G2", "G3")]
    + [Variant("V", g) for g in ("G1", "G2", "G3")]
)


def snapshot_times(d: date, close_hm: tuple[int, int]) -> pd.DatetimeIndex:
    start = pd.Timestamp(f"{d.isoformat()} 09:35", tz=ET)
    end = pd.Timestamp(f"{d.isoformat()} {close_hm[0]:02d}:{close_hm[1]:02d}", tz=ET)
    return pd.date_range(start, end, freq="5min")


def bs_gamma(S, K, sigma, tau):
    S, K, sigma, tau = (np.asarray(x, dtype=float) for x in (S, K, sigma, tau))
    with np.errstate(divide="ignore", invalid="ignore"):
        st = sigma * np.sqrt(tau)
        d1 = (np.log(S / K) + 0.5 * sigma ** 2 * tau) / st
        g = np.exp(-0.5 * d1 ** 2) / np.sqrt(2 * np.pi) / (S * st)
    return np.where(np.isfinite(g) & (st > 0), g, 0.0)


def classify_sides(df: pd.DataFrame) -> pd.DataFrame:
    """Adds side_tag and side_quote in {'ask', 'bid', 'mid', 'none'}."""
    tags = df["tags"].fillna("").str.lower()
    df["side_tag"] = np.select(
        [tags.str.contains("ask_side"), tags.str.contains("bid_side"), tags.str.contains("mid_side")],
        ["ask", "bid", "mid"], "none")
    b, a, p = df["nbbo_bid"], df["nbbo_ask"], df["price"]
    valid = (a > b) & (b >= 0) & a.notna() & b.notna() & p.notna()
    x = (p - b) / (a - b)
    df["side_quote"] = np.select(
        [valid & (x >= QUOTE_ASK_X), valid & (x <= QUOTE_BID_X), valid], ["ask", "bid", "mid"], "none")
    return df


def prepare(tape: pd.DataFrame, d: date, root: str, snaps: pd.DatetimeIndex) -> pd.DataFrame:
    """0DTE, non-canceled trades of one root, with snapshot bucket and sides."""
    occ_root = tape["option_chain_id"].str.extract(r"^([A-Z]+)\d")[0]
    df = tape[(occ_root == root) & (tape["expiry"] == d) & (~tape["canceled"].fillna(False).astype(bool))].copy()
    df = df.sort_values("executed_at", kind="stable")
    ex = df["executed_at"].dt.tz_convert(ET)
    # bucket b: first snapshot >= executed_at, so the trade counts from snapshot b onward
    snap_ns = snaps.as_unit("ns").asi8
    df["b"] = np.searchsorted(snap_ns, ex.dt.as_unit("ns").astype("int64").to_numpy(), side="left")
    df = df[df["b"] < len(snaps)]
    df["is_call"] = df["option_type"].str.lower().str.startswith("c")
    df["g1"] = df["gamma"].fillna(0.0) * df["underlying_price"] ** 2   # per contract, at trade time
    return classify_sides(df)


def _cum(per: pd.DataFrame, contracts: pd.Index, nb: int, cols: list[str]) -> dict[str, np.ndarray]:
    """Per (contract, bucket) sums -> cumulative (contract x bucket) arrays."""
    out = {}
    idx = pd.MultiIndex.from_product([contracts, range(nb)], names=["option_chain_id", "b"])
    full = per.reindex(idx, fill_value=0.0)
    for c in cols:
        out[c] = full[c].to_numpy().reshape(len(contracts), nb).cumsum(axis=1)
    return out


def _last(df: pd.DataFrame, col: str, contracts: pd.Index, nb: int) -> np.ndarray:
    """Latest non-null value of col at or before each bucket (contract x bucket), NaN if none."""
    s = df.dropna(subset=[col]).groupby(["option_chain_id", "b"])[col].last()
    idx = pd.MultiIndex.from_product([contracts, range(nb)], names=["option_chain_id", "b"])
    arr = s.reindex(idx).to_numpy().reshape(len(contracts), nb)
    return pd.DataFrame(arr).ffill(axis=1).to_numpy()


def rebuild_day(tape: pd.DataFrame, bars: pd.DataFrame, d: date, close_hm=(16, 0),
                root: str = "SPXW", variants=VARIANTS) -> pd.DataFrame:
    from prices import spot_at
    snaps = snapshot_times(d, close_hm)
    nb = len(snaps)
    df = prepare(tape, d, root, snaps)
    if df.empty:
        return pd.DataFrame()
    spot = np.array([spot_at(bars, t) for t in snaps])
    close_ts = pd.Timestamp(f"{d.isoformat()} {close_hm[0]:02d}:{close_hm[1]:02d}", tz=ET)
    tau = np.maximum((close_ts - snaps).total_seconds().to_numpy() / 60.0, 1.0) / 525_600.0

    meta = df.groupby("option_chain_id").agg(strike=("strike", "first"), is_call=("is_call", "first"),
                                             oi=("open_interest", "first"))
    contracts = meta.index
    K = meta["strike"].to_numpy()
    is_call = meta["is_call"].to_numpy()
    oi = meta["oi"].fillna(0).to_numpy(dtype=float)

    # cumulative contracts and trade-time dollar gamma by side, per side rule
    agg = {}
    for rule in ("tag", "quote"):
        sc = f"side_{rule}"
        for side in ("ask", "bid", "mid"):
            m = df[sc] == side
            df[f"n_{rule}_{side}"] = np.where(m, df["size"], 0.0)
            df[f"g1_{rule}_{side}"] = np.where(m, df["size"] * df["g1"], 0.0)
    df["n_all"] = df["size"].astype(float)
    df["g1_all"] = df["size"] * df["g1"]
    sum_cols = [c for c in df.columns if c.startswith(("n_", "g1_"))]
    per = df.groupby(["option_chain_id", "b"])[sum_cols].sum()
    agg = _cum(per, contracts, nb, sum_cols)

    last_g = _last(df, "gamma", contracts, nb)
    last_iv = _last(df, "implied_volatility", contracts, nb)
    # strike-interpolated IV for contracts not yet traded (G2 only)
    iv = last_iv.copy()
    for j in range(nb):
        for call_flag in (True, False):
            sel = is_call == call_flag
            have = sel & np.isfinite(iv[:, j]) & (iv[:, j] > 0)
            need = sel & ~have
            if have.sum() >= 2 and need.any():
                order = np.argsort(K[have])
                iv[need, j] = np.interp(K[need], K[have][order], iv[have, j][order])
    S2 = spot ** 2
    gamma_at = {
        "G2": bs_gamma(spot[None, :], K[:, None], np.nan_to_num(iv, nan=0.0), tau[None, :]) * S2[None, :],
        "G3": np.nan_to_num(last_g, nan=0.0) * S2[None, :],
    }

    rows = []
    keep = np.abs(K[:, None] / spot[None, :] - 1.0) <= BAND_KEEP
    for v in variants:
        if v.view == "D":
            b = {}
            for side in ("ask", "bid", "mid"):
                if v.gamma == "G1":
                    b[side] = agg[f"g1_{v.side}_{side}"]
                else:
                    b[side] = agg[f"n_{v.side}_{side}"] * gamma_at[v.gamma]
            half = 0.5 * b["mid"] if v.mid == "split" else 0.0
            ask, bid = b["ask"] + half, b["bid"] + half
            leg = {"call_ask": np.where(is_call[:, None], ask, 0.0),
                   "call_bid": np.where(is_call[:, None], bid, 0.0),
                   "put_ask": np.where(~is_call[:, None], ask, 0.0),
                   "put_bid": np.where(~is_call[:, None], bid, 0.0)}
            leg = {k: BUCKET_SIGN[k] * x for k, x in leg.items()}
            net = sum(leg.values())
        else:
            if v.view == "O":
                base = oi[:, None] * gamma_at[v.gamma]
            elif v.gamma == "G1":
                base = agg["g1_all"]
            else:
                base = agg["n_all"] * gamma_at[v.gamma]
            sgn = np.where(is_call, LEG_SIGN["call"], LEG_SIGN["put"])[:, None]
            net = sgn * base
            leg = {}
        frame = {"net": net, **leg}
        long = []
        for name, arr in frame.items():
            a = np.where(keep, arr, np.nan)
            s = (pd.DataFrame(a, columns=range(nb)).assign(strike=K)
                 .groupby("strike").sum(min_count=1).stack())
            long.append(s.rename(name))
        out = pd.concat(long, axis=1).reset_index().rename(columns={"level_1": "b"})
        out = out.dropna(subset=["net"])
        out["variant"] = v.id
        out["view"] = v.view
        rows.append(out)
    res = pd.concat(rows, ignore_index=True)
    res["snap"] = snaps[res["b"].to_numpy()]
    res["spot"] = spot[res["b"].to_numpy()]
    res["date"] = d
    res["root"] = root
    cols = ["date", "root", "snap", "variant", "view", "strike", "spot", "net",
            "call_ask", "call_bid", "put_ask", "put_bid"]
    for c in cols:
        if c not in res:
            res[c] = np.nan
    return res[cols]
