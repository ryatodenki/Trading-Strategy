"""Contract calendar (quarterly expiries, symbols) and US holiday rules.

The holiday list is only used to *explain* missing or short days in the
validation report; the backtest detects short sessions from the data itself.
"""

from __future__ import annotations

import datetime as dt
import re

import pandas as pd

MONTH_CODES = {"H": 3, "M": 6, "U": 9, "Z": 12}
CODE_FOR_MONTH = {v: k for k, v in MONTH_CODES.items()}
_SYMBOL_RE = re.compile(r"^(?P<root>[A-Z]{1,3}?)(?P<code>[FGHJKMNQUVXZ])(?P<year>\d{1,2})$")


def third_friday(year: int, month: int) -> dt.date:
    first = dt.date(year, month, 1)
    offset = (4 - first.weekday()) % 7  # Friday == 4
    return first + dt.timedelta(days=offset + 14)


def quarterly_expiries(start: dt.date, end: dt.date) -> list[dt.date]:
    out = []
    for year in range(start.year, end.year + 2):
        for month in (3, 6, 9, 12):
            exp = third_friday(year, month)
            if start <= exp <= end + dt.timedelta(days=120):
                out.append(exp)
    return out


def contract_symbol(root: str, expiry: dt.date, year_digits: int = 1) -> str:
    return f"{root}{CODE_FOR_MONTH[expiry.month]}{str(expiry.year)[-year_digits:]}"


def parse_symbol(symbol: str, ref_date: dt.date) -> tuple[str, dt.date] | None:
    """Parse e.g. 'MNQH4' / 'NQZ19' into (root, expiry).

    One-digit years are ambiguous across decades; the expiry chosen is the
    first one on or after ``ref_date`` minus one year (i.e. the contract that
    could plausibly be trading at ``ref_date``).  Returns None for spreads and
    anything unparseable.
    """
    if "-" in symbol or ":" in symbol or " " in symbol:
        return None
    m = _SYMBOL_RE.match(symbol)
    if not m or m["code"] not in MONTH_CODES:
        return None
    month = MONTH_CODES[m["code"]]
    ydig = m["year"]
    if len(ydig) == 2:
        year = 2000 + int(ydig)
    else:
        decade = ref_date.year - ref_date.year % 10
        year = decade + int(ydig)
        if dt.date(year, month, 28) < ref_date - dt.timedelta(days=365):
            year += 10
        elif dt.date(year, month, 1) > ref_date + dt.timedelta(days=3 * 365):
            year -= 10
    return m["root"], third_friday(year, month)


# ---------------------------------------------------------------------------
# US holidays affecting CME equity-index futures (full closures or early halts)
# ---------------------------------------------------------------------------

def _easter(year: int) -> dt.date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: dt.date) -> dt.date:
    if day.weekday() == 5:
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


def us_holidays(start_year: int, end_year: int) -> pd.DataFrame:
    rows = []
    for y in range(start_year, end_year + 1):
        rows += [
            (_observed(dt.date(y, 1, 1)), "New Year's Day"),
            (_nth_weekday(y, 1, 0, 3), "MLK Day"),
            (_nth_weekday(y, 2, 0, 3), "Presidents Day"),
            (_easter(y) - dt.timedelta(days=2), "Good Friday"),
            (_last_weekday(y, 5, 0), "Memorial Day"),
            (_observed(dt.date(y, 7, 4)), "Independence Day"),
            (_nth_weekday(y, 9, 0, 1), "Labor Day"),
            (_nth_weekday(y, 11, 3, 4), "Thanksgiving"),
            (_nth_weekday(y, 11, 3, 4) + dt.timedelta(days=1), "Day after Thanksgiving (early close)"),
            (_observed(dt.date(y, 12, 25)), "Christmas"),
        ]
        if y >= 2022:
            rows.append((_observed(dt.date(y, 6, 19)), "Juneteenth"))
    special = [
        (dt.date(2012, 10, 29), "Hurricane Sandy"),
        (dt.date(2012, 10, 30), "Hurricane Sandy"),
        (dt.date(2018, 12, 5), "National day of mourning (G.H.W. Bush)"),
        (dt.date(2025, 1, 9), "National day of mourning (J. Carter)"),
    ]
    rows += [r for r in special if start_year <= r[0].year <= end_year]
    out = pd.DataFrame(rows, columns=["date", "holiday"])
    out["date"] = pd.to_datetime(out["date"])
    return out.sort_values("date").reset_index(drop=True)
