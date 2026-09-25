"""Run the PATTERNS.md hypotheses stage by stage and log every test.

Stages (each refuses to run unless the one before produced passes):
  explore   all 9 hypotheses on MNQ, explore split; Holm across 9
  validate  explore passes only, MNQ, validate split; Holm across the passes
  mes       hypotheses that passed both, on MES, explore and validate splits
  final     hypotheses that passed both, MNQ, final split; needs unlock_final=True

A filter hypothesis (H8, H9) is tested on the pooled trades of the rules H1-H7.  In
validate, a surviving filter therefore needs those rules' validate trades; they are
generated for the pooled test only, and the rules' own results are not computed.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from mnqbt.backtest.engine import EngineSettings, Market, simulate
from mnqbt.config import ROOT, apply_overrides, get
from mnqbt.data.store import load_processed, results_dir
from mnqbt.reports.metrics import bootstrap_mean_ci, bootstrap_p_positive, holm, summarize
from mnqbt.strategies.benchmark import random_benchmark
from mnqbt.strategies.common import Ctx
from mnqbt.strategies.patterns import BY_ID, FILTERS, HYPOTHESES, RULES, Hypothesis, daily_trend, news_days
from mnqbt.strategies.run import dev_frames, run_each

SPLITS = {"explore": ("2010-06-07", "2018-08-09"), "validate": ("2018-08-10", "2022-12-30"), "final": ("2023-01-03", "2100-01-01")}
POINT_VALUE = {"MNQ": 2.0, "MES": 5.0}
PAIR = {"MNQ": "MES", "MES": "MNQ"}
BOOT = 10_000
ALPHA = 0.05


# ---------------------------------------------------------------------------- data
@dataclass
class World:
    ctx: Ctx
    mk: Market
    st: EngineSettings
    start: pd.Timestamp
    end: pd.Timestamp
    instrument: str
    split: str


def load_world(cfg: dict, dataset: str, instrument: str, split: str) -> World:
    """Bars of ``instrument`` (its SMT pair as the second series) up to the end of ``split``; nothing later is loaded."""
    s, e = (pd.Timestamp(x) for x in SPLITS[split])
    fr = load_processed(cfg, dataset, [instrument, PAIR[instrument], "day_flags"])
    F, mk = dev_frames(cfg, fr[instrument], fr[PAIR[instrument]], fr["day_flags"], end=e)
    st = EngineSettings.from_cfg(apply_overrides(cfg, {"instruments.point_value": POINT_VALUE[instrument]}))
    ctx = Ctx(F, cfg)
    return World(ctx, mk, st, max(s, ctx.first_day), min(e, ctx.last_day), instrument, split)


def rule_trades(h: Hypothesis, w: World) -> pd.DataFrame:
    """Trades of rule ``h`` entered inside the split, tagged for the filter tests."""
    it = h.build(w.ctx)
    it = it[(it["tdate"] >= w.start) & (it["tdate"] <= w.end) & (it["flatten_ns"] <= w.mk.ts[-1])].reset_index(drop=True)
    t = simulate(w.mk, it, w.st)[0] if h.mode == "single" else run_each(w.mk, w.st, it)
    t["tdate"] = pd.DatetimeIndex(t["tdate"])
    t["hypothesis"] = h.id
    t["news_day"] = t["tdate"].isin(news_days(w.ctx.cfg))
    trend = daily_trend(w.ctx).reindex(t["tdate"]).to_numpy()
    t["trend"] = trend
    t["aligned"] = np.where(np.isnan(trend), np.nan, (t["dir"].to_numpy() == trend).astype(float))
    return t.sort_values("fill_ns", kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------------------- statistics
def bootstrap_diff(r: np.ndarray, in_a: np.ndarray, days: np.ndarray, reps: int = BOOT, seed: int = 1) -> dict:
    """Mean of group A minus mean of group B, resampling whole trading days: delta, 95% CI, one-sided p (H0: delta <= 0)."""
    codes, uniq = pd.factorize(days)
    a = in_a.astype(float)
    sa, na = np.bincount(codes, weights=r * a), np.bincount(codes, weights=a)
    sb, nb = np.bincount(codes, weights=r * (1 - a)), np.bincount(codes, weights=1 - a)
    rng = np.random.default_rng(seed)
    d = np.empty(reps)
    for k in range(0, reps, 1000):
        pick = rng.integers(0, len(uniq), size=(min(1000, reps - k), len(uniq)))
        with np.errstate(invalid="ignore", divide="ignore"):
            d[k:k + len(pick)] = sa[pick].sum(1) / na[pick].sum(1) - sb[pick].sum(1) / nb[pick].sum(1)
    d = d[np.isfinite(d)]
    delta = r[a > 0].mean() - r[a == 0].mean()
    return {"delta": float(delta), "ci_low": float(np.quantile(d, 0.025)), "ci_high": float(np.quantile(d, 0.975)),
            "p": float((1 + (d <= 0).sum()) / (1 + len(d))), "n_a": int(a.sum()), "n_b": int((1 - a).sum()),
            "mean_a": float(r[a > 0].mean()), "mean_b": float(r[a == 0].mean())}


def deflated_sharpe(r: np.ndarray, trial_srs: np.ndarray) -> float:
    """Deflated Sharpe ratio (Bailey & Lopez de Prado 2014) of per-trade returns ``r``: the probability that the
    true Sharpe ratio exceeds the best one expected from len(trial_srs) unskilled trials with their spread."""
    r = np.asarray(r, float)
    n, T = len(trial_srs), len(r)
    if T < 3 or n < 2 or r.std(ddof=1) == 0:
        return np.nan
    sr = r.mean() / r.std(ddof=1)
    z = r - r.mean()
    m2 = (z ** 2).mean()
    skew, kurt = (z ** 3).mean() / m2 ** 1.5, (z ** 4).mean() / m2 ** 2
    nd, g = NormalDist(), 0.5772156649
    sr0 = math.sqrt(np.var(trial_srs, ddof=1)) * ((1 - g) * nd.inv_cdf(1 - 1 / n) + g * nd.inv_cdf(1 - 1 / (n * math.e)))
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    return float(nd.cdf((sr - sr0) * math.sqrt(T - 1) / math.sqrt(denom))) if denom > 0 else np.nan


def rule_stats(t: pd.DataFrame, cfg: dict) -> dict:
    if t.empty:
        return {"trades": 0, "p": np.nan}
    s = summarize(t, reps=BOOT, level=0.95, min_trades=int(get(cfg, "research.min_trades_warning")))
    r = t["r_net"].to_numpy(float)
    s["p"] = bootstrap_p_positive(r, BOOT, groups=pd.DatetimeIndex(t["tdate"]).to_numpy(), seed=1)
    s["sr_trade"] = float(r.mean() / r.std(ddof=1)) if len(r) > 1 and r.std(ddof=1) > 0 else np.nan
    return s


def filter_stats(h: Hypothesis, pooled: pd.DataFrame) -> dict:
    t = pooled
    if h.slug == "skip_news":
        in_a = ~t["news_day"].to_numpy(bool)                  # A = kept (non-news) trades
    else:
        t = t[t["aligned"].notna()]
        in_a = t["aligned"].to_numpy(float) > 0                # A = trend-aligned trades
    out = bootstrap_diff(t["r_net"].to_numpy(float), in_a, pd.DatetimeIndex(t["tdate"]).to_numpy())
    out["trades"] = len(t)
    return out


# ---------------------------------------------------------------------------- log
def _commit() -> str:
    try:
        h = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "mnqbt", "config"], capture_output=True, text=True,
                               cwd=ROOT).stdout.strip()
        return h + ("+uncommitted" if dirty else "")
    except OSError:
        return ""


def out_dir(cfg: dict, dataset: str) -> Path:
    p = results_dir(cfg) / dataset / "patterns"
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_log(cfg: dict, dataset: str) -> pd.DataFrame:
    f = out_dir(cfg, dataset) / "test_log.jsonl"
    return pd.DataFrame([json.loads(x) for x in f.read_text().splitlines() if x.strip()]) if f.exists() else pd.DataFrame()


def append_log(cfg: dict, dataset: str, rows: list[dict]) -> None:
    stamp, commit = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), _commit()
    with open(out_dir(cfg, dataset) / "test_log.jsonl", "a") as f:
        for r in rows:
            clean = {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in r.items()}
            f.write(json.dumps({"time_utc": stamp, "commit": commit, **clean}) + "\n")


def study_of(log: pd.DataFrame) -> pd.Series:
    """Which study each log row belongs to (rows written before the gamma study have none: patterns)."""
    return log["study"].fillna("patterns") if "study" in log else pd.Series("patterns", index=log.index)


def passed(log: pd.DataFrame, stage: str, study: str = "patterns") -> list[str]:
    """Hypotheses that passed the latest run of ``stage`` of ``study``."""
    if log.empty:
        return []
    log = log[study_of(log) == study]
    if not (log["stage"] == stage).any():
        return []
    last = log[log["stage"] == stage]["time_utc"].max()
    x = log[(log["stage"] == stage) & (log["time_utc"] == last)]
    return sorted(x.loc[x["passed"].astype(bool), "hypothesis"].unique().tolist(), key=lambda h: int(h[1:]))


# ---------------------------------------------------------------------------- stages
@dataclass
class StageResult:
    stage: str
    rows: list[dict] = field(default_factory=list)       # one per test, as logged
    trades: dict[str, pd.DataFrame] = field(default_factory=dict)
    note: str = ""


def _test_split(cfg: dict, w: World, ids: list[str], family: int, stage: str, reps: int, bench: bool) -> StageResult:
    """Run hypotheses ``ids`` on one world; Holm across ``family`` tests (the ``ids``)."""
    res = StageResult(stage)
    wanted = [BY_ID[i] for i in ids]
    need_rules = [h for h in RULES if h.id in ids or any(f.id in ids for f in FILTERS)]
    trades = {h.id: rule_trades(h, w) for h in need_rules}
    res.trades = trades
    rows = []
    for h in wanted:
        if h.build is not None:
            m = rule_stats(trades[h.id], cfg)
            rows.append({"hypothesis": h.id, "name": h.name, "kind": "rule", "trades": m.get("trades", 0),
                         "avg_r_net": m.get("avg_r_net"), "avg_r_gross": m.get("avg_r_gross"), "win_rate": m.get("win_rate"),
                         "ci_low": m.get("ci_day_low"), "ci_high": m.get("ci_day_high"), "profit_factor": m.get("profit_factor"),
                         "trades_per_year": m.get("trades_per_year"), "max_dd_r": m.get("max_dd_r"), "p": m["p"],
                         "sr_trade": m.get("sr_trade")})
        else:
            pooled = pd.concat([trades[r.id] for r in RULES], ignore_index=True)
            m = filter_stats(h, pooled)
            rows.append({"hypothesis": h.id, "name": h.name, "kind": "filter", "trades": m["trades"], "delta": m["delta"],
                         "ci_low": m["ci_low"], "ci_high": m["ci_high"], "p": m["p"], "n_kept": m["n_a"], "n_removed": m["n_b"],
                         "avg_r_kept": m["mean_a"], "avg_r_removed": m["mean_b"]})
    adj = holm(np.array([r["p"] if r["p"] is not None else np.nan for r in rows], float))
    srs = np.array([r["sr_trade"] for r in rows if r["kind"] == "rule" and r.get("sr_trade") is not None], float)
    for r, a in zip(rows, adj):
        effect = r["avg_r_net"] if r["kind"] == "rule" else r["delta"]
        r.update(study="patterns", stage=stage, split=w.split, instrument=w.instrument, start=str(w.start.date()), end=str(w.end.date()),
                 p_adj=float(a), adjustment=f"Holm across {family}", passed=bool(effect is not None and effect > 0 and a < ALPHA))
        if r["kind"] == "rule" and len(srs) >= 2 and stage == "explore":
            r["deflated_sharpe"] = deflated_sharpe(trades[r["hypothesis"]]["r_net"].to_numpy(float), srs)
        if bench and r["kind"] == "rule" and r["passed"]:
            b = random_benchmark(w.ctx, w.mk, w.st, trades[r["hypothesis"]], w.start, w.end, reps, seed=7)
            r.update(p_random=b["p_value"], random_avg_r=b["bench_mean"])
    res.rows = rows
    return res


def run_stage(cfg: dict, dataset: str, stage: str, reps: int = 1000, unlock_final: bool = False) -> StageResult:
    log = read_log(cfg, dataset)
    if stage == "explore":
        ids = [h.id for h in HYPOTHESES]
        res = _test_split(cfg, load_world(cfg, dataset, "MNQ", "explore"), ids, len(ids), stage, reps, bench=True)
    elif stage == "validate":
        ids = passed(log, "explore", "patterns")
        if not ids:
            return StageResult(stage, note="Nothing passed explore, so validate was not used.")
        res = _test_split(cfg, load_world(cfg, dataset, "MNQ", "validate"), ids, len(ids), stage, reps, bench=False)
    elif stage == "mes":
        ids = sorted(set(passed(log, "explore", "patterns")) & set(passed(log, "validate", "patterns")), key=lambda h: int(h[1:]))
        if not ids:
            return StageResult(stage, note="Nothing passed both explore and validate, so there is nothing to check on MES.")
        res = StageResult(stage)
        for split in ("explore", "validate"):
            part = _test_split(cfg, load_world(cfg, dataset, "MES", split), ids, len(ids), stage, reps, bench=False)
            res.rows += part.rows
        for h in ids:  # combined p over both periods; holds if > 0 in both and combined p < 0.05
            rs = [r for r in res.rows if r["hypothesis"] == h]
            eff = [r["avg_r_net"] if r["kind"] == "rule" else r["delta"] for r in rs]
            pc = 1 - NormalDist().cdf(sum(NormalDist().inv_cdf(1 - min(max(r["p"], 1e-12), 1 - 1e-12)) for r in rs) / math.sqrt(len(rs)))
            for r in rs:
                r.update(p_combined=pc, passed=bool(all(e is not None and e > 0 for e in eff) and pc < ALPHA),
                         adjustment="Stouffer across the two periods")
    elif stage == "final":
        if not unlock_final:
            raise SystemExit("the final test is locked: pass unlock_final / --unlock-final only when told to")
        ids = sorted(set(passed(log, "explore", "patterns")) & set(passed(log, "validate", "patterns")), key=lambda h: int(h[1:]))
        if not ids:
            return StageResult(stage, note="Nothing passed explore and validate, so the final test stays unused.")
        res = _test_split(cfg, load_world(cfg, dataset, "MNQ", "final"), ids, len(ids), stage, reps, bench=False)
    else:
        raise ValueError(stage)
    append_log(cfg, dataset, res.rows)
    return res


# ---------------------------------------------------------------------------- reports
def _f(x, fmt="{:+.3f}") -> str:
    return "—" if x is None or (isinstance(x, float) and not math.isfinite(x)) else fmt.format(x)


def _p(x) -> str:
    return "—" if x is None or (isinstance(x, float) and not math.isfinite(x)) else ("<0.0001" if x < 1e-4 else f"{x:.4f}")


def stage_report(res: StageResult) -> str:
    L = [f"# Pattern search — stage `{res.stage}`", "", "Pre-registered in [PATTERNS.md](../../../PATTERNS.md). "
         "1R = 10% of the entry day's daily ATR. Costs as in the harness. p is one-sided (effect > 0), from 10,000 "
         "resamples of whole trading days.", ""]
    if res.note:
        return "\n".join(L + [f"**{res.note}**", ""])
    rules = [r for r in res.rows if r["kind"] == "rule"]
    filters = [r for r in res.rows if r["kind"] == "filter"]
    if rules:
        L += ["## Rules", "", "| # | hypothesis | instrument / split | trades | /yr | win % | avg R net | avg R gross | 95% CI | PF | "
              "p | p adj. | deflated Sharpe | random-entry p | passes |", "|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|"]
        for r in rules:
            L.append(f"| {r['hypothesis']} | {r['name']} | {r['instrument']} {r['split']} | {r['trades']:,} | {_f(r.get('trades_per_year'), '{:.0f}')} | "
                     f"{_f(100 * r['win_rate'] if r.get('win_rate') is not None else None, '{:.1f}')} | {_f(r.get('avg_r_net'))} | "
                     f"{_f(r.get('avg_r_gross'))} | [{_f(r.get('ci_low'))}, {_f(r.get('ci_high'))}] | {_f(r.get('profit_factor'), '{:.2f}')} | "
                     f"{_p(r['p'])} | {_p(r.get('p_adj'))} | {_f(r.get('deflated_sharpe'), '{:.3f}')} | {_p(r.get('p_random'))} | "
                     f"{'**yes**' if r['passed'] else 'no'} |")
        L.append("")
    if filters:
        L += ["## Filters (pooled trades of H1–H7)", "", "| # | hypothesis | instrument / split | trades | kept | avg R kept | removed | "
              "avg R removed | Δ | 95% CI | p | p adj. | passes |", "|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---|"]
        for r in filters:
            L.append(f"| {r['hypothesis']} | {r['name']} | {r['instrument']} {r['split']} | {r['trades']:,} | {r['n_kept']:,} | "
                     f"{_f(r['avg_r_kept'])} | {r['n_removed']:,} | {_f(r['avg_r_removed'])} | {_f(r['delta'])} | "
                     f"[{_f(r['ci_low'])}, {_f(r['ci_high'])}] | {_p(r['p'])} | {_p(r.get('p_adj'))} | {'**yes**' if r['passed'] else 'no'} |")
        L.append("")
    adj = sorted({r.get("adjustment", "") for r in res.rows})
    L += [f"Multiple-testing adjustment: {', '.join(adj)}.", ""]
    ok = [r["hypothesis"] for r in res.rows if r["passed"]]
    L += [f"**Passed:** {', '.join(sorted(set(ok), key=lambda h: int(h[1:])))}" if ok else "**Nothing passed this stage.**", ""]
    return "\n".join(L)


EARLIER = """## Earlier tests on these dates (other rules, same data)

- Step 3 (results/real/step3_variants.md): the ICT setup and 18 variants plus 2 engine checks, 2010-06 → 2022-12. None had an edge.
- STRATEGIES.md (results/real/strategies_dev.md): 15 published strategies, 2010-06 → 2022-12. None qualified.
- Earlier breakdowns of those runs (by session, level type, year) were looked at; they are part of why validate is not fresh data.
"""


def log_report(cfg: dict, dataset: str) -> str:
    log = read_log(cfg, dataset)
    L = ["# Pattern search and gamma study — every test run", "", "Generated from `test_log.jsonl`, which gets one line per test, "
         "appended and never edited. Hypotheses and rules: [PATTERNS.md](../../../PATTERNS.md) (H1–H9) and "
         "[GAMMA.md](../../../GAMMA.md) (G1–G5; each has a main test and a gamma contrast). \"passes\" is the hypothesis's "
         "verdict at that stage.", ""]
    if log.empty:
        L += ["No tests run yet.", ""]
    else:
        log = log.assign(study=study_of(log))
        L += ["| time (UTC) | commit | study | stage | instrument | split | # | test | hypothesis | trades | effect (avg R or Δ) | "
              "95% CI | p | p adj. | passes |", "|---|---|---|---|---|---|---|---|---|---:|---:|---|---:|---:|---|"]
        for r in log.to_dict("records"):
            eff = r.get("avg_r_net") if r.get("kind") in ("rule", "main") else r.get("delta")
            pa = r.get("p_combined") if r.get("stage") == "mes" else r.get("p_adj")
            test = {"rule": "rule", "filter": "filter", "main": "main", "contrast": "contrast"}.get(r.get("kind"), "")
            L.append(f"| {r['time_utc']} | {r['commit']} | {r['study']} | {r['stage']} | {r['instrument']} | {r['split']} | "
                     f"{r['hypothesis']} | {test} | {r['name']} | {r['trades']:,} | {_f(eff)} | [{_f(r.get('ci_low'))}, "
                     f"{_f(r.get('ci_high'))}] | {_p(r.get('p'))} | {_p(pa)} | {'yes' if r['passed'] else 'no'} |")
        L.append("")
    return "\n".join(L + [EARLIER])
