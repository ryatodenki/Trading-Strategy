"""Triggers: MNQ swing points, tagged with SMT divergence vs MES and key-level proximity.

Every confirmed MNQ swing on ``smt.timeframe`` is a candidate trigger:
a swing HIGH is a potential bearish reversal, a swing LOW a bullish one.
Two independent yes/no tags are attached, so the backtest can require either,
both, or neither (Step 3 "remove one condition"):

SMT (bearish case; bullish mirrors with lows):
    p  = previous MNQ swing high, between ``min_separation_bars`` and
         ``lookback_bars`` bars before the current swing high j
    MNQ higher high:  high_MNQ[j] > high_MNQ[p]
    MES higher high:  max(high_MES[j-w .. j+w]) > max(high_MES[p-w .. p+w])
    SMT  <=>  exactly one of the two made a higher high   ("or vice versa")
    (w = align_window_bars, capped at swing_n so nothing after confirmation is used)

Key level (``levels.mode``):
  near  : |MNQ swing extreme - nearest key level| <= tolerance
  sweep : the swing extreme traded through a key level by > 0 and <= tolerance
using the level table as it stood at the START of the swing bar (so the swing
cannot create its own level).  High-type levels for swing highs, low-type for lows.

Known at: close of bar j + swing_n (the swing's confirmation).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.config import get, resolve_dist
from mnqbt.rules.levels import level_columns, nearest_level
from mnqbt.rules.swings import swing_flags


def _centered_max(x: np.ndarray, w: int) -> np.ndarray:
    return pd.Series(x).rolling(2 * w + 1, center=True, min_periods=1).max().to_numpy()


def _centered_min(x: np.ndarray, w: int) -> np.ndarray:
    return pd.Series(x).rolling(2 * w + 1, center=True, min_periods=1).min().to_numpy()


def detect_triggers(a: pd.DataFrame, b: pd.DataFrame, levels: pd.DataFrame, atr: np.ndarray, cfg: dict) -> pd.DataFrame:
    """``a`` = MNQ bars, ``b`` = MES bars reindexed onto ``a`` (NaN where missing)."""
    s = get(cfg, "rules.smt")
    n = int(s["swing_n"])
    w = min(int(s["align_window_bars"]), n)
    lookback, min_sep = int(s["lookback_bars"]), int(s["min_separation_bars"])
    tol = resolve_dist(get(cfg, "rules.levels.tolerance"), atr)

    ha, la = a["high"].to_numpy(float), a["low"].to_numpy(float)
    hb, lb = b["high"].to_numpy(float), b["low"].to_numpy(float)
    is_sh, is_sl = swing_flags(ha, la, n)
    start, known = a["start_ns"].to_numpy(), a["known_ns"].to_numpy()

    frames = []
    for side, flags, xa, xb_win, better in (
        (1, is_sh, ha, _centered_max(hb, w), np.greater),
        (-1, is_sl, la, _centered_min(lb, w), np.less),
    ):
        j = np.flatnonzero(flags)
        cand = np.searchsorted(j, j - min_sep, side="right") - 1
        has_p = cand >= 0
        p = np.where(has_p, j[np.maximum(cand, 0)], -1)
        has_p &= (j - p) <= lookback
        pp = np.maximum(p, 0)
        a_now, a_prev = xa[j], xa[pp]
        b_now, b_prev = xb_win[j], xb_win[pp]
        with np.errstate(invalid="ignore"):
            a_better = better(a_now, a_prev)
            b_better = better(b_now, b_prev)
        valid = has_p & ~np.isnan(b_now) & ~np.isnan(b_prev)
        smt = valid & (a_better != b_better)

        core_cols = level_columns(cfg, side, include_value_area=False)
        va_cols = ["vah" if side > 0 else "val"]
        core_name, core_dist = nearest_level(levels, j, core_cols, a_now)
        va_name, va_dist = nearest_level(levels, j, va_cols, a_now)
        t = tol[j]
        # sweep: the swing traded THROUGH a level (by at least one tick, at most the tolerance)
        def swept(cols):
            if not cols:
                return np.zeros(len(j), bool)
            v = levels[cols].to_numpy(float)[j]
            beyond = side * (a_now[:, None] - v)
            with np.errstate(invalid="ignore"):
                return ((beyond > 1e-9) & (beyond <= t[:, None])).any(axis=1)
        frames.append(
            pd.DataFrame(
                {
                    "dir": -side,                      # swing high -> short setup
                    "pos": j,
                    "extreme": a_now,
                    "start_ns": start[j],
                    "known_ns": known[j + n],
                    "prev_pos": p,
                    "prev_extreme": np.where(has_p, a_prev, np.nan),
                    "pair_now": b_now,
                    "pair_prev": np.where(has_p, b_prev, np.nan),
                    "smt": smt,
                    "smt_leader": np.where(smt, np.where(a_better, "MNQ", "MES"), ""),
                    "level_core": core_name,
                    "dist_core": core_dist,
                    "near_core": core_dist <= t,
                    "level_va": va_name,
                    "dist_va": va_dist,
                    "near_va": va_dist <= t,
                    "sweep_core": swept(core_cols),
                    "sweep_va": swept(va_cols),
                    "tol": t,
                    "atr": atr[j],
                    "tdate": a["tdate"].to_numpy()[j],
                }
            )
        )
    out = pd.concat(frames, ignore_index=True)
    out["near_core"] = out["near_core"].fillna(False).astype(bool)
    out["near_va"] = out["near_va"].fillna(False).astype(bool)
    return out.sort_values(["known_ns", "dir"], kind="stable").reset_index(drop=True)
