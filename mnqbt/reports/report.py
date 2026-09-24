"""Markdown report writers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from mnqbt.reports.metrics import BREAKDOWNS, breakdown


def _f(x, fmt="{:+.3f}"):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—" if not (isinstance(x, float) and np.isinf(x)) else "∞"
    return fmt.format(x)


def summary_table(results) -> str:
    head = ("| variant | trades | /yr | win % | avg R net | 95% CI (trades) | 95% CI (day blocks) | PF | net $ | "
            "max DD $ | max DD R | longest losing streak | same-bar ambiguous | note |")
    lines = [head, "|" + "---|" * 14]
    for r in results:
        s = r.summary
        if not s.get("trades"):
            lines.append(f"| {r.name} | 0 | | | | | | | | | | | | NO TRADES |")
            continue
        lines.append(
            f"| {r.name} | {s['trades']} | {s['trades_per_year']:.0f} | {100 * s['win_rate']:.1f} | {_f(s['avg_r_net'])} | "
            f"[{_f(s['ci_low'])}, {_f(s['ci_high'])}] | [{_f(s['ci_day_low'])}, {_f(s['ci_day_high'])}] | "
            f"{_f(s['profit_factor'], '{:.2f}')} | {s['net_pnl_usd']:,.0f} | {s['max_dd_usd']:,.0f} | {s['max_dd_r']:.1f} | "
            f"{s['longest_losing_streak']} | {100 * s['ambiguous_bar_share']:.1f}% | {'⚠ ' + s['warning'] if s['warning'] else ''} |"
        )
    return "\n".join(lines)


def df_to_md(df: pd.DataFrame, floatfmt: dict | None = None) -> str:
    if df is None or df.empty:
        return "_(none)_"
    floatfmt = floatfmt or {}
    cols = [str(df.index.name or "")] + [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    int_cols = {c for c in df.columns if pd.api.types.is_integer_dtype(df[c])}
    for pos in range(len(df)):
        cells = [str(df.index[pos])]
        for c in df.columns:
            v = df[c].iloc[pos]
            if c in int_cols:
                cells.append(f"{int(v):,}")
            elif isinstance(v, (float, np.floating)):
                cells.append(_f(float(v), floatfmt.get(c, "{:.3f}")))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def breakdown_md(trades: pd.DataFrame, keys: list[str]) -> str:
    fmt = {"win_rate": "{:.1%}", "avg_r_net": "{:+.3f}", "net_pnl_usd": "{:,.0f}", "profit_factor": "{:.2f}"}
    parts = []
    for k in keys:
        col = BREAKDOWNS[k]
        b = breakdown(trades, col)
        if b.empty:
            continue
        b.index.name = k
        parts += [f"**By {k}**", "", df_to_md(b, fmt), ""]
    return "\n".join(parts)


def funnel_md(funnel: dict) -> str:
    lines = ["| step | count |", "|---|---:|"]
    lines += [f"| {k} | {v:,} |" for k, v in funnel.items()]
    return "\n".join(lines)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path
