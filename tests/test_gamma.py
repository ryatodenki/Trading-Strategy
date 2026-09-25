"""GAMMA.md hypotheses: gamma timing, rule definitions, trailing stops, no lookahead, runner (synthetic data only)."""

import numpy as np
import pandas as pd
import pytest

from mnqbt.backtest.engine import EngineSettings, Market, run_order, simulate
from mnqbt.config import get, resolve_dist
from mnqbt.data.build import combined_day_flags
from mnqbt.data.continuous import build_continuous
from mnqbt.data.gex import gamma_regime, load_gex
from mnqbt.data.synthetic import generate
from mnqbt.data.validate import clean
from mnqbt.rules.fvg import detect_fvgs, entry_price
from mnqbt.rules.swings import swings
from mnqbt.strategies.benchmark import random_benchmark
from mnqbt.strategies.common import Ctx
from mnqbt.strategies.explore import World, passed
from mnqbt.strategies.gamma import BY_ID, HYPOTHESES, TARGET_LEVELS, breakout
from mnqbt.strategies.gamma_run import GammaWorld, _test_split, stage_report
from mnqbt.strategies.patterns import BY_ID as H, R_ATR, _tod
from mnqbt.strategies.run import dev_frames, run_each
from mnqbt.strategies.vwap import vwap_trend
from mnqbt.timeutil import NS_PER_MIN, to_ns_index


@pytest.fixture(scope="module")
def data(cfg):
    raw = generate("2020-01-02", "2020-12-31", seed=2)
    a, _, sched = build_continuous(raw["MNQ"], cfg, root="MNQ")
    b, _, _ = build_continuous(raw["MES"], cfg, root="MES", forced_schedule=sched)
    a, b = to_ns_index(clean(a)), to_ns_index(clean(b))
    return a, b, combined_day_flags(a, b, cfg)[0]


@pytest.fixture(scope="module")
def world(cfg, data):
    F, mk = dev_frames(cfg, *data, end="2100-01-01")
    return Ctx(F, cfg), mk


@pytest.fixture(scope="module")
def ctx(world):
    return world[0]


@pytest.fixture(scope="module")
def gex(ctx):
    """Synthetic GEX on cash dates: sign blocks of 10 trading days, ~30% negative."""
    days = ctx.trading_days()
    rng = np.random.default_rng(0)
    sign = np.repeat(rng.choice([-1.0, 1.0], size=len(days) // 10 + 1, p=[0.3, 0.7]), 10)[:len(days)]
    return pd.Series(sign * rng.uniform(1e8, 5e9, len(days)), index=days)


@pytest.fixture(scope="module")
def regime(ctx, gex):
    return gamma_regime(gex, ctx.trading_days())


def _build(h, ctx, regime, swap=False):
    return h.build(ctx, regime, swap) if h.matched == 0 else h.build(ctx)


# ---------------------------------------------------------------------------- gamma timing
def test_regime_uses_only_gex_dated_before_the_day():
    gex = pd.Series([2e9, -1e9, 0.0, 3e9], index=pd.to_datetime(["2021-03-01", "2021-03-02", "2021-03-03", "2021-03-05"]))
    days = pd.to_datetime(["2021-03-01", "2021-03-02", "2021-03-03", "2021-03-04", "2021-03-05", "2021-03-08", "2021-03-12",
                           "2021-03-15"])
    r = gamma_regime(gex, days)
    assert np.isnan(r["2021-03-01"])                  # nothing published before the first date
    assert r["2021-03-02"] == 1                       # uses 03-01, not its own -1
    assert r["2021-03-03"] == -1                      # uses 03-02
    assert np.isnan(r["2021-03-04"])                  # 03-03 was exactly 0: no regime
    assert np.isnan(r["2021-03-05"])                  # latest before is 03-03 (0), not its own 3e9
    assert r["2021-03-08"] == 1                       # over the weekend: 03-05
    assert r["2021-03-12"] == 1                       # 7 days old: still used
    assert np.isnan(r["2021-03-15"])                  # 10 days old: stale


def test_regime_is_prefix_invariant(ctx, gex):
    days = ctx.trading_days()
    full = gamma_regime(gex, days)
    for cut in days[[40, 120, 200]]:
        part = gamma_regime(gex[gex.index <= cut], days[days <= cut])
        pd.testing.assert_series_equal(part, full[days <= cut])


def test_load_gex_reads_the_csv_and_cuts_at_the_end(tmp_path, cfg):
    f = tmp_path / "DIX.csv"
    f.write_text("date,price,dix,gex\n2011-05-02,1361.2,0.37,1.9e9\n2011-05-03,1356.6,0.40,-2.5e8\n2011-05-04,1347.3,0.41,1.1e9\n")
    g = load_gex(cfg, end="2011-05-03", path=f)
    assert list(g.index.strftime("%Y-%m-%d")) == ["2011-05-02", "2011-05-03"] and g.iloc[1] == -2.5e8


# ---------------------------------------------------------------------------- rules
def test_every_rule_measures_r_in_a_tenth_of_atr(ctx, regime):
    for h in HYPOTHESES:
        it = _build(h, ctx, regime)
        assert len(it) > 5, h.id
        assert np.allclose(it["risk_unit"].astype(float), R_ATR * it["atr"].astype(float)), h.id


def test_g1_is_the_sweep_rule_on_prior_day_value_area(ctx):
    it = BY_ID["G1"].build(ctx)
    bars, lv = ctx.F.bars("a", "5min"), ctx.F.levels(ctx.cfg, "5min")
    start = bars["start_ns"].to_numpy(np.int64)
    tod = _tod(ctx.et_minute(start))
    day = pd.DatetimeIndex(bars["tdate"].to_numpy())
    daily = ctx.F.daily(ctx.cfg)
    for _, r in it.iterrows():
        k = int(np.searchsorted(start, r["placed_ns"] - 5 * NS_PER_MIN))
        short = r["dir"] < 0
        col = "vah" if short else "val"
        L = lv[col].to_numpy(float)
        assert L[k] == daily[col + "_prior"][day[k]]                          # the prior full day's value area
        same = np.flatnonzero((day == day[k]) & (tod >= 0))
        hit = (bars["high"].to_numpy()[same] >= L[same] + ctx.tick) if short else (bars["low"].to_numpy()[same] <= L[same] - ctx.tick)
        assert same[hit][0] == k                                             # first trade-through since 18:00
        assert _tod(180) <= tod[k] < _tod(900)
        if short:
            assert bars["close"].iat[k] < L[k] and r["stop"] == bars["high"].iat[k] + ctx.tick
        else:
            assert bars["close"].iat[k] > L[k] and r["stop"] == bars["low"].iat[k] - ctx.tick
        assert r["flatten_ns"] - r["placed_ns"] <= 60 * NS_PER_MIN


def test_g2_g3_g4_reuse_the_declared_rules_unchanged(ctx):
    g2 = BY_ID["G2"].build(ctx)
    pooled = pd.concat([H[i].build(ctx) for i in ("H5", "H6", "H7")], ignore_index=True)
    key = ["placed_ns", "dir", "stop", "flatten_ns", "risk_unit"]
    pd.testing.assert_frame_equal(g2[key].sort_values(key).reset_index(drop=True), pooled[key].sort_values(key).reset_index(drop=True))
    assert (np.diff(g2["placed_ns"].to_numpy()) >= 0).all()
    pd.testing.assert_frame_equal(BY_ID["G3"].build(ctx), H["H1"].build(ctx))
    g4, v = BY_ID["G4"].build(ctx), vwap_trend(ctx)
    pd.testing.assert_frame_equal(g4.drop(columns="risk_unit"), v.drop(columns="risk_unit"))
    assert BY_ID["G2"].mode == "single" and BY_ID["G1"].mode == "single"


def _g5_reference(ctx, regime, days) -> list[dict]:
    """GAMMA.md G5 re-derived bar by bar, straight from the text (slow; limited to ``days``)."""
    F, cfg, tick = ctx.F, ctx.cfg, ctx.tick
    b5, b15 = F.bars("a", "5min"), F.bars("a", "15min")
    start, end = b5["start_ns"].to_numpy(np.int64), b5["known_ns"].to_numpy(np.int64)
    c = b5["close"].to_numpy(float)
    lo, hi = b5["low"].to_numpy(float), b5["high"].to_numpy(float)
    day = pd.DatetimeIndex(b5["tdate"].to_numpy())
    tod = _tod(ctx.et_minute(start))
    atr = F.atr_for(cfg, b5)
    lv = F.levels(cfg, "5min")
    sw = swings(b5, 2)
    SW = {kind: sw[sw["kind"] == kind].sort_values("known_ns") for kind in (1, -1)}
    fc = get(cfg, "rules.fvg")
    fv5 = detect_fvgs(b5, "5min", resolve_dist(fc["min_size"], F.atr_for(cfg, b5)), 12, True)
    fv15 = detect_fvgs(b15, "15min", resolve_dist(fc["min_size"], F.atr_for(cfg, b15)), 12, True)
    sc = get(cfg, "setup.stop")
    flat_day = F.flatten_ns(cfg)
    out = []
    for k in np.flatnonzero(day.isin(days)):
        if k == 0 or day[k - 1] != day[k] or not (_tod(180) <= tod[k] < _tod(900)):
            continue
        g = regime.get(day[k], np.nan)
        if not ctx.can_enter(day[k:k + 1])[0] or not np.isfinite(g):
            continue
        hs = SW[1][SW[1]["known_ns"] <= start[k]]["price"].to_numpy()
        ls = SW[-1][SW[-1]["known_ns"] <= start[k]]["price"].to_numpy()
        if len(hs) < 2 or len(ls) < 2:
            continue
        for d in (1, -1):
            same, other = (hs, ls) if d > 0 else (ls, hs)
            if not (d * same[-1] > d * same[-2] and d * other[-1] > d * other[-2]):
                continue
            pdl = lv["pdh" if d > 0 else "pdl"].iat[k]
            crossed = [L for L in (same[-1], pdl) if np.isfinite(L) and d * c[k] > d * L and d * c[k - 1] <= d * L]
            if not crossed:
                continue
            t = end[k]
            a15 = fv15[(fv15["dir"] == d) & (fv15["known_ns"] <= t) & (fv15["expire_ns"] > t) & (fv15["tdate"] == day[k])]
            f5 = fv5[(fv5["dir"] == d) & (fv5["known_ns"] <= t)]
            if a15.empty or f5.empty:
                continue
            z = f5.sort_values("known_ns", kind="stable").iloc[-1]
            if not (z["expire_ns"] > t and pd.Timestamp(z["tdate"]) == day[k]):
                continue
            e = float(entry_price(np.array([z["top"]]), np.array([z["bottom"]]), np.array([d]), 0.5, tick)[0])
            seg = slice(int(z["c3_pos"]) + 1, k + 1)
            if (lo[seg] <= e).any() if d > 0 else (hi[seg] >= e).any():
                continue
            buf = float(resolve_dist(sc["buffer"], atr[k]))
            stop = np.floor((other[-1] - buf) / tick + 1e-9) * tick if d > 0 else np.ceil((other[-1] + buf) / tick - 1e-9) * tick
            risk = d * (e - stop)
            if not (risk > 0 and resolve_dist(sc["min_risk"], atr[k]) <= risk <= resolve_dist(sc["max_risk"], atr[k])):
                continue
            row = {"placed_ns": int(t), "dir": d, "entry": e, "stop": stop, "regime": int(g)}
            if g > 0:
                lvls = lv[TARGET_LEVELS[d]].iloc[k].to_numpy(float)
                beyond = lvls[np.isfinite(lvls) & (d * lvls > d * (e + d * risk))]
                raw = (beyond.min() if d > 0 else beyond.max()) if len(beyond) else e + 2 * d * risk
                row["target"] = np.ceil(raw / tick - 1e-9) * tick if d > 0 else np.floor(raw / tick + 1e-9) * tick
                row["trail_ns"] = []
            else:
                row["target"] = np.nan
                opp = SW[-d]
                later = opp[(opp["known_ns"] > t) & (opp["known_ns"] < flat_day[day[k]])]
                row["trail_ns"] = later["known_ns"].tolist()
                p = later["price"].to_numpy(float)
                row["trail_px"] = (np.floor((p - buf) / tick + 1e-9) * tick if d > 0 else np.ceil((p + buf) / tick - 1e-9) * tick).tolist()
            out.append(row)
    return out


def test_g5_finds_exactly_the_setups_the_text_describes(ctx, regime):
    it = breakout(ctx, regime)
    days = pd.DatetimeIndex(sorted(set(it["tdate"])))[:60]
    ref = _g5_reference(ctx, regime, days)
    got = it[it["tdate"].isin(days)].reset_index(drop=True)
    assert len(ref) >= 20 and len(got) == len(ref)
    ref = sorted(ref, key=lambda r: (r["placed_ns"], r["dir"]))
    for r, (_, g) in zip(ref, got.iterrows()):
        assert (g["placed_ns"], g["dir"], g["regime"]) == (r["placed_ns"], r["dir"], r["regime"])
        assert g["entry"] == pytest.approx(r["entry"]) and g["stop"] == pytest.approx(r["stop"])
        assert (np.isnan(g["target"]) and np.isnan(r["target"])) or g["target"] == pytest.approx(r["target"])
        assert list(g["trail_ns"]) == r["trail_ns"]
        if r["trail_ns"]:
            assert np.allclose(g["trail_px"], r["trail_px"])
        assert g["exit_style"] == ("fixed" if r["regime"] > 0 else "trail")
        assert g["entry_type"] == "limit" and g["expire_ns"] <= g["placed_ns"] + 60 * NS_PER_MIN
    assert {"fixed", "trail"} <= set(got["exit_style"])


def test_g5_swap_keeps_entries_and_swaps_exits(ctx, regime):
    a, b = breakout(ctx, regime), breakout(ctx, regime, swap=True)
    key = ["placed_ns", "dir", "entry", "stop", "expire_ns", "regime"]
    pd.testing.assert_frame_equal(a[key], b[key])
    assert ((a["exit_style"] == "fixed") == (b["exit_style"] == "trail")).all()
    assert b.loc[b["regime"] > 0, "target"].isna().all() and b.loc[b["regime"] < 0, "target"].notna().all()


# ---------------------------------------------------------------------------- engine: trailing stop
def _mk(prices_low, prices_high):
    idx = pd.date_range("2024-03-05 14:30", periods=len(prices_low), freq="1min", tz="UTC")
    lo, hi = np.asarray(prices_low, float), np.asarray(prices_high, float)
    return idx, Market.from_frame(pd.DataFrame({"open": (lo + hi) / 2, "high": hi, "low": lo, "close": (lo + hi) / 2}, index=idx))


def test_trailing_stop_moves_only_when_known_and_never_loosens(cfg):
    st = EngineSettings.from_cfg(cfg)
    lo = [100, 100, 101, 103, 104, 102.5, 106, 107, 104.75, 110]
    idx, mk = _mk(lo, [x + 1 for x in lo])
    order = {"placed_ns": idx[1].value, "dir": 1, "expire_ns": idx[9].value, "flatten_ns": idx[9].value, "stop": 95.0,
             "target": np.nan, "entry_type": "market", "entry": np.nan, "target_src": "abs", "target_r": np.nan, "risk_unit": 4.0,
             "trail_ns": np.array([idx[0].value, idx[3].value, idx[6].value, idx[6].value + 30_000_000_000], np.int64),
             "trail_px": np.array([200.0, 102.0, 99.0, 105.0])}
    # idx[0] update is before the fill: ignored (it would stop out at once); 102 from bar 3; 99 looser: ignored;
    # 105 timed mid-bar 6 applies from bar 7.  Bar 5 (low 102.5) survives 102; bar 8 (low 104.75) hits 105.
    _, t, _, _ = run_order(mk, st, order)
    assert t["exit_reason"] == "stop" and t["exit_ns"] == idx[8].value
    assert t["exit_price"] == pytest.approx(min(mk.open[8], 105.0) - st.slippage_ticks_stop * st.tick)
    assert t["stop"] == 95.0 and t["stop_last"] == 105.0


def test_trailing_stop_short_and_gap_through(cfg):
    st = EngineSettings.from_cfg(cfg)
    hi = [100, 100, 99, 97, 96, 99.5]
    idx, mk = _mk([x - 1 for x in hi], hi)
    order = {"placed_ns": idx[1].value, "dir": -1, "expire_ns": idx[5].value + 60_000_000_000, "flatten_ns": idx[5].value + 60_000_000_000,
             "stop": 104.0, "target": np.nan, "entry_type": "market", "entry": np.nan, "target_src": "abs", "target_r": np.nan,
             "risk_unit": 4.0, "trail_ns": np.array([idx[4].value], np.int64), "trail_px": np.array([98.0])}
    _, t, _, _ = run_order(mk, st, order)
    assert t["exit_ns"] == idx[5].value and t["exit_reason"] == "stop"
    assert t["exit_price"] == pytest.approx(max(mk.open[5], 98.0) + st.tick)   # opened above the stop: filled at the open


def test_no_trail_means_the_old_behaviour(cfg, ctx, world, regime):
    mk = world[1]
    st = EngineSettings.from_cfg(cfg)
    it = breakout(ctx, regime)
    fixed = it[it["exit_style"] == "fixed"].drop(columns=["trail_ns", "trail_px"])
    a = simulate(mk, fixed, st)[0]
    b = simulate(mk, it[it["exit_style"] == "fixed"], st)[0]
    pd.testing.assert_series_equal(a["r_net"], b["r_net"])
    assert (a["stop_last"] == a["stop"]).all()


# ---------------------------------------------------------------------------- no lookahead
def test_every_decision_is_reproducible_from_data_before_placement(cfg, data, ctx, regime):
    a, b, flags = data
    checked = 0
    for h in HYPOTHESES:
        full = _build(h, ctx, regime)
        for k in np.unique(np.linspace(len(full) // 3, len(full) - 1, 3).astype(int)):
            row = full.iloc[k]
            cut = pd.Timestamp(int(row["placed_ns"]), tz="UTC")
            F_t, _ = dev_frames(cfg, a[a.index < cut], b[b.index < cut], flags, end="2100-01-01")
            trunc = _build(h, Ctx(F_t, cfg), regime)
            same = (trunc["placed_ns"] == row["placed_ns"]) & (trunc["dir"] == row["dir"])
            if "level" in trunc:                                  # G2 pools levels: two sweeps can share a minute
                same &= trunc["level"] == row["level"]
            match = trunc[same]
            assert len(match) == 1, f"{h.id}: order at {cut} not reproducible from data before it"
            cols = ["stop", "risk_unit", "ref_price"] + (["entry", "target", "expire_ns", "exit_style"] if h.matched == 0 else [])
            pd.testing.assert_series_equal(match.iloc[0][cols], row[cols], check_names=False, obj=h.id)
            checked += 1
    assert checked >= 2 * len(HYPOTHESES)


def test_trailing_updates_known_by_a_time_do_not_change_with_later_data(cfg, data, ctx, regime):
    a, b, flags = data
    full = breakout(ctx, regime)
    trail = full[full["trail_ns"].map(len) >= 2]
    assert len(trail) >= 3
    for _, row in trail.iloc[[0, len(trail) // 2, -1]].iterrows():
        t_cut = int(row["trail_ns"][1])                          # after the 2nd update became known
        cut = pd.Timestamp(t_cut, tz="UTC")
        F_t, _ = dev_frames(cfg, a[a.index < cut], b[b.index < cut], flags, end="2100-01-01")
        trunc = breakout(Ctx(F_t, cfg), regime)
        m = trunc[(trunc["placed_ns"] == row["placed_ns"]) & (trunc["dir"] == row["dir"])].iloc[0]
        known = row["trail_ns"] <= t_cut
        assert list(m["trail_ns"]) == list(row["trail_ns"][known])
        assert np.allclose(m["trail_px"], row["trail_px"][known])


# ---------------------------------------------------------------------------- runner and log
@pytest.fixture(scope="module")
def explore_res(cfg, world, regime):
    ctx, mk = world
    w = World(ctx, mk, EngineSettings.from_cfg(cfg), ctx.first_day, ctx.last_day, "MNQ", "explore")
    return _test_split(cfg, GammaWorld(w, regime), [h.id for h in HYPOTHESES], "explore", reps=10, holm_on_contrasts=True, bench=False)


def test_explore_family_is_ten_tests_and_report_renders(explore_res):
    res = explore_res
    assert len(res.rows) == 10 and {r["kind"] for r in res.rows} == {"main", "contrast"}
    assert all(r["adjustment"] == "Holm across 10 tests" and r["study"] == "gamma" for r in res.rows)
    g5 = res.trades["G5"]
    assert set(g5["variant"]) == {"matched", "swapped"} and len(res.by_regime) == 2
    for r in res.rows:
        if r["kind"] == "main" and BY_ID[r["hypothesis"]].matched:
            t = res.trades[r["hypothesis"]]
            assert r["trades"] == int((t["regime"] == BY_ID[r["hypothesis"]].matched).sum())
    txt = stage_report(res)
    assert "Contrasts" in txt and "G5 by regime" in txt


def test_random_walk_shows_no_gross_edge(explore_res):
    """A lookahead bug makes gross R strongly positive even on a random walk; each hypothesis's matched trades must not."""
    res = explore_res
    for r in res.rows:
        if r["kind"] == "main" and r["trades"] >= 20:
            t = res.trades[r["hypothesis"]]
            t = t[t["variant"] == "matched"] if "variant" in t else t[t["regime"] == BY_ID[r["hypothesis"]].matched]
            g = t["r_gross"].to_numpy(float)
            assert g.mean() / (g.std(ddof=1) / np.sqrt(len(g))) < 3.0, r["hypothesis"]


def test_random_benchmark_runs_on_allowed_days_only(cfg, world, regime):
    ctx, mk = world
    st = EngineSettings.from_cfg(cfg)
    t = run_each(mk, st, BY_ID["G3"].build(ctx))
    t["tdate"] = pd.DatetimeIndex(t["tdate"])
    allowed = regime.index[regime < 0]
    b = random_benchmark(ctx, mk, st, t.iloc[:20], ctx.first_day, ctx.last_day, reps=5, seed=1, allowed_days=allowed)
    assert len(b["dist"]) == 5 and np.isfinite(b["p_value"])


def test_passed_is_kept_apart_per_study():
    log = pd.DataFrame([{"stage": "explore", "time_utc": "2026-01-01T00:00:00", "hypothesis": "H3", "passed": True},
                        {"stage": "explore", "time_utc": "2026-02-01T00:00:00", "hypothesis": "G2", "passed": True, "study": "gamma"},
                        {"stage": "explore", "time_utc": "2026-02-01T00:00:00", "hypothesis": "G4", "passed": False, "study": "gamma"}])
    assert passed(log, "explore") == ["H3"]                   # old rows without a study are the pattern search
    assert passed(log, "explore", "gamma") == ["G2"] and passed(log, "validate", "gamma") == []
