"""No-lookahead: deleting the future must not change anything that was knowable before it.

Every feature table carries the time each row becomes known.  We compute all
of them on the full series and again on the series truncated at many random
intraday times T; every row known at or before T must be identical.  This is
verified to catch injected bugs such as "swing known at the swing bar",
"FVG known at the third candle's open" and "SMT peeks at later MES bars"
(see the mutation check described in README.md).

A second family runs the strategy on a pure random walk, where no rule can
have an edge: gross R must not be significantly positive.  The market-entry
variant (no FVG) is included because it trades right at the trigger and so is
the most sensitive to trigger-timing lookahead.
"""

import numpy as np
import pandas as pd
import pytest

from mnqbt.backtest.engine import EngineSettings, Market, simulate
from mnqbt.config import VARIANTS_CONFIG, apply_overrides, load_yaml
from mnqbt.data.build import combined_day_flags
from mnqbt.data.continuous import build_continuous
from mnqbt.data.synthetic import generate
from mnqbt.data.validate import clean
from mnqbt.reports.metrics import bootstrap_mean_ci
from mnqbt.rules.features import Features
from mnqbt.rules.setups import build_intents
from mnqbt.rules.swings import swings
from mnqbt.timeutil import NS_PER_MIN, ns, to_ns_index

rng = np.random.default_rng(42)
_minutes = rng.integers(0, 80 * 1440, size=15)
CUTS = [pd.Timestamp("2021-02-15", tz="UTC") + pd.Timedelta(minutes=int(m)) for m in _minutes]


def _series(cfg, start, end, seed):
    raw = generate(start, end, seed=seed)
    a, _, sched = build_continuous(raw["MNQ"], cfg, root="MNQ")
    b, _, _ = build_continuous(raw["MES"], cfg, root="MES", forced_schedule=sched)
    return to_ns_index(clean(a)), to_ns_index(clean(b))


def _features(cfg, a, b):
    return Features(cfg, a, b, combined_day_flags(a, b, cfg)[0])


def _variant(cfg, name):
    v = load_yaml(VARIANTS_CONFIG)
    if name == "full":
        return apply_overrides(cfg, v["full"])
    if name == "no_fvg":
        return apply_overrides(apply_overrides(cfg, v["full"]), v["remove_one"]["no_fvg"])
    if name == "baseline_no_fvg":
        return apply_overrides(cfg, {"setup.require.fvg": False})
    if name == "liquidity":
        return apply_overrides(cfg, v["add_one"]["liquidity_target"])
    return cfg


@pytest.fixture(scope="module")
def series(cfg):
    return _series(cfg, "2021-01-04", "2021-05-28", 11)


@pytest.fixture(scope="module")
def full_features(cfg, series):
    return _features(cfg, *series)


def _known_before(df, col, cut):
    return df[df[col] <= cut].reset_index(drop=True)


@pytest.mark.parametrize("cut", CUTS, ids=[c.strftime("%m%d-%H%M") for c in CUTS])
def test_every_feature_is_prefix_invariant(cfg, series, full_features, cut):
    a, b = series
    full = full_features
    trunc = _features(cfg, a[a.index < cut], b[b.index < cut])
    c = cut.value

    for tf in ("5min", "15min", "60min"):
        pd.testing.assert_frame_equal(_known_before(swings(full.bars("a", tf), 2), "known_ns", c),
                                      _known_before(swings(trunc.bars("a", tf), 2), "known_ns", c))
    pd.testing.assert_frame_equal(_known_before(full.triggers(cfg), "known_ns", c), _known_before(trunc.triggers(cfg), "known_ns", c))
    for tf in ("5min", "15min"):
        fc = apply_overrides(cfg, {"rules.fvg.timeframe": tf})
        pd.testing.assert_frame_equal(_known_before(full.fvgs(fc), "known_ns", c), _known_before(trunc.fvgs(fc), "known_ns", c))
    pd.testing.assert_frame_equal(_known_before(full.structure(cfg), "known_ns", c), _known_before(trunc.structure(cfg), "known_ns", c))
    pd.testing.assert_frame_equal(_known_before(full.chop(cfg), "known_ns", c), _known_before(trunc.chop(cfg), "known_ns", c))

    # level table rows are known at their bar's START
    lf, lt = full.levels(cfg, "5min"), trunc.levels(cfg, "5min")
    sf = full.bars("a", "5min")["start_ns"].to_numpy()
    keep = sf < c  # a bar starting exactly at the cut has no data in the truncated series
    pd.testing.assert_frame_equal(lf[keep].reset_index(drop=True), lt.iloc[: keep.sum()].reset_index(drop=True))

    # VWAP at a 1m bar is known at that bar's close
    vf, vt = full.vwap(cfg), trunc.vwap(cfg)
    k = int(((ns(full.a1.index) + NS_PER_MIN) <= c).sum())
    np.testing.assert_array_equal(vf[:k], vt[:k])

    # daily context: every "prior" column of every date up to the cut day
    df_, dt_ = full.daily(cfg), trunc.daily(cfg)
    cols = ["atr", "pdh", "pdl", "vol_ratio", "vol_state", "vah_prior", "val_prior", "poc_prior"]
    pd.testing.assert_frame_equal(df_.loc[dt_.index, cols], dt_[cols])


@pytest.mark.parametrize("name", ["baseline", "full", "no_fvg", "liquidity"])
def test_intents_and_trades_are_prefix_invariant(cfg, series, name):
    cv = _variant(cfg, name)
    a, b = series
    full = _features(cv, a, b)
    fi, _ = build_intents(full, cv)
    st = EngineSettings.from_cfg(cv)
    ft, _ = simulate(Market.from_frame(full.a1), fi, st)
    cols = ["placed_ns", "dir", "entry", "stop", "target", "risk", "level", "smt", "vol_state", "chop", "structure",
            "vwap", "va_loc", "fvg_top", "fvg_bottom", "target_src", "session"]
    for cut in CUTS[:6]:
        trunc = _features(cv, a[a.index < cut], b[b.index < cut])
        ti, _ = build_intents(trunc, cv)
        # the cut day itself may be flagged differently (it is incomplete), so compare earlier days
        cut_day = pd.Timestamp(cut.tz_convert("America/New_York").date())
        fa = fi[(fi["tdate"] < cut_day) & (fi["placed_ns"] <= cut.value)].reset_index(drop=True)
        ta = ti[(ti["tdate"] < cut_day) & (ti["placed_ns"] <= cut.value)].reset_index(drop=True)
        pd.testing.assert_frame_equal(fa[cols], ta[cols])
        tt, _ = simulate(Market.from_frame(trunc.a1), ti, st)
        # Day-level tradeable flags use the whole day (holiday half-days are pre-announced, so this is
        # equivalent to a calendar lookup), so the incomplete cut day is excluded from the comparison.
        done = lambda t: t[(t["exit_ns"] < cut.value - NS_PER_MIN) & (t["tdate"] < cut_day)][  # noqa: E731
            ["fill_ns", "exit_ns", "entry", "exit_price", "r_net"]].reset_index(drop=True)
        pd.testing.assert_frame_equal(done(ft), done(tt))


@pytest.mark.parametrize("name", ["baseline", "full", "no_fvg", "liquidity"])
def test_each_order_is_reproducible_from_data_before_its_placement(cfg, series, name):
    """The strongest form: cut the data exactly at an order's placement time (keep only bars that
    STARTED before it) and rebuild everything — the same order must come out, field for field.
    Day flags are taken from the full data (they are calendar/data-quality inputs, see README)."""
    cv = _variant(cfg, name)
    a, b = series
    flags = combined_day_flags(a, b, cv)[0]
    full = Features(cv, a, b, flags)
    fi, _ = build_intents(full, cv)
    cols = ["placed_ns", "dir", "entry", "stop", "target", "risk", "level", "smt", "vol_state", "chop", "structure",
            "vwap", "va_loc", "fvg_top", "fvg_bottom", "target_src", "session", "news_day"]
    sample = fi.iloc[np.linspace(0, len(fi) - 1, 10).astype(int)]
    for _, row in sample.iterrows():
        cut = pd.Timestamp(int(row["placed_ns"]), tz="UTC")
        trunc = Features(cv, a[a.index < cut], b[b.index < cut], flags)
        ti, _ = build_intents(trunc, cv)
        match = ti[(ti["placed_ns"] == row["placed_ns"]) & (ti["trig_known_ns"] == row["trig_known_ns"])]
        assert len(match) == 1, f"order placed at {cut} not reproducible from data before it"
        pd.testing.assert_series_equal(match.iloc[0][cols], row[cols], check_names=False)


@pytest.mark.slow
@pytest.mark.parametrize("name", ["baseline", "baseline_no_fvg"])
def test_random_walk_shows_no_edge_before_costs(cfg, name):
    cv = _variant(cfg, name)
    F = _features(cv, *_series(cv, "2018-01-02", "2020-12-31", 3))
    it, _ = build_intents(F, cv)
    tr, _ = simulate(Market.from_frame(F.a1), it, EngineSettings.from_cfg(cv))
    assert len(tr) > 300
    lo, hi = bootstrap_mean_ci(tr["r_gross"].to_numpy(), 2000, 0.99)
    # A martingale cannot be beaten: gross R must not be significantly positive.
    assert lo < 0.0, f"gross R 99% CI [{lo:.3f}, {hi:.3f}] is entirely positive on a random walk -> lookahead?"
    assert tr["r_net"].mean() < 0.05


@pytest.mark.slow
def test_matched_random_benchmark_does_not_reject_on_a_random_walk(cfg, series):
    """On a martingale the signal is worthless, so the matched benchmark must not call it significant."""
    from mnqbt.backtest.random_bench import random_benchmark
    from mnqbt.reports.metrics import enrich

    F = _features(cfg, *series)
    it, _ = build_intents(F, cfg)
    st = EngineSettings.from_cfg(cfg)
    tr, _ = simulate(Market.from_frame(F.a1), it, st)
    bm = random_benchmark(F, cfg, enrich(tr), "2021-01-01", "2021-12-31", 60, st, seed=3)
    assert len(bm["dist"]) == 60
    assert bm["p_value"] > 0.02
    assert bm["bench_p05"] < bm["strategy"] + 0.25  # strategy is not far outside the random band
