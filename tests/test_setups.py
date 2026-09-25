import pytest

from mnqbt.config import apply_overrides, get, resolve_dist
from mnqbt.data.build import combined_day_flags
from mnqbt.data.continuous import build_continuous
from mnqbt.data.synthetic import generate
from mnqbt.data.validate import clean
from mnqbt.rules.features import Features
from mnqbt.rules.setups import build_intents
from mnqbt.timeutil import to_ns_index


@pytest.fixture(scope="module")
def features(cfg):
    raw = generate("2021-01-04", "2021-04-30", seed=5)
    a, _, sched = build_continuous(raw["MNQ"], cfg, root="MNQ")
    b, _, _ = build_continuous(raw["MES"], cfg, root="MES", forced_schedule=sched)
    a, b = to_ns_index(clean(a)), to_ns_index(clean(b))
    return Features(cfg, a, b, combined_day_flags(a, b, cfg)[0])


def _orders(F, cfg, confirm):
    it, _ = build_intents(F, apply_overrides(cfg, {"setup.confirm": confirm}))
    return it.set_index(["placed_ns", "trig_known_ns"])


def test_confirmation_is_smt_or_trend(cfg, features):
    both, smt, trend, none = (_orders(features, cfg, c) for c in (["smt", "trend"], ["smt"], ["trend"], []))
    assert len(smt) and len(trend)
    assert set(both.index) == set(smt.index) | set(trend.index)
    assert set(both.index) <= set(none.index)
    assert set(smt["confirm"]) <= {"smt", "smt+trend"} and set(trend["confirm"]) <= {"trend", "smt+trend"}
    assert (smt["smt"]).all()


def test_trend_confirmation_matches_its_definition(cfg, features):
    t = _orders(features, cfg, ["trend"])
    assert (t["structure_aligned"] == 1).all()
    assert (~t["choppy"].astype(bool)).all()
    assert ((t["dir"] > 0) == (t["vwap_side"] == "above")).all()


def test_unknown_confirmation_is_rejected(cfg, features):
    with pytest.raises(ValueError, match="unknown setup.confirm"):
        build_intents(features, apply_overrides(cfg, {"setup.confirm": ["gamma"]}))


def test_stop_wider_than_40_percent_of_atr_is_skipped(cfg, features):
    assert resolve_dist(get(cfg, "setup.stop.max_risk"), 100.0) == pytest.approx(40.0)
    capped = _orders(features, cfg, [])
    old = {"setup.stop.max_risk": {"points": 1.0e9, "atr_frac": 0.40}}      # the setting before the fix: no cap at all
    uncapped = _orders(features, apply_overrides(cfg, old), [])
    wide = uncapped["risk"] > 0.40 * uncapped["atr"]
    assert wide.any()                                                    # the sample has some to skip
    assert (capped["risk"] <= 0.40 * capped["atr"]).all()
    assert set(capped.index) == set(uncapped.index[~wide])
