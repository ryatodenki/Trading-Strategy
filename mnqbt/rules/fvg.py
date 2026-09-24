"""Fair value gaps on a bar timeframe.

Three consecutive bars c1, c2, c3 (same trading day, no missing bin between):
* Bullish FVG if low(c3) > high(c1): zone [high(c1), low(c3)]
* Bearish FVG if high(c3) < low(c1): zone [high(c3), low(c1)]
Size = top - bottom must be >= min_size (points / ATR fraction).  The FVG is
known at the close of c3 and stays usable for ``max_age_bars`` bars after
that (``expire_ns``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.rules.bars import tf_minutes
from mnqbt.timeutil import NS_PER_MIN


def detect_fvgs(bars: pd.DataFrame, tf: str, min_size: np.ndarray | float, max_age_bars: int) -> pd.DataFrame:
    width = tf_minutes(tf) * NS_PER_MIN
    h = bars["high"].to_numpy(float)
    l = bars["low"].to_numpy(float)
    start = bars["start_ns"].to_numpy()
    td = bars["tdate"].to_numpy()
    min_size = np.broadcast_to(np.asarray(min_size, float), h.shape)
    k = np.arange(2, len(bars))
    contiguous = (start[k] - start[k - 2] == 2 * width) & (td[k] == td[k - 2])
    rows = []
    for direction, top, bottom in (
        (1, l[k], h[k - 2]),       # bullish: gap between c1 high and c3 low
        (-1, l[k - 2], h[k]),      # bearish: gap between c3 high and c1 low
    ):
        size = top - bottom
        with np.errstate(invalid="ignore"):
            ok = contiguous & (size > 0) & (size >= min_size[k])
        kk = k[ok]
        rows.append(
            pd.DataFrame(
                {
                    "dir": direction,
                    "top": top[ok],
                    "bottom": bottom[ok],
                    "size": size[ok],
                    "c1_start_ns": start[kk - 2],
                    "c3_pos": kk,
                    "known_ns": start[kk] + width,
                    "expire_ns": start[kk] + width + max_age_bars * width,
                    "tdate": td[kk],
                }
            )
        )
    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["known_ns", "dir"], kind="stable").reset_index(drop=True)


def entry_price(fvg_top: np.ndarray, fvg_bottom: np.ndarray, direction: np.ndarray, fraction: float, tick: float) -> np.ndarray:
    """Limit price inside the FVG, measured from the edge price reaches first.

    fraction 0 = near edge (top of a bullish FVG), 0.5 = midpoint, 1 = far edge.
    Rounded one tick deeper into the zone when off-grid (fewer, not more, fills).
    """
    size = fvg_top - fvg_bottom
    raw = np.where(direction > 0, fvg_top - fraction * size, fvg_bottom + fraction * size)
    return np.where(direction > 0, np.floor(raw / tick + 1e-9) * tick, np.ceil(raw / tick - 1e-9) * tick)
