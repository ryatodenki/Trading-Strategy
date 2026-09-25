"""Run the GAMMA.md hypotheses stage by stage and log every test (same log as the pattern search).

Each hypothesis has two tests:
  main      average net R > 0 on its matched days (G1, G2 positive gamma; G3, G4 negative; G5 every
            day with a regime, exits chosen by the regime)
  contrast  Δ > 0: matched days minus opposite days (G1-G4), or gamma-matched exits minus swapped
            exits on the same entry signals (G5); whole trading days resampled
Explore: Holm across all 10 tests; a hypothesis passes if its main test is significant and Δ > 0.
Validate: explore passes only; Holm across their main tests; Δ > 0 again.
MES: those that passed both, on MES (explore and validate splits), Stouffer-combined, reported only.
Final: locked unless unlock_final.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np
import pandas as pd

from mnqbt.backtest.engine import simulate
from mnqbt.data.gex import load_gex, gamma_regime
from mnqbt.reports.metrics import holm
from mnqbt.strategies.benchmark import random_benchmark
from mnqbt.strategies.explore import (ALPHA, SPLITS, World, _f, _p, append_log, bootstrap_diff, deflated_sharpe, load_world,
                                      out_dir, passed, read_log, rule_stats)
from mnqbt.strategies.gamma import BY_ID, HYPOTHESES, GammaHypothesis
from mnqbt.strategies.run import run_each

STUDY = "gamma"
REGIME_NAME = {1: "positive", -1: "negative", 0: "exits by regime"}


def _order(ids) -> list[str]:
    return sorted(set(ids), key=lambda h: int(h[1:]))


# ---------------------------------------------------------------------------- data
@dataclass
class GammaWorld:
    w: World
    regime: pd.Series        # +1 / -1 / NaN per trading day; no GEX dated after the split end is loaded


def load_gamma_world(cfg: dict, dataset: str, instrument: str, split: str, gex: pd.Series | None = None) -> GammaWorld:
    w = load_world(cfg, dataset, instrument, split)
    end = pd.Timestamp(SPLITS[split][1])
    g = load_gex(cfg, end=end) if gex is None else gex[gex.index <= end]
    return GammaWorld(w, gamma_regime(g, w.ctx.trading_days()))


def regime_days(gw: GammaWorld) -> dict:
    """Entry-eligible days of the split by regime (description only)."""
    w = gw.w
    days = w.ctx.trading_days()
    days = days[(days >= w.start) & (days <= w.end)]
    days = days[w.ctx.can_enter(days)]
    r = gw.regime.reindex(days)
    return {"positive": int((r > 0).sum()), "negative": int((r < 0).sum()), "none": int(r.isna().sum()),
            "first_with_regime": str(r.dropna().index.min().date()) if r.notna().any() else None}


def hypothesis_trades(h: GammaHypothesis, gw: GammaWorld, swap: bool = False) -> pd.DataFrame:
    """All trades of ``h`` entered inside the split on days with a regime, tagged with the day's regime."""
    w = gw.w
    it = h.build(w.ctx, gw.regime, swap) if h.matched == 0 else h.build(w.ctx)
    it = it[(it["tdate"] >= w.start) & (it["tdate"] <= w.end) & (it["flatten_ns"] <= w.mk.ts[-1])].reset_index(drop=True)
    t = simulate(w.mk, it, w.st)[0] if h.mode == "single" else run_each(w.mk, w.st, it)
    t["tdate"] = pd.DatetimeIndex(t["tdate"])
    t["regime"] = gw.regime.reindex(t["tdate"]).to_numpy()
    t["hypothesis"] = h.id
    return t[t["regime"].notna()].sort_values("fill_ns", kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------------------- tests
@dataclass
class GammaResult:
    stage: str
    rows: list[dict] = field(default_factory=list)
    trades: dict[str, pd.DataFrame] = field(default_factory=dict)
    regime_days: list[dict] = field(default_factory=list)
    by_regime: list[dict] = field(default_factory=list)      # G5 split by regime, description only
    note: str = ""


def _main_and_contrast(h: GammaHypothesis, gw: GammaWorld, cfg: dict) -> tuple[dict, dict, pd.DataFrame, list[dict]]:
    t = hypothesis_trades(h, gw)
    if h.matched == 0:
        main_t = t
        alt = hypothesis_trades(h, gw, swap=True)
        r = np.r_[t["r_net"].to_numpy(float), alt["r_net"].to_numpy(float)]
        in_a = np.r_[np.ones(len(t), bool), np.zeros(len(alt), bool)]
        days = np.r_[pd.DatetimeIndex(t["tdate"]).values, pd.DatetimeIndex(alt["tdate"]).values]
        what = "gamma-matched exits − swapped exits"
        groups = ([(f"{REGIME_NAME[g]} gamma", "regime", g) for g in (1, -1)] + [(f"{tf} FVG", "fvg_tf", tf) for tf in ("15min", "5min")]
                  + [("FVG at the level", "at_level", True), ("FVG not at the level", "at_level", False)])
        extra = [{"hypothesis": h.id, "group": name, "trades": int((t[col] == v).sum()),
                  "avg_r_net": float(t.loc[t[col] == v, "r_net"].mean()) if (t[col] == v).any() else None,
                  "avg_r_net_swapped": float(alt.loc[alt[col] == v, "r_net"].mean()) if (alt[col] == v).any() else None}
                 for name, col, v in groups]
        t = pd.concat([t.assign(variant="matched"), alt.assign(variant="swapped")], ignore_index=True)
    else:
        main_t = t[t["regime"] == h.matched]
        r = t["r_net"].to_numpy(float)
        in_a = (t["regime"] == h.matched).to_numpy()
        days = pd.DatetimeIndex(t["tdate"]).values
        what = f"{REGIME_NAME[h.matched]} days − {REGIME_NAME[-h.matched]} days"
        extra = []
    m = rule_stats(main_t, cfg)
    main = {"hypothesis": h.id, "name": h.name, "kind": "main", "trades": m.get("trades", 0), "avg_r_net": m.get("avg_r_net"),
            "avg_r_gross": m.get("avg_r_gross"), "win_rate": m.get("win_rate"), "ci_low": m.get("ci_day_low"),
            "ci_high": m.get("ci_day_high"), "profit_factor": m.get("profit_factor"), "trades_per_year": m.get("trades_per_year"),
            "max_dd_r": m.get("max_dd_r"), "p": m["p"], "sr_trade": m.get("sr_trade"),
            "days": REGIME_NAME[h.matched] if h.matched else "every day with a regime"}
    if in_a.any() and (~in_a).any():
        c = bootstrap_diff(r, in_a, days)
        contrast = {"hypothesis": h.id, "name": h.name, "kind": "contrast", "trades": int(len(r)), "delta": c["delta"],
                    "ci_low": c["ci_low"], "ci_high": c["ci_high"], "p": c["p"], "n_matched": c["n_a"], "n_opposite": c["n_b"],
                    "avg_r_matched": c["mean_a"], "avg_r_opposite": c["mean_b"], "contrast": what}
    else:
        contrast = {"hypothesis": h.id, "name": h.name, "kind": "contrast", "trades": int(len(r)), "delta": None, "p": np.nan,
                    "n_matched": int(in_a.sum()), "n_opposite": int((~in_a).sum()), "contrast": what}
    return main, contrast, t, extra


def _test_split(cfg: dict, gw: GammaWorld, ids: list[str], stage: str, reps: int, holm_on_contrasts: bool,
                bench: bool) -> GammaResult:
    res = GammaResult(stage, regime_days=[{"instrument": gw.w.instrument, "split": gw.w.split, **regime_days(gw)}])
    mains, contrasts = [], []
    for hid in ids:
        h = BY_ID[hid]
        main, con, t, extra = _main_and_contrast(h, gw, cfg)
        mains.append(main)
        contrasts.append(con)
        res.trades[hid] = t
        res.by_regime += extra
    fam = mains + contrasts if holm_on_contrasts else mains
    # a test that could not be computed (no trades) stays in the family as p = 1, so the family size is fixed
    adj = holm(np.nan_to_num(np.array([np.nan if r["p"] is None else r["p"] for r in fam], float), nan=1.0))
    for r, a in zip(fam, adj):
        r["p_adj"] = float(a)
    family = f"Holm across {len(fam)} tests" + ("" if holm_on_contrasts else " (main tests)")
    srs = np.array([r["sr_trade"] for r in mains if r.get("sr_trade") is not None], float)
    w = gw.w
    for main, con in zip(mains, contrasts):
        ok = (main["avg_r_net"] is not None and main["avg_r_net"] > 0 and main["p_adj"] < ALPHA
              and con.get("delta") is not None and con["delta"] > 0)
        for r in (main, con):
            r.update(study=STUDY, stage=stage, split=w.split, instrument=w.instrument, start=str(w.start.date()),
                     end=str(w.end.date()), adjustment=family, passed=bool(ok))
        if stage == "explore" and len(srs) >= 2 and main["trades"]:
            t = res.trades[main["hypothesis"]]
            t = t[t["variant"] == "matched"] if "variant" in t else t[t["regime"] == BY_ID[main["hypothesis"]].matched]
            main["deflated_sharpe"] = deflated_sharpe(t["r_net"].to_numpy(float), srs)
        h = BY_ID[main["hypothesis"]]
        if bench and ok and h.matched != 0:
            t = res.trades[h.id]
            t = t[t["regime"] == h.matched]
            allowed = gw.regime.index[gw.regime == h.matched]
            b = random_benchmark(w.ctx, w.mk, w.st, t, w.start, w.end, reps, seed=7, allowed_days=allowed)
            main.update(p_random=b["p_value"], random_avg_r=b["bench_mean"])
    res.rows = [r for pair in zip(mains, contrasts) for r in pair]
    return res


def run_stage(cfg: dict, dataset: str, stage: str, reps: int = 1000, unlock_final: bool = False,
              gex: pd.Series | None = None) -> GammaResult:
    log = read_log(cfg, dataset)
    if stage == "explore":
        ids = [h.id for h in HYPOTHESES]
        res = _test_split(cfg, load_gamma_world(cfg, dataset, "MNQ", "explore", gex), ids, stage, reps, True, bench=True)
    elif stage == "validate":
        ids = passed(log, "explore", STUDY)
        if not ids:
            return GammaResult(stage, note="Nothing passed explore, so validate was not used.")
        res = _test_split(cfg, load_gamma_world(cfg, dataset, "MNQ", "validate", gex), ids, stage, reps, False, bench=False)
    elif stage == "mes":
        ids = _order(set(passed(log, "explore", STUDY)) & set(passed(log, "validate", STUDY)))
        if not ids:
            return GammaResult(stage, note="Nothing passed both explore and validate, so there is nothing to check on MES.")
        res = GammaResult(stage)
        for split in ("explore", "validate"):
            part = _test_split(cfg, load_gamma_world(cfg, dataset, "MES", split, gex), ids, stage, reps, False, bench=False)
            res.rows += part.rows
            res.regime_days += part.regime_days
            res.by_regime += part.by_regime
        for h in ids:
            ms = [r for r in res.rows if r["hypothesis"] == h and r["kind"] == "main"]
            pc = 1 - NormalDist().cdf(sum(NormalDist().inv_cdf(1 - min(max(r["p"], 1e-12), 1 - 1e-12)) for r in ms) / math.sqrt(len(ms)))
            holds = all(r["avg_r_net"] is not None and r["avg_r_net"] > 0 for r in ms) and pc < ALPHA
            for r in res.rows:
                if r["hypothesis"] == h:
                    r.update(p_combined=pc, passed=bool(holds), adjustment="Stouffer across the two periods")
    elif stage == "final":
        if not unlock_final:
            raise SystemExit("the final test is locked: pass unlock_final / --unlock-final only when told to")
        ids = _order(set(passed(log, "explore", STUDY)) & set(passed(log, "validate", STUDY)))
        if not ids:
            return GammaResult(stage, note="Nothing passed explore and validate, so the final test stays unused.")
        res = _test_split(cfg, load_gamma_world(cfg, dataset, "MNQ", "final", gex), ids, stage, reps, False, bench=False)
    else:
        raise ValueError(stage)
    append_log(cfg, dataset, res.rows)
    return res


# ---------------------------------------------------------------------------- report
def gamma_dir(cfg: dict, dataset: str):
    p = out_dir(cfg, dataset).parent / "gamma"
    p.mkdir(parents=True, exist_ok=True)
    return p


def stage_report(res: GammaResult) -> str:
    L = [f"# Gamma study — stage `{res.stage}`", "", "Pre-registered in [GAMMA.md](../../../GAMMA.md). 1R = 10% of the entry "
         "day's daily ATR. Costs as in the harness. p is one-sided (effect > 0), from 10,000 resamples of whole trading days. "
         "Every test is also in the shared log: [../patterns/README.md](../patterns/README.md).", ""]
    if res.note:
        return "\n".join(L + [f"**{res.note}**", ""])
    if res.regime_days:
        L += ["## Days by gamma regime (entry-eligible days; description only)", "", "| instrument / split | positive | negative | "
              "no regime | first day with a regime |", "|---|---:|---:|---:|---|"]
        for d in res.regime_days:
            L.append(f"| {d['instrument']} {d['split']} | {d['positive']:,} | {d['negative']:,} | {d['none']:,} | {d['first_with_regime']} |")
        L.append("")
    mains = [r for r in res.rows if r["kind"] == "main"]
    cons = [r for r in res.rows if r["kind"] == "contrast"]
    L += ["## Main tests: does the rule make money on its matched days?", "", "| # | hypothesis | instrument / split | days | trades | "
          "/yr | win % | avg R net | avg R gross | 95% CI (net) | PF | p | p adj. | deflated Sharpe | random-entry p | passes |",
          "|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|"]
    for r in mains:
        flag = " ⚠" if r["trades"] and r["trades"] < 100 else ""
        L.append(f"| {r['hypothesis']} | {r['name']} | {r['instrument']} {r['split']} | {r['days']} | {r['trades']:,}{flag} | "
                 f"{_f(r.get('trades_per_year'), '{:.0f}')} | {_f(100 * r['win_rate'] if r.get('win_rate') is not None else None, '{:.1f}')} | "
                 f"{_f(r.get('avg_r_net'))} | {_f(r.get('avg_r_gross'))} | [{_f(r.get('ci_low'))}, {_f(r.get('ci_high'))}] | "
                 f"{_f(r.get('profit_factor'), '{:.2f}')} | {_p(r['p'])} | {_p(r.get('p_adj') if res.stage != 'mes' else r.get('p_combined'))} | "
                 f"{_f(r.get('deflated_sharpe'), '{:.3f}')} | {_p(r.get('p_random'))} | {'**yes**' if r['passed'] else 'no'} |")
    L += ["", "⚠ fewer than 100 trades.", "", "## Contrasts: does gamma help?", "", "| # | contrast | instrument / split | "
          "matched trades | avg R matched | opposite trades | avg R opposite | Δ | 95% CI | p | p adj. |",
          "|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|"]
    for r in cons:
        L.append(f"| {r['hypothesis']} | {r['contrast']} | {r['instrument']} {r['split']} | {r['n_matched']:,} | "
                 f"{_f(r.get('avg_r_matched'))} | {r['n_opposite']:,} | {_f(r.get('avg_r_opposite'))} | {_f(r.get('delta'))} | "
                 f"[{_f(r.get('ci_low'))}, {_f(r.get('ci_high'))}] | {_p(r['p'])} | {_p(r.get('p_adj'))} |")
    L.append("")
    if res.by_regime:
        L += ["## G5 by regime, FVG timeframe and FVG at the level (description only)", "", "| group | trades | avg R net (gamma-matched exits) | "
              "avg R net (swapped exits) |", "|---|---:|---:|---:|"]
        for r in res.by_regime:
            L.append(f"| {r['group']} | {r['trades']:,} | {_f(r['avg_r_net'])} | {_f(r['avg_r_net_swapped'])} |")
        L.append("")
    adj = sorted({r.get("adjustment", "") for r in res.rows})
    L += [f"Multiple-testing adjustment: {', '.join(adj)}. A hypothesis passes if its main test's adjusted p < 0.05 with "
          "avg R > 0, and its contrast Δ > 0.", ""]
    ok = _order(r["hypothesis"] for r in mains if r["passed"])
    L += [f"**Passed:** {', '.join(ok)}" if ok else "**Nothing passed this stage.**", ""]
    return "\n".join(L)
