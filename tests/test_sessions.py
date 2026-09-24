import pandas as pd

from mnqbt.data.sessions import annotate, session_end_times, trading_dates
from mnqbt.data.validate import day_flags
from mnqbt.rules.levels import daily_table, level_table
from mnqbt.rules.bars import resample

ET = "America/New_York"


def _utc(local: str) -> pd.Timestamp:
    return pd.Timestamp(local, tz=ET).tz_convert("UTC")


def test_trading_date_rolls_at_18_et(cfg):
    idx = pd.DatetimeIndex([_utc("2024-03-03 18:00"), _utc("2024-03-04 16:59"), _utc("2024-03-04 18:00"), _utc("2024-03-08 16:59")])
    td = trading_dates(idx, cfg)
    assert [str(d.date()) for d in td] == ["2024-03-04", "2024-03-04", "2024-03-05", "2024-03-08"]  # Sunday evening -> Monday


def test_dst_cash_open_is_always_0930_et(cfg):
    winter = pd.Timestamp("2024-03-08 14:30", tz="UTC")   # EST (UTC-5)
    summer = pd.Timestamp("2024-03-11 13:30", tz="UTC")   # EDT (UTC-4) after the 2024-03-10 switch
    a = annotate(pd.DataFrame({"open": [1.0, 1.0], "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
                              index=pd.DatetimeIndex([winter, summer])), cfg)
    assert a["et_min"].tolist() == [570, 570]
    assert a["session"].tolist() == ["ny", "ny"]
    # the same UTC clock time is London session after the switch
    b = annotate(pd.DataFrame({"open": [1.0], "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
                              index=pd.DatetimeIndex([pd.Timestamp("2024-03-11 13:29", tz="UTC")])), cfg)
    assert b["session"].tolist() == ["london"]


def test_session_boundaries(cfg):
    stamps = ["2024-03-04 18:00", "2024-03-05 02:59", "2024-03-05 03:00", "2024-03-05 09:29", "2024-03-05 09:30",
              "2024-03-05 15:59", "2024-03-05 16:00"]
    idx = pd.DatetimeIndex([_utc(s) for s in stamps])
    a = annotate(pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx), cfg)
    assert a["session"].tolist() == ["asia", "asia", "london", "london", "ny", "ny", ""]


def test_session_end_times_follow_dst(cfg):
    td = pd.DatetimeIndex(["2024-03-08", "2024-03-11"])
    ends = session_end_times(td, "ny", cfg)
    assert [str(t) for t in ends] == ["2024-03-08 21:00:00+00:00", "2024-03-11 20:00:00+00:00"]
    asia = session_end_times(td, "asia", cfg)
    assert [str(t) for t in asia] == ["2024-03-08 08:00:00+00:00", "2024-03-11 07:00:00+00:00"]


def _two_days(cfg):
    """1m bars for trading dates Tue 2024-03-05 and Wed 2024-03-06 with known session extremes."""
    idx = []
    for day in ("2024-03-05", "2024-03-06"):
        start = pd.Timestamp(day, tz=ET) - pd.Timedelta(hours=6)  # 18:00 previous evening
        idx.append(pd.date_range(start, periods=23 * 60, freq="1min").tz_convert("UTC"))
    idx = idx[0].append(idx[1]).as_unit("ns")
    df = pd.DataFrame({"open": 100.0, "high": 100.25, "low": 99.75, "close": 100.0, "volume": 10.0}, index=idx)
    def put(local, hi=None, lo=None):
        t = _utc(local)
        if hi is not None:
            df.loc[t, "high"] = hi
        if lo is not None:
            df.loc[t, "low"] = lo
    put("2024-03-06 01:00", hi=110.0)   # Asia high of Wed
    put("2024-03-06 05:00", lo=90.0)    # London low of Wed
    put("2024-03-05 10:00", hi=120.0)   # NY high of Tue
    return annotate(df, cfg)


def test_session_levels_only_after_session_end(cfg):
    m1 = _two_days(cfg)
    flags = day_flags(m1, cfg, 0.25)
    flags["tradeable"] = True
    daily = daily_table(m1, flags, cfg)
    b5 = resample(m1, "5min")
    lt = level_table(b5, m1, daily, resample(m1, "15min"), cfg)
    at = lambda local: lt.loc[_utc(local)]  # noqa: E731
    # Wednesday's Asia high (110) is not a level during Asia, only from 03:00
    assert at("2024-03-06 02:55")["asia_h"] != 110.0
    assert at("2024-03-06 03:00")["asia_h"] == 110.0
    # Wednesday London low (90) becomes a level only at 09:30
    assert at("2024-03-06 09:25")["london_l"] != 90.0
    assert at("2024-03-06 09:30")["london_l"] == 90.0
    # Tuesday's NY high (120) is the prior-NY level during Wednesday, and Tuesday's high is PDH
    assert at("2024-03-06 04:00")["ny_h"] == 120.0
    assert at("2024-03-06 04:00")["pdh"] == 120.0
    # running day high never includes the bar itself
    assert at("2024-03-06 01:00")["dh"] == 100.25
    assert at("2024-03-06 01:05")["dh"] == 110.0


def test_short_session_flagged(cfg):
    idx = pd.date_range(_utc("2024-01-14 18:00"), _utc("2024-01-15 12:59"), freq="1min").as_unit("ns")  # MLK early halt
    full = pd.date_range(_utc("2024-01-15 18:00"), periods=23 * 60, freq="1min").as_unit("ns")
    df = pd.DataFrame({"open": 1.0, "high": 1.25, "low": 0.75, "close": 1.0, "volume": 1}, index=idx.append(full))
    f = day_flags(df, cfg, 0.25)
    assert bool(f.loc["2024-01-15", "short"]) and bool(f.loc["2024-01-15", "early_close"])
    assert not bool(f.loc["2024-01-16", "short"])
    assert f.loc["2024-01-15", "holiday"] == "MLK Day"
