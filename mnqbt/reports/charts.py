"""Static PNG charts for reports (matplotlib, light theme).

Candles are drawn in ink only (hollow = up, filled = down) so that color is
free for the overlays, and every overlay carries a text label so nothing
depends on color alone.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948",
)
LEVEL_LABEL = {
    "pdh": "Prior-day high", "pdl": "Prior-day low", "dh": "Day high (so far)", "dl": "Day low (so far)",
    "asia_h": "Asia high", "asia_l": "Asia low", "london_h": "London high", "london_l": "London low",
    "ny_h": "Prior NY high", "ny_l": "Prior NY low", "vah": "Prior VAH", "val": "Prior VAL",
}


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    ax.grid(True, color=GRID, linewidth=0.6, linestyle="-")
    ax.set_axisbelow(True)


def _label(name: str) -> str:
    if name.startswith("sh") and name[2:].isdigit():
        return f"15m swing high #{name[2:]}"
    if name.startswith("sl") and name[2:].isdigit():
        return f"15m swing low #{name[2:]}"
    return LEVEL_LABEL.get(name, name)


def _candles(ax, bars: pd.DataFrame, width: float = 0.62):
    for i, (o, h, l, c) in enumerate(bars[["open", "high", "low", "close"]].to_numpy()):
        ax.vlines(i, l, h, color=INK2, linewidth=0.8, zorder=2)
        up = c >= o
        lo, hi = (o, c) if up else (c, o)
        ax.add_patch(Rectangle((i - width / 2, lo), width, max(hi - lo, 1e-9), facecolor=SURFACE if up else INK2,
                               edgecolor=INK2, linewidth=0.8, zorder=3))


def _pos(start_ns: np.ndarray, t: int) -> int:
    return int(np.searchsorted(start_ns, t, side="right") - 1)


def plot_setup(F, cfg: dict, trade: pd.Series, path: Path, tf: str = "5min", before: int = 40, after: int = 16) -> Path:
    """Two-panel chart (MNQ over MES) of one trade with every rule element drawn."""
    from mnqbt.config import get

    a = F.bars("a", tf)
    b = F.bars("b", tf).reindex(a.index)
    sa = a["start_ns"].to_numpy()
    p_trig = _pos(sa, int(trade["trig_start_ns"]))
    p_prev = int(trade["trig_prev_pos"]) if trade["trig_prev_pos"] >= 0 else p_trig
    p_place = _pos(sa, int(trade["placed_ns"]))
    p_fill = _pos(sa, int(trade["fill_ns"]))
    p_exit = _pos(sa, int(trade["exit_ns"]))
    lo = max(0, min(p_prev, p_trig) - before // 3, p_trig - before)
    hi = min(len(a), max(p_exit, p_place) + after)
    # stay inside the trade's trading day (no VWAP reset / maintenance halt in the picture)
    td_bars = a["tdate"].to_numpy()
    same = np.flatnonzero(td_bars == td_bars[p_fill])
    lo, hi = max(lo, int(same[0])), min(hi, int(same[-1]) + 1)
    A, B = a.iloc[lo:hi], b.iloc[lo:hi]
    off = lambda p: p - lo  # noqa: E731

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7.8), sharex=True, gridspec_kw={"height_ratios": [3, 1.6]}, facecolor=SURFACE)
    for ax in (ax1, ax2):
        _style(ax)
    _candles(ax1, A)
    _candles(ax2, B.dropna())
    d = int(trade["dir"])
    xr = hi - lo

    # key level
    lv_tbl = F.levels(cfg, get(cfg, "rules.smt.timeframe"))
    name = str(trade.get("level", ""))
    if name and name in lv_tbl:
        lvl = float(lv_tbl[name].iloc[p_trig])
        ax1.axhline(lvl, color=MUTED, linewidth=1.2, zorder=1)
        ax1.text(xr - 0.5, lvl, f" {_label(name)}  {lvl:,.2f}", color=INK2, fontsize=8, va="bottom", ha="right")

    # VWAP (1m, sampled at 5m closes)
    vw = F.vwap(cfg)
    idx_1m = np.searchsorted(F.ts, A["known_ns"].to_numpy(), side="left") - 1
    ax1.plot(np.arange(len(A)), vw[np.clip(idx_1m, 0, len(vw) - 1)], color=ORANGE, linewidth=1.4, zorder=4)
    ax1.text(len(A) - 0.5, vw[np.clip(idx_1m[-1], 0, len(vw) - 1)], " VWAP", color=INK2, fontsize=8, va="center")

    # prior value area
    daily = F.daily(cfg)
    td = pd.Timestamp(trade["tdate"])
    for col, lab in (("vah_prior", "Prior VAH"), ("val_prior", "Prior VAL")):
        v = daily.at[td, col] if td in daily.index else np.nan
        ylo, yhi = A["low"].min(), A["high"].max()
        if np.isfinite(v) and ylo - 0.2 * (yhi - ylo) <= v <= yhi + 0.2 * (yhi - ylo):
            ax1.axhline(v, color=VIOLET, linewidth=0.9, zorder=1)
            ax1.text(0.2, v, f"{lab} {v:,.2f}", color=INK2, fontsize=7.5, va="bottom")

    # FVG box
    if pd.notna(trade.get("fvg_top")):
        from mnqbt.rules.bars import tf_minutes

        fvg_w = tf_minutes(get(cfg, "rules.fvg.timeframe")) * 60_000_000_000
        c1 = _pos(sa, int(trade["fvg_known_ns"]) - 3 * fvg_w)
        p_known = _pos(sa, int(trade["fvg_known_ns"]) - 1)
        x0 = off(c1)
        x1 = off(max(p_fill, p_known) + 1)
        ax1.add_patch(Rectangle((x0 - 0.4, trade["fvg_bottom"]), x1 - x0 + 0.8, trade["fvg_top"] - trade["fvg_bottom"],
                                facecolor=BLUE, alpha=0.14, edgecolor="none", zorder=1))
        ax1.text(x0 - 0.4, trade["fvg_top"] if d < 0 else trade["fvg_bottom"], f" {tf} FVG", color=INK2, fontsize=8,
                 va="bottom" if d < 0 else "top")

    # SMT: connect the two swing extremes on each instrument
    col = "high" if d < 0 else "low"
    if trade["trig_prev_pos"] >= 0:
        xa = [off(p_prev), off(p_trig)]
        ya = [trade["prev_extreme"], trade["extreme"]]
        ax1.plot(xa, ya, color=MAGENTA, linewidth=2, zorder=5)
        ax1.scatter(xa, ya, s=36, color=MAGENTA, edgecolor=SURFACE, linewidth=1.5, zorder=6)
        yb = [trade["pair_prev"], trade["pair_now"]]
        ax2.plot(xa, yb, color=MAGENTA, linewidth=2, zorder=5)
        ax2.scatter(xa, yb, s=36, color=MAGENTA, edgecolor=SURFACE, linewidth=1.5, zorder=6)
        a_word = ("higher high" if trade["extreme"] > trade["prev_extreme"] else "lower high") if d < 0 else (
            "lower low" if trade["extreme"] < trade["prev_extreme"] else "higher low")
        b_word = ("higher high" if trade["pair_now"] > trade["pair_prev"] else "lower high") if d < 0 else (
            "lower low" if trade["pair_now"] < trade["pair_prev"] else "higher low")
        va = "bottom" if d < 0 else "top"
        ax1.text(off(p_trig) + 0.6, trade["extreme"], f"MNQ {a_word}", color=INK, fontsize=8.5, va=va)
        ax2.text(off(p_trig) + 0.6, trade["pair_now"], f"MES {b_word}  (SMT: {'yes' if trade['smt'] else 'no'})",
                 color=INK, fontsize=8.5, va=va)

    # order & trade
    xs, xe = off(p_place), off(p_exit) + 0.5
    for price, colr, lab in ((trade["entry"], BLUE, "entry"), (trade["stop"], RED, "stop"), (trade["target"], GREEN, "target")):
        ax1.hlines(price, xs, xe, color=colr, linewidth=1.6, zorder=5)
        ax1.text(xe + 0.2, price, f" {lab} {price:,.2f}", color=INK2, fontsize=8, va="center")
    ax1.axvline(xs, color=AXIS, linewidth=0.8, zorder=0)
    ax1.text(xs, ax1.get_ylim()[1], " order placed", color=MUTED, fontsize=7.5, va="top")
    ax1.scatter([off(p_fill)], [trade["entry"]], marker="^" if d > 0 else "v", s=70, color=BLUE, edgecolor=SURFACE, zorder=7)
    ax1.scatter([off(p_exit)], [trade["exit_price"]], marker="X", s=70, color=INK, edgecolor=SURFACE, zorder=7)

    # x axis in ET
    et = A.index.tz_convert(get(cfg, "project.timezone"))
    step = max(1, len(A) // 10)
    ticks = np.arange(0, len(A), step)
    ax2.set_xticks(ticks)
    ax2.set_xticklabels([et[i].strftime("%H:%M") for i in ticks])
    ax2.set_xlim(-1, len(A) + 7)
    ax1.set_ylabel("MNQ", color=MUTED, fontsize=9)
    ax2.set_ylabel("MES", color=MUTED, fontsize=9)
    side = "Long" if d > 0 else "Short"
    title = (
        f"{side} · {td.date()} ({et[0].strftime('%a')}) · {trade.get('fill_session', '')} session · "
        f"result {trade['r_net']:+.2f}R net, ${trade['pnl_usd']:+,.2f} ({trade['exit_reason']})"
    )
    sub = f"Times ET · {tf} candles · key level: {_label(name) if name else 'none'} · SMT leader: {trade.get('smt_leader') or '—'}"
    fig.text(0.012, 0.985, title, color=INK, fontsize=11.5, va="top", ha="left")
    fig.text(0.012, 0.952, sub, color=INK2, fontsize=8.5, va="top", ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)
    return path


def plot_equity(series: dict[str, pd.DataFrame], path: Path, title: str) -> Path:
    """Cumulative net R by exit date for up to three variants."""
    colors = [BLUE, ORANGE, AQUA]
    fig, ax = plt.subplots(figsize=(11, 4.2), facecolor=SURFACE)
    _style(ax)
    for (name, t), colr in zip(list(series.items())[:3], colors):
        if t is None or t.empty:
            continue
        t = t.sort_values("exit_ns")
        x = pd.to_datetime(t["exit_ns"], utc=True)
        y = t["r_net"].cumsum().to_numpy()
        ax.plot(x, y, color=colr, linewidth=2, label=name)
        ax.text(x.iloc[-1], y[-1], f"  {name} {y[-1]:+.1f}R", color=INK2, fontsize=8, va="center")
    ax.axhline(0, color=AXIS, linewidth=1)
    ax.set_ylabel("cumulative R (net of costs)", color=MUTED, fontsize=9)
    ax.set_title(title, loc="left", color=INK, fontsize=11)
    if len(series) > 1:
        ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="upper left")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)
    return path


def plot_by_year(tbl: pd.DataFrame, path: Path, title: str) -> Path:
    """Average net R per year (bars) with trade counts labelled."""
    fig, ax = plt.subplots(figsize=(11, 3.6), facecolor=SURFACE)
    _style(ax)
    x = np.arange(len(tbl))
    v = tbl["avg_r_net"].to_numpy()
    ax.bar(x, v, width=0.55, color=BLUE, zorder=3)
    ax.axhline(0, color=AXIS, linewidth=1)
    for xi, vi, n in zip(x, v, tbl["trades"].to_numpy()):
        ax.text(xi, vi, f"{vi:+.2f}\n n={n}", ha="center", va="bottom" if vi >= 0 else "top", fontsize=7.5, color=INK2)
    ax.set_xticks(x)
    ax.set_xticklabels([str(i) for i in tbl.index])
    ax.set_ylabel("avg R per trade (net)", color=MUTED, fontsize=9)
    ax.set_title(title, loc="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)
    return path


def plot_benchmark(dist: np.ndarray, strat: float, path: Path, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(9, 3.6), facecolor=SURFACE)
    _style(ax)
    ax.hist(dist, bins=40, color=MUTED, alpha=0.6, zorder=3)
    ax.axvline(strat, color=BLUE, linewidth=2, zorder=4)
    ax.text(strat, ax.get_ylim()[1] * 0.95, f"  strategy {strat:+.3f}R", color=INK, fontsize=9, va="top")
    ax.set_xlabel("average net R per trade of a random-entry run", color=MUTED, fontsize=9)
    ax.set_ylabel("runs", color=MUTED, fontsize=9)
    ax.set_title(title, loc="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)
    return path
