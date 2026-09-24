"""Trading-day and session labelling in America/New_York time.

Conventions used everywhere in the package:

* Bar timestamps are UTC and mark the bar OPEN.  A 1m bar stamped 14:30 UTC
  covers [14:30, 14:31) and its values are known at 14:31.
* A trading day runs from ``trading_day_start`` (18:00 ET) on the previous
  calendar day to ``trading_day_end`` (17:00 ET).  Sunday 18:00 belongs to
  Monday's trading day.
* Sessions are defined in ET wall-clock time in the config, so DST shifts are
  absorbed by the UTC->ET conversion.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.config import get, hhmm_to_minutes

MINUTES_PER_DAY = 1440
DAY = pd.Timedelta(days=1)


def et_parts(index: pd.DatetimeIndex, tz: str) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """Return (minute-of-day in ET, naive ET calendar date) for a UTC index."""
    et = index.tz_convert(tz)
    minute = (et.hour * 60 + et.minute).to_numpy()
    date = et.tz_localize(None).normalize()
    return minute, date


def trading_dates(index: pd.DatetimeIndex, cfg: dict) -> pd.DatetimeIndex:
    tz = get(cfg, "project.timezone")
    start = hhmm_to_minutes(get(cfg, "sessions.trading_day_start"))
    minute, date = et_parts(index, tz)
    return date + pd.to_timedelta((minute >= start).astype(int), unit="D")


def session_labels(minute: np.ndarray, cfg: dict) -> np.ndarray:
    """Label each ET minute-of-day with its session name ('' outside sessions)."""
    labels = np.full(minute.shape, "", dtype=object)
    for name, (s, e) in get(cfg, "sessions.definitions").items():
        s_m, e_m = hhmm_to_minutes(s), hhmm_to_minutes(e)
        if s_m < e_m:
            mask = (minute >= s_m) & (minute < e_m)
        else:  # wraps midnight
            mask = (minute >= s_m) | (minute < e_m)
        labels[mask & (labels == "")] = name
    return labels


def minutes_into_trading_day(minute: np.ndarray, cfg: dict) -> np.ndarray:
    start = hhmm_to_minutes(get(cfg, "sessions.trading_day_start"))
    return (minute - start) % MINUTES_PER_DAY


def annotate(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Add ET/session columns to a bar frame indexed by UTC bar-open time."""
    tz = get(cfg, "project.timezone")
    start = hhmm_to_minutes(get(cfg, "sessions.trading_day_start"))
    minute, date = et_parts(df.index, tz)
    out = df.copy()
    out["et_min"] = minute.astype(np.int16)
    out["tdate"] = date + pd.to_timedelta((minute >= start).astype(int), unit="D")
    out["session"] = pd.Categorical(session_labels(minute, cfg))
    out["tod"] = minutes_into_trading_day(minute, cfg).astype(np.int16)
    return out


def et_time_on_tdate(tdates: pd.DatetimeIndex | pd.Series, hhmm: str, cfg: dict) -> pd.DatetimeIndex:
    """UTC timestamp of ET wall-clock ``hhmm`` inside each trading date.

    Times at or after the trading-day start (e.g. 18:00, 20:00) fall on the
    previous calendar day; earlier times fall on the trading date itself.
    """
    tz = get(cfg, "project.timezone")
    start = hhmm_to_minutes(get(cfg, "sessions.trading_day_start"))
    m = hhmm_to_minutes(hhmm)
    td = pd.DatetimeIndex(tdates)
    cal = td - DAY if m >= start else td
    naive = cal + pd.Timedelta(minutes=m)
    return naive.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def session_end_times(tdates: pd.DatetimeIndex, session: str, cfg: dict) -> pd.DatetimeIndex:
    """Scheduled UTC end time of ``session`` for each trading date."""
    _, end = get(cfg, "sessions.definitions")[session]
    return et_time_on_tdate(tdates, end, cfg)


def in_windows(minute: np.ndarray, windows: list[list[str]]) -> np.ndarray:
    """True where ET minute-of-day falls in any [start, end) window (wrap allowed)."""
    mask = np.zeros(minute.shape, dtype=bool)
    for s, e in windows or []:
        s_m, e_m = hhmm_to_minutes(s), hhmm_to_minutes(e)
        if s_m < e_m:
            mask |= (minute >= s_m) & (minute < e_m)
        else:
            mask |= (minute >= s_m) | (minute < e_m)
    return mask
