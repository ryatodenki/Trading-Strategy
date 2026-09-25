"""SqueezeMetrics' free daily gamma exposure (GEX) series and the day-by-day gamma regime (GAMMA.md).

The CSV (``date, price, dix, gex``) is fetched once into ``datastore/gex/`` (git-ignored: the
site's terms do not allow redistributing it).  GEX for cash date D is published after the close,
so futures trading day T uses the GEX dated on the latest cash date strictly before T.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from mnqbt.data.store import data_dir

GEX_URL = "https://squeezemetrics.com/monitor/static/DIX.csv"
MAX_AGE_DAYS = 7          # a GEX value older than this (calendar days before T) gives no regime


def gex_path(cfg: dict) -> Path:
    return data_dir(cfg) / "gex" / "DIX.csv"


def download_gex(cfg: dict, force: bool = False) -> Path:
    """Fetch the CSV once.  Refuses to overwrite an existing file unless ``force``."""
    import requests

    p = gex_path(cfg)
    if p.exists() and not force:
        raise SystemExit(f"{p} already exists; pass --force to fetch it again")
    r = requests.get(GEX_URL, timeout=60)
    r.raise_for_status()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(r.content)
    return p


def load_gex(cfg: dict, end=None, path: Path | None = None) -> pd.Series:
    """GEX by cash date (float, sorted), with nothing dated after ``end``."""
    df = pd.read_csv(path or gex_path(cfg))
    s = pd.Series(pd.to_numeric(df["gex"], errors="coerce").to_numpy(float), index=pd.DatetimeIndex(pd.to_datetime(df["date"])))
    s = s[~s.index.duplicated(keep="last")].dropna().sort_index()
    return s if end is None else s[s.index <= pd.Timestamp(end)]


def gamma_regime(gex: pd.Series, days: pd.DatetimeIndex, max_age_days: int = MAX_AGE_DAYS) -> pd.Series:
    """+1 (GEX > 0), -1 (GEX < 0) or NaN for each futures trading day: the GEX dated on the latest
    cash date strictly before the day, if it is at most ``max_age_days`` calendar days old."""
    days = pd.DatetimeIndex(days)
    pos = np.searchsorted(gex.index.values, days.values, side="left") - 1      # latest date strictly before
    ok = pos >= 0
    val = np.where(ok, gex.to_numpy()[np.maximum(pos, 0)], np.nan)
    age = (days.values - gex.index.values[np.maximum(pos, 0)]) / np.timedelta64(1, "D")
    val = np.where(ok & (age <= max_age_days), val, np.nan)
    return pd.Series(np.sign(val), index=days).replace(0.0, np.nan)
