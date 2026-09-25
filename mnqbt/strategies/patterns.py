"""The pattern hypotheses declared in PATTERNS.md, as order intents for the harness engine.

Every trade's R unit is 10% of the entry day's daily ATR (``risk_unit``), whether or
not the rule has a stop, so all hypotheses are comparable and can be pooled.  As in
the rest of strategies/, decisions use only bars that started before the order time,
and order times come from the clock and the calendar.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Callable

import numpy as np
import pandas as pd

from mnqbt.config import get
from mnqbt.rules.news import load_news
from mnqbt.strategies.common import RTH_CLOSE, RTH_OPEN, Ctx, intents
from mnqbt.timeutil import NS_PER_MIN

R_ATR = 0.10                     # 1R = 10% of the daily ATR
DAY_START = 18 * 60              # trading day starts 18:00 ET


def _tod(et_minute: np.ndarray) -> np.ndarray:
    """Minutes since the 18:00 start of the trading day."""
    return (np.asarray(et_minute) - DAY_START) % 1440


def _unit(it: pd.DataFrame) -> pd.DataFrame:
    it["risk_unit"] = R_ATR * it["atr"]
    return it


def _entry_days(ctx: Ctx) -> pd.DatetimeIndex:
    td = ctx.trading_days()
    return td[ctx.can_enter(td)]


# ---------------------------------------------------------------------------- time of day (#1-4)
def timed(ctx: Ctx, from_min: int, to_min: int, entry_min: int, exit_min: int | None, sign: int) -> pd.DataFrame:
    """Direction = ``sign`` x sign(close of the bar starting ``to_min`` - 1 minute - open of the bar at
    ``from_min``); enter at ``entry_min``, exit at ``exit_min`` (None = the close)."""
    days = _entry_days(ctx)
    o = ctx.open_of_bar(ctx.at(days, from_min))
    c = ctx.close_of_bar(ctx.at(days, to_min - 1))
    d = sign * np.sign(c - o)
    keep = np.isfinite(d) & (d != 0)
    td = days[keep]
    exit_ns = ctx.close_ns(td) if exit_min is None else ctx.at(td, exit_min)
    return _unit(intents(ctx, td, ctx.at(td, entry_min), d[keep].astype(int), td, exit_ns, c[keep]))


open_drive = partial(timed, from_min=RTH_OPEN, to_min=RTH_OPEN + 5, entry_min=RTH_OPEN + 5, exit_min=10 * 60, sign=1)
london_ny = partial(timed, from_min=3 * 60, to_min=RTH_OPEN, entry_min=RTH_OPEN, exit_min=11 * 60 + 30, sign=1)
lunch_reversal = partial(timed, from_min=RTH_OPEN, to_min=12 * 60, entry_min=12 * 60, exit_min=13 * 60 + 30, sign=-1)
close_continuation = partial(timed, from_min=RTH_OPEN, to_min=15 * 60, entry_min=15 * 60, exit_min=None, sign=1)


# ---------------------------------------------------------------------------- sweeps (#5-7)
def sweep_reversal(ctx: Ctx, cols: tuple[str, str], known_from: int, window: tuple[int, int]) -> pd.DataFrame:
    """Fade the first 5-minute trade-through of a level (level-table columns ``cols`` = high, low) after
    it is known (ET minute ``known_from``), when that bar starts inside ``window`` and closes back inside
    the level.  Enter at the next 5-minute open, stop 1 tick beyond the sweep bar, exit after 60 minutes
    or at 16:00."""
    F, cfg, tick = ctx.F, ctx.cfg, ctx.tick
    bars = F.bars("a", "5min")
    lv = F.levels(cfg, "5min")
    start = bars["start_ns"].to_numpy(np.int64)
    tod = _tod(ctx.et_minute(start))
    day = pd.DatetimeIndex(bars["tdate"].to_numpy())
    hi, lo, cl = (bars[k].to_numpy(float) for k in ("high", "low", "close"))
    live = tod >= _tod(known_from)
    w0, w1 = _tod(window[0]), _tod(window[1])
    frames = []
    for side, col in ((1, cols[0]), (-1, cols[1])):
        L = lv[col].to_numpy(float)
        with np.errstate(invalid="ignore"):
            through = (hi >= L + tick) if side > 0 else (lo <= L - tick)
            back_inside = (cl < L) if side > 0 else (cl > L)
        rows = np.flatnonzero(live & through)
        first = pd.Series(rows).groupby(day[rows].values).first().to_numpy()   # first trade-through of each day
        k = first[(tod[first] >= w0) & (tod[first] < w1) & back_inside[first]]
        td = day[k]
        ok = ctx.can_enter(td)
        k, td = k[ok], td[ok]
        placed = start[k] + 5 * NS_PER_MIN
        flat = np.minimum(placed + 60 * NS_PER_MIN, ctx.at(td, RTH_CLOSE))
        stop = hi[k] + tick if side > 0 else lo[k] - tick
        frames.append(intents(ctx, td, placed, np.full(len(k), -side), td, flat, cl[k], stop=stop,
                              level=np.full(len(k), col)))
    return _unit(pd.concat(frames, ignore_index=True).sort_values("placed_ns", kind="stable").reset_index(drop=True))


sweep_asia = partial(sweep_reversal, cols=("asia_h", "asia_l"), known_from=3 * 60, window=(3 * 60, 12 * 60))
sweep_london = partial(sweep_reversal, cols=("london_h", "london_l"), known_from=RTH_OPEN, window=(RTH_OPEN, 15 * 60))
sweep_prior_day = partial(sweep_reversal, cols=("pdh", "pdl"), known_from=DAY_START, window=(3 * 60, 15 * 60))


# ---------------------------------------------------------------------------- filter labels (#8-9)
def news_days(cfg: dict) -> pd.DatetimeIndex:
    """CPI, FOMC and NFP dates (``rules.news.kinds``)."""
    return pd.DatetimeIndex(load_news(cfg)["date"])


def daily_trend(ctx: Ctx) -> pd.Series:
    """+1 / -1 for each trading day: the previous trading day's 15:59 close above / below the mean of
    the last 50 such closes (NaN until 50 closes exist)."""
    days = ctx.trading_days()
    c = pd.Series(ctx.close_of_bar(ctx.at(days, RTH_CLOSE - 1)), index=days).dropna()
    t = np.sign(c - c.rolling(50, min_periods=50).mean())
    pos = np.searchsorted(t.index.values, days.values, side="left") - 1     # the last close before each day
    return pd.Series(np.where(pos >= 0, t.to_numpy()[np.maximum(pos, 0)], np.nan), index=days)


# ---------------------------------------------------------------------------- registry
@dataclass(frozen=True)
class Hypothesis:
    id: str
    slug: str
    name: str
    build: Callable[[Ctx], pd.DataFrame] | None   # None for the filters
    mode: str = "each"                              # each | single (one position at a time across the rule's intents)


HYPOTHESES: tuple[Hypothesis, ...] = (
    Hypothesis("H1", "open_drive", "Open drive (09:35-10:00)", open_drive),
    Hypothesis("H2", "london_ny", "London -> NY overlap continuation (09:30-11:30)", london_ny),
    Hypothesis("H3", "lunch_reversal", "Lunch reversal (12:00-13:30)", lunch_reversal),
    Hypothesis("H4", "close_continuation", "Close continuation (15:00-16:00)", close_continuation),
    Hypothesis("H5", "sweep_asia", "Asia high/low sweep reversal", sweep_asia, "single"),
    Hypothesis("H6", "sweep_london", "London high/low sweep reversal", sweep_london, "single"),
    Hypothesis("H7", "sweep_prior_day", "Prior-day high/low sweep reversal", sweep_prior_day, "single"),
    Hypothesis("H8", "skip_news", "Skip CPI / FOMC / NFP days (filter on H1-H7)", None),
    Hypothesis("H9", "with_trend", "Trade with the daily trend (filter on H1-H7)", None),
)
RULES = tuple(h for h in HYPOTHESES if h.build is not None)
FILTERS = tuple(h for h in HYPOTHESES if h.build is None)
BY_ID = {h.id: h for h in HYPOTHESES}
