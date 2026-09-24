"""Feature computation with caching keyed by the config values each feature depends on.

Variants change only a few parameters, so bars, swings, level tables and
triggers are computed once and reused.  All features are causal (each value
carries the time it becomes known), so computing them over the full history
leaks nothing into earlier dates — tests/test_no_lookahead.py checks this.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from mnqbt.config import get, resolve_dist
from mnqbt.data.sessions import annotate, et_time_on_tdate
from mnqbt.rules.bars import resample
from mnqbt.rules.fvg import detect_fvgs
from mnqbt.rules.levels import daily_table, level_table
from mnqbt.rules.mood import chop_table
from mnqbt.rules.smt import detect_triggers
from mnqbt.rules.structure import structure_state
from mnqbt.rules.vwap import vwap
from mnqbt.timeutil import ns, to_ns_index


class Features:
    def __init__(self, cfg: dict, a1: pd.DataFrame, b1: pd.DataFrame, flags: pd.DataFrame):
        """a1 / b1: continuous 1m bars of the traded instrument and its SMT pair."""
        self.base_cfg = cfg
        self.a1 = self._prep(a1, cfg)
        self.b1 = self._prep(b1, cfg)
        self.flags = flags
        self._cache: dict = {}
        self.ts = ns(self.a1.index)

    @staticmethod
    def _prep(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
        df = to_ns_index(df)
        cols = ["open", "high", "low", "close", "volume"]
        return annotate(df[cols], cfg) if "tdate" not in df else df

    def _cached(self, name: str, cfg: dict, paths: list[str], fn):
        key = (name, json.dumps([get(cfg, p) for p in paths], default=str, sort_keys=True))
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    # -- building blocks ----------------------------------------------------
    def bars(self, which: str, tf: str) -> pd.DataFrame:
        src = self.a1 if which == "a" else self.b1
        return self._cached(f"bars_{which}_{tf}", self.base_cfg, [], lambda: resample(src, tf))

    def daily(self, cfg: dict) -> pd.DataFrame:
        return self._cached("daily", cfg, ["rules.atr_days", "rules.mood", "rules.value_area", "sessions"],
                            lambda: daily_table(self.a1, self.flags, cfg))

    def atr_for(self, cfg: dict, bars: pd.DataFrame) -> np.ndarray:
        return self.daily(cfg)["atr"].reindex(pd.DatetimeIndex(bars["tdate"].to_numpy())).to_numpy()

    def levels(self, cfg: dict, tf: str) -> pd.DataFrame:
        lv = get(cfg, "rules.levels")
        return self._cached(f"levels_{tf}", cfg, ["rules.levels", "rules.atr_days", "rules.value_area", "sessions"],
                            lambda: level_table(self.bars("a", tf), self.a1, self.daily(cfg), self.bars("a", lv["swing_timeframe"]), cfg))

    def triggers(self, cfg: dict) -> pd.DataFrame:
        tf = get(cfg, "rules.smt.timeframe")

        def make():
            a = self.bars("a", tf)
            b = self.bars("b", tf).reindex(a.index)
            return detect_triggers(a, b, self.levels(cfg, tf), self.atr_for(cfg, a), cfg)

        return self._cached("triggers", cfg, ["rules.smt", "rules.levels.use", "rules.levels.swing_timeframe", "rules.levels.swing_n",
                                             "rules.levels.swing_count", "rules.levels.tolerance", "rules.atr_days", "rules.value_area"], make)

    def fvgs(self, cfg: dict) -> pd.DataFrame:
        f = get(cfg, "rules.fvg")

        def make():
            bars = self.bars("a", f["timeframe"])
            min_size = resolve_dist(f["min_size"], self.atr_for(cfg, bars))
            return detect_fvgs(bars, f["timeframe"], min_size, int(f["max_age_bars"]))

        return self._cached("fvgs", cfg, ["rules.fvg", "rules.atr_days"], make)

    def structure(self, cfg: dict) -> pd.DataFrame:
        s = get(cfg, "rules.structure")
        return self._cached("structure", cfg, ["rules.structure"],
                            lambda: structure_state(self.bars("a", s["timeframe"]), int(s["swing_n"]), s["break_on"]))

    def chop(self, cfg: dict) -> pd.DataFrame:
        m = get(cfg, "rules.mood")
        return self._cached("chop", cfg, ["rules.mood.chop_method", "rules.mood.chop_timeframe", "rules.mood.chop_lookback",
                                          "rules.mood.er_choppy_below", "rules.mood.adx_choppy_below"],
                            lambda: chop_table(self.bars("a", m["chop_timeframe"]), m["chop_method"], int(m["chop_lookback"]),
                                               float(m["er_choppy_below"]), float(m["adx_choppy_below"])))

    def vwap(self, cfg: dict) -> np.ndarray:
        return self._cached("vwap", cfg, ["rules.vwap.anchor"], lambda: vwap(self.a1, get(cfg, "rules.vwap.anchor")))

    def flatten_ns(self, cfg: dict) -> pd.Series:
        """UTC ns of the flatten time for each trading date."""
        def make():
            td = pd.DatetimeIndex(np.unique(self.a1["tdate"].to_numpy()))
            return pd.Series(ns(et_time_on_tdate(td, get(cfg, "setup.flatten_time"), cfg)), index=td)
        return self._cached("flatten", cfg, ["setup.flatten_time", "sessions"], make)
