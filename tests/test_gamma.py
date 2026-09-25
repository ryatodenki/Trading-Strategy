"""GAMMA.md hypotheses: gamma timing, rule definitions, trailing stops, no lookahead, runner (synthetic data only)."""

import copy

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
from mnqbt.strategies.gamma import BY_ID, HYPOTHESES, _G5Inputs, _setups, breakout
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
    """GAMMA.md G5 re-derived FVG by FVG, straight from the text (slow; limited to ``days``)."""
    F, cfg, tick = ctx.F, ctx.cfg, ctx.tick
    b5 = F.bars("a", "5min")
    start5 = b5["start_ns"].to_numpy(np.int64)
    lv = F.levels(cfg, "5min")
    vw = F.vwap(cfg)
    ts1, day1 = ctx.ts, ctx.bar_tdate
    sw = swings(b5, 2)
    SW = {kind: sw[sw["kind"] == kind].sort_values("known_ns") for kind in (1, -1)}
    fc, sc = get(cfg, "rules.fvg"), get(cfg, "setup.stop")
    flat_day = F.flatten_ns(cfg)

    def vwap_known_at(t, day):
        i = int(np.searchsorted(ts1, t, side="left")) - 1
        return vw[i] if i >= 0 and day1[i] == day else np.nan

    def tod(t):
        return _tod(ctx.et_minute(np.array([t])))[0]

    setups = []
    for tf, width in (("5min", 5), ("15min", 15)):
        bars = F.bars("a", tf)
        fv = detect_fvgs(bars, tf, resolve_dist(fc["min_size"], F.atr_for(cfg, bars)), 12, True)
        for _, z in fv[pd.DatetimeIndex(fv["tdate"]).isin(days)].iterrows():
            d, day = int(z["dir"]), pd.Timestamp(z["tdate"])
            c1 = int(z["c1_start_ns"])
            c3_start, c3_end = int(z["known_ns"]) - width * NS_PER_MIN, int(z["known_ns"])
            if not (tod(c3_start) >= _tod(180) and tod(c3_end) < _tod(15 * 60 + 30)):       # London and NY
                continue
            if not ctx.can_enter(pd.DatetimeIndex([day]))[0] or not np.isfinite(regime.get(day, np.nan)):
                continue
            hs = SW[1][SW[1]["known_ns"] <= c1]["price"].to_numpy()
            ls = SW[-1][SW[-1]["known_ns"] <= c1]["price"].to_numpy()
            if len(hs) < 2 or len(ls) < 2:
                continue
            up, down = hs[-1] > hs[-2] and ls[-1] > ls[-2], hs[-1] < hs[-2] and ls[-1] < ls[-2]
            if not (up if d > 0 else down):
                continue
            r = int(np.searchsorted(start5, c1))
            if r >= len(start5) or start5[r] != c1:
                continue
            if d > 0:
                levels = {"swing": hs[-1], "pdh": lv["pdh"].iat[r], "dh": lv["dh"].iat[r]}
            else:
                levels = {"swing": ls[-1], "pdl": lv["pdl"].iat[r], "dl": lv["dl"].iat[r]}
            levels.update(vah=lv["vah"].iat[r], val=lv["val"].iat[r], vwap=vwap_known_at(c1, day))
            o1, cl3 = bars["open"].iat[int(z["c3_pos"]) - 2], bars["close"].iat[int(z["c3_pos"])]
            broken = [n for n, L in levels.items() if np.isfinite(L) and d * o1 <= d * L < d * cl3]
            if not broken:
                continue
            atr = ctx.atr_on(pd.DatetimeIndex([day]))[0]
            e = float(entry_price(np.array([z["top"]]), np.array([z["bottom"]]), np.array([d]), 0.5, tick)[0])
            buf = 0.01 * atr
            stop = np.floor((z["bottom"] - buf) / tick + 1e-9) * tick if d > 0 else np.ceil((z["top"] + buf) / tick - 1e-9) * tick
            risk = d * (e - stop)
            if not (risk > 0 and resolve_dist(sc["min_risk"], atr) <= risk <= resolve_dist(sc["max_risk"], atr)):
                continue
            t = int(z["known_ns"])
            r_order = int(np.searchsorted(start5, t)) - 1
            names = ["pdh", "dh", "asia_h", "london_h", "ny_h", "sh1", "sh2", "sh3", "vah", "val"] if d > 0 else \
                    ["pdl", "dl", "asia_l", "london_l", "ny_l", "sl1", "sl2", "sl3", "vah", "val"]
            lvls = np.r_[lv[names].iloc[r_order].to_numpy(float), vwap_known_at(t, day)]
            beyond = lvls[np.isfinite(lvls) & (d * lvls > d * e)]
            if len(beyond):
                nearest = beyond.min() if d > 0 else beyond.max()
                if d * (nearest - e) <= risk:                                               # R:R 1:1 or less: pass
                    continue
            else:
                nearest = e + 2 * d * risk
            at = any(np.isfinite(L) and z["bottom"] <= L <= z["top"] for L in levels.values())
            setups.append({"placed_ns": t, "dir": d, "fvg_tf": tf, "day": day, "entry": e, "stop": stop, "risk": risk,
                           "buf": buf, "level": set(broken), "at_level": at, "nearest": nearest})
    out = []
    for x in setups:
        t, d, day = x["placed_ns"], x["dir"], x["day"]
        g = regime[day]
        last_order = ctx.at(pd.DatetimeIndex([day]), 15 * 60 + 30)[0]
        expire = last_order
        if x["fvg_tf"] == "5min":
            later = sorted(y["placed_ns"] for y in setups if y["fvg_tf"] == "15min" and y["dir"] == d and t < y["placed_ns"] < last_order)
            if later:
                expire = later[0]
        row = {**x, "regime": int(g), "expire_ns": expire}
        if g > 0:
            raw = x["nearest"]
            row["target"] = np.ceil(raw / tick - 1e-9) * tick if d > 0 else np.floor(raw / tick + 1e-9) * tick
            row["trail_ns"] = []
        else:
            row["target"] = np.nan
            opp = SW[-d]
            later = opp[(opp["known_ns"] > t) & (opp["known_ns"] < flat_day[day])]
            row["trail_ns"] = later["known_ns"].tolist()
            p = later["price"].to_numpy(float)
            row["trail_px"] = (np.floor((p - x["buf"]) / tick + 1e-9) * tick if d > 0 else np.ceil((p + x["buf"]) / tick - 1e-9) * tick).tolist()
        out.append(row)
    return out


def test_g5_finds_exactly_the_setups_the_text_describes(ctx, regime):
    it = breakout(ctx, regime)
    days = pd.DatetimeIndex(sorted(set(it["tdate"])))[:50]
    ref = sorted(_g5_reference(ctx, regime, days), key=lambda r: (r["placed_ns"], r["fvg_tf"] != "15min", r["dir"]))
    got = it[it["tdate"].isin(days)].reset_index(drop=True)
    assert len(ref) >= 40 and len(got) == len(ref)
    for r, (_, g) in zip(ref, got.iterrows()):
        assert (g["placed_ns"], g["dir"], g["fvg_tf"], g["regime"]) == (r["placed_ns"], r["dir"], r["fvg_tf"], r["regime"])
        assert set(g["level"].split("+")) == r["level"] and g["at_level"] == r["at_level"]
        assert g["reward_risk"] > 1.0
        assert g["entry"] == pytest.approx(r["entry"]) and g["stop"] == pytest.approx(r["stop"])
        assert g["expire_ns"] == r["expire_ns"]
        assert (np.isnan(g["target"]) and np.isnan(r["target"])) or g["target"] == pytest.approx(r["target"])
        assert list(g["trail_ns"]) == r["trail_ns"]
        if r["trail_ns"]:
            assert np.allclose(g["trail_px"], r["trail_px"])
        assert g["exit_style"] == ("fixed" if r["regime"] > 0 else "trail") and g["entry_type"] == "limit"
    assert {"fixed", "trail"} <= set(got["exit_style"]) and {"5min", "15min"} <= set(got["fvg_tf"])
    assert (got["replaced_at"] > 0).any() and got["level"].str.contains("vwap|vah|val").any()
    assert got["at_level"].any() and not got["at_level"].all()


def test_g5_a_15_minute_setup_replaces_a_waiting_5_minute_order(ctx, regime):
    it = breakout(ctx, regime)
    rep = it[it["replaced_at"] > 0]
    assert len(rep) >= 3 and (rep["fvg_tf"] == "5min").all()
    for _, r in rep.iterrows():
        m = it[(it["fvg_tf"] == "15min") & (it["dir"] == r["dir"]) & (it["placed_ns"] == r["replaced_at"])]
        assert len(m) == 1 and m["tdate"].iat[0] == r["tdate"]           # cancelled exactly when the 15m order goes in
        assert r["expire_ns"] == r["replaced_at"] > r["placed_ns"]
    same_time = it.groupby("placed_ns")["fvg_tf"].agg(list)
    for tfs in same_time[same_time.map(len) > 1]:
        assert tfs == sorted(tfs, key=lambda t: t != "15min")            # 15m first when both appear at once


def test_g5_stop_buffer_is_one_percent_of_atr_even_when_that_is_under_a_point(ctx, regime):
    small = copy.copy(ctx)
    small.atr = ctx.atr * 0.2                                        # ATRs of ~20-60 points: 1% is under 1 point
    st = pd.concat([_setups(small, _G5Inputs(small), tf, d, regime) for tf in ("5min", "15min") for d in (1, -1)])
    assert len(st) >= 5 and (0.01 * st["atr"] < 1.0).all()
    far = np.where(st["dir"] > 0, st["fvg_bottom"], st["fvg_top"])
    gap = st["dir"] * (far - st["stop"])                             # how far the stop sits beyond the FVG
    assert ((gap >= 0.01 * st["atr"] - 1e-9) & (gap < 0.01 * st["atr"] + ctx.tick)).all()


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
            cols = ["stop", "risk_unit", "ref_price"] + (["entry", "target", "exit_style", "fvg_tf"] if h.matched == 0 else [])
            pd.testing.assert_series_equal(match.iloc[0][cols], row[cols], check_names=False, obj=h.id)
            checked += 1
    assert checked >= 2 * len(HYPOTHESES)


def test_the_15_minute_replacement_is_known_from_data_before_it(cfg, data, ctx, regime):
    """The cancel time of a replaced 5m order is a real 15m order placement, rebuilt from data before that time."""
    a, b, flags = data
    full = breakout(ctx, regime)
    rep = full[full["replaced_at"] > 0]
    for _, r in rep.iloc[[0, len(rep) // 2, -1]].iterrows():
        cut = pd.Timestamp(int(r["replaced_at"]), tz="UTC")
        F_t, _ = dev_frames(cfg, a[a.index < cut], b[b.index < cut], flags, end="2100-01-01")
        trunc = breakout(Ctx(F_t, cfg), regime)
        new = trunc[(trunc["placed_ns"] == r["replaced_at"]) & (trunc["dir"] == r["dir"]) & (trunc["fvg_tf"] == "15min")]
        ref = full[(full["placed_ns"] == r["replaced_at"]) & (full["dir"] == r["dir"]) & (full["fvg_tf"] == "15min")]
        assert len(new) == 1 and new["entry"].iat[0] == ref["entry"].iat[0] and new["stop"].iat[0] == ref["stop"].iat[0]
        old = trunc[(trunc["placed_ns"] == r["placed_ns"]) & (trunc["dir"] == r["dir"]) & (trunc["fvg_tf"] == "5min")]
        assert old["expire_ns"].iat[0] == r["replaced_at"]


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
    assert set(g5["variant"]) == {"matched", "swapped"} and len(res.by_regime) == 6
    for r in res.rows:
        if r["kind"] == "main" and BY_ID[r["hypothesis"]].matched:
            t = res.trades[r["hypothesis"]]
            assert r["trades"] == int((t["regime"] == BY_ID[r["hypothesis"]].matched).sum())
    txt = stage_report(res)
    assert "Contrasts" in txt and "G5 by regime, FVG timeframe and FVG at the level" in txt


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


def test_g5_trade_charts_render(cfg, world, regime, tmp_path):
    from mnqbt.reports.gamma_charts import plot_g5_equity, plot_g5_trade

    ctx, mk = world
    it = breakout(ctx, regime)
    tr = simulate(mk, it, EngineSettings.from_cfg(cfg))[0]
    g = _G5Inputs(ctx)
    for style in ("fixed", "trail"):
        t = tr[tr["exit_style"] == style].iloc[0]
        f = plot_g5_trade(ctx, g, it.loc[int(t["intent"])], t, 1.5e9, tmp_path / f"{style}.png")
        assert f.stat().st_size > 20_000
    assert plot_g5_equity(tr, tmp_path / "eq.png", "t").stat().st_size > 10_000
