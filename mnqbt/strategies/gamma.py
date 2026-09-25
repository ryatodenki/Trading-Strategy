"""The GAMMA.md hypotheses (G1-G5) as order intents for the harness engine.

G1-G4 are built on every day; the runner splits their trades by the day's gamma regime
(matched vs opposite days).  G5 needs the regime while building, because the regime picks
its exit: a fixed target on positive-gamma days, a trailing stop on negative-gamma days.
As everywhere in strategies/, decisions use only bars that started before the order time.
Every trade's R unit is 10% of the day's ATR (``risk_unit``).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Callable

import numpy as np
import pandas as pd

from mnqbt.config import get, resolve_dist
from mnqbt.rules.bars import tf_minutes
from mnqbt.rules.fvg import detect_fvgs, entry_price
from mnqbt.rules.levels import _asof
from mnqbt.rules.swings import swings
from mnqbt.strategies.common import INTENT_COLUMNS, Ctx
from mnqbt.strategies.patterns import (DAY_START, R_ATR, _tod, _unit, open_drive, sweep_asia, sweep_london, sweep_prior_day,
                                       sweep_reversal)
from mnqbt.strategies.vwap import vwap_trend
from mnqbt.timeutil import NS_PER_MIN

# ---------------------------------------------------------------------------- G1-G4
va_sweep = partial(sweep_reversal, cols=("vah", "val"), known_from=DAY_START, window=(3 * 60, 15 * 60))


def session_sweeps(ctx: Ctx) -> pd.DataFrame:
    """H5 + H6 + H7 of PATTERNS.md, pooled (one position at a time is applied by the runner)."""
    parts = [f(ctx) for f in (sweep_asia, sweep_london, sweep_prior_day)]
    return pd.concat(parts, ignore_index=True).sort_values("placed_ns", kind="stable").reset_index(drop=True)


def vwap_trend_r(ctx: Ctx) -> pd.DataFrame:
    """STRATEGIES.md #9 with R = 10% of ATR."""
    return _unit(vwap_trend(ctx))


# ---------------------------------------------------------------------------- G5
SWING_N = 2                         # 5-minute swings, 2 bars each side
FIRST_MIN = 3 * 60                  # London and NY: the FVG's third candle starts at or after 03:00 ET ...
LAST_ORDER_MIN = 15 * 60 + 30       # ... and closes before 15:30; orders wait with no time limit, but not past 15:30
BUFFER_ATR = 0.01                   # stop buffer beyond the FVG: 1% of ATR ("2 pips")
RR_MIN, TARGET_FALLBACK = 1.0, 2.0  # pass unless the nearest key level is more than 1x the stop distance away; none: 2x
BREAK_LEVELS = {1: ["swing", "pdh", "dh", "vah", "val", "vwap"], -1: ["swing", "pdl", "dl", "vah", "val", "vwap"]}
TARGET_LEVELS = {1: ["pdh", "dh", "asia_h", "london_h", "ny_h", "sh1", "sh2", "sh3", "vah", "val"],
                 -1: ["pdl", "dl", "asia_l", "london_l", "ny_l", "sl1", "sl2", "sl3", "vah", "val"]}   # + VWAP at the order
TF_RANK = {"15min": 0, "5min": 1}   # set up at the same moment: the 15-minute FVG goes first


def _round(price, up: bool, tick: float) -> np.ndarray:
    x = np.asarray(price, float) / tick
    return (np.ceil(x - 1e-9) if up else np.floor(x + 1e-9)) * tick


def _fvgs(ctx: Ctx, tf: str) -> pd.DataFrame:
    """Harness FVGs (3 same-direction candles, gap >= rules.fvg.min_size) on ``tf``."""
    f = get(ctx.cfg, "rules.fvg")
    bars = ctx.F.bars("a", tf)
    return detect_fvgs(bars, tf, resolve_dist(f["min_size"], ctx.F.atr_for(ctx.cfg, bars)), int(f["max_age_bars"]), True)


def _vwap_at(ctx: Ctx, vw: np.ndarray, t_ns: np.ndarray, day: np.ndarray) -> np.ndarray:
    """VWAP known at ``t_ns``: at the close of the last 1m bar that started before it, on the same trading day."""
    i = np.searchsorted(ctx.ts, t_ns, side="left") - 1
    j = np.maximum(i, 0)
    return np.where((i >= 0) & (ctx.bar_tdate.values[j] == np.asarray(day, "datetime64[ns]")), vw[j], np.nan)


class _G5Inputs:
    """Everything G5 reads, computed once per build."""

    def __init__(self, ctx: Ctx):
        F, cfg = ctx.F, ctx.cfg
        self.b5 = F.bars("a", "5min")
        self.start5 = self.b5["start_ns"].to_numpy(np.int64)
        self.lv = F.levels(cfg, "5min")
        self.vw = F.vwap(cfg)
        sw = swings(self.b5, SWING_N)
        self.sw = {}
        for kind in (1, -1):
            x = sw[sw["kind"] == kind].sort_values("known_ns", kind="stable")
            self.sw[kind] = (x["known_ns"].to_numpy(np.int64), x["price"].to_numpy(float))
        s_cfg = get(cfg, "setup.stop")
        self.min_risk, self.max_risk = s_cfg["min_risk"], s_cfg["max_risk"]
        self.flat = F.flatten_ns(cfg)


def _setups(ctx: Ctx, g: _G5Inputs, tf: str, d: int, regime: pd.Series, stop_at: str = "fvg") -> pd.DataFrame:
    """Direction-``d`` breakout FVGs on ``tf``: the FVG's candles carried price through a key level (candle 1
    opened at or below it, candle 3 closed above it, for a long), in 5-minute higher-high / higher-low structure;
    levels and swings as known when candle 1 starts.  Stop 1% of ATR beyond the FVG's far edge (``stop_at="fvg"``,
    round 1) or beyond the latest 5-minute swing low (long) / high (short) confirmed by the order (``"swing"``,
    round 2, no maximum risk)."""
    fv = _fvgs(ctx, tf)
    fv = fv[fv["dir"] == d].reset_index(drop=True)
    bars = ctx.F.bars("a", tf)
    width = tf_minutes(tf) * NS_PER_MIN
    c1 = fv["c1_start_ns"].to_numpy(np.int64)
    c3 = fv["c3_pos"].to_numpy(int)
    c1_open, c3_close = bars["open"].to_numpy(float)[c3 - 2], bars["close"].to_numpy(float)[c3]
    day = pd.DatetimeIndex(fv["tdate"].to_numpy())
    r5 = np.searchsorted(g.start5, c1, side="left")
    ok = r5 < len(g.start5)
    ok[ok] &= g.start5[r5[ok]] == c1[ok]                      # the 5m bar where candle 1 starts
    r5 = np.where(ok, r5, 0)
    hi_kn, hi_px = g.sw[1]
    lo_kn, lo_px = g.sw[-1]
    h1, h2 = _asof(hi_kn, hi_px, c1, 1), _asof(hi_kn, hi_px, c1, 2)
    l1, l2 = _asof(lo_kn, lo_px, c1, 1), _asof(lo_kn, lo_px, c1, 2)
    with np.errstate(invalid="ignore"):
        trend = ((h1 > h2) & (l1 > l2)) if d > 0 else ((h1 < h2) & (l1 < l2))
    level = {"swing": h1 if d > 0 else l1, "vwap": _vwap_at(ctx, g.vw, c1, day.values)}
    for name in BREAK_LEVELS[d]:
        if name not in level:
            level[name] = g.lv[name].to_numpy(float)[r5]
    top, bottom = fv["top"].to_numpy(float), fv["bottom"].to_numpy(float)
    names = np.full(len(fv), "", dtype=object)
    at_level = np.zeros(len(fv), bool)
    for name in BREAK_LEVELS[d]:
        L = level[name]
        with np.errstate(invalid="ignore"):
            broken = (d * c1_open <= d * L) & (d * L < d * c3_close)
            at_level |= (bottom <= L) & (L <= top)
        names = np.where(broken, np.where(names == "", name, names + "+" + name), names)
    known = fv["known_ns"].to_numpy(np.int64)
    c3_start_tod, c3_close_tod = _tod(ctx.et_minute(known - width)), _tod(ctx.et_minute(known))
    keep = (ok & trend & (names != "") & (c3_start_tod >= _tod(FIRST_MIN)) & (c3_close_tod < _tod(LAST_ORDER_MIN))
            & ctx.can_enter(day) & np.isfinite(regime.reindex(day).to_numpy(float)))
    fv, day, names, top, bottom, at_level = fv[keep], day[keep], names[keep], top[keep], bottom[keep], at_level[keep]
    atr = ctx.atr_on(day)
    entry = entry_price(top, bottom, np.full(len(fv), d), 0.5, ctx.tick)
    buf = BUFFER_ATR * atr
    placed = fv["known_ns"].to_numpy(np.int64)
    if stop_at == "fvg":
        anchor, anchor_ns = (bottom if d > 0 else top), placed           # the FVG, confirmed at the order
        max_risk = resolve_dist(g.max_risk, atr)
    elif stop_at == "swing":
        kn, px = g.sw[-d]                                     # swing lows for a long, swing highs for a short
        j = np.searchsorted(kn, placed, side="right") - 1     # the latest one confirmed by the order
        anchor = np.where(j >= 0, px[np.maximum(j, 0)], np.nan)
        anchor_ns = np.where(j >= 0, kn[np.maximum(j, 0)], 0)
        max_risk = np.full(len(fv), np.inf)
    else:
        raise ValueError(stop_at)
    stop = _round(anchor - d * buf, d < 0, ctx.tick)
    risk = d * (entry - stop)
    with np.errstate(invalid="ignore"):
        ok = np.isfinite(risk) & (risk > 0) & (risk >= resolve_dist(g.min_risk, atr)) & (risk <= max_risk)
    return pd.DataFrame({"placed_ns": fv["known_ns"].to_numpy(np.int64)[ok], "dir": d, "fvg_tf": tf, "tdate": day[ok],
                         "entry": entry[ok], "stop": stop[ok], "stop_dist": risk[ok], "atr": atr[ok], "buffer": buf[ok],
                         "fvg_top": top[ok], "fvg_bottom": bottom[ok], "fvg_c1_ns": fv["c1_start_ns"].to_numpy(np.int64)[ok],
                         "stop_ref_ns": np.asarray(anchor_ns, np.int64)[ok],
                         "level": names[ok], "at_level": at_level[ok]})


def _nearest_level(ctx: Ctx, g: _G5Inputs, st: pd.DataFrame) -> np.ndarray:
    """Nearest key level strictly beyond each setup's entry, as of the order (NaN if none)."""
    placed, d, entry = st["placed_ns"].to_numpy(np.int64), st["dir"].to_numpy(int), st["entry"].to_numpy(float)
    row = np.searchsorted(g.start5, placed, side="left") - 1          # the last 5m bar that started before the order
    vw_now = _vwap_at(ctx, g.vw, placed, pd.DatetimeIndex(st["tdate"]).values)
    out = np.full(len(st), np.nan)
    for side in (1, -1):
        m = np.flatnonzero(d == side)
        vals = np.column_stack([g.lv[TARGET_LEVELS[side]].to_numpy(float)[row[m]], vw_now[m]])
        with np.errstate(invalid="ignore"):
            cand = np.where(side * vals > side * entry[m][:, None], vals, np.inf if side > 0 else -np.inf)
        best = cand.min(axis=1) if side > 0 else cand.max(axis=1)
        out[m] = np.where(np.isfinite(best), best, np.nan)
    return out


def breakout(ctx: Ctx, regime: pd.Series, swap: bool = False, stop_at: str = "fvg") -> pd.DataFrame:
    """G5 (GAMMA.md): a 5- or 15-minute FVG whose candles broke a key level, in the direction of 5-minute
    structure; taken only if the nearest key level beyond the entry is more than 1x the stop distance away;
    limit entry at the FVG midpoint (a 15-minute setup replaces a waiting 5-minute order); stop 1% of ATR
    beyond the FVG; exit by the day's gamma: fixed target on positive days, trailing stop on negative days
    (``swap`` reverses that, for the contrast)."""
    g = _G5Inputs(ctx)
    tick = ctx.tick
    st = pd.concat([_setups(ctx, g, tf, d, regime, stop_at) for tf in ("5min", "15min") for d in (1, -1)], ignore_index=True)
    cols = INTENT_COLUMNS + ["expire_ns", "entry_type", "entry", "trail_ns", "trail_px", "exit_style", "regime", "level",
                             "at_level", "fvg_tf", "target_kind", "stop_dist", "reward_risk", "replaced_at", "fvg_top", "fvg_bottom",
                             "fvg_c1_ns", "stop_ref_ns"]
    if st.empty:
        return pd.DataFrame(columns=cols)
    # reward:risk more than 1:1 to the nearest key level beyond the entry (none: the 2x fallback)
    nearest = _nearest_level(ctx, g, st)
    d0, e0, r0 = st["dir"].to_numpy(int), st["entry"].to_numpy(float), st["stop_dist"].to_numpy(float)
    rr = np.where(np.isfinite(nearest), d0 * (nearest - e0) / r0, TARGET_FALLBACK)
    keep = rr > RR_MIN
    st, nearest, rr = st[keep].reset_index(drop=True), nearest[keep], rr[keep]
    if st.empty:
        return pd.DataFrame(columns=cols)

    td = pd.DatetimeIndex(st["tdate"])
    placed, d = st["placed_ns"].to_numpy(np.int64), st["dir"].to_numpy(int)
    entry, stop, risk = st["entry"].to_numpy(float), st["stop"].to_numpy(float), st["stop_dist"].to_numpy(float)
    reg = regime.reindex(td).to_numpy(float)
    flat = g.flat.reindex(td).to_numpy(np.int64)
    expire = ctx.at(td, LAST_ORDER_MIN)

    # 15 minutes beats 5 minutes: a waiting 5m order is cancelled when the next same-direction 15m setup is
    # confirmed after it and before 15:30 (so on the same trading day)
    replaced = np.zeros(len(st), np.int64)
    is15 = (st["fvg_tf"] == "15min").to_numpy()
    for side in (1, -1):
        p15 = np.sort(placed[is15 & (d == side)])
        k = np.flatnonzero(~is15 & (d == side))
        if len(p15) == 0 or len(k) == 0:
            continue
        nxt = np.searchsorted(p15, placed[k], side="right")
        cand = p15[np.minimum(nxt, len(p15) - 1)]
        hit = (nxt < len(p15)) & (cand < expire[k])
        replaced[k[hit]] = cand[hit]
    expire = np.where(replaced > 0, replaced, expire)

    found = np.isfinite(nearest)
    tgt = np.array([float(_round(x, dd > 0, tick)) for x, dd in zip(np.where(found, nearest, entry + d * TARGET_FALLBACK * risk), d)])
    trail = (reg < 0) != swap

    rows = []
    for i in range(len(st)):
        t_ns, t_px = np.array([], np.int64), np.array([], float)
        if trail[i]:
            kn, px = g.sw[-d[i]]
            a, b = np.searchsorted(kn, placed[i], side="right"), np.searchsorted(kn, flat[i], side="left")
            t_ns, t_px = kn[a:b], _round(px[a:b] - d[i] * st["buffer"].iat[i], d[i] < 0, tick)
        rows.append({
            "placed_ns": int(placed[i]), "dir": int(d[i]), "flatten_ns": int(flat[i]), "expire_ns": int(expire[i]),
            "stop": float(stop[i]), "target": np.nan if trail[i] else float(tgt[i]), "target_src": "abs", "target_r": np.nan,
            "risk_unit": R_ATR * float(st["atr"].iat[i]), "ref_price": float(entry[i]), "atr": float(st["atr"].iat[i]),
            "tdate": td[i], "exit_tdate": td[i], "entry_type": "limit", "entry": float(entry[i]), "trail_ns": t_ns, "trail_px": t_px,
            "exit_style": "trail" if trail[i] else "fixed", "regime": int(reg[i]), "level": st["level"].iat[i],
            "at_level": bool(st["at_level"].iat[i]), "fvg_tf": st["fvg_tf"].iat[i],
            "target_kind": "none" if trail[i] else ("level" if found[i] else "2x_stop"), "stop_dist": float(risk[i]),
            "reward_risk": float(rr[i]), "replaced_at": int(replaced[i]), "fvg_top": float(st["fvg_top"].iat[i]),
            "fvg_bottom": float(st["fvg_bottom"].iat[i]), "fvg_c1_ns": int(st["fvg_c1_ns"].iat[i]),
            "stop_ref_ns": int(st["stop_ref_ns"].iat[i]),
        })
    out = pd.DataFrame(rows)[cols]
    out["_rank"] = out["fvg_tf"].map(TF_RANK)
    return out.sort_values(["placed_ns", "_rank", "dir"], kind="stable").drop(columns="_rank").reset_index(drop=True)


# ---------------------------------------------------------------------------- registry
@dataclass(frozen=True)
class GammaHypothesis:
    id: str
    slug: str
    name: str
    build: Callable[..., pd.DataFrame]     # build(ctx) for G1-G4; build(ctx, regime, swap) for G5
    mode: str                              # each | single (one position at a time across the rule's intents)
    matched: int                           # +1 positive-gamma days, -1 negative, 0 = every day (G5: exits by regime)


HYPOTHESES: tuple[GammaHypothesis, ...] = (
    GammaHypothesis("G1", "va_sweep_pos", "Prior-day VAH/VAL sweep fade, positive gamma", va_sweep, "single", 1),
    GammaHypothesis("G2", "sweeps_pos", "Asia/London/prior-day sweep reversal, positive gamma", session_sweeps, "single", 1),
    GammaHypothesis("G3", "open_drive_neg", "Open drive (09:35-10:00), negative gamma", open_drive, "each", -1),
    GammaHypothesis("G4", "vwap_trend_neg", "VWAP trend following, negative gamma", vwap_trend_r, "each", -1),
    GammaHypothesis("G5", "breakout_gamma_exits", "Key-level breakout FVG (15m over 5m), R:R > 1; fixed target (+gamma) / trailing stop (-gamma)",
                    breakout, "single", 0),
)
BY_ID = {h.id: h for h in HYPOTHESES}

# Round 2 (GAMMA.md, MNQ 2019-07 -> 2022-12): G1-G4 unchanged; G5 with the stop beyond the latest swing
HYPOTHESES_R2: tuple[GammaHypothesis, ...] = HYPOTHESES[:4] + (
    GammaHypothesis("G5", "breakout_gamma_exits_swing_stop",
                    "Key-level breakout FVG (15m over 5m), stop beyond the latest swing, R:R > 1; fixed target (+gamma) / "
                    "trailing stop (-gamma)", partial(breakout, stop_at="swing"), "single", 0),
)
BY_ID_R2 = {h.id: h for h in HYPOTHESES_R2}
