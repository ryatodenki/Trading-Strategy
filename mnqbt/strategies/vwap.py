"""VWAP trend following, VWAP mean reversion and the volatility-regime switch (STRATEGIES.md #9-11)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.rules.vwap import vwap
from mnqbt.strategies.common import RTH_CLOSE, RTH_OPEN, Ctx, intents
from mnqbt.timeutil import NS_PER_MIN


def vwap_bands(ctx: Ctx) -> tuple[np.ndarray, np.ndarray]:
    """VWAP anchored at each session start (09:30 for the cash session) and the volume-weighted
    standard deviation of the typical price around it; both known at each bar's close."""
    a = ctx.F.a1
    vw = vwap(a, "session")
    tp = (ctx.h + ctx.l + ctx.c) / 3.0
    key = pd.factorize(pd.Series(a["tdate"].astype(str).to_numpy()) + "|" + a["session"].astype(str).to_numpy())[0]
    g = pd.DataFrame({"k": key, "v": ctx.v, "pv2": tp * tp * ctx.v}).groupby("k", sort=False)
    cv, cpv2 = g["v"].cumsum().to_numpy(), g["pv2"].cumsum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        var = np.where(cv > 0, cpv2 / cv - vw * vw, np.nan)
    return vw, np.sqrt(np.maximum(var, 0.0))


def _rth_rows(ctx: Ctx, last_minute: int) -> np.ndarray:
    """Bars of tradeable days from 09:30 up to ``last_minute`` (inclusive)."""
    m = (ctx.et_min >= RTH_OPEN) & (ctx.et_min <= last_minute)
    rows = np.flatnonzero(m)
    return rows[ctx.can_enter(ctx.bar_tdate[rows])]


def vwap_trend(ctx: Ctx) -> pd.DataFrame:
    """#9: long above VWAP, short below, decided at each 1m close 09:30-15:58 and traded at the next
    open; a reversal is an exit and a new entry at the same open; flat at the close."""
    vw, _ = vwap_bands(ctx)
    rows = _rth_rows(ctx, RTH_CLOSE - 2)
    day = ctx.bar_tdate[rows]
    s = pd.Series(np.sign(ctx.c[rows] - vw[rows])).replace(0, np.nan)
    s = s.groupby(day.values).ffill().fillna(0).to_numpy(int)   # unchanged if equal
    new_day = np.r_[True, day[1:] != day[:-1]]
    change = new_day | (s != np.r_[0, s[:-1]])
    starts = np.flatnonzero(change & (s != 0))
    # a position runs until the next change that day, else until the close
    seg_id = np.cumsum(change) - 1
    change_pos = np.flatnonzero(change)
    nxt = np.r_[change_pos[1:], len(s)]           # next change after each segment start
    ends = nxt[seg_id[starts]]
    td = day[starts]
    close = ctx.close_ns(td)
    same_day_end = (ends < len(s)) & (ends < len(day)) & (day[np.minimum(ends, len(day) - 1)] == td)
    exit_ns = np.where(same_day_end, ctx.ts[rows[np.minimum(ends, len(rows) - 1)]] + NS_PER_MIN, close)
    placed = ctx.ts[rows[starts]] + NS_PER_MIN
    return intents(ctx, td, placed, s[starts], td, np.minimum(exit_ns, close), ctx.c[rows[starts]],
                   vol_state=ctx.vol_state.reindex(td).fillna("").to_numpy())


def vwap_reversion(ctx: Ctx) -> pd.DataFrame:
    """#10: a 1m close moving from inside to outside VWAP +-2 sigma is faded at the next open;
    target VWAP, stop VWAP +-3 sigma (both at the signal bar); no new entries at or after 15:30."""
    vw, sd = vwap_bands(ctx)
    rows = _rth_rows(ctx, 15 * 60 + 28)
    day = ctx.bar_tdate[rows]
    c, v, s = ctx.c[rows], vw[rows], sd[rows]
    above, below = c > v + 2 * s, c < v - 2 * s
    prev_same_day = np.r_[False, day[1:] == day[:-1]]
    was_above, was_below = np.r_[False, above[:-1]] & prev_same_day, np.r_[False, below[:-1]] & prev_same_day
    # the previous close must have been inside the bands on the same day
    sig_short, sig_long = above & prev_same_day & ~was_above, below & prev_same_day & ~was_below
    k = np.flatnonzero(sig_short | sig_long)
    d = np.where(sig_short[k], -1, 1)
    stop = v[k] - d * 3 * s[k]
    risk = d * (c[k] - stop)
    td = day[k]
    keep = risk >= ctx.min_risk(ctx.atr_on(td))
    k, d, stop, td = k[keep], d[keep], stop[keep], td[keep]
    return intents(ctx, td, ctx.ts[rows[k]] + NS_PER_MIN, d, td, ctx.close_ns(td), c[k], stop=stop, target=v[k],
                   vol_state=ctx.vol_state.reindex(td).fillna("").to_numpy())
