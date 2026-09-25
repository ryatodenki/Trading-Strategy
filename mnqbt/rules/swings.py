"""Swing highs/lows ("fractals") with an explicit confirmation lag.

Definition (N = ``n`` bars each side):
    swing high at bar j  <=>  high[j] >  max(high[j-N .. j-1])
                          and high[j] >= max(high[j+1 .. j+N])
Strict on the left and non-strict on the right means that of two equal
highs, only the first is a swing.  The swing is only *known* at the close of
bar j+N — that is its ``known_ns`` and it must not be used earlier.
Swing lows mirror this with lows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


def _window_max(x: np.ndarray, n: int) -> np.ndarray:
    """out[i] = max(x[i : i+n]) for i in 0..len-n (NaN-propagating)."""
    return sliding_window_view(x, n).max(axis=1)


def swing_flags(high: np.ndarray, low: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    high = np.asarray(high, float)
    low = np.asarray(low, float)
    m = len(high)
    is_sh = np.zeros(m, bool)
    is_sl = np.zeros(m, bool)
    if m < 2 * n + 1:
        return is_sh, is_sl
    wh = _window_max(high, n)
    wl = -_window_max(-low, n)
    j = np.arange(n, m - n)
    left_h, right_h = wh[j - n], wh[j + 1]
    left_l, right_l = wl[j - n], wl[j + 1]
    with np.errstate(invalid="ignore"):
        is_sh[j] = (high[j] > left_h) & (high[j] >= right_h)
        is_sl[j] = (low[j] < left_l) & (low[j] <= right_l)
    return is_sh, is_sl


def swings(bars: pd.DataFrame, n: int) -> pd.DataFrame:
    """Swing events for a bar frame from ``rules.bars.resample``.

    Columns: pos (bar position), kind (+1 high / -1 low), price, start_ns
    (swing bar start), known_ns (confirmation bar close), confirm_pos.
    Sorted by known_ns, then kind.
    """
    is_sh, is_sl = swing_flags(bars["high"].to_numpy(), bars["low"].to_numpy(), n)
    start = bars["start_ns"].to_numpy()
    known = bars["known_ns"].to_numpy()
    frames = []
    for kind, flags, col in ((1, is_sh, "high"), (-1, is_sl, "low")):
        pos = np.flatnonzero(flags)
        frames.append(
            pd.DataFrame(
                {
                    "pos": pos,
                    "kind": kind,
                    "price": bars[col].to_numpy()[pos],
                    "start_ns": start[pos],
                    "known_ns": known[pos + n],
                    "confirm_pos": pos + n,
                }
            )
        )
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["known_ns", "kind"], kind="stable").reset_index(drop=True)
