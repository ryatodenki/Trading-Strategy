import numpy as np
import pandas as pd

from mnqbt.rules.fvg import detect_fvgs, entry_price
from tests.conftest import bars_from_ohlc

TF_NS = 5 * 60 * 10**9


def test_bullish_fvg_zone_and_known_time():
    rows = [(100, 101, 99, 100.5), (100.5, 106, 100.25, 105.5), (105.5, 107, 103, 106.5)]
    b = bars_from_ohlc(rows)
    f = detect_fvgs(b, "5min", 1.0, 12)
    assert len(f) == 1
    g = f.iloc[0]
    assert g["dir"] == 1
    assert (g["bottom"], g["top"]) == (101.0, 103.0)  # high of c1 .. low of c3
    assert g["size"] == 2.0
    assert g["known_ns"] == b["start_ns"].iloc[2] + TF_NS  # only known once c3 has closed
    assert g["expire_ns"] == g["known_ns"] + 12 * TF_NS


def test_bearish_fvg():
    rows = [(110, 111, 108, 108.5), (108.5, 108.75, 102, 102.5), (102.5, 105, 101, 101.5)]
    f = detect_fvgs(bars_from_ohlc(rows), "5min", 1.0, 12)
    assert len(f) == 1
    g = f.iloc[0]
    assert g["dir"] == -1
    assert (g["bottom"], g["top"]) == (105.0, 108.0)  # high of c3 .. low of c1


def test_min_size_filters_small_gaps():
    rows = [(100, 101, 99, 100.5), (100.5, 103, 100.25, 102.5), (102.5, 104, 101.5, 103.5)]  # gap 0.5
    b = bars_from_ohlc(rows)
    assert len(detect_fvgs(b, "5min", 1.0, 12)) == 0
    assert len(detect_fvgs(b, "5min", 0.5, 12)) == 1


def test_overlapping_candles_are_not_a_gap():
    rows = [(100, 102, 99, 101), (101, 104, 100.5, 103.5), (103.5, 105, 101.75, 104)]  # c3 low < c1 high
    assert len(detect_fvgs(bars_from_ohlc(rows), "5min", 0.25, 12)) == 0


def test_missing_bin_breaks_the_pattern():
    rows = [(100, 101, 99, 100.5), (100.5, 106, 100.25, 105.5), (105.5, 107, 103, 106.5)]
    b = bars_from_ohlc(rows)
    b.iloc[2, b.columns.get_loc("start_ns")] += TF_NS  # c3 is 10 minutes after c2 (a hole)
    assert len(detect_fvgs(b, "5min", 1.0, 12)) == 0


def test_fvg_cannot_span_trading_days():
    # 16:50, 16:55 then 18:00 ET (next trading day) - the maintenance halt is not an FVG
    idx = [pd.Timestamp("2024-03-05 16:50", tz="America/New_York"), pd.Timestamp("2024-03-05 16:55", tz="America/New_York")]
    b = bars_from_ohlc([(100, 101, 99, 100.5), (100.5, 106, 100.25, 105.5), (105.5, 107, 103, 106.5)],
                       start=str(idx[0].tz_convert("UTC").tz_localize(None)))
    b.iloc[2, b.columns.get_loc("tdate")] = b["tdate"].iloc[1] + pd.Timedelta(days=1)
    assert len(detect_fvgs(b, "5min", 1.0, 12)) == 0


def test_entry_price_fraction_and_tick_rounding():
    top, bottom = np.array([103.0, 103.0, 108.0]), np.array([101.0, 101.75, 105.0])
    d = np.array([1, 1, -1])
    assert entry_price(top, bottom, d, 0.5, 0.25).tolist() == [102.0, 102.25, 106.5]
    # 101.75..103 midpoint 102.375 -> rounded one tick deeper into the zone for a long (102.25)
    assert entry_price(top, bottom, d, 0.0, 0.25).tolist() == [103.0, 103.0, 105.0]
    assert entry_price(top, bottom, d, 1.0, 0.25).tolist() == [101.0, 101.75, 108.0]


def test_same_direction_needs_three_candles_closing_the_gaps_way():
    from mnqbt.rules.fvg import detect_fvgs
    from tests.conftest import bars_from_ohlc
    up = [(100, 102, 99, 101.5), (101.5, 106, 101, 105.5), (105.5, 108, 104, 107.5)]   # gap 102 -> 104, three up candles
    assert len(detect_fvgs(bars_from_ohlc(up), "5min", 1.0, 12, same_direction=True)) == 1
    mixed = up[:2] + [(107.5, 108, 104, 105)]                                           # third candle closes down
    assert len(detect_fvgs(bars_from_ohlc(mixed), "5min", 1.0, 12)) == 1
    assert len(detect_fvgs(bars_from_ohlc(mixed), "5min", 1.0, 12, same_direction=True)) == 0
