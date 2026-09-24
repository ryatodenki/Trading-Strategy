"""Synthetic per-contract 1m bars for two correlated index futures.

Used for unit tests and pipeline smoke runs only.  The price path is a
martingale (random walk with stochastic volatility), so NO strategy can have a
real edge on it: a backtest that shows one on synthetic data has a bug —
typically lookahead.  That makes it a useful end-to-end check.

Features that exercise the pipeline:
* CME hours: 18:00-17:00 ET, weekends closed, a few holiday closures and
  early (13:00 ET) halts.  DST is handled because minutes are built in ET.
* Intraday volatility/volume seasonality and daily vol regimes.
* Quarterly contracts with a carry basis, so every roll has a real price gap,
  plus an overlapping back month whose volume ramps up into the roll.
* Optional proxy roots (NQ/ES) before a splice date and micro roots after.
* Optional injected defects (spike, gap, duplicate) for validation tests.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from mnqbt.data.calendar import contract_symbol, quarterly_expiries, us_holidays

TZ = "America/New_York"
FULL_CLOSE = {"New Year's Day", "Good Friday", "Christmas"}
EARLY_1300 = {"MLK Day", "Presidents Day", "Memorial Day", "Juneteenth", "Independence Day", "Labor Day", "Thanksgiving"}


def _intraday_profile(et_min: np.ndarray) -> np.ndarray:
    """Relative per-minute volatility by ET minute-of-day."""
    p = np.full(et_min.shape, 0.45)
    p[(et_min >= 180) & (et_min < 570)] = 0.75            # London
    p[(et_min >= 480) & (et_min < 570)] = 1.00            # 08:00-09:30 data releases
    ny = (et_min >= 570) & (et_min < 960)
    p[ny] = 1.0
    p[(et_min >= 570) & (et_min < 630)] = 2.0             # open hour
    p[(et_min >= 690) & (et_min < 810)] = 0.8             # lunch
    p[(et_min >= 900) & (et_min < 960)] = 1.3             # last hour
    return p


def trading_calendar(start: str, end: str) -> pd.DataFrame:
    days = pd.bdate_range(start, end)
    hol = us_holidays(days[0].year, days[-1].year)
    kind = dict(zip(hol["date"], hol["holiday"]))
    rows = []
    for d in days:
        name = kind.get(d)
        if name in FULL_CLOSE:
            continue
        halt = "17:00"
        if name in EARLY_1300:
            halt = "13:00"
        elif name and "after Thanksgiving" in name:
            halt = "13:15"
        rows.append((d, halt))
    return pd.DataFrame(rows, columns=["tdate", "halt"])


def _minutes_for_day(tdate: pd.Timestamp, halt: str) -> pd.DatetimeIndex:
    start = (tdate - pd.Timedelta(days=1)) + pd.Timedelta(hours=18)
    hh, mm = map(int, halt.split(":"))
    stop = tdate + pd.Timedelta(hours=hh, minutes=mm)
    local = pd.date_range(start, stop, freq="1min", inclusive="left")
    return local.tz_localize(TZ, ambiguous="NaT", nonexistent="NaT").dropna().tz_convert("UTC")


def spot_paths(
    start: str,
    end: str,
    seed: int = 0,
    start_prices: tuple[float, float] = (15000.0, 4500.0),
    daily_sigma: tuple[float, float] = (170.0, 42.0),
    rho: float = 0.9,
    steps_per_minute: int = 6,
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, pd.Series]:
    """Sub-minute spot paths for (A, B).  Returns index, paths[n, k] x2, daily vol multiplier."""
    rng = np.random.default_rng(seed)
    cal = trading_calendar(start, end)
    idx_parts, tdates = [], []
    for tdate, halt in cal.itertuples(index=False):
        m = _minutes_for_day(tdate, halt)
        idx_parts.append(m)
        tdates.append(np.full(len(m), tdate.value))
    index = idx_parts[0].append(idx_parts[1:]) if len(idx_parts) > 1 else idx_parts[0]
    tdate_arr = pd.to_datetime(np.concatenate(tdates))

    # Daily log-vol AR(1) -> calm / volatile regimes.
    n_days = len(cal)
    lv = np.zeros(n_days)
    for i in range(1, n_days):
        lv[i] = 0.9 * lv[i - 1] + 0.22 * rng.standard_normal()
    day_mult = pd.Series(np.exp(lv), index=cal["tdate"])

    et = index.tz_convert(TZ)
    et_min = (et.hour * 60 + et.minute).to_numpy()
    prof = _intraday_profile(et_min)
    full_day_prof = _intraday_profile(np.r_[np.arange(1080, 1440), np.arange(0, 1020)])
    norm = np.sqrt((full_day_prof**2).sum())
    mult = day_mult.reindex(tdate_arr).to_numpy()

    n, k = len(index), steps_per_minute
    z1 = rng.standard_normal((n, k))
    z2 = rng.standard_normal((n, k))
    paths = []
    for sig_day, p0, zz in (
        (daily_sigma[0], start_prices[0], rho * z1 + np.sqrt(1 - rho**2) * z2),
        (daily_sigma[1], start_prices[1], z1),
    ):
        sig_step = (sig_day / norm) * prof * mult / np.sqrt(k)
        steps = zz * sig_step[:, None]
        path = p0 + np.cumsum(steps.ravel()).reshape(n, k)
        paths.append(path)
    return index, paths[0], paths[1], day_mult


def _bars_from_path(index: pd.DatetimeIndex, path: np.ndarray, tick: float) -> pd.DataFrame:
    q = np.round(path / tick) * tick
    return pd.DataFrame(
        {"open": q[:, 0], "high": q.max(axis=1), "low": q.min(axis=1), "close": q[:, -1]},
        index=index,
    )


def contract_bars(
    index: pd.DatetimeIndex,
    path: np.ndarray,
    root: str,
    carry_per_day: float,
    active_from: str | None,
    active_to: str | None,
    rng: np.random.Generator,
    tick: float = 0.25,
    base_volume: float = 400.0,
    roll_days_before_expiry: int = 8,
) -> pd.DataFrame:
    """Per-contract bars: price = spot + carry * days_to_expiry (constant within a day)."""
    et = index.tz_convert(TZ)
    et_min = (et.hour * 60 + et.minute).to_numpy()
    tdate = et.tz_localize(None).normalize() + pd.to_timedelta((et_min >= 1080).astype(int), unit="D")
    lo = pd.Timestamp(active_from) if active_from else tdate.min()
    hi = pd.Timestamp(active_to) if active_to else tdate.max()
    vol_prof = _intraday_profile(et_min) ** 1.2
    expiries = quarterly_expiries(tdate.min().date() - dt.timedelta(days=100), tdate.max().date())
    frames = []
    for i, exp in enumerate(expiries):
        exp_ts = pd.Timestamp(exp)
        roll = exp_ts - pd.Timedelta(days=roll_days_before_expiry)
        prev_roll = pd.Timestamp(expiries[i - 1]) - pd.Timedelta(days=roll_days_before_expiry) if i else roll - pd.Timedelta(days=91)
        # Lives from ~3 weeks before it becomes front until its expiry.
        live = (tdate >= prev_roll - pd.Timedelta(days=21)) & (tdate <= exp_ts) & (tdate >= lo) & (tdate <= hi)
        if not live.any():
            continue
        rows = np.flatnonzero(live)
        td = tdate[rows]
        dte = (exp_ts - td).days.to_numpy().astype(float)
        basis = carry_per_day * dte
        bars = _bars_from_path(index[rows], path[rows] + basis[:, None], tick)
        # Volume share: front ~1, back month tiny until it ramps into the roll.
        days_to_roll = (roll - td).days.to_numpy()
        days_since_prev_roll = (td - prev_roll).days.to_numpy()
        share = np.where(days_to_roll > 0, 1.0, 0.15)                     # after its roll: fading
        pre = days_since_prev_roll < 0                                      # before it is front
        share = np.where(pre, np.clip(0.03 + 0.25 * (7 + days_since_prev_roll), 0.03, 0.9), share)
        vol = base_volume * vol_prof[rows] * share * rng.lognormal(0, 0.5, len(rows))
        keep = rng.random(len(rows)) < np.clip(0.05 + share, 0, 1)
        bars["volume"] = np.maximum(1, np.round(vol)).astype(np.int64)
        bars["symbol"] = contract_symbol(root, exp)
        frames.append(bars[keep])
    return pd.concat(frames).sort_index()


def generate(
    start: str = "2021-01-04",
    end: str = "2021-06-30",
    seed: int = 0,
    splice_date: str | None = None,
    proxy_roots: tuple[str, str] = ("NQ", "ES"),
    roots: tuple[str, str] = ("MNQ", "MES"),
    inject_defects: bool = False,
    overlap_days: int = 30,
) -> dict[str, pd.DataFrame]:
    """Return {root: per-contract bar frame} for the traded pair (and proxies)."""
    rng = np.random.default_rng(seed + 1)
    index, pa, pb, _ = spot_paths(start, end, seed)
    out: dict[str, pd.DataFrame] = {}
    carry = {"A": 1.5, "B": 0.4}
    if splice_date:
        sp = pd.Timestamp(splice_date)
        before = str((sp + pd.Timedelta(days=overlap_days)).date())
        after = str((sp - pd.Timedelta(days=overlap_days)).date())
        out[proxy_roots[0]] = contract_bars(index, pa, proxy_roots[0], carry["A"], None, before, rng)
        out[proxy_roots[1]] = contract_bars(index, pb, proxy_roots[1], carry["B"], None, before, rng)
        out[roots[0]] = contract_bars(index, pa, roots[0], carry["A"], after, None, rng)
        out[roots[1]] = contract_bars(index, pb, roots[1], carry["B"], after, None, rng)
    else:
        out[roots[0]] = contract_bars(index, pa, roots[0], carry["A"], None, None, rng)
        out[roots[1]] = contract_bars(index, pb, roots[1], carry["B"], None, None, rng)

    if inject_defects:
        df = out[roots[0]]
        front = df["symbol"].value_counts().idxmax()
        rows = np.flatnonzero(df["symbol"].to_numpy() == front)
        i = rows[len(rows) // 2]
        df.iloc[i, df.columns.get_loc("high")] += 400.0             # bad tick spike
        t0 = df.index[rows[len(rows) // 3]]
        hole = (df.index >= t0) & (df.index < t0 + pd.Timedelta(minutes=60)) & (df["symbol"] == front).to_numpy()
        df = df[~hole]                                                # 60-minute hole
        df = pd.concat([df, df.iloc[[len(df) // 4]]]).sort_index()    # duplicate row
        out[roots[0]] = df
    return out
