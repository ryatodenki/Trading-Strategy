"""Databento historical download with a mandatory cost quote and budget cap.

Nothing here runs unless you call it.  ``quote`` only asks Databento what a
request would cost (free).  ``download`` refuses to run if the quoted total
exceeds ``--max-cost`` (default: databento.max_cost_usd in the config).

Requires:
* ``pip install databento``
* the API key in the environment variable named by databento.api_key_env
* network access to hist.databento.com
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import dataclass

import pandas as pd

from mnqbt.config import get
from mnqbt.data.store import raw_dir

log = logging.getLogger(__name__)
OVERLAP_DAYS = 35  # proxy and micro data overlap around the splice so it can be measured


@dataclass(frozen=True)
class Request:
    root: str
    start: str  # inclusive, YYYY-MM-DD
    end: str    # exclusive, YYYY-MM-DD

    @property
    def symbol(self) -> str:
        return f"{self.root}.FUT"

    @property
    def filename(self) -> str:
        return f"{self.root}_{self.start}_{self.end}.parquet"


def _year_chunks(root: str, start: dt.date, end: dt.date) -> list[Request]:
    out, cur = [], start
    while cur < end:
        nxt = min(dt.date(cur.year + 1, 1, 1), end)
        out.append(Request(root, cur.isoformat(), nxt.isoformat()))
        cur = nxt
    return out


def plan_requests(cfg: dict, end: str | None = None, include_proxies: bool = True) -> list[Request]:
    """Yearly requests: proxies (NQ/ES) up to the splice, micros (MNQ/MES) after it."""
    splice = pd.Timestamp(get(cfg, "instruments.splice_date")).date()
    hist_start = pd.Timestamp(get(cfg, "databento.history_start")).date()
    end_d = pd.Timestamp(end).date() if end else dt.date.today()
    micro_start = splice - dt.timedelta(days=OVERLAP_DAYS)
    proxy_end = splice + dt.timedelta(days=OVERLAP_DAYS)
    reqs: list[Request] = []
    for micro in (get(cfg, "instruments.traded"), get(cfg, "instruments.pair")):
        reqs += _year_chunks(micro, micro_start, end_d)
        if include_proxies:
            reqs += _year_chunks(get(cfg, "instruments.proxies")[micro], hist_start, min(proxy_end, end_d))
    return reqs


def _client(cfg: dict):
    try:
        import databento as db
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("pip install databento  (or: pip install -e '.[databento]')") from exc
    key_env = get(cfg, "databento.api_key_env")
    key = os.environ.get(key_env)
    if not key:
        raise SystemExit(f"environment variable {key_env} is not set")
    return db.Historical(key)


def quote(cfg: dict, requests: list[Request]) -> pd.DataFrame:
    client = _client(cfg)
    rows = []
    for r in requests:
        kwargs = dict(dataset=get(cfg, "databento.dataset"), symbols=[r.symbol], schema=get(cfg, "databento.schema"),
                      start=r.start, end=r.end, stype_in="parent")
        cost = client.metadata.get_cost(**kwargs)
        size = client.metadata.get_billable_size(**kwargs)
        rows.append({"root": r.root, "start": r.start, "end": r.end, "usd": float(cost), "gb": size / 1e9})
    out = pd.DataFrame(rows)
    return out


def download(cfg: dict, requests: list[Request], max_cost: float | None = None, force: bool = False) -> pd.DataFrame:
    """Download requests not already on disk, after checking the total quote against the budget."""
    budget = float(max_cost if max_cost is not None else get(cfg, "databento.max_cost_usd"))
    todo = [r for r in requests if force or not (raw_dir(cfg, "databento", r.root) / r.filename).exists()]
    if not todo:
        log.info("all requested files already downloaded")
        return pd.DataFrame()
    q = quote(cfg, todo)
    total = float(q["usd"].sum())
    print(q.to_string(index=False))
    print(f"TOTAL quoted cost: ${total:,.2f}  (budget ${budget:,.2f})")
    if total > budget:
        raise SystemExit(f"quote ${total:,.2f} exceeds budget ${budget:,.2f}; nothing downloaded")
    client = _client(cfg)
    for r in todo:
        store = client.timeseries.get_range(
            dataset=get(cfg, "databento.dataset"), symbols=[r.symbol], schema=get(cfg, "databento.schema"),
            start=r.start, end=r.end, stype_in="parent",
        )
        df = store.to_df(price_type="float", pretty_ts=True, map_symbols=True)
        df = df[["symbol", "open", "high", "low", "close", "volume"]]
        df.index = pd.DatetimeIndex(df.index).tz_convert("UTC")
        df.index.name = "ts"
        out = raw_dir(cfg, "databento", r.root)
        out.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out / r.filename)
        print(f"saved {r.filename}: {len(df):,} rows, {df['symbol'].nunique()} instruments")
    return q
