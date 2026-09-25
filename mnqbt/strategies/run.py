"""Run the STRATEGIES.md candidates on the development period only and write the report."""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass

import numpy as np
import pandas as pd

from mnqbt.backtest.engine import TRADE_COLUMNS, EngineSettings, Market, run_order, simulate
from mnqbt.config import get
from mnqbt.data.sessions import trading_dates
from mnqbt.data.store import load_processed
from mnqbt.reports.metrics import benjamini_hochberg, bootstrap_p_positive, holm, summarize
from mnqbt.rules.features import Features
from mnqbt.strategies import STRATEGIES, Strategy, build
from mnqbt.strategies.benchmark import random_benchmark
from mnqbt.strategies.common import Ctx
from mnqbt.timeutil import ns


def dev_frames(cfg: dict, a: pd.DataFrame, b: pd.DataFrame, flags: pd.DataFrame) -> tuple[Features, Market]:
    """Features and market cut at research.dev_end: later bars are dropped before anything is computed.
    Contract rolls (including the NQ -> MNQ switch) come from the continuous series' ``contract`` column."""
    end = pd.Timestamp(get(cfg, "research.dev_end"))
    a, b = (x[trading_dates(x.index, cfg) <= end] for x in (a, b))
    contract = a["contract"].astype(str).to_numpy()
    roll_ns = ns(a.index)[1:][contract[1:] != contract[:-1]]
    F = Features(cfg, a, b, flags.loc[:end])
    return F, Market.from_frame(F.a1, roll_ns)


def load_dev(cfg: dict, dataset: str) -> tuple[Features, Market]:
    t, p = get(cfg, "instruments.traded"), get(cfg, "instruments.pair")
    fr = load_processed(cfg, dataset, [t, p, "day_flags"])
    return dev_frames(cfg, fr[t], fr[p], fr["day_flags"])


def run_each(mk: Market, st: EngineSettings, it: pd.DataFrame) -> pd.DataFrame:
    """Every intent through the engine on its own (no busy check: the strategy's own rules keep
    positions from overlapping)."""
    trades = []
    for k, row in enumerate(it.to_dict("records")):
        _, trade, _, _ = run_order(mk, st, row)
        if trade is not None:
            trade["intent"] = k
            trades.append(trade)
    df = pd.DataFrame(trades, columns=TRADE_COLUMNS)
    tags = [c for c in it.columns if c not in df.columns]
    return df.join(it[tags].reset_index(drop=True), on="intent")


def run_strategy(s: Strategy, ctx: Ctx, mk: Market, st: EngineSettings) -> pd.DataFrame:
    """All trades of ``s`` that open and close inside the loaded (development) data."""
    parts = []
    for part, it in build(s, ctx):
        it = it[(it["flatten_ns"] <= mk.ts[-1]) & (it["exit_tdate"] <= ctx.last_day)].reset_index(drop=True)
        parts.append(simulate(mk, it, st)[0] if part.mode == "single" else run_each(mk, st, it))
    t = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=TRADE_COLUMNS)
    t = t.sort_values("fill_ns", kind="stable").reset_index(drop=True)
    t["tdate"] = pd.DatetimeIndex(t["tdate"])
    t["strategy"] = s.name
    return t


def evaluate(trades: pd.DataFrame, cfg: dict, boot: int) -> dict:
    s = summarize(trades, reps=int(get(cfg, "research.bootstrap_reps")), level=float(get(cfg, "research.ci_level")),
                  min_trades=int(get(cfg, "research.min_trades_warning")))
    if trades.empty:
        return s
    r = trades["r_net"].to_numpy(float)
    yr = pd.DatetimeIndex(trades["tdate"]).year
    s["p_edge"] = bootstrap_p_positive(r, boot, groups=pd.DatetimeIndex(trades["tdate"]).to_numpy(), seed=1)
    by = trades.groupby(yr)["r_net"].agg(["mean", "size", "sum"])
    s["by_year"] = by
    s["best_year"] = int(by["sum"].idxmax())
    s["avg_r_without_best_year"] = float(r[yr != s["best_year"]].mean()) if (yr != s["best_year"]).any() else np.nan
    s["years_positive"] = int((by["mean"] > 0).sum())
    s["years"] = len(by)
    return s


_G: dict = {}


def _bench(name: str) -> tuple[str, dict]:
    g = _G
    return name, random_benchmark(g["ctx"], g["mk"], g["st"], g["trades"][name], g["start"], g["end"], g["reps"], seed=7)


@dataclass
class Results:
    strategies: list[Strategy]
    trades: dict[str, pd.DataFrame]
    stats: dict[str, dict]
    bench: dict[str, dict]
    first_day: pd.Timestamp
    last_day: pd.Timestamp
    finalists: list[str]


def run_all(cfg: dict, F: Features, mk: Market, names: list[str] | None = None, reps: int = 1000, boot: int = 10000,
            jobs: int = 4) -> Results:
    ctx = Ctx(F, cfg)
    st = EngineSettings.from_cfg(cfg)
    chosen = [s for s in STRATEGIES if names is None or s.name in names]
    trades = {s.name: run_strategy(s, ctx, mk, st) for s in chosen}
    last = pd.Timestamp(get(cfg, "research.dev_end"))
    for n, t in trades.items():  # nothing may reach into the holdout
        assert t.empty or pd.DatetimeIndex(t["exit_tdate"]).max() <= last, n
    stats = {n: evaluate(t, cfg, boot) for n, t in trades.items()}

    _G.update(ctx=ctx, mk=mk, st=st, trades=trades, start=ctx.first_day, end=ctx.last_day, reps=reps)
    order = sorted(trades, key=lambda n: -len(trades[n]))   # longest first balances the workers
    if jobs > 1:
        with mp.get_context("fork").Pool(jobs) as pool:
            bench = dict(pool.imap_unordered(_bench, order))
    else:
        bench = dict(map(_bench, order))

    ns_ = list(trades)
    pe = np.array([stats[n].get("p_edge", np.nan) for n in ns_])
    pr = np.array([bench[n]["p_value"] for n in ns_])
    for n, he, qe, hr, qr in zip(ns_, holm(pe), benjamini_hochberg(pe), holm(pr), benjamini_hochberg(pr)):
        s = stats[n]
        s.update(holm_edge=he, bh_edge=qe, holm_random=hr, bh_random=qr)
        s["qualifies"] = bool(s.get("trades", 0) >= int(get(cfg, "research.min_trades_warning")) and he < 0.05 and hr < 0.05
                              and s.get("avg_r_without_best_year", -1) > 0)
    finalists = sorted((n for n in ns_ if stats[n]["qualifies"]), key=lambda n: -stats[n]["ci_day_low"])[:2]
    return Results(chosen, trades, stats, bench, ctx.first_day, ctx.last_day, finalists)


# ---------------------------------------------------------------------------- report
def _f(x, fmt="{:+.3f}") -> str:
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else fmt.format(x)


def _p(x) -> str:
    return "—" if x is None or not np.isfinite(x) else ("<0.0001" if x < 1e-4 else f"{x:.4f}")


def report(res: Results, cfg: dict, reps: int, boot: int, commit: str = "") -> str:
    n_all = len(res.strategies)
    L = [f"# Candidate strategies — development period ({res.first_day.date()} → {res.last_day.date()})", "",
         f"Rules, statistics and the finalist rule were fixed in [STRATEGIES.md](../../STRATEGIES.md) before this run{commit}. "
         f"Each of the {n_all} strategies was run once with no parameter tuned. Bars after {get(cfg, 'research.dev_end')} "
         "were never loaded, and every trade opens and closes inside the period: **the 2023+ holdout is untouched**.", "",
         "- **R**: the stop distance for strategies with a stop; one daily ATR for strategies without one (column *1R*). "
         "R values scale with that choice; p-values and profit factors do not.",
         "- Costs: $0.60 per side, 1 tick slippage on market orders and stops, rolls charged as a close and a reopen.",
         f"- **p (edge)**: one-sided, H0 average net R ≤ 0, {boot:,} bootstrap resamples of whole trading days.",
         f"- **p (random)**: {reps:,} runs of the same trades moved to random days (same direction, time of day, holding "
         "length, stop in ATRs, target in R); share of runs doing at least as well.",
         f"- **Holm / BH**: adjusted across all {n_all} strategies (family-wise error / false discovery rate).", ""]

    L += ["## Results after costs", "",
          "| strategy | trades | /yr | win % | avg R net | avg R gross | 95% CI (trades) | 95% CI (days) | PF | net $ | max DD $ | max DD R | 1R |",
          "|---|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---|"]
    for s in res.strategies:
        m = res.stats[s.name]
        if not m.get("trades"):
            L.append(f"| {s.name} | 0 | | | | | | | | | | | {s.r_unit} |")
            continue
        warn = " ⚠" if m["trades"] < int(get(cfg, "research.min_trades_warning")) else ""
        L.append(f"| {s.name}{warn} | {m['trades']:,} | {m['trades_per_year']:.0f} | {100 * m['win_rate']:.1f} | "
                 f"{_f(m['avg_r_net'])} | {_f(m['avg_r_gross'])} | [{_f(m['ci_low'])}, {_f(m['ci_high'])}] | "
                 f"[{_f(m['ci_day_low'])}, {_f(m['ci_day_high'])}] | {_f(m['profit_factor'], '{:.2f}')} | "
                 f"{m['net_pnl_usd']:,.0f} | {m['max_dd_usd']:,.0f} | {m['max_dd_r']:.1f} | {s.r_unit} |")
    L += ["", "## Tests, corrected for testing all strategies", "",
          "| strategy | p (edge) | Holm | BH q | random avg R | random 5–95% | p (random) | Holm | BH q | avg R without best year | qualifies |",
          "|---|---:|---:|---:|---:|---|---:|---:|---:|---|---|"]
    for s in res.strategies:
        m, b = res.stats[s.name], res.bench[s.name]
        if not m.get("trades"):
            continue
        L.append(f"| {s.name} | {_p(m['p_edge'])} | {_p(m['holm_edge'])} | {_p(m['bh_edge'])} | {_f(b['bench_mean'])} | "
                 f"[{_f(b['bench_p05'])}, {_f(b['bench_p95'])}] | {_p(b['p_value'])} | {_p(m['holm_random'])} | "
                 f"{_p(m['bh_random'])} | {_f(m['avg_r_without_best_year'])} (best {m['best_year']}) | "
                 f"{'**yes**' if m['qualifies'] else 'no'} |")
    L += ["", "## Finalists", "",
          "Rule (STRATEGIES.md): Holm-adjusted p (edge) < 0.05, Holm-adjusted p (random) < 0.05, at least 100 trades, and "
          "average net R still positive without the best year; at most two, ranked by the lower day-block CI bound.", ""]
    L += ([f"- **{n}**" for n in res.finalists] if res.finalists else ["**None qualifies.**"]) + [""]

    years = sorted({y for s in res.strategies for y in res.stats[s.name].get("by_year", pd.DataFrame()).index})
    for title, col, fmt in (("average net R per trade", "mean", "{:+.2f}"), ("trades", "size", "{:.0f}")):
        L += [f"## Per year — {title}", "", "| strategy | " + " | ".join(map(str, years)) + " | years > 0 |",
              "|---|" + "---:|" * (len(years) + 1)]
        for s in res.strategies:
            m = res.stats[s.name]
            by = m.get("by_year", pd.DataFrame(columns=["mean", "size"]))
            cells = [fmt.format(by.at[y, col]) if y in by.index else "" for y in years]
            pos = f"{m['years_positive']}/{m['years']}" if m.get("trades") else ""
            L.append(f"| {s.name} | " + " | ".join(cells) + f" | {pos if col == 'mean' else ''} |")
        L.append("")

    L += ["## VWAP rules by volatility regime (description only, not tests)", "",
          "| strategy | regime | trades | avg R net | win % |", "|---|---|---:|---:|---:|"]
    for n in ("vwap_trend", "vwap_reversion"):
        t = res.trades.get(n)
        if t is None or t.empty:
            continue
        for reg, g in t.groupby("vol_state"):
            L.append(f"| {n} | {reg or '—'} | {len(g):,} | {g['r_net'].mean():+.3f} | {100 * (g['r_net'] > 0).mean():.1f} |")
    L.append("")
    return "\n".join(L)
