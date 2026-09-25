"""Cash-session clock strategies: opening range, intraday momentum, overnight, gaps (STRATEGIES.md #1-8)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.strategies.common import RTH_OPEN, Ctx, intents


def _entry_days(ctx: Ctx) -> pd.DatetimeIndex:
    td = ctx.trading_days()
    return td[ctx.can_enter(td)]


def opening_range(ctx: Ctx, minutes: int) -> pd.DataFrame:
    """#1-3: trade the direction of the first ``minutes`` of the cash session; stop at its far end, 10R target."""
    days = _entry_days(ctx)
    in_range = (ctx.et_min >= RTH_OPEN) & (ctx.et_min < RTH_OPEN + minutes)
    bars = pd.DataFrame({"tdate": ctx.bar_tdate[in_range], "m": ctx.et_min[in_range], "o": ctx.o[in_range],
                         "h": ctx.h[in_range], "l": ctx.l[in_range], "c": ctx.c[in_range]})
    g = bars.groupby("tdate")
    r = pd.DataFrame({"first_m": g["m"].first(), "last_m": g["m"].last(), "open": g["o"].first(), "close": g["c"].last(),
                      "high": g["h"].max(), "low": g["l"].min()}).reindex(days)
    # the range must start with the 09:30 bar and end with its last minute
    ok = (r["first_m"] == RTH_OPEN) & (r["last_m"] == RTH_OPEN + minutes - 1)
    d = np.sign(r["close"] - r["open"]).fillna(0).to_numpy(int)
    stop = np.where(d > 0, r["low"], r["high"])
    risk = d * (r["close"].to_numpy() - stop)
    keep = ok.to_numpy() & (d != 0) & (risk >= ctx.min_risk(ctx.atr_on(days)))
    td = days[keep]
    return intents(ctx, td, ctx.at(td, RTH_OPEN + minutes), d[keep], td, ctx.close_ns(td), r["close"].to_numpy()[keep],
                   stop=stop[keep], target_r=10.0)


def intraday_momentum(ctx: Ctx, signal_minute: int) -> pd.DataFrame:
    """#4-5: sign of the return from the previous 15:59 close to the close just before ``signal_minute``;
    traded from 15:30 to the close."""
    days = _entry_days(ctx)
    prev = ctx.shift_days(days, -1)
    p0 = ctx.close_of_bar(ctx.at(prev, 15 * 60 + 59))
    p1 = ctx.last_close_before(ctx.at(days, signal_minute))
    d = np.sign(p1 - p0)
    keep = ~np.isnan(d) & (d != 0)
    td = days[keep]
    return intents(ctx, td, ctx.at(td, 15 * 60 + 30), d[keep].astype(int), td, ctx.close_ns(td),
                   ctx.last_close_before(ctx.at(td, 15 * 60 + 30)))


def overnight(ctx: Ctx) -> pd.DataFrame:
    """#6: long from the close to the next trading day's open."""
    td = _entry_days(ctx)
    nxt = ctx.shift_days(td, 1)
    placed = ctx.close_ns(td)
    return intents(ctx, td, placed, np.ones(len(td), int), nxt, ctx.at(nxt, RTH_OPEN), ctx.last_close_before(placed))


def _gaps(ctx: Ctx) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """Days with a measurable gap: (days, previous 15:59 close, 09:30 open).  Orders go in at 09:31, once the open is known."""
    days = _entry_days(ctx)
    p0 = ctx.close_of_bar(ctx.at(ctx.shift_days(days, -1), 15 * 60 + 59))
    op = ctx.open_of_bar(ctx.at(days, RTH_OPEN))
    gap = op - p0
    keep = ~np.isnan(gap) & (np.abs(gap) >= ctx.min_risk(ctx.atr_on(days)))
    return days[keep], p0[keep], op[keep]


def gap_fade(ctx: Ctx) -> pd.DataFrame:
    """#7: fade the gap; target the previous close, stop as far beyond the open as the gap."""
    td, p0, op = _gaps(ctx)
    gap = op - p0
    d = -np.sign(gap).astype(int)
    return intents(ctx, td, ctx.at(td, RTH_OPEN + 1), d, td, ctx.close_ns(td), op, stop=op + gap, target=p0)


def gap_go(ctx: Ctx) -> pd.DataFrame:
    """#8: trade in the gap's direction; stop at the previous close, out at the close."""
    td, p0, op = _gaps(ctx)
    d = np.sign(op - p0).astype(int)
    return intents(ctx, td, ctx.at(td, RTH_OPEN + 1), d, td, ctx.close_ns(td), op, stop=p0)
