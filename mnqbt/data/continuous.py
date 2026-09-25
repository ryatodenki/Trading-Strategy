"""Continuous-contract construction with explicit roll schedule and back-adjustment.

Input is a frame of *per-contract* 1m bars (UTC index = bar open, columns
``symbol, open, high, low, close, volume``), e.g. a Databento ``parent``
request, FirstRate individual-contract files, or NinjaTrader exports.

Why additive back-adjustment: every rule in this project works in points
(FVG size, distance to a level, stop distance, P&L).  Adding the roll gap to
all older bars keeps every point distance exact, including prior-day levels
that straddle a roll.  Trades never straddle a roll because rolls happen at
the trading-day boundary and all positions are flat by ``flatten_time``.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from mnqbt.config import get
from mnqbt.data.calendar import parse_symbol
from mnqbt.data.sessions import trading_dates

log = logging.getLogger(__name__)
PRICE_COLS = ["open", "high", "low", "close"]


def outright_contracts(df: pd.DataFrame, root: str | None = None) -> pd.DataFrame:
    """Table of outright contracts in ``df``: symbol, root, expiry."""
    first_seen = df.groupby("symbol", observed=True).apply(lambda g: g.index.min(), include_groups=False)
    rows = []
    for sym, ts in first_seen.items():
        parsed = parse_symbol(str(sym), ts.date())
        if parsed is None:
            continue
        r, expiry = parsed
        if root is not None and r != root:
            continue
        rows.append((str(sym), r, pd.Timestamp(expiry)))
    return pd.DataFrame(rows, columns=["symbol", "root", "expiry"]).sort_values("expiry").reset_index(drop=True)


def daily_volume(df: pd.DataFrame, tdate: pd.DatetimeIndex) -> pd.DataFrame:
    return (
        pd.DataFrame({"tdate": tdate, "symbol": df["symbol"].astype(str).to_numpy(), "volume": df["volume"].to_numpy()})
        .groupby(["tdate", "symbol"])["volume"].sum().unstack("symbol").fillna(0.0)
    )


def roll_schedule(df: pd.DataFrame, cfg: dict, contracts: pd.DataFrame, tdate: pd.DatetimeIndex) -> pd.DataFrame:
    """Which expiry is 'front' on each trading date.  Returns tdate, expiry, symbol."""
    rule = get(cfg, "continuous.roll_rule")
    vol = daily_volume(df, tdate)
    sym_for_exp = dict(zip(contracts["expiry"], contracts["symbol"]))
    exp_for_sym = dict(zip(contracts["symbol"], contracts["expiry"]))
    vol = vol[[c for c in vol.columns if c in exp_for_sym]]
    dates = vol.index
    chosen: list[pd.Timestamp] = []

    if rule == "calendar":
        days = int(get(cfg, "continuous.roll_days_before_expiry"))
        roll_dates = contracts["expiry"] - pd.Timedelta(days=days)
        for d in dates:
            eligible = contracts.loc[roll_dates > d, "expiry"]
            chosen.append(eligible.iloc[0] if len(eligible) else contracts["expiry"].iloc[-1])
    elif rule == "volume":
        current = None
        prev_row = None
        for d, row in vol.iterrows():
            if current is None:
                current = exp_for_sym[row.idxmax()]
            elif prev_row is not None:
                later = [s for s in prev_row.index if exp_for_sym[s] > current and prev_row[s] > 0]
                cur_sym = sym_for_exp.get(current)
                cur_vol = prev_row.get(cur_sym, 0.0)
                if later:
                    best = max(later, key=lambda s: prev_row[s])
                    if prev_row[best] > cur_vol:
                        current = exp_for_sym[best]
            chosen.append(current)
            prev_row = row
    else:
        raise ValueError(f"unknown roll_rule {rule!r}")

    out = pd.DataFrame({"tdate": dates, "expiry": chosen})
    out["symbol"] = out["expiry"].map(sym_for_exp)
    return out


def _last_common_close(bars_old: pd.DataFrame, bars_new: pd.DataFrame) -> tuple[pd.Timestamp, float, float] | None:
    common = bars_old.index.intersection(bars_new.index)
    if len(common) == 0:
        return None
    t = common.max()
    return t, float(bars_old.at[t, "close"]), float(bars_new.at[t, "close"])


def build_continuous(
    df: pd.DataFrame,
    cfg: dict,
    root: str | None = None,
    forced_schedule: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Stitch per-contract bars into one back-adjusted series.

    Returns (continuous_bars, roll_table, schedule).  ``forced_schedule`` (a
    frame with tdate/expiry) makes this instrument roll on exactly the same
    dates as another one — used so MES rolls with MNQ.
    """
    contracts = outright_contracts(df, root)
    if contracts.empty:
        raise ValueError("no outright contracts found in input")
    df = df[df["symbol"].astype(str).isin(set(contracts["symbol"]))]
    key = pd.MultiIndex.from_arrays([df.index, df["symbol"].astype(str)])
    df = df[~key.duplicated(keep="last")]
    tdate = trading_dates(df.index, cfg)

    if forced_schedule is not None:
        sym_for_exp = dict(zip(contracts["expiry"], contracts["symbol"]))
        sched = forced_schedule[["tdate", "expiry"]].copy()
        sched["symbol"] = sched["expiry"].map(sym_for_exp)
        missing = sched["symbol"].isna()
        if missing.any():
            log.warning("forced schedule references %d dates with no matching contract", int(missing.sum()))
            sched = sched[~missing]
    else:
        sched = roll_schedule(df, cfg, contracts, tdate)

    codes, uniques = pd.factorize(df["symbol"].astype(str))
    code_of = {s: i for i, s in enumerate(uniques)}
    by_symbol, tdate_by_symbol = {}, {}
    for s in sched["symbol"].unique():
        rows = np.flatnonzero(codes == code_of[s])
        by_symbol[s] = df.iloc[rows].drop(columns="symbol")
        tdate_by_symbol[s] = tdate[rows]

    # Pieces of the stitched series, one per contiguous run of the same contract.
    sched = sched.sort_values("tdate").reset_index(drop=True)
    run_id = (sched["symbol"] != sched["symbol"].shift()).cumsum()
    pieces, rolls = [], []
    prev_sym = None
    for _, run in sched.groupby(run_id, sort=True):
        sym = run["symbol"].iloc[0]
        bars = by_symbol[sym]
        td = tdate_by_symbol[sym]
        mask = np.isin(td.values, run["tdate"].values)
        piece = bars[mask].copy()
        piece["contract"] = sym
        pieces.append(piece)
        if prev_sym is not None:
            roll_day = run["tdate"].iloc[0]
            old, new = by_symbol[prev_sym], bars
            old_td, new_td = tdate_by_symbol[prev_sym], td
            found = None
            for back in range(1, 6):  # search the last few days before the roll for a common minute
                day = roll_day - pd.Timedelta(days=back)
                found = _last_common_close(old[old_td == day], new[new_td == day])
                if found:
                    break
            if found:
                t, c_old, c_new = found
                gap, method = c_new - c_old, "last_common_minute"
            else:
                last_old = old[old_td < roll_day]
                first_new = piece
                t = last_old.index.max() if len(last_old) else pd.NaT
                gap = float(first_new["open"].iloc[0] - last_old["close"].iloc[-1]) if len(last_old) and len(first_new) else 0.0
                method = "jump_fallback"
                log.warning("roll %s->%s on %s: no common minute, using raw jump", prev_sym, sym, roll_day.date())
            rolls.append({"roll_tdate": roll_day, "old": prev_sym, "new": sym, "gap_ts": t, "gap": gap, "method": method})
        prev_sym = sym

    cont = pd.concat(pieces).sort_index()
    cont = cont[~cont.index.duplicated(keep="last")]
    roll_table = pd.DataFrame(rolls, columns=["roll_tdate", "old", "new", "gap_ts", "gap", "method"])

    cont_td = trading_dates(cont.index, cfg)
    offset = np.zeros(len(cont))
    if get(cfg, "continuous.adjustment") == "additive" and len(roll_table):
        # Each bar gets the sum of all gaps of rolls that happen after its trading date.
        r_dates = roll_table["roll_tdate"].to_numpy()
        gaps = roll_table["gap"].to_numpy()
        suffix = np.concatenate([np.cumsum(gaps[::-1])[::-1], [0.0]])
        pos = np.searchsorted(r_dates, cont_td.values, side="right")
        offset = suffix[pos]
    cont[PRICE_COLS] = cont[PRICE_COLS].to_numpy() + offset[:, None]
    cont["adj"] = offset
    return cont, roll_table, sched


def splice(older: pd.DataFrame, newer: pd.DataFrame, splice_tdate: str | pd.Timestamp, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Join a proxy series (NQ/ES) before ``splice_tdate`` onto the real series (MNQ/MES).

    The older series is shifted by the price difference at the last minute
    both traded before the splice, so the joined series is continuous.
    """
    d = pd.Timestamp(splice_tdate)
    old_td = trading_dates(older.index, cfg)
    new_td = trading_dates(newer.index, cfg)
    old_part = older[old_td < d]
    new_part = newer[new_td >= d]
    overlap_old = older[old_td < d]
    overlap_new = newer[new_td < d]
    found = _last_common_close(overlap_old, overlap_new)
    if found is None:
        raise ValueError(
            "splice needs overlapping data: download the newer instrument from a few weeks before the splice date"
        )
    t, c_old, c_new = found
    gap = c_new - c_old
    # Same instrument family, so the RAW prices should agree to within a tick or two;
    # most of `gap` is just the newer series' own back-adjustment.
    raw_diff = (c_new - float(overlap_new.at[t, "adj"])) - (c_old - float(overlap_old.at[t, "adj"]))
    old_part = old_part.copy()
    old_part[PRICE_COLS] = old_part[PRICE_COLS].to_numpy() + gap
    old_part["adj"] = old_part["adj"] + gap
    joined = pd.concat([old_part, new_part]).sort_index()
    return joined, {"splice_tdate": d, "gap_ts": t, "gap": gap, "raw_price_diff": raw_diff}
