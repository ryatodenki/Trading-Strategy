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


def _run(a_highs, b_highs, cfg, **lv):
    cfg = apply_overrides(cfg, {"rules.smt.swing_n": 2, "rules.smt.align_window_bars": 1, "rules.smt.min_separation_bars": 3,
                                "rules.smt.lookback_bars": 24, "rules.levels.tolerance": {"points": 1.0, "atr_frac": 0.0}})
    a, b = _bars(a_highs), _bars(b_highs)
    atr = np.full(len(a), 50.0)
    t = detect_triggers(a, b, _levels(a, **lv), atr, cfg)
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
    t = detect_triggers(a, b, _levels(a), np.full(len(a), 50.0), cfg2)
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
