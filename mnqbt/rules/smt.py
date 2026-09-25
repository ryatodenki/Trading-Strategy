"""Triggers: MNQ swing points, tagged with SMT divergence vs MES and key-level proximity.

Every confirmed MNQ swing on ``smt.timeframe`` is a candidate trigger:
a swing HIGH is a potential bearish reversal, a swing LOW a bullish one.
Two independent yes/no tags are attached, so the backtest can require either,
both, or neither (Step 3 "remove one condition"):

SMT, ``smt.mode: session`` (bearish case; bullish mirrors with lows):
    L_MNQ, L_MES = the same session / prior-day high on each index (e.g. the
                   London high), as known at the start of swing bar j
    MNQ took it:  high_MNQ[j] - L_MNQ  in [min_size, tolerance]
    MES took it:  max(high_MES[j-w .. j+w]) - L_MES >= min_size
    SMT  <=>  MNQ took its level and MES did not, or MES took its level and
              MNQ's swing stopped at most ``tolerance`` short of its own
    e.g. both indices made a London high; in NY only one of them takes it out.

SMT, ``smt.mode: swing`` (the older 5m version):
    p  = previous MNQ swing high, between ``min_separation_bars`` and
         ``lookback_bars`` bars before the current swing high j
    MNQ higher high:  high_MNQ[j] > high_MNQ[p]
    MES higher high:  max(high_MES[j-w .. j+w]) > max(high_MES[p-w .. p+w])
    SMT  <=>  exactly one of the two made a higher high   ("or vice versa")
              and that one beat its previous high by >= smt.min_size

min_size and tolerance are measured in each index's own points and daily ATR;
w = align_window_bars, capped at swing_n so nothing after confirmation is used.

Key level (``levels.mode``):
  near  : |MNQ swing extreme - nearest key level| <= tolerance
  sweep : the swing extreme traded through a key level by > 0 and <= tolerance
          (the level reported is the swept one closest to the extreme)
using the level table as it stood at the START of the SMT's first swing p (so
neither swing of the pair can be the level, e.g. a "day high" set by p); for a
swing with no previous swing in range, at the start of the swing bar itself.
High-type levels for swing highs, low-type for lows.

Known at: close of bar j + swing_n (the swing's confirmation).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.config import get, resolve_dist
from mnqbt.rules.levels import SESSION_NAMES, level_columns, nearest_level
from mnqbt.rules.swings import swing_flags


def _centered_max(x: np.ndarray, w: int) -> np.ndarray:
    return pd.Series(x).rolling(2 * w + 1, center=True, min_periods=1).max().to_numpy()


def _centered_min(x: np.ndarray, w: int) -> np.ndarray:
    return pd.Series(x).rolling(2 * w + 1, center=True, min_periods=1).min().to_numpy()


def _swept(levels: pd.DataFrame, rows: np.ndarray, cols: list[str], price: np.ndarray, side: int,
           tol: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Name and depth of the level ``price`` traded through by > 0 and <= ``tol`` (the shallowest if several)."""
    if not cols:
        return np.full(len(rows), "", dtype=object), np.full(len(rows), np.nan)
    beyond = side * (price[:, None] - levels[cols].to_numpy(float)[rows])
    with np.errstate(invalid="ignore"):
        ok = (beyond > 1e-9) & (beyond <= tol[:, None])
    depth = np.where(ok, beyond, np.inf)
    best = depth.argmin(axis=1)
    d = depth[np.arange(len(rows)), best]
    hit = np.isfinite(d)
    return np.where(hit, np.array(cols, dtype=object)[best], ""), np.where(hit, d, np.nan)


def _session_smt(levels: pd.DataFrame, levels_b: pd.DataFrame, j: np.ndarray, cols: list[str], side: int,
                 a_now: np.ndarray, b_now: np.ndarray, tol: np.ndarray, min_a: np.ndarray, min_b: np.ndarray):
    """Session SMT at swings ``j``: (smt, leader, level name, MNQ level, MES level); the level nearest MNQ's extreme wins."""
    if not cols:
        empty = np.full(len(j), np.nan)
        return np.zeros(len(j), bool), np.full(len(j), "", dtype=object), np.full(len(j), "", dtype=object), empty, empty
    la, lb = levels[cols].to_numpy(float)[j], levels_b[cols].to_numpy(float)[j]
    a_by, b_by = side * (a_now[:, None] - la), side * (b_now[:, None] - lb)
    with np.errstate(invalid="ignore"):
        a_took = (a_by >= min_a[:, None] - 1e-9) & (a_by <= tol[:, None])
        a_short = (a_by <= 0) & (a_by >= -tol[:, None])     # MNQ stopped at most `tol` short of its level
        b_took, b_not = b_by >= min_b[:, None] - 1e-9, b_by <= 0
    mnq_leads, mes_leads = a_took & b_not, b_took & a_short
    best = np.where(mnq_leads | mes_leads, np.abs(a_by), np.inf).argmin(axis=1)
    r = np.arange(len(j))
    smt = (mnq_leads | mes_leads)[r, best]
    leader = np.where(smt, np.where(mnq_leads[r, best], "MNQ", "MES"), "")
    name = np.where(smt, np.array(cols, dtype=object)[best], "")
    return smt, leader, name, np.where(smt, la[r, best], np.nan), np.where(smt, lb[r, best], np.nan)


def session_smt_columns(cfg: dict, side: int) -> list[str]:
    """Levels a session SMT can use: the same level exists on both indices at the same time."""
    use, s = set(get(cfg, "rules.smt.levels")), "h" if side > 0 else "l"
    return (["pd" + s] if "prior_day" in use else []) + ([f"{n}_{s}" for n in SESSION_NAMES] if "sessions" in use else [])


def detect_triggers(a: pd.DataFrame, b: pd.DataFrame, levels: pd.DataFrame, atr: np.ndarray, atr_b: np.ndarray,
                    cfg: dict, levels_b: pd.DataFrame | None = None) -> pd.DataFrame:
    """``a`` = MNQ bars, ``b`` = MES bars reindexed onto ``a`` (NaN where missing); ``atr`` / ``atr_b`` their daily ATRs;
    ``levels_b`` = MES level table on ``a``'s rows (needed for ``smt.mode: session``)."""
    s = get(cfg, "rules.smt")
    session = s["mode"] == "session"
    if session and levels_b is None:
        raise ValueError("smt.mode 'session' needs the MES level table (levels_b)")
    n = int(s["swing_n"])
    w = min(int(s["align_window_bars"]), n)
    lookback, min_sep = int(s["lookback_bars"]), int(s["min_separation_bars"])
    tol = resolve_dist(get(cfg, "rules.levels.tolerance"), atr)
    min_a, min_b = resolve_dist(s["min_size"], atr), resolve_dist(s["min_size"], atr_b)

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
        # the index that made the new extreme must beat its previous one by at least min_size
        with np.errstate(invalid="ignore"):
            big_enough = np.where(a_better, side * (a_now - a_prev) >= min_a[j] - 1e-9,
                                  side * (b_now - b_prev) >= min_b[j] - 1e-9)
        smt = valid & (a_better != b_better) & big_enough
        leader = np.where(smt, np.where(a_better, "MNQ", "MES"), "")
        smt_name, smt_la, smt_lb = np.full(len(j), "", dtype=object), np.full(len(j), np.nan), np.full(len(j), np.nan)
        if session:
            smt, leader, smt_name, smt_la, smt_lb = _session_smt(levels, levels_b, j, session_smt_columns(cfg, side), side,
                                                                 a_now, b_now, tol[j], min_a[j], min_b[j])

        core_cols = level_columns(cfg, side, include_value_area=False)
        va_cols = ["vah" if side > 0 else "val"]
        lv_row = np.where(has_p, p, j)       # levels that existed before the SMT's first swing
        core_name, core_dist = nearest_level(levels, lv_row, core_cols, a_now)
        va_name, va_dist = nearest_level(levels, lv_row, va_cols, a_now)
        t = tol[j]
        # sweep: the swing traded THROUGH a level (by at least one tick, at most the tolerance)
        sw_core_name, sw_core_depth = _swept(levels, lv_row, core_cols, a_now, side, t)
        sw_va_name, sw_va_depth = _swept(levels, lv_row, va_cols, a_now, side, t)
        frames.append(
            pd.DataFrame(
                {
                    "dir": -side,                      # swing high -> short setup
                    "pos": j,
                    "extreme": a_now,
                    "start_ns": start[j],
                    "known_ns": known[j + n],
                    "prev_pos": p,
                    "level_pos": lv_row,
                    "prev_extreme": np.where(has_p, a_prev, np.nan),
                    "pair_now": b_now,
                    "pair_prev": np.where(has_p, b_prev, np.nan),
                    "smt": smt,
                    "smt_leader": leader,
                    "smt_level": smt_name,             # session mode: the level both indices were tested at
                    "smt_level_a": smt_la,
                    "smt_level_b": smt_lb,
                    "level_core": core_name,
                    "dist_core": core_dist,
                    "near_core": core_dist <= t,
                    "level_va": va_name,
                    "dist_va": va_dist,
                    "near_va": va_dist <= t,
                    "sweep_core": sw_core_name != "",
                    "sweep_va": sw_va_name != "",
                    "sweep_level_core": sw_core_name,
                    "sweep_depth_core": sw_core_depth,
                    "sweep_level_va": sw_va_name,
                    "sweep_depth_va": sw_va_depth,
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
