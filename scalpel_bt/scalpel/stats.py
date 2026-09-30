"""Trade statistics, bootstrap CI, deflated Sharpe ratio."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats as sps

CRISES = [("2015-08-17", "2015-09-30"), ("2018-01-29", "2018-04-30"), ("2018-10-01", "2018-12-31")]


def boot_ci_mean(x: np.ndarray, n_boot: int = 10000, seed: int = 7, alpha: float = 0.05):
    x = np.asarray(x, float)
    if len(x) < 2:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    means = x[idx].mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def max_drawdown(pnl: np.ndarray) -> float:
    if len(pnl) == 0:
        return 0.0
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
    return float((eq - peak).min())


def profit_factor(x):
    g, b = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / b) if b > 0 else np.inf


def trade_frame(fr, res: dict) -> pd.DataFrame:
    b = fr.bars
    t = pd.DataFrame({
        "entry_time": b.index[res["ei"]], "exit_time": b.index[res["xi"]],
        "side": res["side"], "entry": res["entry"], "exit": res["exit"], "stop": res["stop"],
        "gross": res["gross"], "net": res["net"], "risk": res["risk"], "reason": res["reason"],
        "bars_held": res["xi"] - res["ei"] + 1,
    })
    sgn = 1.0 if res["side"] == "long" else -1.0
    for col in ("entry", "exit", "stop"):
        t[col] = t[col] * sgn
    t["R"] = t["net"] / t["risk"]
    t["tday"] = b["tday"].values[res["ei"]]
    t["year"] = pd.DatetimeIndex(t["tday"]).year
    t["vix_prev"] = fr.feat["vix_prev"].values[res["ei"]]
    t["roll_week"] = fr.feat["roll_week"].values[res["ei"]]
    return t


def summarize(t: pd.DataFrame, years=range(2013, 2020), boot=True) -> dict:
    x = t["net"].values
    n = len(x)
    out = dict(n=n)
    if n == 0:
        out.update(ev=np.nan, win=np.nan, pf=np.nan, total=0.0, mdd=0.0, sharpe_t=np.nan,
                   ev_R=np.nan, ci_lo=np.nan, ci_hi=np.nan, ciR_lo=np.nan, worst=np.nan,
                   pos_years=0, total_ex_best=np.nan, total_ex_crisis=np.nan)
        for y in years:
            out[f"pnl_{y}"] = 0.0; out[f"n_{y}"] = 0
        return out
    sd = x.std(ddof=1) if n > 1 else np.nan
    out.update(ev=float(x.mean()), win=float((x > 0).mean()), pf=profit_factor(x),
               total=float(x.sum()), mdd=max_drawdown(x), sharpe_t=float(x.mean() / sd) if sd and sd > 0 else np.nan,
               ev_R=float(t["R"].mean()), worst=float(x.min()),
               avg_bars=float(t["bars_held"].mean()))
    if boot:
        out["ci_lo"], out["ci_hi"] = boot_ci_mean(x)
        out["ciR_lo"], _ = boot_ci_mean(t["R"].values)
    yp = t.groupby("year")["net"].agg(["sum", "size"])
    for y in years:
        out[f"pnl_{y}"] = float(yp["sum"].get(y, 0.0))
        out[f"n_{y}"] = int(yp["size"].get(y, 0))
    ys = np.array([out[f"pnl_{y}"] for y in years])
    out["pos_years"] = int((ys > 0).sum())
    out["total_ex_best"] = float(ys.sum() - ys.max())
    td = pd.DatetimeIndex(t["tday"])
    crisis = np.zeros(n, bool)
    for a, b_ in CRISES:
        crisis |= (td >= a) & (td <= b_)
    out["total_ex_crisis"] = float(x[~crisis].sum())
    return out


def expected_max_sr(var_sr: float, n_trials: int) -> float:
    """E[max SR] under the null across N trials (Bailey & Lopez de Prado 2014)."""
    g = 0.5772156649
    z1 = sps.norm.ppf(1 - 1.0 / n_trials)
    z2 = sps.norm.ppf(1 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(var_sr) * ((1 - g) * z1 + g * z2))


def deflated_sharpe(sr: float, T: int, skew: float, kurt: float, var_sr: float, n_trials: int) -> dict:
    """sr, var_sr per-observation (not annualised); kurt is raw kurtosis (normal = 3)."""
    sr0 = expected_max_sr(var_sr, n_trials)
    den = np.sqrt(1 - skew * sr + (kurt - 1) / 4.0 * sr ** 2)
    z = (sr - sr0) * np.sqrt(T - 1) / den
    return dict(sr=sr, sr0=sr0, dsr=float(sps.norm.cdf(z)), z=float(z))


def psr(sr: float, T: int, skew: float, kurt: float, sr_star: float = 0.0) -> float:
    den = np.sqrt(1 - skew * sr + (kurt - 1) / 4.0 * sr ** 2)
    return float(sps.norm.cdf((sr - sr_star) * np.sqrt(T - 1) / den))
