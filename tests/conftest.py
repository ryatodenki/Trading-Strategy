from __future__ import annotations

import pandas as pd
import pytest

from mnqbt.config import load_config
from mnqbt.data.sessions import annotate
from mnqbt.timeutil import ns


@pytest.fixture(scope="session")
def cfg():
    return load_config()


def bars_from_ohlc(rows, start="2024-03-05 14:30", freq="5min", cfg=None):
    """Bar frame (as produced by rules.bars.resample) from a list of (o, h, l, c)."""
    cfg = cfg or load_config()
    idx = pd.date_range(pd.Timestamp(start, tz="UTC"), periods=len(rows), freq=freq).as_unit("ns")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx, dtype=float)
    df["volume"] = 100.0
    m = annotate(df, cfg)
    width = pd.Timedelta(freq).value
    out = df.copy()
    out["tdate"] = m["tdate"].to_numpy()
    out["n1"] = 1
    out["start_ns"] = ns(idx)
    out["known_ns"] = ns(idx) + width
    return out


def m1_from_ohlc(rows, start="2024-03-05 14:30", cfg=None):
    """Annotated 1m bars (UTC index) from (o, h, l, c) rows."""
    cfg = cfg or load_config()
    idx = pd.date_range(pd.Timestamp(start, tz="UTC"), periods=len(rows), freq="1min").as_unit("ns")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx, dtype=float)
    df["volume"] = 100.0
    return annotate(df, cfg)


def flat_rows(n, price=100.0):
    return [(price, price + 0.25, price - 0.25, price)] * n
