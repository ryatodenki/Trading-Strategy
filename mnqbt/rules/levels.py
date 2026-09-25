"""Daily statistics and the key-level table.

Every value in the level table for a query bar is known at the START of that
bar, i.e. built from strictly earlier data:

* prior_day   pdh / pdl   : high / low of the previous FULL trading day (18:00-17:00 ET)
* current_day dh / dl     : running high / low of today's bars before this bar
* sessions    asia_h/l, london_h/l, ny_h/l : most recent session instance whose
                            scheduled end time has passed (today's Asia after 03:00,
                            yesterday's NY until today's NY ends, ...)
* swings      sh1..shK / sl1..slK : K most recent confirmed swing highs / lows on
                            ``levels.swing_timeframe``
* value area  vah / val / poc : prior full day's value area (used only when the
                            value_area piece is on in ``levels`` mode)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.config import get, hhmm_to_minutes, resolve_dist
from mnqbt.data.sessions import session_end_times
from mnqbt.rules.mood import vol_state
from mnqbt.rules.profile import daily_value_areas
from mnqbt.rules.swings import swings
from mnqbt.timeutil import ns

SESSION_NAMES = ("asia", "london", "ny")


def _daily_bars(m1: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    """One row per trading date: OHLC, true range, full-day and tradeable flags."""
    g = m1.groupby("tdate", sort=True)
    d = pd.DataFrame(
        {"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(), "n_bars": g.size()}
    )
    d.index = pd.DatetimeIndex(d.index)
    prev_close = d["close"].shift(1)
    d["tr"] = np.maximum(d["high"], prev_close.fillna(d["high"])) - np.minimum(d["low"], prev_close.fillna(d["low"]))
    fl = flags.reindex(d.index)
    d["full"] = ~fl["short"].fillna(True).astype(bool)
    d["tradeable"] = fl["tradeable"].fillna(False).astype(bool) if "tradeable" in fl else d["full"]
    return d


def _prior_full(d: pd.DataFrame, values_on_full_days: np.ndarray) -> np.ndarray:
    """Value at the most recent FULL day strictly before each day of ``d``.

    So short/holiday sessions never become the reference day and nothing from
    the day itself is used.
    """
    prev_full_pos = np.searchsorted(d.index[d["full"]].values, d.index.values, side="left") - 1
    if len(values_on_full_days) == 0:
        return np.full(len(d), np.nan)
    return np.where(prev_full_pos >= 0, values_on_full_days[np.maximum(prev_full_pos, 0)], np.nan)


def _atr(d: pd.DataFrame, cfg: dict) -> np.ndarray:
    n_atr = int(get(cfg, "rules.atr_days"))
    return _prior_full(d, d.loc[d["full"], "tr"].rolling(n_atr, min_periods=n_atr).mean().to_numpy())


def daily_atr(m1: pd.DataFrame, flags: pd.DataFrame, cfg: dict) -> pd.Series:
    """Daily ATR by trading date, as in ``daily_table`` (used for the SMT pair's own scale)."""
    d = _daily_bars(m1, flags)
    return pd.Series(_atr(d, cfg), index=d.index, name="atr")


def daily_table(m1: pd.DataFrame, flags: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """One row per trading date: OHLC, TR, full-day flag, ATR, prior-day levels, vol regime, prior VA."""
    d = _daily_bars(m1, flags)
    full = d[d["full"]]

    def prior(values_on_full_days: np.ndarray) -> np.ndarray:
        return _prior_full(d, values_on_full_days)

    d["atr"] = _atr(d, cfg)
    d["pdh"] = prior(full["high"].to_numpy())
    d["pdl"] = prior(full["low"].to_numpy())

    mood = get(cfg, "rules.mood")
    fast = prior(full["tr"].rolling(int(mood["vol_fast_days"]), min_periods=int(mood["vol_fast_days"])).mean().to_numpy())
    slow = prior(full["tr"].rolling(int(mood["vol_slow_days"]), min_periods=int(mood["vol_slow_days"])).mean().to_numpy())
    with np.errstate(invalid="ignore", divide="ignore"):
        d["vol_ratio"] = fast / slow
    d["vol_state"] = vol_state(d["vol_ratio"].to_numpy(), float(mood["calm_below"]), float(mood["volatile_above"]))

    va_cfg = get(cfg, "rules.value_area")
    tick = float(get(cfg, "instruments.tick_size"))
    bucket = pd.Series(resolve_dist(va_cfg["bucket"], d["atr"].to_numpy()), index=d.index)
    bucket = np.maximum(tick, np.round(bucket / tick) * tick)
    ny = get(cfg, "sessions.definitions")["ny"]
    va = daily_value_areas(
        m1, bucket, float(va_cfg["pct"]), va_cfg["source"] == "prior_rth", (hhmm_to_minutes(ny[0]), hhmm_to_minutes(ny[1]))
    )
    va.index = pd.DatetimeIndex(va.index)
    va = va.reindex(d.index)
    for col in ("val", "vah", "poc"):
        d[col] = va[col].to_numpy()
        d[f"{col}_prior"] = prior(va[col].to_numpy()[d["full"].to_numpy()])
    return d


def session_table(m1: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    """Per session name: completed instances sorted by scheduled end (end_ns, high, low)."""
    out = {}
    lab = m1["session"].astype(str).to_numpy()
    for name in SESSION_NAMES:
        sub = m1[lab == name]
        if sub.empty:
            out[name] = pd.DataFrame(columns=["end_ns", "high", "low"])
            continue
        g = sub.groupby("tdate", sort=True)
        t = pd.DataFrame({"high": g["high"].max(), "low": g["low"].min()})
        t["end_ns"] = ns(session_end_times(pd.DatetimeIndex(t.index), name, cfg))
        out[name] = t.sort_values("end_ns")
    return out


def _asof(values_known_ns: np.ndarray, values: np.ndarray, query_ns: np.ndarray, back: int = 1) -> np.ndarray:
    """values[i] for the ``back``-th most recent row with known_ns <= query (NaN if none)."""
    idx = np.searchsorted(values_known_ns, query_ns, side="right") - back
    ok = idx >= 0
    out = np.full(len(query_ns), np.nan)
    out[ok] = values[idx[ok]]
    return out


def level_table(q_bars: pd.DataFrame, m1: pd.DataFrame, daily: pd.DataFrame, swing_bars: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Key levels known at the start of each bar of ``q_bars``."""
    lv = get(cfg, "rules.levels")
    start = q_bars["start_ns"].to_numpy()
    td = pd.DatetimeIndex(q_bars["tdate"].to_numpy())
    out = pd.DataFrame(index=q_bars.index)
    out["pdh"] = daily["pdh"].reindex(td).to_numpy()
    out["pdl"] = daily["pdl"].reindex(td).to_numpy()

    grp = pd.Series(q_bars["tdate"].to_numpy())
    out["dh"] = pd.Series(q_bars["high"].to_numpy()).groupby(grp).cummax().groupby(grp).shift(1).to_numpy()
    out["dl"] = pd.Series(q_bars["low"].to_numpy()).groupby(grp).cummin().groupby(grp).shift(1).to_numpy()

    for name, t in session_table(m1, cfg).items():
        e = t["end_ns"].to_numpy(np.int64)
        out[f"{name}_h"] = _asof(e, t["high"].to_numpy(float), start)
        out[f"{name}_l"] = _asof(e, t["low"].to_numpy(float), start)

    sw = swings(swing_bars, int(lv["swing_n"]))
    for kind, prefix in ((1, "sh"), (-1, "sl")):
        s = sw[sw["kind"] == kind].sort_values("known_ns")
        kn, px = s["known_ns"].to_numpy(np.int64), s["price"].to_numpy(float)
        for k in range(1, int(lv["swing_count"]) + 1):
            out[f"{prefix}{k}"] = _asof(kn, px, start, back=k)

    out["vah"] = daily["vah_prior"].reindex(td).to_numpy()
    out["val"] = daily["val_prior"].reindex(td).to_numpy()
    out["poc"] = daily["poc_prior"].reindex(td).to_numpy()
    return out


def level_columns(cfg: dict, side: int, include_value_area: bool) -> list[str]:
    """Columns of the level table that count as key levels for highs (side=+1) or lows (-1)."""
    use = set(get(cfg, "rules.levels.use"))
    s = "h" if side > 0 else "l"
    cols = []
    if "prior_day" in use:
        cols.append("pd" + s)
    if "current_day" in use:
        cols.append("d" + s)
    if "sessions" in use:
        cols += [f"{n}_{s}" for n in SESSION_NAMES]
    if "swings" in use:
        cols += [f"s{s}{k}" for k in range(1, int(get(cfg, "rules.levels.swing_count")) + 1)]
    if include_value_area:
        cols.append("vah" if side > 0 else "val")
    return cols


def nearest_level(table: pd.DataFrame, rows: np.ndarray, cols: list[str], price: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For each (row, price): name and absolute distance of the nearest level among ``cols``."""
    if len(rows) == 0 or not cols:
        return np.array([], dtype=object), np.array([])
    vals = table[cols].to_numpy(float)[rows]
    dist = np.abs(vals - price[:, None])
    dist_f = np.where(np.isnan(dist), np.inf, dist)
    best = dist_f.argmin(axis=1)
    d = dist_f[np.arange(len(rows)), best]
    names = np.array(cols, dtype=object)[best]
    names = np.where(np.isinf(d), "", names)
    return names, np.where(np.isinf(d), np.nan, d)
