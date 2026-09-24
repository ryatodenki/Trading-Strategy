import numpy as np
import pandas as pd

from mnqbt.config import apply_overrides
from mnqbt.data.continuous import build_continuous, splice
from mnqbt.data.sessions import trading_dates
from mnqbt.data.synthetic import generate


def test_calendar_roll_dates_and_additive_adjustment(cfg):
    raw = generate("2021-01-04", "2021-07-30", seed=5)["MNQ"]
    cont, rolls, _ = build_continuous(raw, cfg, root="MNQ")
    # CME convention: 8 calendar days before the 3rd-Friday expiry (a Thursday)
    assert [str(d.date()) for d in rolls["roll_tdate"]] == ["2021-03-11", "2021-06-10"]
    assert (pd.DatetimeIndex(rolls["roll_tdate"]).day_name() == "Thursday").all()
    # newest contract is raw prices; older segments are shifted by the sum of later gaps
    last = cont[cont["contract"] == cont["contract"].iloc[-1]]
    assert (last["adj"] == 0).all()
    first = cont[cont["contract"] == "MNQH1"]
    assert np.allclose(first["adj"], rolls["gap"].sum())
    # every intra-contract point distance is preserved exactly
    raw_h = raw[raw["symbol"] == "MNQH1"]
    common = first.index.intersection(raw_h.index)[:500]
    assert np.allclose(first.loc[common, "close"].diff().dropna(), raw_h.loc[common, "close"].diff().dropna())


def test_forced_schedule_rolls_pair_on_same_days(cfg):
    d = generate("2021-01-04", "2021-07-30", seed=5)
    _, r_a, sched = build_continuous(d["MNQ"], cfg, root="MNQ")
    _, r_b, _ = build_continuous(d["MES"], cfg, root="MES", forced_schedule=sched)
    assert list(r_a["roll_tdate"]) == list(r_b["roll_tdate"])


def test_volume_roll_uses_previous_day_only(cfg):
    vcfg = apply_overrides(cfg, {"continuous.roll_rule": "volume"})
    raw = generate("2021-01-04", "2021-04-30", seed=5)["MNQ"]
    _, rolls, _ = build_continuous(raw, vcfg, root="MNQ")
    roll_day = rolls["roll_tdate"].iloc[0]
    td = trading_dates(raw.index, vcfg)
    vol = pd.DataFrame({"td": td, "sym": raw["symbol"].to_numpy(), "v": raw["volume"].to_numpy()}).groupby(["td", "sym"])["v"].sum().unstack()
    days = vol.index
    prev = days[days.get_loc(roll_day) - 1]
    before_prev = days[days.get_loc(roll_day) - 2]
    assert vol.loc[prev, "MNQM1"] > vol.loc[prev, "MNQH1"]          # crossover happened on the previous day
    assert vol.loc[before_prev, "MNQM1"] <= vol.loc[before_prev, "MNQH1"]  # ...and not earlier


def test_splice_proxy_to_micro_has_no_raw_gap(cfg):
    d = generate("2021-01-04", "2021-06-30", seed=2, splice_date="2021-04-01")
    nq, _, s_nq = build_continuous(d["NQ"], cfg, root="NQ")
    mnq, _, _ = build_continuous(d["MNQ"], cfg, root="MNQ")
    joined, info = splice(nq, mnq, "2021-04-01", cfg)
    assert abs(info["raw_price_diff"]) < 1e-9
    td = trading_dates(joined.index, cfg)
    assert joined[td < pd.Timestamp("2021-04-01")]["contract"].str.startswith("NQ").all()
    assert joined[td >= pd.Timestamp("2021-04-01")]["contract"].str.startswith("MNQ").all()
    assert not joined.index.duplicated().any()
