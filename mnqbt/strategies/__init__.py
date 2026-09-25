"""Candidate strategies from published research, declared in STRATEGIES.md before any backtest.

Each entry lists the rule builders it is made of and how their orders run:
``each``   every intent runs on its own (reversals and back-to-back holds, where
           one position ends exactly when the next begins);
``single`` one position at a time: an intent placed while a position is open is
           skipped (the engine's ``simulate``).
``regime`` keeps only the builder's intents on days of that volatility regime.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Callable

import pandas as pd

from mnqbt.strategies.common import Ctx
from mnqbt.strategies.intraday import gap_fade, gap_go, intraday_momentum, opening_range, overnight
from mnqbt.strategies.monthly import pre_holiday, sma10m, tsmom, turn_of_month
from mnqbt.strategies.vwap import vwap_reversion, vwap_trend


@dataclass(frozen=True)
class Part:
    build: Callable[[Ctx], pd.DataFrame]
    mode: str = "each"            # each | single
    regime: str | None = None     # calm | normal | volatile


@dataclass(frozen=True)
class Strategy:
    name: str
    family: str
    source: str
    parts: tuple[Part, ...]
    r_unit: str                   # what 1R is


STOP_R, ATR_R = "stop distance", "1 daily ATR"
STRATEGIES: tuple[Strategy, ...] = (
    Strategy("orb5", "Opening range", "Zarattini, Barbon & Aziz (2023)", (Part(partial(opening_range, minutes=5)),), STOP_R),
    Strategy("orb15", "Opening range", "as orb5, 15-min range", (Part(partial(opening_range, minutes=15)),), STOP_R),
    Strategy("orb30", "Opening range", "as orb5, 30-min range", (Part(partial(opening_range, minutes=30)),), STOP_R),
    Strategy("im_first_half_hour", "Intraday momentum", "Gao, Han, Li & Zhou (2018)",
             (Part(partial(intraday_momentum, signal_minute=10 * 60)),), ATR_R),
    Strategy("im_rest_of_day", "Intraday momentum", "Baltussen, Da, Lammers & Martens (2021)",
             (Part(partial(intraday_momentum, signal_minute=15 * 60 + 30)),), ATR_R),
    Strategy("overnight", "Overnight drift", "Cliff, Cooper & Gulen (2008); Boyarchenko et al. (2023)", (Part(overnight),), ATR_R),
    Strategy("gap_fade", "Gap", "plainest rule", (Part(gap_fade),), STOP_R),
    Strategy("gap_go", "Gap", "plainest rule", (Part(gap_go),), STOP_R),
    Strategy("vwap_trend", "VWAP", "Zarattini & Aziz (2023)", (Part(vwap_trend),), ATR_R),
    Strategy("vwap_reversion", "VWAP", "plainest rule (2σ / 3σ bands)", (Part(vwap_reversion, "single"),), STOP_R),
    Strategy("vwap_regime", "VWAP × volatility", "#9 on volatile days, #10 on calm days",
             (Part(vwap_trend, regime="volatile"), Part(vwap_reversion, "single", regime="calm")), "ATR (trend) / stop (reversion)"),
    Strategy("tsmom", "Trend following", "Moskowitz, Ooi & Pedersen (2012)", (Part(tsmom),), ATR_R),
    Strategy("sma10m", "Trend following", "Faber (2007)", (Part(sma10m),), ATR_R),
    Strategy("turn_of_month", "Calendar", "Ariel (1987); McConnell & Xu (2008)", (Part(turn_of_month),), ATR_R),
    Strategy("pre_holiday", "Calendar", "Ariel (1990); Lakonishok & Smidt (1988)", (Part(pre_holiday),), ATR_R),
)
BY_NAME = {s.name: s for s in STRATEGIES}


def build(strategy: Strategy, ctx: Ctx) -> list[tuple[Part, pd.DataFrame]]:
    """The intents of each part of ``strategy`` (regime parts filtered to their days)."""
    out = []
    for part in strategy.parts:
        it = part.build(ctx)
        if part.regime is not None:
            it = it[it["vol_state"] == part.regime].reset_index(drop=True)
        out.append((part, it))
    return out
