"""Major-news day calendar (FOMC, NFP; add CPI or anything else to the CSV).

``config/news_days.csv`` columns: date, kind, time_et, source.
* FOMC: statement days compiled from the Federal Reserve's published meeting
  calendars (includes the two March 2020 emergency cuts).  Verify against
  federalreserve.gov before relying on it for anything live.
* NFP: generated from the BLS scheduling rule (third Friday after the week
  containing the 12th of the reference month, with the January and July-4
  holiday adjustments), plus overrides for shutdown-delayed releases.
  Approximate — edit the CSV if you have the official schedule.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from mnqbt.config import ROOT, get, hhmm_to_minutes

FOMC = """
2010-01-27 2010-03-16 2010-04-28 2010-06-23 2010-08-10 2010-09-21 2010-11-03 2010-12-14
2011-01-26 2011-03-15 2011-04-27 2011-06-22 2011-08-09 2011-09-21 2011-11-02 2011-12-13
2012-01-25 2012-03-13 2012-04-25 2012-06-20 2012-08-01 2012-09-13 2012-10-24 2012-12-12
2013-01-30 2013-03-20 2013-05-01 2013-06-19 2013-07-31 2013-09-18 2013-10-30 2013-12-18
2014-01-29 2014-03-19 2014-04-30 2014-06-18 2014-07-30 2014-09-17 2014-10-29 2014-12-17
2015-01-28 2015-03-18 2015-04-29 2015-06-17 2015-07-29 2015-09-17 2015-10-28 2015-12-16
2016-01-27 2016-03-16 2016-04-27 2016-06-15 2016-07-27 2016-09-21 2016-11-02 2016-12-14
2017-02-01 2017-03-15 2017-05-03 2017-06-14 2017-07-26 2017-09-20 2017-11-01 2017-12-13
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-03-03 2020-03-16 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16 2026-10-28 2026-12-09
"""

# Release date overrides: {rule-computed date: actual date or None if no release}
NFP_OVERRIDES = {
    dt.date(2013, 10, 4): dt.date(2013, 10, 22),   # government shutdown
    dt.date(2013, 11, 1): dt.date(2013, 11, 8),
    dt.date(2025, 10, 3): dt.date(2025, 11, 20),   # government shutdown (Sep report)
    dt.date(2025, 11, 7): None,                    # Oct report folded into the Dec 16 release
    dt.date(2025, 12, 5): dt.date(2025, 12, 16),
}


def nfp_release(year: int, month: int) -> dt.date:
    ry, rm = (year, month - 1) if month > 1 else (year - 1, 12)
    d12 = dt.date(ry, rm, 12)
    sat = d12 + dt.timedelta(days=(5 - d12.weekday()) % 7)
    rel = sat + dt.timedelta(days=20)
    if month == 1 and rel.day <= 3:
        rel += dt.timedelta(days=7)
    if month == 7 and rel.day in (3, 4):
        observed = dt.date(year, 7, 3) if dt.date(year, 7, 4).weekday() == 5 else dt.date(year, 7, 4)
        if rel == observed:
            rel -= dt.timedelta(days=1)
    return rel


def default_news_frame(start_year: int = 2010, end_year: int = 2026) -> pd.DataFrame:
    rows = [(pd.Timestamp(d), "FOMC", "14:00", "Fed meeting calendar") for d in FOMC.split()]
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            rel = nfp_release(y, m)
            if rel in NFP_OVERRIDES:
                new = NFP_OVERRIDES[rel]
                if new is None:
                    continue
                rows.append((pd.Timestamp(new), "NFP", "08:30", "BLS (shutdown-adjusted)"))
            else:
                rows.append((pd.Timestamp(rel), "NFP", "08:30", "BLS rule (approximate)"))
    out = pd.DataFrame(rows, columns=["date", "kind", "time_et", "source"])
    return out.sort_values(["date", "kind"]).reset_index(drop=True)


def load_news(cfg: dict) -> pd.DataFrame:
    path = Path(get(cfg, "rules.news.file"))
    path = path if path.is_absolute() else ROOT / path
    df = pd.read_csv(path, parse_dates=["date"])
    return df[df["kind"].isin(get(cfg, "rules.news.kinds"))]


def news_block_mask(tdates: np.ndarray, et_min: np.ndarray, cfg: dict) -> np.ndarray:
    """True where a new entry would violate the news filter.

    ``day`` mode blocks the whole trading date; ``window`` mode blocks
    +-window_minutes around the release time on that date.
    """
    news = load_news(cfg)
    td = pd.DatetimeIndex(tdates).normalize()
    if get(cfg, "rules.news.mode") == "day":
        return td.isin(pd.DatetimeIndex(news["date"]))
    w = int(get(cfg, "rules.news.window_minutes"))
    mask = np.zeros(len(td), bool)
    for d, t in zip(news["date"], news["time_et"]):
        m = hhmm_to_minutes(t)
        mask |= (td == d) & (np.abs(et_min.astype(int) - m) <= w)
    return mask
