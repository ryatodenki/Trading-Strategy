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
WINDOW = (3 * 60, 15 * 60)          # breakout bar starts 03:00-15:00 ET
FVG_AGE = 12                        # bars of the FVG's own timeframe
ORDER_MINUTES = 60                  # limit order lifetime
LAST_ORDER_MIN = 15 * 60 + 30       # ...and never past 15:30
TARGET_MIN, TARGET_FALLBACK = 1.0, 2.0   # nearest key level >= 1x stop distance, else 2x
TARGET_LEVELS = {1: ["pdh", "dh", "asia_h", "london_h", "ny_h", "sh1", "sh2", "sh3"],
                 -1: ["pdl", "dl", "asia_l", "london_l", "ny_l", "sl1", "sl2", "sl3"]}


def _round(price, up: bool, tick: float) -> np.ndarray:
    x = np.asarray(price, float) / tick
    return (np.ceil(x - 1e-9) if up else np.floor(x + 1e-9)) * tick


def _fvgs(ctx: Ctx, tf: str) -> pd.DataFrame:
    f = get(ctx.cfg, "rules.fvg")
    bars = ctx.F.bars("a", tf)
    return detect_fvgs(bars, tf, resolve_dist(f["min_size"], ctx.F.atr_for(ctx.cfg, bars)), FVG_AGE, True)


def _latest_alive(fv: pd.DataFrame, d: int, t_ns: np.ndarray, day: np.ndarray) -> np.ndarray:
    """Row of the most recent direction-``d`` FVG known by ``t_ns``, if still alive then and from the same
    trading day (-1 otherwise).  Every FVG lives equally long, so the latest known is the latest to expire."""
    x = fv[fv["dir"] == d].sort_values("known_ns", kind="stable")
    kn = x["known_ns"].to_numpy(np.int64)
    i = np.searchsorted(kn, t_ns, side="right") - 1
    ok = i >= 0
    j = np.maximum(i, 0)
    ok &= x["expire_ns"].to_numpy(np.int64)[j] > t_ns
    ok &= pd.DatetimeIndex(x["tdate"].to_numpy()[j]).values == np.asarray(day, "datetime64[ns]")
    return np.where(ok, x.index.to_numpy()[j], -1)


def breakout(ctx: Ctx, regime: pd.Series, swap: bool = False) -> pd.DataFrame:
    """G5: breakout of the latest 5m swing high / prior-day high in a higher-high, higher-low 5m structure
    (shorts mirror), with a 15m FVG present; limit entry at the midpoint of the latest untouched 5m FVG;
    stop beyond the latest 5m swing low; exit by the day's gamma: fixed target on positive days, trailing
    stop on negative days (``swap`` reverses that, for the contrast)."""
    F, cfg, tick = ctx.F, ctx.cfg, ctx.tick
    b5 = F.bars("a", "5min")
    start, end = b5["start_ns"].to_numpy(np.int64), b5["known_ns"].to_numpy(np.int64)
    h, l, c = (b5[k].to_numpy(float) for k in ("high", "low", "close"))
    day = pd.DatetimeIndex(b5["tdate"].to_numpy())
    tod = _tod(ctx.et_minute(start))
    atr = F.atr_for(cfg, b5)
    lv = F.levels(cfg, "5min")

    sw = swings(b5, SWING_N)
    last = {}
    for kind in (1, -1):
        s = sw[sw["kind"] == kind].sort_values("known_ns", kind="stable")
        kn, px = s["known_ns"].to_numpy(np.int64), s["price"].to_numpy(float)
        last[kind] = (_asof(kn, px, start, 1), _asof(kn, px, start, 2), kn, px)   # as of each bar's start
    with np.errstate(invalid="ignore"):
        trend = {1: (last[1][0] > last[1][1]) & (last[-1][0] > last[-1][1]),
                 -1: (last[1][0] < last[1][1]) & (last[-1][0] < last[-1][1])}
    prev_c = np.r_[np.nan, c[:-1]]
    same_prev = np.r_[False, day[1:] == day[:-1]]
    in_window = (tod >= _tod(WINDOW[0])) & (tod < _tod(WINDOW[1]))
    fv5, fv15 = _fvgs(ctx, "5min"), _fvgs(ctx, "15min")
    s_cfg = get(cfg, "setup.stop")
    buffer = resolve_dist(s_cfg["buffer"], atr)
    rmin, rmax = resolve_dist(s_cfg["min_risk"], atr), resolve_dist(s_cfg["max_risk"], atr)
    flat_day = F.flatten_ns(cfg)
    reg = regime.reindex(day).to_numpy(float)

    rows = []
    for d in (1, -1):
        swing_lvl = last[d][0]
        prior = lv["pdh" if d > 0 else "pdl"].to_numpy(float)
        with np.errstate(invalid="ignore"):
            cross_sw = same_prev & (d * c > d * swing_lvl) & (d * prev_c <= d * swing_lvl)
            cross_pd = same_prev & (d * c > d * prior) & (d * prev_c <= d * prior)
        k = np.flatnonzero(in_window & trend[d] & (cross_sw | cross_pd) & ctx.can_enter(day) & np.isfinite(reg))
        if len(k) == 0:
            continue
        placed = end[k]
        ok15 = _latest_alive(fv15, d, placed, day[k].values) >= 0
        f5 = _latest_alive(fv5, d, placed, day[k].values)
        k, placed, f5 = k[ok15 & (f5 >= 0)], placed[ok15 & (f5 >= 0)], f5[ok15 & (f5 >= 0)]
        z = fv5.loc[f5]
        entry = entry_price(z["top"].to_numpy(), z["bottom"].to_numpy(), np.full(len(k), d), 0.5, tick)
        c3 = z["c3_pos"].to_numpy(int)
        untouched = np.array([b <= a or ((l[a + 1:b + 1].min() > e) if d > 0 else (h[a + 1:b + 1].max() < e))
                              for a, b, e in zip(c3, k, entry)], bool)   # no bar after c3, up to the breakout bar, reached the entry
        opp = last[-d][0][k]                                          # the higher low (long) / lower high (short)
        stop = _round(opp - d * buffer[k], d < 0, tick)
        risk = d * (entry - stop)
        with np.errstate(invalid="ignore"):
            keep = untouched & np.isfinite(risk) & (risk > 0) & (risk >= rmin[k]) & (risk <= rmax[k])
        k, placed, entry, stop, risk = k[keep], placed[keep], entry[keep], stop[keep], risk[keep]
        td = day[k]
        flat = flat_day.reindex(td).to_numpy(np.int64)
        expire = np.minimum(placed + ORDER_MINUTES * NS_PER_MIN, ctx.at(td, LAST_ORDER_MIN))
        trail = (reg[k] < 0) != swap
        # fixed target: nearest key level >= 1x stop distance beyond the entry, else 2x
        vals = lv[TARGET_LEVELS[d]].to_numpy(float)[k]
        thresh = (entry + d * TARGET_MIN * risk)[:, None]
        with np.errstate(invalid="ignore"):
            cand = np.where((vals > thresh) if d > 0 else (vals < thresh), vals, np.inf if d > 0 else -np.inf)
        best = cand.min(axis=1) if d > 0 else cand.max(axis=1)
        tgt = _round(np.where(np.isfinite(best), best, entry + d * TARGET_FALLBACK * risk), d > 0, tick)
        tgt_src = np.where(np.isfinite(best), "level", "2x_stop")
        # trailing stop: 5m swings on the stop side confirmed after placement, before the flatten time
        kn, px = last[-d][2], last[-d][3]
        for i in range(len(k)):
            t_ns, t_px = np.array([], np.int64), np.array([], float)
            if trail[i]:
                a, b = np.searchsorted(kn, placed[i], side="right"), np.searchsorted(kn, flat[i], side="left")
                t_ns, t_px = kn[a:b], _round(px[a:b] - d * buffer[k[i]], d < 0, tick)
            rows.append({
                "placed_ns": int(placed[i]), "dir": d, "flatten_ns": int(flat[i]), "expire_ns": int(expire[i]),
                "stop": float(stop[i]), "target": np.nan if trail[i] else float(tgt[i]), "target_src": "abs",
                "target_r": np.nan, "risk_unit": R_ATR * float(atr[k[i]]), "ref_price": float(c[k[i]]), "atr": float(atr[k[i]]),
                "tdate": td[i], "exit_tdate": td[i], "entry_type": "limit", "entry": float(entry[i]),
                "trail_ns": t_ns, "trail_px": t_px, "exit_style": "trail" if trail[i] else "fixed", "regime": int(reg[k[i]]),
                "level": "swing+pdh" if (cross_sw[k[i]] and cross_pd[k[i]]) else ("swing" if cross_sw[k[i]] else "prior_day"),
                "target_kind": "none" if trail[i] else tgt_src[i], "stop_dist": float(risk[i]),
            })
    cols = INTENT_COLUMNS + ["expire_ns", "entry_type", "entry", "trail_ns", "trail_px", "exit_style", "regime", "level",
                             "target_kind", "stop_dist"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows)[cols].sort_values(["placed_ns", "dir"], kind="stable").reset_index(drop=True)


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
    GammaHypothesis("G5", "breakout_gamma_exits", "Breakout + FVG entry; fixed target (+gamma) / trailing stop (-gamma)",
                    breakout, "single", 0),
)
BY_ID = {h.id: h for h in HYPOTHESES}
