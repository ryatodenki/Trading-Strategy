"""PATTERNS.md hypotheses: rule definitions, no lookahead, statistics (synthetic data only)."""

import numpy as np
import pandas as pd
import pytest

from mnqbt.backtest.engine import EngineSettings, Market, run_order
from mnqbt.data.build import combined_day_flags
from mnqbt.data.continuous import build_continuous
from mnqbt.data.synthetic import generate
from mnqbt.data.validate import clean
from mnqbt.strategies.common import RTH_OPEN, Ctx
from mnqbt.strategies.explore import bootstrap_diff, deflated_sharpe, passed
from mnqbt.strategies.patterns import R_ATR, RULES, _tod, daily_trend
from mnqbt.strategies.run import dev_frames
from mnqbt.timeutil import NS_PER_MIN, to_ns_index


@pytest.fixture(scope="module")
def data(cfg):
    raw = generate("2020-01-02", "2020-12-31", seed=2)
    a, _, sched = build_continuous(raw["MNQ"], cfg, root="MNQ")
    b, _, _ = build_continuous(raw["MES"], cfg, root="MES", forced_schedule=sched)
    a, b = to_ns_index(clean(a)), to_ns_index(clean(b))
    return a, b, combined_day_flags(a, b, cfg)[0]


@pytest.fixture(scope="module")
def ctx(cfg, data):
    F, _ = dev_frames(cfg, *data, end="2100-01-01")
    return Ctx(F, cfg)


def _rule(hid):
    return next(h for h in RULES if h.id == hid)


def test_every_rule_measures_r_in_a_tenth_of_atr(ctx):
    for h in RULES:
        it = h.build(ctx)
        assert len(it), h.id
        assert np.allclose(it["risk_unit"], R_ATR * it["atr"]), h.id


@pytest.mark.parametrize("hid, frm, to, entry, sign", [("H1", RTH_OPEN, RTH_OPEN + 5, RTH_OPEN + 5, 1),
                                                         ("H2", 180, RTH_OPEN, RTH_OPEN, 1),
                                                         ("H3", RTH_OPEN, 720, 720, -1),
                                                         ("H4", RTH_OPEN, 900, 900, 1)])
def test_time_of_day_rules(ctx, hid, frm, to, entry, sign):
    it = _rule(hid).build(ctx)
    td = pd.DatetimeIndex(it["tdate"])
    o, c = ctx.open_of_bar(ctx.at(td, frm)), ctx.close_of_bar(ctx.at(td, to - 1))
    assert (it["dir"].to_numpy() == sign * np.sign(c - o)).all()
    assert (ctx.et_minute(it["placed_ns"].to_numpy()) == entry).all()
    assert np.isnan(it["stop"]).all()


@pytest.mark.parametrize("hid, cols, known, window", [("H5", ("asia_h", "asia_l"), 180, (180, 720)),
                                                       ("H6", ("london_h", "london_l"), RTH_OPEN, (RTH_OPEN, 900)),
                                                       ("H7", ("pdh", "pdl"), 18 * 60, (180, 900))])
def test_sweep_rules(ctx, hid, cols, known, window):
    """Each sweep trade: the bar before entry is the day's first trade-through of the level after it is
    known, starts inside the window, closes back inside; stop 1 tick beyond it; out within 60 minutes."""
    it = _rule(hid).build(ctx)
    assert len(it) > 10
    bars, lv = ctx.F.bars("a", "5min"), ctx.F.levels(ctx.cfg, "5min")
    start = bars["start_ns"].to_numpy(np.int64)
    tod = _tod(ctx.et_minute(start))
    day = pd.DatetimeIndex(bars["tdate"].to_numpy())
    for _, r in it.iterrows():
        k = int(np.searchsorted(start, r["placed_ns"] - 5 * NS_PER_MIN))
        short = r["dir"] < 0
        L = lv[cols[0] if short else cols[1]].to_numpy(float)
        same = np.flatnonzero((day == day[k]) & (tod >= _tod(known)))
        thr = same[(bars["high"].to_numpy()[same] >= L[same] + ctx.tick) if short else (bars["low"].to_numpy()[same] <= L[same] - ctx.tick)]
        assert thr[0] == k                                                     # first trade-through that day
        assert _tod(window[0]) <= tod[k] < _tod(window[1])
        if short:
            assert bars["close"].iat[k] < L[k] and r["stop"] == bars["high"].iat[k] + ctx.tick
        else:
            assert bars["close"].iat[k] > L[k] and r["stop"] == bars["low"].iat[k] - ctx.tick
        assert r["flatten_ns"] - r["placed_ns"] <= 60 * NS_PER_MIN


def test_every_decision_is_reproducible_from_data_before_placement(cfg, data, ctx):
    a, b, flags = data
    checked = 0
    for h in RULES:
        full = h.build(ctx)
        for k in np.unique(np.linspace(len(full) // 3, len(full) - 1, 2).astype(int)):
            row = full.iloc[k]
            cut = pd.Timestamp(int(row["placed_ns"]), tz="UTC")
            F_t, _ = dev_frames(cfg, a[a.index < cut], b[b.index < cut], flags, end="2100-01-01")
            trunc = h.build(Ctx(F_t, cfg))
            match = trunc[(trunc["placed_ns"] == row["placed_ns"]) & (trunc["dir"] == row["dir"])]
            assert len(match) == 1, f"{h.id}: order at {cut} not reproducible from data before it"
            pd.testing.assert_series_equal(match.iloc[0][["stop", "risk_unit", "ref_price"]], row[["stop", "risk_unit", "ref_price"]],
                                           check_names=False, obj=h.id)
            checked += 1
    assert checked == 2 * len(RULES)


def test_daily_trend_uses_only_earlier_closes(ctx):
    t = daily_trend(ctx)
    days = ctx.trading_days()
    closes = pd.Series(ctx.close_of_bar(ctx.at(days, 15 * 60 + 59)), index=days).dropna()
    d = t.dropna().index[5]
    prev = closes[closes.index < d]
    assert t[d] == np.sign(prev.iloc[-1] - prev.iloc[-50:].mean())


def test_order_risk_unit_sets_r_even_with_a_stop(cfg):
    st = EngineSettings.from_cfg(cfg)
    idx = pd.date_range("2024-03-05 14:30", periods=6, freq="1min", tz="UTC")
    p = np.array([100, 101, 102, 103, 104, 105], float)
    mk = Market.from_frame(pd.DataFrame({"open": p, "high": p + 0.25, "low": p - 0.25, "close": p}, index=idx))
    order = {"placed_ns": idx[1].value, "dir": 1, "expire_ns": idx[4].value, "flatten_ns": idx[4].value, "stop": 90.0,
             "target": np.nan, "entry_type": "market", "entry": np.nan, "target_src": "abs", "target_r": np.nan, "risk_unit": 4.0}
    _, t, _, _ = run_order(mk, st, order)
    assert t["risk_pts"] == 4.0 and t["r_net"] == pytest.approx(t["pnl_usd"] / (4.0 * st.point_value))


def test_bootstrap_diff_and_deflated_sharpe():
    rng = np.random.default_rng(0)
    days = np.repeat(pd.date_range("2020-01-01", periods=400), 3).values
    in_a = np.tile([True, True, False], 400)
    r = rng.normal(0, 1, len(days)) + np.where(in_a, 0.3, 0.0)
    out = bootstrap_diff(r, in_a, days, reps=2000)
    assert out["delta"] > 0 and out["ci_low"] > 0 and out["p"] < 0.01
    null = bootstrap_diff(rng.normal(0, 1, len(days)), in_a, days, reps=2000)
    assert null["p"] > 0.01
    x = rng.normal(0.1, 1, 2000)
    srs = rng.normal(0, 0.05, 7)
    assert 0.0 <= deflated_sharpe(x, srs) <= 1.0
    assert deflated_sharpe(x, srs * 3) < deflated_sharpe(x, srs)   # more spread across trials = more deflation


def test_later_stages_only_take_the_latest_passes():
    log = pd.DataFrame([{"stage": "explore", "time_utc": "2026-01-01T00:00:00", "hypothesis": "H3", "passed": True},
                        {"stage": "explore", "time_utc": "2026-01-02T00:00:00", "hypothesis": "H3", "passed": False},
                        {"stage": "explore", "time_utc": "2026-01-02T00:00:00", "hypothesis": "H8", "passed": True}])
    assert passed(log, "explore") == ["H8"] and passed(log, "validate") == []
