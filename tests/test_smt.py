import numpy as np
import pandas as pd

from mnqbt.config import apply_overrides
from mnqbt.rules.smt import detect_triggers
from tests.conftest import bars_from_ohlc


def _bars(highs, lows=None):
    highs = np.asarray(highs, float)
    lows = np.asarray(lows, float) if lows is not None else highs - 2
    rows = [((h + l) / 2, h, l, (h + l) / 2) for h, l in zip(highs, lows)]
    return bars_from_ohlc(rows)


def _levels(a, **cols):
    lv = pd.DataFrame(index=a.index)
    for c in ["pdh", "pdl", "dh", "dl", "asia_h", "asia_l", "london_h", "london_l", "ny_h", "ny_l",
              "sh1", "sh2", "sh3", "sl1", "sl2", "sl3", "vah", "val", "poc"]:
        lv[c] = cols.get(c, np.nan)
    return lv


# two swing highs at bars 3 and 9 (n=2); lows are flat
A_HIGHS = [10, 11, 12, 20, 13, 12, 13, 14, 15, 22, 16, 14, 13]


def _run(a_highs, b_highs, cfg, atr_b=50.0, **lv):
    cfg = apply_overrides(cfg, {"rules.smt.swing_n": 2, "rules.smt.align_window_bars": 1, "rules.smt.min_separation_bars": 3,
                                "rules.smt.lookback_bars": 24, "rules.levels.tolerance": {"points": 1.0, "atr_frac": 0.0}})
    a, b = _bars(a_highs), _bars(b_highs)
    t = detect_triggers(a, b, _levels(a, **lv), np.full(len(a), 50.0), np.full(len(a), atr_b), cfg)
    return a, t[(t["dir"] == -1) & (t["pos"] == 9)]


def test_bearish_smt_mnq_higher_high_mes_lower_high(cfg):
    b_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 19, 16, 14, 13]  # MES fails to exceed 20
    a, t = _run(A_HIGHS, b_highs, cfg)
    assert len(t) == 1
    r = t.iloc[0]
    assert bool(r["smt"]) and r["smt_leader"] == "MNQ"
    assert r["prev_pos"] == 3 and r["extreme"] == 22
    assert r["known_ns"] == a["known_ns"].iloc[11]  # confirmed 2 bars after the swing


def test_no_smt_when_both_make_higher_highs(cfg):
    b_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 21, 16, 14, 13]
    _, t = _run(A_HIGHS, b_highs, cfg)
    assert not bool(t.iloc[0]["smt"])


def test_smt_vice_versa_mes_leads(cfg):
    a_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 19, 16, 14, 13]  # MNQ lower high
    b_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 22, 16, 14, 13]  # MES higher high
    _, t = _run(a_highs, b_highs, cfg)
    assert bool(t.iloc[0]["smt"]) and t.iloc[0]["smt_leader"] == "MES"


def test_mes_window_alignment(cfg):
    # MES makes its higher high one bar AFTER MNQ's swing -> still "the same swing" within +-1 bar -> no SMT
    b_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 16, 21, 14, 13]
    _, t = _run(A_HIGHS, b_highs, cfg)
    assert not bool(t.iloc[0]["smt"])


def test_bullish_smt_on_lows(cfg):
    lows = np.array([20, 19, 18, 10, 17, 18, 17, 16, 15, 8, 14, 16, 17], float)
    b_lows = lows.copy()
    b_lows[9] = 11  # MES higher low
    cfg2 = apply_overrides(cfg, {"rules.levels.tolerance": {"points": 1.0, "atr_frac": 0.0}})
    a, b = _bars(lows + 3, lows), _bars(b_lows + 3, b_lows)
    t = detect_triggers(a, b, _levels(a), np.full(len(a), 50.0), np.full(len(a), 50.0), cfg2)
    r = t[(t["dir"] == 1) & (t["pos"] == 9)].iloc[0]
    assert bool(r["smt"]) and r["smt_leader"] == "MNQ"


def test_key_level_proximity_uses_level_known_before_swing(cfg):
    b_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 19, 16, 14, 13]
    _, t = _run(A_HIGHS, b_highs, cfg, pdh=21.5)
    assert bool(t.iloc[0]["near_core"]) and t.iloc[0]["level_core"] == "pdh"
    _, t = _run(A_HIGHS, b_highs, cfg, pdh=25.0)
    assert not bool(t.iloc[0]["near_core"])


def test_sweep_mode_requires_trading_through_the_level(cfg):
    b_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 19, 16, 14, 13]
    _, t = _run(A_HIGHS, b_highs, cfg, pdh=21.5)   # extreme 22 trades 0.5 through 21.5
    assert bool(t.iloc[0]["sweep_core"])
    _, t = _run(A_HIGHS, b_highs, cfg, pdh=22.5)   # 0.5 short of the level: near, but not a sweep
    assert bool(t.iloc[0]["near_core"]) and not bool(t.iloc[0]["sweep_core"])


def test_smt_needs_minimum_break(cfg):
    # min_size = max(0.5 pt, 1% of ATR 50) = 0.5: MNQ beating 20 by 1 tick is not SMT, by 2 ticks it is
    b_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 19, 16, 14, 13]
    for top, smt in ((20.25, False), (20.5, True)):
        a_highs = list(A_HIGHS)
        a_highs[9] = top
        _, t = _run(a_highs, b_highs, cfg)
        assert bool(t.iloc[0]["smt"]) is smt


def test_smt_minimum_uses_the_leaders_own_atr(cfg):
    # MES leads by 2 pts: enough at an MES ATR of 50 (min 0.5), not at 400 (min 4)
    a_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 19, 16, 14, 13]
    b_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 22, 16, 14, 13]
    assert bool(_run(a_highs, b_highs, cfg, atr_b=50.0)[1].iloc[0]["smt"])
    assert not bool(_run(a_highs, b_highs, cfg, atr_b=400.0)[1].iloc[0]["smt"])


def test_sweep_reports_the_swept_level_not_the_nearest(cfg):
    b_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 19, 16, 14, 13]
    _, t = _run(A_HIGHS, b_highs, cfg, pdh=21.5, dh=22.25)   # extreme 22: dh is nearer but not traded through
    r = t.iloc[0]
    assert r["level_core"] == "dh" and r["sweep_level_core"] == "pdh" and r["sweep_depth_core"] == 0.5


def test_level_must_exist_before_the_smts_first_swing(cfg):
    # The first swing (bar 3, high 20) lifts the running day high from 19 to 20. The second swing
    # (bar 9, 20.5) sweeps that 20 by 0.5, but it is the SMT's own first swing, not a key level.
    b_highs = [10, 11, 12, 20, 13, 12, 13, 14, 15, 19, 16, 14, 13]
    a_highs = list(A_HIGHS)
    a_highs[9] = 20.5
    dh = np.where(np.arange(len(a_highs)) <= 3, 19.0, 20.0)
    _, t = _run(a_highs, b_highs, cfg, dh=dh)
    r = t.iloc[0]
    assert bool(r["smt"]) and r["level_pos"] == 3
    assert not bool(r["sweep_core"]) and not bool(r["near_core"])     # 19 is 1.5 away: beyond the 1-pt tolerance
    # a level that already existed (prior-day high 20.25) still counts
    _, t = _run(a_highs, b_highs, cfg, dh=dh, pdh=20.25)
    assert bool(t.iloc[0]["sweep_core"]) and t.iloc[0]["sweep_level_core"] == "pdh"
