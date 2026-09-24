"""Market mood: volatility regime (per day) and chop (intraday).

Volatility regime for trading date d uses only days before d:
    ratio = mean(true range, last ``vol_fast_days``) / mean(true range, last ``vol_slow_days``)
    calm if ratio < calm_below, volatile if ratio > volatile_above, else normal.

Chop on ``chop_timeframe`` bars, known at each bar's close:
    er  = |close_t - close_{t-n}| / sum_{i=t-n+1..t} |close_i - close_{i-1}|   (Kaufman efficiency ratio)
    adx = Wilder ADX(n)
    choppy if er < er_choppy_below (or adx < adx_choppy_below).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def vol_state(ratio: np.ndarray, calm_below: float, volatile_above: float) -> np.ndarray:
    """calm / normal / volatile from the fast/slow true-range ratio ('' when unknown)."""
    r = np.asarray(ratio, float)
    with np.errstate(invalid="ignore"):
        return np.where(np.isnan(r), "", np.where(r < calm_below, "calm", np.where(r > volatile_above, "volatile", "normal")))


def efficiency_ratio(close: np.ndarray, n: int) -> np.ndarray:
    c = pd.Series(np.asarray(close, float))
    net = (c - c.shift(n)).abs()
    path = c.diff().abs().rolling(n, min_periods=n).sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        er = (net / path).to_numpy(copy=True)
    er[path.to_numpy() == 0] = 0.0
    return er


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> np.ndarray:
    h, l, c = (pd.Series(np.asarray(x, float)) for x in (high, low, close))
    up = h.diff()
    dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    alpha = 1.0 / n
    atr = tr.ewm(alpha=alpha, adjust=False, min_periods=n).mean()
    pdi = 100 * pd.Series(plus_dm).ewm(alpha=alpha, adjust=False, min_periods=n).mean() / atr
    mdi = 100 * pd.Series(minus_dm).ewm(alpha=alpha, adjust=False, min_periods=n).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=alpha, adjust=False, min_periods=n).mean().to_numpy()


def chop_table(bars: pd.DataFrame, method: str, n: int, er_below: float, adx_below: float) -> pd.DataFrame:
    if method == "er":
        val = efficiency_ratio(bars["close"].to_numpy(), n)
        choppy = val < er_below
    elif method == "adx":
        val = adx(bars["high"].to_numpy(), bars["low"].to_numpy(), bars["close"].to_numpy(), n)
        choppy = val < adx_below
    else:
        raise ValueError(f"unknown chop method {method!r}")
    choppy = np.where(np.isnan(val), False, choppy)
    return pd.DataFrame({"chop": val, "choppy": choppy, "known_ns": bars["known_ns"].to_numpy()}, index=bars.index)
