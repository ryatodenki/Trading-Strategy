"""Higher-timeframe bars built from 1m bars, with explicit 'known at' times.

A 5m bar that starts at 09:30 ET covers the 1m bars 09:30..09:34 and is
known at 09:35 (``known_ns``).  Nothing derived from it may be used before
then.  Bins are aligned to wall-clock multiples of the timeframe; because ET
is a whole-hour offset from UTC, 5/15/60-minute UTC bins are also ET bins.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.timeutil import NS_PER_MIN, ns


def tf_minutes(tf: str) -> int:
    tf = tf.strip().lower()
    if tf.endswith("min"):
        return int(tf[:-3])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    if tf.endswith("m"):
        return int(tf[:-1])
    raise ValueError(f"bad timeframe {tf!r}")


def resample(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """OHLCV bars of ``tf`` from annotated 1m bars (needs a ``tdate`` column).

    Columns: open high low close volume tdate n1 start_ns known_ns.
    Index: bin start (UTC).
    """
    minutes = tf_minutes(tf)
    t = ns(m1.index)
    if minutes == 1:
        out = m1[["open", "high", "low", "close", "volume"]].copy()
        out["tdate"] = m1["tdate"].to_numpy()
        out["n1"] = 1
        out["start_ns"] = t
        out["known_ns"] = t + NS_PER_MIN
        return out
    width = minutes * NS_PER_MIN
    b = t // width * width
    starts = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    ends = np.r_[starts[1:], len(b)] - 1
    o, h, l, c = (m1[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    v = m1["volume"].to_numpy(float)
    out = pd.DataFrame(
        {
            "open": o[starts],
            "high": np.maximum.reduceat(h, starts),
            "low": np.minimum.reduceat(l, starts),
            "close": c[ends],
            "volume": np.add.reduceat(v, starts),
            "tdate": m1["tdate"].to_numpy()[starts],
            "n1": ends - starts + 1,
            "start_ns": b[starts],
            "known_ns": b[starts] + width,
        },
        index=pd.DatetimeIndex(b[starts].view("datetime64[ns]")).tz_localize("UTC"),
    )
    return out


def align_pair(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Reindex bar frame ``b`` onto ``a``'s bins (missing bars -> NaN)."""
    return b.reindex(a.index)


def asof_index(known_ns: np.ndarray, query_ns: np.ndarray | int) -> np.ndarray:
    """Position of the last row with known_ns <= query (or -1).  known_ns must be sorted."""
    return np.searchsorted(known_ns, query_ns, side="right") - 1
