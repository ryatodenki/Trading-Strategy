"""Market structure (order flow) state from swing breaks.

* Bullish (+1) once a bar CLOSES above the most recent confirmed swing high.
* Bearish (-1) once a bar closes below the most recent confirmed swing low.
* The state persists until the opposite break.  0 = not yet determined.
With ``break_on: wick`` the bar's high/low is used instead of its close.
The state at a bar is known at that bar's close (``known_ns``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.rules.swings import swings


def structure_state(bars: pd.DataFrame, n: int, break_on: str = "close") -> pd.DataFrame:
    m = len(bars)
    sw = swings(bars, n)
    sh_level = np.full(m, np.nan)
    sl_level = np.full(m, np.nan)
    for kind, arr in ((1, sh_level), (-1, sl_level)):
        s = sw[sw["kind"] == kind]
        arr[s["confirm_pos"].to_numpy()] = s["price"].to_numpy()
    sh_level = pd.Series(sh_level).ffill().to_numpy()
    sl_level = pd.Series(sl_level).ffill().to_numpy()
    close = bars["close"].to_numpy(float)
    up_px = close if break_on == "close" else bars["high"].to_numpy(float)
    dn_px = close if break_on == "close" else bars["low"].to_numpy(float)
    with np.errstate(invalid="ignore"):
        up = up_px > sh_level
        dn = dn_px < sl_level
    event = np.where(up & ~dn, 1.0, np.where(dn & ~up, -1.0, np.nan))
    state = pd.Series(event).ffill().fillna(0).to_numpy().astype(np.int8)
    flip = np.r_[False, state[1:] != state[:-1]] & (state != 0)
    return pd.DataFrame(
        {"state": state, "flip": flip, "sh_level": sh_level, "sl_level": sl_level, "known_ns": bars["known_ns"].to_numpy()},
        index=bars.index,
    )
