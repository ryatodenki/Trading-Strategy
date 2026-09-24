"""Fill logic: through vs touch, same-bar conservatism, cancels, slippage, costs, one position."""

import numpy as np
import pandas as pd
import pytest

from mnqbt.backtest.engine import EngineSettings, Market, simulate

MIN = 60 * 10**9
T0 = int(pd.Timestamp("2024-03-05 15:00", tz="UTC").value)


def mk(rows):
    """rows: list of (o, h, l, c) 1m bars starting at T0."""
    a = np.asarray(rows, float)
    return Market(ts=T0 + MIN * np.arange(len(a)), open=a[:, 0], high=a[:, 1], low=a[:, 2], close=a[:, 3],
                  session=np.full(len(a), "ny"))


def settings(**kw):
    base = dict(fill_mode="through", same_bar="stop_first", commission_per_side=0.60, slippage_ticks_stop=1,
                slippage_ticks_market=1, contracts=1, tick=0.25, point_value=2.0)
    base.update(kw)
    return EngineSettings(**base)


def intent(dir=1, entry=100.0, stop=98.0, target=104.0, placed=0, expire=60, flatten=120, entry_type="limit", target_r=2.0):
    return {"placed_ns": T0 + placed * MIN, "dir": dir, "entry": entry, "stop": stop, "target": target,
            "expire_ns": T0 + expire * MIN, "flatten_ns": T0 + flatten * MIN, "entry_type": entry_type,
            "target_src": "r_multiple", "target_r": target_r, "cancel_reason_at_expiry": "timeout", "tdate": pd.Timestamp("2024-03-05")}


def run(rows, intents, **kw):
    return simulate(mk(rows), pd.DataFrame(intents), settings(**kw))


FLAT = (101.0, 101.5, 100.5, 101.0)


def test_through_needs_a_tick_beyond_touch_does_not():
    rows = [FLAT, (101, 101, 100.0, 100.5)] + [FLAT] * 5  # low touches 100 exactly
    tr, log = run(rows, [intent()])
    assert tr.empty and log["status"].iloc[0].startswith("expired")
    tr, _ = run(rows, [intent()], fill_mode="touch")
    assert len(tr) == 1 and tr["entry"].iloc[0] == 100.0


def test_fill_then_target_and_costs():
    rows = [FLAT, (101, 101, 99.75, 100.5), (100.5, 103, 100.25, 102.5), (102.5, 104.5, 102, 104)]
    tr, _ = run(rows, [intent()])
    t = tr.iloc[0]
    assert t["exit_reason"] == "target" and t["exit_price"] == 104.0
    assert t["gross_pts"] == 4.0
    assert t["pnl_usd"] == pytest.approx(4.0 * 2 - 1.20)       # $8 gross - 2 x $0.60
    assert t["r_net"] == pytest.approx((8 - 1.2) / 4.0)          # risk 2 pts = $4


def test_stop_in_fill_bar_counts_and_pays_slippage():
    rows = [FLAT, (101, 101, 97.5, 98.0)] + [FLAT] * 3
    tr, _ = run(rows, [intent()])
    t = tr.iloc[0]
    assert t["exit_reason"] == "stop" and t["exit_price"] == 97.75  # 98 - 1 tick
    assert t["pnl_usd"] == pytest.approx(-2.25 * 2 - 1.2)


def test_target_in_fill_bar_only_if_close_beyond():
    # fill bar spans 99.5..104.5 but closes at 102: we cannot know the high came after the fill
    rows = [FLAT, (101, 104.5, 99.5, 102.0), (102, 102.5, 101.5, 102), (102, 102.5, 101.5, 102)]
    tr, _ = run(rows, [intent(flatten=3)])
    assert tr["exit_reason"].iloc[0] == "flatten"
    rows[1] = (101, 104.5, 99.5, 104.25)  # closes beyond the target -> target reached after the fill
    tr, _ = run(rows, [intent(flatten=3)])
    assert tr["exit_reason"].iloc[0] == "target"


def test_same_bar_stop_and_target_is_a_stop_unless_optimistic():
    rows = [FLAT, (101, 101, 99.5, 100.5), (100.5, 104.5, 97.5, 101)] + [FLAT] * 2
    tr, _ = run(rows, [intent()])
    assert tr["exit_reason"].iloc[0] == "stop" and bool(tr["ambiguous_bar"].iloc[0])
    tr, _ = run(rows, [intent()], same_bar="target_first")
    assert tr["exit_reason"].iloc[0] == "target"


def test_resolver_decides_ambiguous_bar():
    rows = [FLAT, (101, 101, 99.5, 100.5), (100.5, 104.5, 97.5, 101)] + [FLAT] * 2
    m = mk(rows)
    tr, _ = simulate(m, pd.DataFrame([intent()]), settings(), resolver=lambda ts, d, s, t: "target")
    assert tr["exit_reason"].iloc[0] == "target"


def test_gap_through_stop_fills_at_open():
    rows = [FLAT, (101, 101, 99.5, 100.5), (96.0, 96.5, 95.5, 96.0)] + [FLAT]
    tr, _ = run(rows, [intent()])
    assert tr["exit_price"].iloc[0] == 95.75  # open 96 - 1 tick, worse than the 98 stop


def test_target_reached_before_fill_cancels():
    rows = [FLAT, (101, 104.25, 100.75, 104), (104, 104, 99, 99.5)] + [FLAT]
    tr, log = run(rows, [intent()])
    assert tr.empty and log["status"].iloc[0] == "cancel_target_first"


def test_order_expires():
    rows = [FLAT] * 10 + [(101, 101, 99, 99.5)]
    tr, log = run(rows, [intent(expire=5)])
    assert tr.empty and log["status"].iloc[0] == "expired_timeout"


def test_flatten_exit_pays_market_slippage():
    rows = [FLAT, (101, 101, 99.75, 100.5)] + [(100.5, 101, 100, 100.5)] * 5
    tr, _ = run(rows, [intent(flatten=4)])
    t = tr.iloc[0]
    assert t["exit_reason"] == "flatten" and t["exit_price"] == 100.25  # open 100.5 - 1 tick


def test_short_side_mirrors():
    rows = [FLAT, (101, 102.25, 101, 101.5), (101.5, 101.75, 97.5, 98)]
    tr, _ = run(rows, [intent(dir=-1, entry=102.0, stop=104.0, target=98.0)])
    t = tr.iloc[0]
    assert t["exit_reason"] == "target" and t["gross_pts"] == 4.0


def test_one_position_at_a_time():
    rows = [FLAT, (101, 101, 99.5, 100.5)] + [(100.5, 101, 100, 100.5)] * 5 + [(100.5, 104.5, 100, 104)] + [FLAT] * 3
    second = intent(placed=3, entry=100.25, stop=99.0, target=102.75)
    tr, log = run(rows, [intent(), second])
    assert len(tr) == 1
    assert log["status"].tolist() == ["filled", "skipped_busy"]


def test_market_entry_uses_next_open_plus_slippage_and_r_target():
    rows = [FLAT, (100.0, 100.5, 99.5, 100.25), (100.25, 104.5, 100, 104.5)]
    tr, _ = run(rows, [intent(entry_type="market", entry=np.nan, stop=98.0, target=np.nan, placed=1)])
    t = tr.iloc[0]
    assert t["entry"] == 100.25                 # open 100 + 1 tick
    assert t["target"] == 104.75                # 100.25 + 2 x 2.25 risk -> 104.75
    assert t["exit_reason"] == "flatten" or t["exit_reason"] == "end_of_data" or t["exit_reason"] == "target"
