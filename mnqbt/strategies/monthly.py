"""Monthly trend following and calendar effects (STRATEGIES.md #12-15).  Every position is opened and
closed at "the close" (16:00, or the last bar's open on an early-close day)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.strategies.common import Ctx, exchange_closures, intents


def _month_ends(ctx: Ctx) -> pd.DatetimeIndex:
    """Last exchange trading day of each month, from the calendar (a day whose next trading day is in
    another month), from the data's first month to a couple of months past its end."""
    days = ctx.days
    ends = days[:-1][days.month[:-1] != days.month[1:]]
    return ends[(ends >= ctx.first_day - pd.Timedelta(days=31)) & (ends <= ctx.last_day + pd.Timedelta(days=62))]


def _close_price(ctx: Ctx, tdates: pd.DatetimeIndex) -> np.ndarray:
    """The last price before "the close" (the 15:59 close on a normal day)."""
    return ctx.last_close_before(ctx.close_ns(tdates))


def _monthly(ctx: Ctx, ends: pd.DatetimeIndex, d: np.ndarray) -> pd.DataFrame:
    """Hold from each month end's close to the next month end's close in direction ``d`` (0 = no trade)."""
    nxt = ends[1:]
    ends, d = ends[:-1], d[:-1]
    keep = (d != 0) & ctx.can_enter(ends)
    e, x = ends[keep], nxt[keep]
    placed = ctx.close_ns(e)
    return intents(ctx, e, placed, d[keep], x, ctx.close_ns(x), ctx.last_close_before(placed))


def tsmom(ctx: Ctx) -> pd.DataFrame:
    """#12: sign of the 12-month change at each month end, held one month."""
    ends = _month_ends(ctx)
    p = _close_price(ctx, ends)
    d = np.sign(p - np.r_[np.full(12, np.nan), p[:-12]])
    return _monthly(ctx, ends, np.nan_to_num(d).astype(int))


def sma10m(ctx: Ctx) -> pd.DataFrame:
    """#13: long for the next month when the month-end close is above the mean of the last 10 month-end closes."""
    ends = _month_ends(ctx)
    p = pd.Series(_close_price(ctx, ends))
    sma = p.rolling(10, min_periods=10).mean()
    return _monthly(ctx, ends, (p > sma).to_numpy().astype(int))


def turn_of_month(ctx: Ctx) -> pd.DataFrame:
    """#14: long from the close of the second-to-last trading day of the month to the close of the
    third trading day of the next month."""
    ends = _month_ends(ctx)
    entry = ctx.shift_days(ends, -1)
    exit_ = ctx.shift_days(ends, 3)
    keep = ctx.can_enter(entry)
    e, x = entry[keep], exit_[keep]
    placed = ctx.close_ns(e)
    return intents(ctx, e, placed, np.ones(len(e), int), x, ctx.close_ns(x), ctx.last_close_before(placed))


def pre_holiday(ctx: Ctx) -> pd.DataFrame:
    """#15: long from the close of the day before the pre-holiday day to the close of the pre-holiday day
    (the last trading day before a scheduled full closure)."""
    hol = exchange_closures(ctx.first_day.year, ctx.last_day.year + 1, scheduled_only=True)
    hol = hol[hol.dayofweek < 5]
    pre = ctx.shift_days(hol, -1)                    # last trading day before the holiday
    pre = pre[(pre >= ctx.first_day) & (pre <= ctx.last_day + pd.Timedelta(days=10))].unique()
    entry = ctx.shift_days(pre, -1)
    keep = ctx.can_enter(entry)
    e, x = entry[keep], pre[keep]
    placed = ctx.close_ns(e)
    return intents(ctx, e, placed, np.ones(len(e), int), x, ctx.close_ns(x), ctx.last_close_before(placed))
