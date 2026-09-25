"""Strategies module (STRATEGIES.md): engine extensions, rules, and no lookahead."""

import numpy as np
import pandas as pd
import pytest

from mnqbt.backtest.engine import EngineSettings, Market, run_order
from mnqbt.data.build import combined_day_flags
from mnqbt.data.continuous import build_continuous
from mnqbt.data.synthetic import generate
from mnqbt.data.validate import clean
from mnqbt.reports.metrics import benjamini_hochberg, holm
from mnqbt.strategies import STRATEGIES
from mnqbt.strategies.benchmark import timed_r_net
from mnqbt.strategies.common import RTH_OPEN, Ctx, exchange_closures
from mnqbt.strategies.run import dev_frames, run_strategy
from mnqbt.timeutil import NS_PER_MIN, to_ns_index


@pytest.fixture(scope="module")
def data(cfg):
    raw = generate("2020-01-02", "2021-06-30", seed=1)   # a seed on which every strategy trades
    a, _, sched = build_continuous(raw["MNQ"], cfg, root="MNQ")
    b, _, _ = build_continuous(raw["MES"], cfg, root="MES", forced_schedule=sched)
    a, b = to_ns_index(clean(a)), to_ns_index(clean(b))
    return a, b, combined_day_flags(a, b, cfg)[0]


@pytest.fixture(scope="module")
def world(cfg, data):
    F, mk = dev_frames(cfg, *data)
    return Ctx(F, cfg), mk, EngineSettings.from_cfg(cfg)


def _market(prices, roll_at=None):
    idx = pd.date_range("2024-03-05 14:30", periods=len(prices), freq="1min", tz="UTC")
    p = np.asarray(prices, float)
    m1 = pd.DataFrame({"open": p, "high": p + 0.25, "low": p - 0.25, "close": p}, index=idx)
    rolls = [int(idx[roll_at].value)] if roll_at is not None else None
    return Market.from_frame(m1, rolls), idx


def test_no_stop_order_uses_its_risk_unit(cfg):
    st = EngineSettings.from_cfg(cfg)
    mk, idx = _market([100, 101, 102, 103, 104, 105])
    order = {"placed_ns": idx[1].value, "dir": 1, "expire_ns": idx[4].value, "flatten_ns": idx[4].value, "stop": np.nan,
             "target": np.nan, "entry_type": "market", "entry": np.nan, "target_src": "abs", "target_r": np.nan, "risk_unit": 20.0}
    _, t, _, _ = run_order(mk, st, order)
    entry, exit_ = 101 + st.tick, 104 - st.tick                     # 1 tick slippage each way
    pnl = (exit_ - entry) * st.point_value - 2 * st.commission_per_side
    assert t["exit_reason"] == "flatten" and t["rolls"] == 0
    assert t["r_net"] == pytest.approx(pnl / (20.0 * st.point_value))


def test_holding_across_a_roll_pays_a_close_and_reopen(cfg):
    st = EngineSettings.from_cfg(cfg)
    mk, idx = _market([100, 101, 102, 103, 104, 105], roll_at=3)
    order = {"placed_ns": idx[1].value, "dir": 1, "expire_ns": idx[4].value, "flatten_ns": idx[4].value, "stop": np.nan,
             "target": np.nan, "entry_type": "market", "entry": np.nan, "target_src": "abs", "target_r": np.nan, "risk_unit": 20.0}
    _, t, _, _ = run_order(mk, st, order)
    assert t["rolls"] == 1
    assert t["commission"] == pytest.approx(4 * st.commission_per_side)
    assert t["net_pts"] == pytest.approx((104 - st.tick) - (101 + st.tick) - 2 * st.tick)


def test_benchmark_fast_path_matches_the_engine(world):
    ctx, mk, st = world
    rng = np.random.default_rng(0)
    i0 = rng.integers(0, len(mk.ts) - 5000, 300)
    placed = mk.ts[i0]
    flat = mk.ts[i0 + rng.integers(1, 4000, 300)]
    d = rng.choice([-1, 1], 300)
    unit = rng.uniform(5, 50, 300)
    fast = timed_r_net(mk, st, placed, flat, d, unit)
    for k in range(300):
        order = {"placed_ns": int(placed[k]), "dir": int(d[k]), "expire_ns": int(flat[k]), "flatten_ns": int(flat[k]),
                 "stop": np.nan, "target": np.nan, "entry_type": "market", "entry": np.nan, "target_src": "abs",
                 "target_r": np.nan, "risk_unit": float(unit[k])}
        _, t, _, _ = run_order(mk, st, order)
        assert t["r_net"] == pytest.approx(fast[k])


# ---------------------------------------------------------------------------- rules
def _intents(ctx, name):
    s = next(x for x in STRATEGIES if x.name == name)
    return s.parts[0].build(ctx)


@pytest.mark.parametrize("minutes", [5, 15, 30])
def test_opening_range_rules(cfg, world, minutes):
    ctx, _, _ = world
    it = _intents(ctx, f"orb{minutes}")
    assert len(it)
    assert (ctx.et_minute(it["placed_ns"].to_numpy()) == RTH_OPEN + minutes).all()
    for _, r in it.sample(20, random_state=0).iterrows():
        t0 = ctx.at([r["tdate"]], RTH_OPEN)[0]
        m = (ctx.ts >= t0) & (ctx.ts < t0 + minutes * NS_PER_MIN)
        o, c = ctx.o[m][0], ctx.c[m][-1]
        assert r["dir"] == np.sign(c - o)
        assert r["stop"] == (ctx.l[m].min() if r["dir"] > 0 else ctx.h[m].max())
        assert r["target_r"] == 10.0 and r["target_src"] == "r_multiple"


def test_gap_fade_targets_the_previous_close_with_a_mirror_stop(world):
    ctx, _, _ = world
    it = _intents(ctx, "gap_fade")
    prev_close = ctx.close_of_bar(ctx.at(ctx.shift_days(pd.DatetimeIndex(it["tdate"]), -1), 15 * 60 + 59))
    op = ctx.open_of_bar(ctx.at(pd.DatetimeIndex(it["tdate"]), RTH_OPEN))
    assert np.allclose(it["target"], prev_close)
    assert np.allclose(it["stop"] - op, op - prev_close)
    assert (it["dir"] == -np.sign(op - prev_close)).all()
    assert (ctx.et_minute(it["placed_ns"].to_numpy()) == RTH_OPEN + 1).all()   # the open is known at 09:31


def test_vwap_trend_reverses_at_the_same_open(world):
    ctx, _, _ = world
    it = _intents(ctx, "vwap_trend")
    same_day = it["tdate"].to_numpy()[1:] == it["tdate"].to_numpy()[:-1]
    back_to_back = it["placed_ns"].to_numpy()[1:] == it["flatten_ns"].to_numpy()[:-1]
    assert (back_to_back[same_day] | (it["flatten_ns"].to_numpy()[:-1][same_day] < it["placed_ns"].to_numpy()[1:][same_day])).all()
    assert (it["dir"].to_numpy()[1:][same_day & back_to_back] == -it["dir"].to_numpy()[:-1][same_day & back_to_back]).all()
    assert np.isnan(it["stop"]).all() and np.allclose(it["risk_unit"], it["atr"])


def test_calendar_windows(world):
    ctx, _, _ = world
    tom = _intents(ctx, "turn_of_month").set_index("tdate")
    assert tom.at[pd.Timestamp("2021-01-28"), "exit_tdate"] == pd.Timestamp("2021-02-03")   # day -2 close -> day +3 close
    ph = _intents(ctx, "pre_holiday").set_index("tdate")
    assert ph.at[pd.Timestamp("2020-11-24"), "exit_tdate"] == pd.Timestamp("2020-11-25")    # Thanksgiving 2020-11-26
    assert (ctx.et_minute(ph["flatten_ns"].to_numpy()) <= 16 * 60).all()


def test_saturday_new_year_is_not_a_closure():
    closed = exchange_closures(2021, 2023)
    assert pd.Timestamp("2021-12-31") not in closed and pd.Timestamp("2022-12-26") in closed
    assert pd.Timestamp("2022-01-01") not in closed and pd.Timestamp("2023-01-02") in closed


def test_holm_and_benjamini_hochberg():
    p = np.array([0.01, 0.04, 0.03, 0.005, np.nan])
    assert np.allclose(holm(p)[:4], [0.03, 0.06, 0.06, 0.02]) and np.isnan(holm(p)[4])
    assert np.allclose(benjamini_hochberg(p)[:4], [0.02, 0.04, 0.04, 0.02])


def test_trades_stay_inside_the_loaded_period(world):
    ctx, mk, st = world
    for s in STRATEGIES:
        t = run_strategy(s, ctx, mk, st)
        assert t.empty or (t["exit_ns"].max() <= mk.ts[-1] and pd.DatetimeIndex(t["exit_tdate"]).max() <= ctx.last_day)


# ---------------------------------------------------------------------------- no lookahead
DECISION = ["dir", "stop", "target", "target_r", "risk_unit", "ref_price"]


def _builders():
    seen, out = set(), []
    for s in STRATEGIES:
        for part in s.parts:
            key = (getattr(part.build, "func", part.build), tuple(sorted(getattr(part.build, "keywords", {}).items())))
            if key not in seen:
                seen.add(key)
                out.append((s.name, part.build))
    return out


def test_every_decision_is_reproducible_from_data_before_placement(cfg, data, world):
    """Cut the data exactly at an order's placement time (keep only bars that STARTED before it),
    rebuild everything, and the same order must come out.  Day flags come from the full data
    (calendar / data-quality inputs, as in tests/test_no_lookahead.py)."""
    a, b, flags = data
    ctx, _, _ = world
    checked = 0
    for name, fn in _builders():
        full = fn(ctx)
        assert not full.empty, f"{name} has no orders on the test data, so it would go unchecked"
        for k in np.unique(np.linspace(len(full) // 3, len(full) - 1, 2).astype(int)):
            row = full.iloc[k]
            cut = pd.Timestamp(int(row["placed_ns"]), tz="UTC")
            F_t, _ = dev_frames(cfg, a[a.index < cut], b[b.index < cut], flags)
            trunc = fn(Ctx(F_t, cfg))
            match = trunc[trunc["placed_ns"] == row["placed_ns"]]
            assert len(match) == 1, f"{name}: order at {cut} not reproducible from data before it"
            pd.testing.assert_series_equal(match.iloc[0][DECISION], row[DECISION], check_names=False, obj=name)
            checked += 1
    assert checked >= 20
