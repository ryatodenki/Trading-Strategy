"""Unit-safe timestamp helpers (pandas 3 defaults to microsecond resolution)."""

from __future__ import annotations

import numpy as np
import pandas as pd

NS_PER_MIN = 60_000_000_000


def ns(x) -> np.ndarray | int:
    """int64 nanoseconds since epoch for a Timestamp / DatetimeIndex / Series / datetime64 array."""
    if isinstance(x, pd.Timestamp):
        return int(x.as_unit("ns").value)
    if isinstance(x, pd.Series):
        x = pd.DatetimeIndex(x)
    if isinstance(x, pd.DatetimeIndex):
        return x.as_unit("ns").asi8
    arr = np.asarray(x)
    if np.issubdtype(arr.dtype, np.datetime64):
        return arr.astype("datetime64[ns]").astype(np.int64)
    return arr.astype(np.int64)


def to_ns_index(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.index, pd.DatetimeIndex) and df.index.unit != "ns":
        df = df.copy()
        df.index = df.index.as_unit("ns")
    return df


def from_ns(values, tz: str | None = "UTC") -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(np.asarray(values, dtype="int64").view("datetime64[ns]"))
    return idx.tz_localize(tz) if tz else idx
