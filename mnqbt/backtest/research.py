"""Research protocol: variants (Step 3), tuning / walk-forward / holdout / benchmark (Step 4)."""

from __future__ import annotations

import datetime as dt
import itertools
import json
from dataclasses import dataclass, field

import pandas as pd

from mnqbt.backtest.engine import EngineSettings, Market, Resolver, simulate
from mnqbt.config import VARIANTS_CONFIG, apply_overrides, get, load_yaml
from mnqbt.data.store import load_processed, results_dir
from mnqbt.reports.metrics import enrich, summarize
from mnqbt.rules.features import Features
from mnqbt.rules.setups import build_intents


@dataclass
class RunResult:
    name: str
    group: str
    overrides: dict
    cfg: dict
    intents: pd.DataFrame
    funnel: dict
    trades: pd.DataFrame
    log: pd.DataFrame
    summary: dict = field(default_factory=dict)


def load_features(cfg: dict, dataset: str) -> Features:
    t, p = get(cfg, "instruments.traded"), get(cfg, "instruments.pair")
    fr = load_processed(cfg, dataset, [t, p, "day_flags"])
    return Features(cfg, fr[t], fr[p], fr["day_flags"])


def period_bounds(F: Features, cfg: dict, which: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    td = pd.DatetimeIndex(F.a1["tdate"].to_numpy())
    first, last = td.min(), td.max()
    if which == "dev":
        return first, min(last, pd.Timestamp(get(cfg, "research.dev_end")))
    if which == "holdout":
        return pd.Timestamp(get(cfg, "research.holdout_start")), last
    if which == "all":
        return first, last
    raise ValueError(which)


def run_one(F: Features, cfg: dict, name: str, start, end, group: str = "", overrides: dict | None = None,
            resolver: Resolver | None = None, mk: Market | None = None) -> RunResult:
    intents, funnel = build_intents(F, cfg, start=str(start.date()), end=str(end.date()))
    mk = mk or Market.from_frame(F.a1)
    trades, log = simulate(mk, intents, EngineSettings.from_cfg(cfg), resolver)
    trades = enrich(trades)
    r = get(cfg, "research")
    summary = summarize(trades, reps=int(r["bootstrap_reps"]), level=float(r["ci_level"]), min_trades=int(r["min_trades_warning"]))
    if len(log):
        for status, n in log["status"].value_counts().items():
            funnel[f"order: {status}"] = int(n)
    return RunResult(name, group, overrides or {}, cfg, intents, funnel, trades, log, summary)


def variant_plan(base_cfg: dict, groups: tuple[str, ...]) -> list[tuple[str, str, dict, dict]]:
    """[(group, name, overrides, cfg)] for the Step 3 suite."""
    v = load_yaml(VARIANTS_CONFIG)
    plan = []
    if "baseline" in groups:
        plan.append(("baseline", "baseline", {}, base_cfg))
    if "add_one" in groups:
        for name, ov in v["add_one"].items():
            plan.append(("add_one", f"+{name}", ov, apply_overrides(base_cfg, ov)))
    full_cfg = apply_overrides(base_cfg, v["full"])
    if "full" in groups:
        plan.append(("full", "full", v["full"], full_cfg))
    if "remove_one" in groups:
        for name, ov in v["remove_one"].items():
            plan.append(("remove_one", f"full {name.replace('no_', '−')}", {**v["full"], **ov}, apply_overrides(full_cfg, ov)))
    if "engine_checks" in groups:
        for name, ov in v["engine_checks"].items():
            plan.append(("engine_checks", f"baseline, {name.replace('_', ' ')}", ov, apply_overrides(base_cfg, ov)))
    return plan


def run_suite(F: Features, base_cfg: dict, start, end,
              groups: tuple[str, ...] = ("baseline", "add_one", "full", "remove_one", "engine_checks")) -> list[RunResult]:
    mk = Market.from_frame(F.a1)
    return [run_one(F, c, name, start, end, group, ov, mk=mk) for group, name, ov, c in variant_plan(base_cfg, groups)]


def grid_combos(base_cfg: dict) -> list[dict]:
    grid = get(base_cfg, "research.tuning_grid") or {}
    keys = list(grid)
    return [dict(zip(keys, vals)) for vals in itertools.product(*(grid[k] for k in keys))]


def tune(F: Features, base_cfg: dict, start, end, min_trades: int = 30) -> pd.DataFrame:
    """Evaluate every grid combination on [start, end]. Returns one row per combination."""
    mk = Market.from_frame(F.a1)
    rows = []
    for combo in grid_combos(base_cfg):
        res = run_one(F, apply_overrides(base_cfg, combo), json.dumps(combo), start, end, "tune", combo, mk=mk)
        rows.append({**{k.split(".")[-1]: v for k, v in combo.items()}, "combo": json.dumps(combo), **res.summary,
                     "_trades": res.trades})
    out = pd.DataFrame(rows)
    out["eligible"] = out["trades"] >= min_trades
    return out


def pick_best(tbl: pd.DataFrame, objective: str) -> dict | None:
    ok = tbl[tbl["eligible"]]
    if ok.empty:
        return None
    return json.loads(ok.sort_values([objective, "trades"], ascending=False).iloc[0]["combo"])


def walk_forward(F: Features, base_cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Anchored walk-forward inside the development period.

    For each test year Y: choose the grid combination with the best objective
    on all development data before Y, then record how that choice did in Y.
    Every combination is simulated once over the whole development period and
    sliced by year (the engine is causal, so a trade in Y only depends on the past).
    """
    dev_start, dev_end = period_bounds(F, base_cfg, "dev")
    r = get(base_cfg, "research")
    objective = r["tuning_objective"]
    tbl = tune(F, base_cfg, dev_start, dev_end)
    combos = [json.loads(c) for c in tbl["combo"]]
    trades_by_combo = {c: t for c, t in zip(tbl["combo"], tbl["_trades"])}
    default_key = json.dumps({k: get(base_cfg, k) for k in combos[0]}) if combos else None
    rows, oos = [], []
    for year in range(int(r["walkforward_first_test_year"]), dev_end.year + 1):
        train_rows = []
        for c in combos:
            t = trades_by_combo[json.dumps(c)]
            tr = t[pd.DatetimeIndex(t["tdate"]).year < year] if len(t) else t
            s = summarize(tr, reps=200, min_trades=int(r["min_trades_warning"]))
            train_rows.append({"combo": json.dumps(c), **s})
        train = pd.DataFrame(train_rows)
        train["eligible"] = train["trades"] >= 30
        best = pick_best(train, objective)
        if best is None:
            continue
        key = json.dumps(best)
        t = trades_by_combo[key]
        test = t[pd.DatetimeIndex(t["tdate"]).year == year] if len(t) else t
        s = summarize(test, reps=500, min_trades=int(r["min_trades_warning"]))
        base_t = trades_by_combo.get(default_key, pd.DataFrame())
        base_test = base_t[pd.DatetimeIndex(base_t["tdate"]).year == year] if len(base_t) else base_t
        rows.append({
            "test_year": year,
            "chosen": ", ".join(f"{k.split('.')[-1]}={v}" for k, v in best.items()),
            "train_avg_r": float(train.set_index("combo").loc[key, objective]),
            "test_trades": s["trades"],
            "test_avg_r": s.get("avg_r_net", float("nan")),
            "test_win_rate": s.get("win_rate", float("nan")),
            "default_params_test_avg_r": float(base_test["r_net"].mean()) if len(base_test) else float("nan"),
        })
        oos.append(test)
    return pd.DataFrame(rows), (pd.concat(oos, ignore_index=True) if oos else pd.DataFrame()), tbl


def holdout_log_path(cfg: dict, dataset: str):
    return results_dir(cfg) / dataset / "holdout_log.jsonl"


def log_holdout(cfg: dict, dataset: str, name: str, overrides: dict, summary: dict, note: str) -> None:
    path = holdout_log_path(cfg, dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "name": name, "overrides": overrides,
           "note": note, **{k: (None if isinstance(v, float) and v != v else v) for k, v in summary.items()}}
    with open(path, "a") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")
