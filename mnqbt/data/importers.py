"""Importers for file exports (NinjaTrader, FirstRate Data, generic CSV).

All importers return the canonical per-contract frame: UTC DatetimeIndex of
bar OPEN times, columns ``symbol, open, high, low, close, volume``.

Timestamp conventions differ by vendor; get them right or every session
boundary is off by a bar:
* NinjaTrader 8 exports stamp each minute bar with its CLOSE time, in the
  time zone configured in NinjaTrader (Tools > Options > General).
* FirstRate Data stamps bars with their OPEN time in US Eastern time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from mnqbt.data.calendar import CODE_FOR_MONTH

_NT_NAME = re.compile(r"^(?P<root>[A-Z]+)\s+(?P<mm>\d{2})-(?P<yy>\d{2})")


def _finish(df: pd.DataFrame, ts: pd.Series, tz: str, ts_is_close: bool, bar_minutes: int, symbol: str) -> pd.DataFrame:
    idx = pd.DatetimeIndex(pd.to_datetime(ts))
    if idx.tz is None:
        idx = idx.tz_localize(tz, ambiguous="infer" if idx.is_monotonic_increasing else "NaT", nonexistent="shift_forward")
    idx = idx.tz_convert("UTC")
    if ts_is_close:
        idx = idx - pd.Timedelta(minutes=bar_minutes)
    out = pd.DataFrame(
        {
            "symbol": symbol,
            "open": df["open"].astype(float).to_numpy(),
            "high": df["high"].astype(float).to_numpy(),
            "low": df["low"].astype(float).to_numpy(),
            "close": df["close"].astype(float).to_numpy(),
            "volume": df["volume"].astype("int64").to_numpy(),
        },
        index=idx,
    )
    out.index.name = "ts"
    return out[out.index.notna()].sort_index()


def symbol_from_ninjatrader_name(path: str | Path) -> str | None:
    """'MNQ 03-24.Last.txt' -> 'MNQH4'."""
    m = _NT_NAME.match(Path(path).name)
    if not m:
        return None
    month = int(m["mm"])
    if month not in CODE_FOR_MONTH:
        return None
    return f"{m['root']}{CODE_FOR_MONTH[month]}{m['yy'][-1]}"


def read_ninjatrader(path: str | Path, tz: str = "America/New_York", symbol: str | None = None) -> pd.DataFrame:
    """NinjaTrader 8 minute export: 'yyyyMMdd HHmmss;open;high;low;close;volume'."""
    sym = symbol or symbol_from_ninjatrader_name(path)
    if not sym:
        raise ValueError(f"cannot infer contract from {path}; pass symbol=")
    raw = pd.read_csv(path, sep=";", header=None, names=["ts", "open", "high", "low", "close", "volume"], dtype={"ts": str})
    ts = pd.to_datetime(raw["ts"], format="%Y%m%d %H%M%S")
    return _finish(raw, ts, tz, ts_is_close=True, bar_minutes=1, symbol=sym)


def read_firstrate(path: str | Path, symbol: str, tz: str = "America/New_York") -> pd.DataFrame:
    """FirstRate Data 1-minute file: 'YYYY-MM-DD HH:MM:SS,open,high,low,close,volume' (header optional)."""
    with open(path) as fh:
        first = fh.readline()
    has_header = not first[:1].isdigit()
    raw = pd.read_csv(path, header=0 if has_header else None)
    raw.columns = ["ts", "open", "high", "low", "close", "volume"][: len(raw.columns)]
    return _finish(raw, raw["ts"], tz, ts_is_close=False, bar_minutes=1, symbol=symbol)


def read_generic_csv(
    path: str | Path,
    symbol: str,
    tz: str,
    ts_is_close: bool,
    columns: dict[str, str] | None = None,
    sep: str = ",",
) -> pd.DataFrame:
    """Any CSV with a timestamp column and OHLCV; ``columns`` maps canonical -> file column names."""
    raw = pd.read_csv(path, sep=sep)
    if columns:
        raw = raw.rename(columns={v: k for k, v in columns.items()})
    raw.columns = [c.lower() for c in raw.columns]
    ts_col = next(c for c in raw.columns if c in ("ts", "timestamp", "time", "datetime", "date"))
    return _finish(raw, raw[ts_col], tz, ts_is_close=ts_is_close, bar_minutes=1, symbol=symbol)
