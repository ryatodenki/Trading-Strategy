"""Volume profile and 70% value area from 1m bars.

Without tick data, each 1m bar's volume is spread evenly over the price
buckets between its low and high (a standard approximation; with 1m bars the
VAH/VAL error is typically a few ticks).  Value area: start at the POC
(highest-volume bucket) and repeatedly add the larger neighbouring bucket
(above or below) until ``pct`` of the day's volume is covered.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def profile(low: np.ndarray, high: np.ndarray, volume: np.ndarray, bucket: float) -> tuple[float, np.ndarray]:
    """Return (price of bucket 0's lower edge, volume per bucket)."""
    lo_i = np.floor(np.asarray(low, float) / bucket + 1e-9).astype(np.int64)
    hi_i = np.floor(np.asarray(high, float) / bucket + 1e-9).astype(np.int64)
    hi_i = np.maximum(hi_i, lo_i)
    base = lo_i.min()
    counts = hi_i - lo_i + 1
    rep = np.repeat(np.arange(len(lo_i)), counts)
    offs = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    idx = lo_i[rep] + offs - base
    w = (np.asarray(volume, float) / counts)[rep]
    return base * bucket, np.bincount(idx, weights=w)


def value_area(vols: np.ndarray, pct: float = 0.70) -> tuple[int, int, int]:
    """(val_idx, vah_idx, poc_idx) bucket indices of the value area."""
    total = vols.sum()
    poc = int(np.argmax(vols))
    lo = hi = poc
    acc = vols[poc]
    n = len(vols)
    target = pct * total
    while acc < target and (lo > 0 or hi < n - 1):
        up = vols[hi + 1] if hi < n - 1 else -1.0
        dn = vols[lo - 1] if lo > 0 else -1.0
        if up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn
    return lo, hi, poc


def value_area_prices(low, high, volume, bucket: float, pct: float = 0.70) -> tuple[float, float, float]:
    """(VAL, VAH, POC) prices; VAL/VAH are outer bucket edges, POC is its bucket midpoint."""
    base, vols = profile(low, high, volume, bucket)
    lo, hi, poc = value_area(vols, pct)
    return base + lo * bucket, base + (hi + 1) * bucket, base + (poc + 0.5) * bucket


def daily_value_areas(
    m1: pd.DataFrame, bucket_by_date: pd.Series, pct: float, rth_only: bool, rth_minutes: tuple[int, int]
) -> pd.DataFrame:
    """VAL/VAH/POC for each trading date's own bars (NOT shifted; caller shifts to 'prior')."""
    df = m1
    if rth_only:
        em = df["et_min"].to_numpy()
        df = df[(em >= rth_minutes[0]) & (em < rth_minutes[1])]
    td = df["tdate"].to_numpy()
    lo_a, hi_a, v_a = (df[k].to_numpy(float) for k in ("low", "high", "volume"))
    bounds = np.flatnonzero(np.r_[True, td[1:] != td[:-1], True])
    rows = []
    for s, e in zip(bounds[:-1], bounds[1:]):
        d = td[s]
        b = bucket_by_date.get(pd.Timestamp(d), np.nan)
        if not np.isfinite(b) or v_a[s:e].sum() <= 0:
            rows.append((d, np.nan, np.nan, np.nan))
            continue
        val, vah, poc = value_area_prices(lo_a[s:e], hi_a[s:e], v_a[s:e], b, pct)
        rows.append((d, val, vah, poc))
    return pd.DataFrame(rows, columns=["tdate", "val", "vah", "poc"]).set_index("tdate")
