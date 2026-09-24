"""Data validation: gaps, bad ticks, missing days, holiday/short sessions, pair alignment.

``day_flags`` is the important output: one row per trading date with the
reasons a day must not be traded.  The backtest reads it; nothing is silently
dropped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.config import get, hhmm_to_minutes
from mnqbt.data.calendar import us_holidays
from mnqbt.data.sessions import annotate
from mnqbt.timeutil import NS_PER_MIN, ns

PRICE_COLS = ["open", "high", "low", "close"]


def basic_checks(df: pd.DataFrame, tick: float, check_grid: bool = True) -> dict:
    """Row-level sanity checks.  Works on raw per-contract or continuous bars."""
    o, h, l, c = (df[k].to_numpy(float) for k in PRICE_COLS)
    bad_ohlc = (h < np.maximum(o, c)) | (l > np.minimum(o, c)) | (h < l)
    nonpos = (np.minimum.reduce([o, h, l, c]) <= 0) | np.isnan([o, h, l, c]).any(axis=0)
    key = df.index if "symbol" not in df else pd.MultiIndex.from_arrays([df.index, df["symbol"].astype(str)])
    dup = key.duplicated(keep="last")
    out = {
        "rows": int(len(df)),
        "duplicate_rows": int(dup.sum()),
        "bad_ohlc_rows": int(bad_ohlc.sum()),
        "nonpositive_or_nan_rows": int(nonpos.sum()),
        "zero_volume_rows": int((df["volume"].to_numpy() <= 0).sum()) if "volume" in df else 0,
    }
    if check_grid:
        off = np.abs(np.round(np.stack([o, h, l, c]) / tick) * tick - np.stack([o, h, l, c])) > 1e-6
        out["off_tick_grid_rows"] = int(off.any(axis=0).sum())
    return out


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicate timestamps (keep last) and rows with impossible OHLC."""
    df = df[~df.index.duplicated(keep="last")]
    o, h, l, c = (df[k].to_numpy(float) for k in PRICE_COLS)
    ok = (h >= np.maximum(o, c)) & (l <= np.minimum(o, c)) & ~np.isnan([o, h, l, c]).any(axis=0)
    return df[ok].sort_index()


def spike_mask(df: pd.DataFrame, cfg: dict, tick: float) -> np.ndarray:
    """Bars whose wick is > spike_mult x rolling median range and reverts within the bar."""
    rng = (df["high"] - df["low"]).to_numpy(float)
    med = pd.Series(rng).rolling(int(get(cfg, "validation.spike_lookback")), min_periods=30).median().shift(1).to_numpy()
    body_hi = np.maximum(df["open"].to_numpy(float), df["close"].to_numpy(float))
    body_lo = np.minimum(df["open"].to_numpy(float), df["close"].to_numpy(float))
    wick = np.maximum(df["high"].to_numpy(float) - body_hi, body_lo - df["low"].to_numpy(float))
    mult = float(get(cfg, "validation.spike_mult"))
    return (wick > mult * np.maximum(med, tick)) & (wick >= 20 * tick)


def day_flags(df: pd.DataFrame, cfg: dict, tick: float) -> pd.DataFrame:
    """Per-trading-date statistics and do-not-trade flags for a continuous series."""
    a = annotate(df[["open", "high", "low", "close", "volume"]], cfg) if "tdate" not in df else df
    ts_min = ns(a.index) // NS_PER_MIN
    td = a["tdate"].to_numpy()
    same_day = np.r_[False, td[1:] == td[:-1]]
    gap = np.r_[0, np.diff(ts_min)] - 1
    gap = np.where(same_day, gap, 0)
    spikes = spike_mask(a, cfg, tick)
    g = pd.DataFrame({"tdate": a["tdate"].to_numpy(), "et_min": a["et_min"].to_numpy(), "gap": gap, "spike": spikes})
    flags = g.groupby("tdate").agg(
        n_bars=("gap", "size"),
        max_gap_min=("gap", "max"),
        n_gaps=("gap", lambda s: int((s > int(get(cfg, "validation.max_gap_minutes"))).sum())),
        last_et_min=("et_min", lambda s: int(s.iloc[-1])),
        spikes=("spike", "sum"),
    )
    typical = flags["n_bars"].rolling(60, min_periods=5).median().shift(1).bfill()
    frac = float(get(cfg, "sessions.short_day_bar_fraction"))
    ny_close = hhmm_to_minutes(get(cfg, "sessions.definitions")["ny"][1])
    flags["early_close"] = flags["last_et_min"] < ny_close - 1
    flags["short"] = (flags["n_bars"] < frac * typical) | flags["early_close"]
    flags["gap_day"] = flags["max_gap_min"] >= int(get(cfg, "validation.gap_day_exclude_minutes"))
    flags["spike_day"] = flags["spikes"] > 0
    hol = us_holidays(flags.index.min().year, flags.index.max().year)
    flags["holiday"] = flags.index.map(dict(zip(hol["date"], hol["holiday"]))).fillna("")
    flags["weekday"] = flags.index.day_name()
    return flags


def missing_weekdays(flags: pd.DataFrame) -> pd.DataFrame:
    """Weekdays with no data at all, labelled with a holiday name when known."""
    all_days = pd.bdate_range(flags.index.min(), flags.index.max())
    missing = all_days.difference(flags.index)
    hol = us_holidays(all_days[0].year, all_days[-1].year)
    names = dict(zip(hol["date"], hol["holiday"]))
    out = pd.DataFrame({"tdate": missing, "holiday": [names.get(d, "") for d in missing]})
    out["explained"] = out["holiday"] != ""
    return out


def pair_alignment(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Per-year coverage of A's minutes in B and correlation of 1m close-to-close changes."""
    common = a.index.intersection(b.index)
    rows = []
    for year in sorted(set(a.index.year)):
        ia = a.index[a.index.year == year]
        ic = common[common.year == year]
        ca = a.loc[ic, "close"].diff()
        cb = b.loc[ic, "close"].diff()
        consecutive = np.r_[False, np.diff(ns(ic)) == NS_PER_MIN]
        corr = np.corrcoef(ca.to_numpy()[consecutive], cb.to_numpy()[consecutive])[0, 1] if consecutive.sum() > 10 else np.nan
        rows.append({"year": year, "bars_a": len(ia), "coverage_in_b": len(ic) / max(len(ia), 1), "corr_1m_changes": corr})
    return pd.DataFrame(rows)


def validation_report(
    name: str,
    raw_checks: dict,
    cont_checks: dict,
    flags: pd.DataFrame,
    rolls: pd.DataFrame,
    pair: pd.DataFrame | None = None,
    cfg: dict | None = None,
) -> str:
    miss = missing_weekdays(flags)
    lines = [f"## {name}", ""]
    lines += [
        f"- Trading dates with data: **{len(flags)}**  ({flags.index.min().date()} → {flags.index.max().date()})",
        f"- 1m bars: {int(flags['n_bars'].sum()):,}; median per full day: {int(flags.loc[~flags['short'], 'n_bars'].median())}",
        f"- Weekdays with no data: {len(miss)} ({int(miss['explained'].sum())} are known holidays; "
        f"**{int((~miss['explained']).sum())} unexplained**)",
        f"- Short / holiday sessions (not traded): {int(flags['short'].sum())} "
        f"(of which early close before 16:00 ET: {int(flags['early_close'].sum())})",
        f"- Days with an intraday hole ≥ {get(cfg, 'validation.gap_day_exclude_minutes') if cfg else '?'} min (not traded): {int(flags['gap_day'].sum())}",
        f"- Days with suspect spikes (not traded): {int(flags['spike_day'].sum())} ({int(flags['spikes'].sum())} bars)",
        "",
        "Row checks (raw contracts → continuous):",
        "",
        "| check | raw | continuous |",
        "|---|---:|---:|",
    ]
    for k in raw_checks:
        lines.append(f"| {k} | {raw_checks[k]:,} | {cont_checks.get(k, '')} |")
    lines.append("")
    if len(rolls):
        lines += ["Rolls (additive back-adjustment gap measured at the last minute both contracts traded):", ""]
        lines.append("| roll trading date | old | new | gap (pts) | measured at (UTC) | method |")
        lines.append("|---|---|---|---:|---|---|")
        for r in rolls.itertuples(index=False):
            lines.append(f"| {pd.Timestamp(r.roll_tdate).date()} | {r.old} | {r.new} | {r.gap:+.2f} | {r.gap_ts} | {r.method} |")
        lines.append("")
    unexplained = miss[~miss["explained"]]
    if len(unexplained):
        lines += ["Unexplained missing weekdays (first 30):", "", ", ".join(str(d.date()) for d in unexplained["tdate"][:30]), ""]
    shorts = flags[flags["short"]]
    if len(shorts):
        lines += ["Short sessions (first 40):", "", "| date | bars | last bar ET | holiday |", "|---|---:|---|---|"]
        for d, r in shorts.head(40).iterrows():
            lines.append(f"| {d.date()} | {r.n_bars} | {r.last_et_min // 60:02d}:{r.last_et_min % 60:02d} | {r.holiday} |")
        lines.append("")
    if pair is not None and len(pair):
        lines += ["Pair alignment (share of traded-instrument minutes that also have a partner bar; 1m change correlation):", ""]
        lines.append("| year | bars | coverage | corr |")
        lines.append("|---|---:|---:|---:|")
        for r in pair.itertuples(index=False):
            lines.append(f"| {r.year} | {r.bars_a:,} | {r.coverage_in_b:.3f} | {r.corr_1m_changes:.3f} |")
        lines.append("")
    return "\n".join(lines)
