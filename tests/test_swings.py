import numpy as np

from mnqbt.rules.structure import structure_state
from mnqbt.rules.swings import swing_flags, swings
from tests.conftest import bars_from_ohlc


def _hl(highs, lows=None):
    highs = np.asarray(highs, float)
    lows = np.asarray(lows if lows is not None else highs - 1, float)
    return highs, lows


def test_swing_high_needs_n_bars_each_side():
    h, l = _hl([1, 2, 3, 5, 4, 3, 2])
    sh, sl = swing_flags(h, l, 2)
    assert np.flatnonzero(sh).tolist() == [3]
    sh1, _ = swing_flags(h, l, 1)
    assert np.flatnonzero(sh1).tolist() == [3]
    sh3, _ = swing_flags(h, l, 3)
    assert np.flatnonzero(sh3).tolist() == [3]
    sh4, _ = swing_flags(h, l, 4)
    assert not sh4.any()  # not enough bars on the left


def test_equal_highs_only_first_counts():
    h, l = _hl([1, 2, 5, 5, 2, 1, 0])
    sh, _ = swing_flags(h, l, 2)
    assert np.flatnonzero(sh).tolist() == [2]


def test_swing_low_mirror():
    lows = np.array([5, 4, 3, 1, 2, 3, 4], float)
    sh, sl = swing_flags(lows + 1, lows, 2)
    assert np.flatnonzero(sl).tolist() == [3]


def test_no_swing_at_the_right_edge_until_confirmed():
    h, l = _hl([1, 2, 3, 4, 5, 6, 7, 9])  # last bar is the highest but has no right side yet
    sh, _ = swing_flags(h, l, 2)
    assert not sh.any()


def test_confirmation_time_is_n_bars_later():
    rows = [(x, x + 1, x - 1, x) for x in [10, 11, 12, 15, 13, 12, 11]]
    b = bars_from_ohlc(rows)
    s = swings(b, 2)
    hi = s[s["kind"] == 1].iloc[0]
    assert hi["pos"] == 3 and hi["confirm_pos"] == 5
    assert hi["known_ns"] == b["known_ns"].iloc[5]  # close of bar j+N, not bar j


def test_swings_are_causal_under_truncation():
    rng = np.random.default_rng(0)
    x = np.cumsum(rng.normal(size=400))
    h, l = x + 0.5, x - 0.5
    full_sh, full_sl = swing_flags(h, l, 3)
    for cut in (50, 123, 300):
        sh, sl = swing_flags(h[:cut], l[:cut], 3)
        confirmed = np.arange(cut) + 3 < cut  # only swings already confirmed inside the truncated series
        assert (sh[confirmed] == full_sh[:cut][confirmed]).all()
        assert (sl[confirmed] == full_sl[:cut][confirmed]).all()


def test_structure_flips_on_close_beyond_swing():
    # up, pullback (swing high at bar 3), rally closing above it -> bullish; then break of swing low -> bearish
    closes = [10, 11, 12, 14, 13, 12, 12.5, 13.5, 15, 16, 14, 12, 11, 9, 8]
    rows = [(c, c + 0.5, c - 0.5, c) for c in closes]
    b = bars_from_ohlc(rows, freq="60min")
    st = structure_state(b, 2, "close")
    state = st["state"].to_numpy()
    assert state[7] == 0          # 13.5 close is still below the 14.5 swing high
    assert state[8] == 1          # 15 close breaks it
    assert state[-1] == -1        # later closes break the 11.5 swing low
    assert st["flip"].sum() == 2
