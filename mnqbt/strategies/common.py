"""Shared pieces for the candidate strategies declared in STRATEGIES.md.

Each strategy turns 1m bars into order intents for the harness engine
(``backtest.engine.run_order``): a market entry, an optional stop / target and a
timed exit.  Decisions use only bars that STARTED before ``placed_ns``, and entry
and exit times come from the clock and the exchange calendar, never from whether
a later bar exists.  So cutting the data at an order's placement time gives the
same decision (tests/test_strategies.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.config import get, resolve_dist
from mnqbt.data.calendar import us_holidays
from mnqbt.data.sessions import et_parts, et_time_on_tdate
from mnqbt.rules.features import Features
from mnqbt.timeutil import NS_PER_MIN, ns

RTH_OPEN, RTH_CLOSE = 9 * 60 + 30, 16 * 60  # ET minutes
UNSCHEDULED = ("Hurricane", "mourning")


def hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def exchange_closures(y0: int, y1: int, scheduled_only: bool = False) -> pd.DatetimeIndex:
    """Full-day US exchange closures (early-close days are trading days)."""
    h = us_holidays(y0, y1)
    h = h[~h["holiday"].str.contains("early close")]
    if scheduled_only:
        h = h[~h["holiday"].str.contains("|".join(UNSCHEDULED))]
    return pd.DatetimeIndex(h["date"])


class Ctx:
    """Bars, calendar and daily inputs for the strategy builders."""

    def __init__(self, F: Features, cfg: dict):
        self.F, self.cfg = F, cfg
        a = F.a1
        self.ts = F.ts
        self.o, self.h, self.l, self.c = (a[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.v = a["volume"].to_numpy(float)
        self.bar_tdate = pd.DatetimeIndex(a["tdate"].to_numpy())
        self.et_min = a["et_min"].to_numpy(int)
        daily = F.daily(cfg)
        self.atr = daily["atr"]
        self.vol_state = daily["vol_state"]
        fl = F.flags
        self.tradeable = fl["tradeable"].astype(bool)
        # early-close days: "the close" is the open of the day's last bar
        self.early_last_min = fl["last_et_min"].where(fl["early_close"].astype(bool))
        first, last = self.bar_tdate.min(), self.bar_tdate.max()
        wd = pd.bdate_range(first - pd.Timedelta(days=400), last + pd.Timedelta(days=100))
        self.days = wd.difference(exchange_closures(wd[0].year, wd[-1].year))   # exchange trading days
        self.first_day, self.last_day = first, last
        self.tick = float(get(cfg, "instruments.tick_size"))
        self.min_risk_spec = get(cfg, "setup.stop.min_risk")

    # -- calendar ----------------------------------------------------------
    def trading_days(self) -> pd.DatetimeIndex:
        """Exchange trading days covered by the data."""
        return self.days[(self.days >= self.first_day) & (self.days <= self.last_day)]

    def shift_days(self, tdates: pd.DatetimeIndex, k: int) -> pd.DatetimeIndex:
        """The k-th exchange trading day after (k > 0) or before (k < 0) each date."""
        pos = np.searchsorted(self.days.values, pd.DatetimeIndex(tdates).values) + k
        return pd.DatetimeIndex(self.days.values[np.clip(pos, 0, len(self.days) - 1)])

    def days_between(self, t0: pd.DatetimeIndex, t1: pd.DatetimeIndex) -> np.ndarray:
        return (np.searchsorted(self.days.values, pd.DatetimeIndex(t1).values)
                - np.searchsorted(self.days.values, pd.DatetimeIndex(t0).values))

    def at(self, tdates, minute: int) -> np.ndarray:
        """UTC ns of ET wall-clock ``minute`` on each trading date."""
        return ns(et_time_on_tdate(pd.DatetimeIndex(tdates), hhmm(minute), self.cfg))

    def at_minutes(self, tdates, minutes) -> np.ndarray:
        """UTC ns of ET wall-clock ``minutes`` (one per date, all before the 18:00 trading-day start)."""
        td = pd.DatetimeIndex(tdates)
        naive = td + pd.to_timedelta(np.asarray(minutes, np.int64), unit="min")
        tz = get(self.cfg, "project.timezone")
        return ns(naive.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC"))

    def et_minute(self, t_ns: np.ndarray) -> np.ndarray:
        minute, _ = et_parts(pd.DatetimeIndex(np.asarray(t_ns, np.int64).view("datetime64[ns]")).tz_localize("UTC"),
                             get(self.cfg, "project.timezone"))
        return np.asarray(minute, int)

    def close_ns(self, tdates) -> np.ndarray:
        """Time of "the close": 16:00, or the start of the last bar on an early-close day."""
        td = pd.DatetimeIndex(tdates)
        out = self.at(td, RTH_CLOSE)
        early = self.early_last_min.reindex(td).to_numpy()
        m = ~np.isnan(early)
        if m.any():
            out[m] = np.array([self.at(td[i:i + 1], int(early[i]))[0] for i in np.flatnonzero(m)])
        return out

    # -- prices --------------------------------------------------------------
    def _bar_at(self, t_ns: np.ndarray) -> np.ndarray:
        i = np.searchsorted(self.ts, t_ns, side="left")
        ok = (i < len(self.ts)) & (self.ts[np.minimum(i, len(self.ts) - 1)] == t_ns)
        return np.where(ok, i, -1)

    def close_of_bar(self, t_ns: np.ndarray) -> np.ndarray:
        """Close of the bar starting exactly at ``t_ns`` (NaN if there is none)."""
        i = self._bar_at(np.asarray(t_ns, np.int64))
        return np.where(i >= 0, self.c[np.maximum(i, 0)], np.nan)

    def open_of_bar(self, t_ns: np.ndarray) -> np.ndarray:
        i = self._bar_at(np.asarray(t_ns, np.int64))
        return np.where(i >= 0, self.o[np.maximum(i, 0)], np.nan)

    def last_close_before(self, t_ns: np.ndarray, max_age_min: int = 5) -> np.ndarray:
        """Close of the last bar that started before ``t_ns`` and at most ``max_age_min`` minutes earlier."""
        t_ns = np.asarray(t_ns, np.int64)
        i = np.searchsorted(self.ts, t_ns, side="left") - 1
        ok = (i >= 0) & (self.ts[np.maximum(i, 0)] >= t_ns - max_age_min * NS_PER_MIN)
        return np.where(ok, self.c[np.maximum(i, 0)], np.nan)

    # -- daily inputs ------------------------------------------------------
    def atr_on(self, tdates) -> np.ndarray:
        return self.atr.reindex(pd.DatetimeIndex(tdates)).to_numpy(float)

    def can_enter(self, tdates) -> np.ndarray:
        """Entry allowed: a tradeable day with an ATR."""
        td = pd.DatetimeIndex(tdates)
        return self.tradeable.reindex(td).fillna(False).to_numpy(bool) & ~np.isnan(self.atr_on(td))

    def min_risk(self, atr: np.ndarray) -> np.ndarray:
        return resolve_dist(self.min_risk_spec, atr)


INTENT_COLUMNS = [
    "placed_ns", "dir", "flatten_ns", "stop", "target", "target_src", "target_r", "risk_unit", "ref_price", "atr",
    "tdate", "exit_tdate",
]


def intents(ctx: Ctx, tdate, placed_ns, d, exit_tdate, flatten_ns, ref_price, stop=np.nan, target=np.nan,
            target_r=np.nan, **tags) -> pd.DataFrame:
    """Order intents in the engine's format.  Without a stop, 1R = one daily ATR (STRATEGIES.md)."""
    td = pd.DatetimeIndex(tdate)
    n = len(td)
    atr = ctx.atr_on(td)
    stop = np.broadcast_to(np.asarray(stop, float), n)
    target_r = np.broadcast_to(np.asarray(target_r, float), n)
    out = pd.DataFrame({
        "placed_ns": np.asarray(placed_ns, np.int64),
        "dir": np.asarray(d, int),
        "flatten_ns": np.asarray(flatten_ns, np.int64),
        "stop": stop,
        "target": np.broadcast_to(np.asarray(target, float), n),
        "target_src": np.where(np.isnan(target_r), "abs", "r_multiple"),
        "target_r": target_r,
        "risk_unit": np.where(np.isnan(stop), atr, np.nan),
        "ref_price": np.asarray(ref_price, float),
        "atr": atr,
        "tdate": td,
        "exit_tdate": pd.DatetimeIndex(exit_tdate),
        **{k: np.asarray(v) for k, v in tags.items()},
    })
    out["expire_ns"] = out["flatten_ns"]
    out["entry_type"] = "market"
    out["entry"] = np.nan
    return out.sort_values("placed_ns", kind="stable").reset_index(drop=True)
