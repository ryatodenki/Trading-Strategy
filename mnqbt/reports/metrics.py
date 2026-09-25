"""Trade statistics, breakdowns and confidence intervals."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

BREAKDOWNS = {
    "session": "fill_session",
    "weekday": "weekday",
    "year": "year",
    "direction": "direction",
    "vol regime": "vol_state",
    "key level": "level",
    "SMT leader": "smt_leader",
    "VWAP side": "vwap_side",
    "value area": "va_loc",
    "structure": "structure_aligned",
    "news day": "news_day",
    "target": "target_src_group",
}


def enrich(trades: pd.DataFrame, tz: str = "America/New_York") -> pd.DataFrame:
    """Add grouping columns used by breakdowns."""
    t = trades.copy()
    if t.empty:
        return t
    td = pd.DatetimeIndex(t["tdate"])
    t["year"] = td.year
    t["weekday"] = pd.Categorical(td.day_name(), ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], ordered=True)
    t["direction"] = np.where(t["dir"] > 0, "long", "short")
    t["target_src_group"] = t["target_src"].astype(str).str.split(":").str[0]
    t["structure_aligned"] = t["structure_aligned"].map({1: "with", -1: "against", 0: "undetermined"})
    t["win"] = t["r_net"] > 0
    return t


def longest_losing_streak(r: np.ndarray) -> int:
    best = cur = 0
    for x in r:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def max_drawdown(values: np.ndarray) -> float:
    """Largest peak-to-trough decline of the cumulative sum (a positive number)."""
    if len(values) == 0:
        return 0.0
    eq = np.concatenate([[0.0], np.cumsum(values)])
    return float((np.maximum.accumulate(eq) - eq).max())


def bootstrap_mean_ci(x: np.ndarray, reps: int, level: float, groups: np.ndarray | None = None, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean.  With ``groups`` (e.g. trading date),
    whole groups are resampled together (block bootstrap) to respect dependence."""
    x = np.asarray(x, float)
    if len(x) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    if groups is None:
        idx = rng.integers(0, len(x), size=(reps, len(x)))
        means = x[idx].mean(axis=1)
    else:
        codes, uniq = pd.factorize(groups)
        sums = np.bincount(codes, weights=x)
        counts = np.bincount(codes)
        pick = rng.integers(0, len(uniq), size=(reps, len(uniq)))
        means = sums[pick].sum(axis=1) / counts[pick].sum(axis=1)
    a = (1 - level) / 2
    return float(np.quantile(means, a)), float(np.quantile(means, 1 - a))


def _t_pvalue(x: np.ndarray) -> float:
    """Two-sided p-value of mean != 0 (normal approximation; fine for n > 30)."""
    n = len(x)
    if n < 3 or np.std(x, ddof=1) == 0:
        return np.nan
    t = np.mean(x) / (np.std(x, ddof=1) / math.sqrt(n))
    return float(math.erfc(abs(t) / math.sqrt(2)))


def summarize(trades: pd.DataFrame, reps: int = 5000, level: float = 0.95, min_trades: int = 100, seed: int = 0) -> dict:
    if trades is None or trades.empty:
        return {"trades": 0, "warning": "NO TRADES"}
    t = trades.sort_values("exit_ns")
    r = t["r_net"].to_numpy(float)
    pnl = t["pnl_usd"].to_numpy(float)
    wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    years = max((t["exit_ns"].max() - t["fill_ns"].min()) / (365.25 * 86400e9), 1e-9)
    ci = bootstrap_mean_ci(r, reps, level, seed=seed)
    ci_day = bootstrap_mean_ci(r, reps, level, groups=pd.DatetimeIndex(t["tdate"]).to_numpy(), seed=seed)
    out = {
        "trades": len(t),
        "trades_per_year": len(t) / years,
        "win_rate": float((r > 0).mean()),
        "avg_r_net": float(r.mean()),
        "avg_r_gross": float(t["r_gross"].mean()),
        "ci_low": ci[0],
        "ci_high": ci[1],
        "ci_day_low": ci_day[0],
        "ci_day_high": ci_day[1],
        "p_value": _t_pvalue(r),
        "profit_factor": float(wins / losses) if losses > 0 else np.inf,
        "net_pnl_usd": float(pnl.sum()),
        "gross_pnl_usd": float(t["gross_usd"].sum()),
        "costs_usd": float((t["commission"] + t["slippage_usd"]).sum()),
        "max_dd_usd": max_drawdown(pnl),
        "max_dd_r": max_drawdown(r),
        "longest_losing_streak": longest_losing_streak(r),
        "avg_bars_held": float(t["bars_held"].mean()),
        "ambiguous_bar_share": float(t["ambiguous_bar"].mean()),
        "warning": "" if len(t) >= min_trades else f"ONLY {len(t)} TRADES (<{min_trades}): do not trust",
    }
    return out


def breakdown(trades: pd.DataFrame, col: str, min_n: int = 1) -> pd.DataFrame:
    if trades.empty or col not in trades:
        return pd.DataFrame()
    g = trades.groupby(col, observed=True, dropna=False)
    out = pd.DataFrame(
        {
            "trades": g.size(),
            "win_rate": g["win"].mean(),
            "avg_r_net": g["r_net"].mean(),
            "net_pnl_usd": g["pnl_usd"].sum(),
            "profit_factor": g["pnl_usd"].apply(lambda s: s[s > 0].sum() / -s[s < 0].sum() if (s < 0).any() else np.inf),
        }
    )
    return out[out["trades"] >= min_n]
