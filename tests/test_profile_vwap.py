import numpy as np
import pandas as pd

from mnqbt.rules.profile import profile, value_area, value_area_prices
from mnqbt.rules.vwap import vwap
from tests.conftest import m1_from_ohlc


def test_profile_spreads_volume_evenly_over_the_range():
    base, vols = profile(np.array([100.0]), np.array([100.75]), np.array([40.0]), 0.25)
    assert base == 100.0 and vols.tolist() == [10.0, 10.0, 10.0, 10.0]


def test_value_area_covers_70_percent_around_poc():
    vols = np.array([1, 2, 5, 20, 40, 20, 5, 2, 1], float)  # total 96
    lo, hi, poc = value_area(vols, 0.70)
    assert poc == 4
    assert vols[lo:hi + 1].sum() >= 0.70 * vols.sum()
    assert (lo, hi) == (3, 5)  # 80 / 96 = 83% after adding both 20s


def test_value_area_prices_edges():
    low = np.array([100.0, 101.0, 101.0, 101.0, 105.0])
    high = low + 0.0
    vol = np.array([1.0, 30.0, 30.0, 30.0, 1.0])
    val, vah, poc = value_area_prices(low, high, vol, 0.25)
    assert (val, vah) == (101.0, 101.25) and poc == 101.125


def test_vwap_is_cumulative_and_resets_each_trading_day(cfg):
    rows = [(100, 101, 99, 100), (102, 103, 101, 102)]
    m1 = m1_from_ohlc(rows, start="2024-03-05 21:58", cfg=cfg)  # 16:58, 16:59 ET
    m2 = m1_from_ohlc([(200, 201, 199, 200)], start="2024-03-05 23:00", cfg=cfg)  # 18:00 ET = new trading day
    m = pd.concat([m1, m2])
    v = vwap(m, "trading_day")
    assert v[0] == 100 and v[1] == 101 and v[2] == 200
