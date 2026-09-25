"""Charts of GAMMA.md G5 trades (your breakout setup): one trade per chart, every rule element drawn,
and the cumulative result.  Same light theme and ink-only candles as reports/charts.py."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from mnqbt.backtest.engine import stop_path  # noqa: E402
from mnqbt.config import get  # noqa: E402
from mnqbt.reports.charts import (AXIS, BLUE, GREEN, INK, INK2, MUTED, ORANGE, RED, SURFACE, VIOLET, _candles, _label,  # noqa: E402
                                  _pos, _style)
from mnqbt.rules.swings import swings  # noqa: E402
from mnqbt.strategies.common import Ctx  # noqa: E402
from mnqbt.strategies.gamma import SWING_N, _G5Inputs, _vwap_at  # noqa: E402

BREAK_LABEL = {"swing": "latest 5m swing high", "vwap": "VWAP"}


def _level_values(ctx: Ctx, g: _G5Inputs, it: pd.Series) -> dict[str, float]:
    """Each broken key level's value as known when the FVG's first candle started (as the rule reads it)."""
    d, c1 = int(it["dir"]), int(it["fvg_c1_ns"])
    r5 = int(np.searchsorted(g.start5, c1))
    kn, px = g.sw[d]
    out = {}
    for name in str(it["level"]).split("+"):
        if name == "swing":
            out[name] = float(px[np.searchsorted(kn, c1, side="right") - 1])
        elif name == "vwap":
            out[name] = float(_vwap_at(ctx, g.vw, np.array([c1]), np.array([np.datetime64(it["tdate"], "ns")]))[0])
        else:
            out[name] = float(g.lv[name].iat[r5])
    return out


def plot_g5_trade(ctx: Ctx, g: _G5Inputs, it: pd.Series, tr: pd.Series, gex: float, path: Path,
                  before: int = 30, after: int = 8) -> Path:
    """``it``: the G5 order (intent), ``tr``: its trade, ``gex``: the GEX value the day's regime came from."""
    cfg = ctx.cfg
    b5 = g.b5
    start5 = g.start5
    d = int(tr["dir"])
    day = pd.Timestamp(tr["tdate"])
    day_rows = np.flatnonzero(pd.DatetimeIndex(b5["tdate"].to_numpy()) == day)
    p_c1, p_place = _pos(start5, int(it["fvg_c1_ns"])), _pos(start5, int(tr["placed_ns"]))
    p_fill, p_exit = _pos(start5, int(tr["fill_ns"])), _pos(start5, int(tr["exit_ns"]))
    lo, hi = max(p_c1 - before, day_rows[0]), min(p_exit + after, day_rows[-1])
    A = b5.iloc[lo:hi + 1]

    def off(p):
        return p - lo

    fig, ax = plt.subplots(figsize=(12, 6.6), facecolor=SURFACE)
    _style(ax)
    _candles(ax, A)
    xr = len(A) + 0.5

    # VWAP (a key level): value known at each 5m close
    i1 = np.searchsorted(ctx.ts, A["known_ns"].to_numpy(np.int64), side="left") - 1
    vw = g.vw[np.clip(i1, 0, len(g.vw) - 1)]
    ax.plot(np.arange(len(A)), vw, color=ORANGE, linewidth=1.3, zorder=4)
    margin = [(vw[-1], " VWAP")]                                      # right-margin labels, spaced out at the end

    # structure: the two latest confirmed 5m swing highs and lows when the FVG's first candle started
    sw = swings(b5, SWING_N)
    for kind in (1, -1):
        s = sw[(sw["kind"] == kind) & (sw["known_ns"] <= int(it["fvg_c1_ns"]))].tail(2)
        names = (("H", "HH") if d > 0 else ("H", "LH")) if kind > 0 else (("L", "HL") if d > 0 else ("L", "LL"))
        for (pos, price), name in zip(s[["pos", "price"]].to_numpy(), names):
            x = off(int(pos))
            if 0 <= x < len(A):
                y_off = 1 if kind > 0 else -1
                ax.scatter([x], [price], marker="v" if kind > 0 else "^", s=40, color=VIOLET, edgecolor=SURFACE, linewidth=1.2, zorder=6)
                ax.annotate(name, (x, price), textcoords="offset points", xytext=(0, 9 * y_off), ha="center",
                            va="bottom" if kind > 0 else "top", color=INK, fontsize=8)

    # the key level(s) the FVG's candles broke
    by_value: dict[float, list[str]] = {}
    for name, v in _level_values(ctx, g, it).items():
        label = "latest 5m swing low" if name == "swing" and d < 0 else BREAK_LABEL.get(name, _label(name))
        by_value.setdefault(round(v, 2), []).append(label)          # levels at the same price share one line and label
    for v, labels in by_value.items():
        ax.hlines(v, 0, off(p_place), color=VIOLET, linewidth=1.4, linestyles=(0, (4, 2)), zorder=4)
        ax.text(0.2, v, f"broken: {' + '.join(labels)} {v:,.2f}", color=INK, fontsize=8, va="bottom")

    # the FVG
    x0 = off(p_c1) - 0.4
    ax.add_patch(Rectangle((x0, it["fvg_bottom"]), off(p_exit) + 0.5 - x0, it["fvg_top"] - it["fvg_bottom"], facecolor=BLUE,
                           alpha=0.13, edgecolor="none", zorder=1))
    ax.text(x0, it["fvg_top"] if d > 0 else it["fvg_bottom"], f" {it['fvg_tf'].replace('min', 'm')} FVG" +
            (" (at the level)" if it["at_level"] else ""), color=INK2, fontsize=8, va="bottom" if d > 0 else "top")

    # order, stop, target / trailing stop
    xs, xe = off(p_place), off(p_exit) + 0.5
    xl = len(A) + 0.3                                                # labels in the right margin, clear of the candles

    def tail(y, colr):                                               # thin dotted lead from the line's end to its label
        ax.hlines(y, xe, len(A) + 0.1, color=colr, linewidth=0.8, linestyles=(0, (1, 2)), alpha=0.7, zorder=4)
    ax.hlines(tr["entry"], xs, xe, color=BLUE, linewidth=1.6, zorder=5)
    tail(tr["entry"], BLUE)
    margin.append((tr["entry"], f" entry {tr['entry']:,.2f}"))
    if isinstance(it["trail_ns"], np.ndarray) and len(it["trail_ns"]):
        g0 = int(np.searchsorted(ctx.ts, int(tr["fill_ns"])))
        g_end = int(np.searchsorted(ctx.ts, int(it["flatten_ns"])))
        path1 = stop_path(ctx.ts, g0, g_end, d, float(it["stop"]), it["trail_ns"], it["trail_px"])
        # stop in force during each 5m bar, from the order to the exit (initial stop before the fill)
        xs_bars = np.arange(p_place, p_exit + 1)
        k1 = np.clip(np.searchsorted(ctx.ts, start5[xs_bars]) - g0, 0, len(path1) - 1)
        stop_y = np.where(start5[xs_bars] <= ctx.ts[g0], it["stop"], path1[k1])
        ax.step(np.r_[off(xs_bars), xe], np.r_[stop_y, stop_y[-1]], where="post", color=RED, linewidth=1.6, zorder=5)
        tail(stop_y[-1], RED)
        margin.append((stop_y[-1], f" trailing stop {stop_y[-1]:,.2f}"))
        ax.text(xs, it["stop"], f"initial stop {it['stop']:,.2f} ", color=INK2, fontsize=8, va="center", ha="right")
    else:
        ax.hlines(tr["stop"], xs, xe, color=RED, linewidth=1.6, zorder=5)
        tail(tr["stop"], RED)
        margin.append((tr["stop"], f" stop {tr['stop']:,.2f}"))
        ax.hlines(tr["target"], xs, xe, color=GREEN, linewidth=1.6, zorder=5)
        tail(tr["target"], GREEN)
        margin.append((tr["target"], f" target {tr['target']:,.2f}"))
    ax.axvline(xs, color=AXIS, linewidth=0.8, zorder=0)
    ax.text(xs, ax.get_ylim()[1], " order placed", color=MUTED, fontsize=7.5, va="top")
    ax.scatter([off(p_fill)], [tr["entry"]], marker="^" if d > 0 else "v", s=70, color=BLUE, edgecolor=SURFACE, zorder=7)
    ax.scatter([off(p_exit)], [tr["exit_price"]], marker="X", s=70, color=INK, edgecolor=SURFACE, zorder=7)

    y0, y1 = ax.get_ylim()
    gap, last = 0.03 * (y1 - y0), -np.inf
    for y, text in sorted(margin, key=lambda m: m[0]):                # push labels apart, keep their order
        y = max(y, last + gap)
        ax.text(xl, y, text, color=INK2, fontsize=8, va="center")
        last = y

    et = A.index.tz_convert(get(cfg, "project.timezone"))
    step = max(1, len(A) // 12)
    ticks = np.arange(0, len(A), step)
    ax.set_xticks(ticks)
    ax.set_xticklabels([et[i].strftime("%H:%M") for i in ticks])
    ax.set_xlim(-1, xr + 11)
    ax.set_ylabel("NQ (back-adjusted)" if day < pd.Timestamp("2019-07-01") else "MNQ (back-adjusted)", color=MUTED, fontsize=9)

    regime = "positive" if tr["regime"] > 0 else "negative"
    style = "fixed target" if it["exit_style"] == "fixed" else "trailing stop, no target"
    reason = {"stop": "stopped out", "target": "target hit", "flatten": "closed at 15:55"}.get(tr["exit_reason"], tr["exit_reason"])
    title = (f"{'Long' if d > 0 else 'Short'} · {day.date()} ({et[0].strftime('%a')}) · {regime} gamma → {style} · "
             f"{tr['r_net']:+.2f}R net (${tr['pnl_usd']:+,.2f} on 1 MNQ), {reason}")
    t_place = pd.Timestamp(int(tr["placed_ns"]), tz="UTC").tz_convert(get(cfg, "project.timezone"))
    t_fill = pd.Timestamp(int(tr["fill_ns"]), tz="UTC").tz_convert(get(cfg, "project.timezone"))
    sub = (f"5m candles, times ET · GEX the evening before: {gex / 1e9:+.2f}bn · {it['fvg_tf'].replace('min', '-minute')} FVG · "
           f"reward:risk to the nearest key level {it['reward_risk']:.1f} · order {t_place:%H:%M}, filled {t_fill:%H:%M} · "
           f"1R = 10% of ATR = {0.1 * tr['atr']:.1f} pts")
    fig.text(0.012, 0.985, title, color=INK, fontsize=11.5, va="top", ha="left")
    fig.text(0.012, 0.948, sub, color=INK2, fontsize=8.5, va="top", ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.925))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)
    return path


def plot_g5_equity(trades: pd.DataFrame, path: Path, title: str) -> Path:
    """Cumulative R per trade, after and before costs, on one axis."""
    t = trades.sort_values("fill_ns")
    x = pd.to_datetime(t["fill_ns"].astype("int64"), utc=True)
    fig, ax = plt.subplots(figsize=(11, 4.4), facecolor=SURFACE)
    _style(ax)
    for col, colr, name in (("r_gross", ORANGE, "before costs"), ("r_net", BLUE, "after costs")):
        y = t[col].cumsum().to_numpy()
        ax.plot(x, y, color=colr, linewidth=2, zorder=3)
        ax.text(x.iloc[-1], y[-1], f"  {name} {y[-1]:+.1f}R", color=INK2, fontsize=8.5, va="center")
    ax.axhline(0, color=AXIS, linewidth=1)
    ax.set_ylabel("cumulative R (1R = 10% of ATR)", color=MUTED, fontsize=9)
    ax.set_xlim(x.iloc[0], x.iloc[-1] + (x.iloc[-1] - x.iloc[0]) * 0.16)
    fig.text(0.012, 0.975, title, color=INK, fontsize=11.5, va="top", ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)
    return path
