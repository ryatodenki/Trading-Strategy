"""Session-anchored VWAP from 1m bars.

VWAP_t = sum(typical_price * volume) / sum(volume) over bars from the anchor
up to and including bar t, typical price = (H + L + C) / 3.  Value at bar t is
known at t's close.  Anchor = start of the trading day (18:00 ET) or the start
of each configured session.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def vwap(m1: pd.DataFrame, anchor: str = "trading_day") -> np.ndarray:
    tp = (m1["high"].to_numpy(float) + m1["low"].to_numpy(float) + m1["close"].to_numpy(float)) / 3.0
    v = m1["volume"].to_numpy(float)
    if anchor == "trading_day":
        key = m1["tdate"].to_numpy()
    elif anchor == "session":
        key = pd.factorize(pd.Series(m1["tdate"].astype(str).to_numpy()) + "|" + m1["session"].astype(str).to_numpy())[0]
    else:
        raise ValueError(f"unknown vwap anchor {anchor!r}")
    df = pd.DataFrame({"k": key, "pv": tp * v, "v": v})
    g = df.groupby("k", sort=False)
    cum_pv = g["pv"].cumsum().to_numpy()
    cum_v = g["v"].cumsum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cum_v > 0, cum_pv / cum_v, np.nan)
