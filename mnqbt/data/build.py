"""Raw per-contract bars -> validated, back-adjusted, spliced continuous MNQ/MES."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from mnqbt.config import get
from mnqbt.data.continuous import build_continuous, splice
from mnqbt.data.store import save_processed
from mnqbt.timeutil import to_ns_index
from mnqbt.data.validate import basic_checks, clean, day_flags, pair_alignment, validation_report

log = logging.getLogger(__name__)


def combined_day_flags(a: pd.DataFrame, b: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Per-date flags for the traded instrument; a date is tradeable only if BOTH series are clean."""
    tick = float(get(cfg, "instruments.tick_size"))
    fa, fb = day_flags(a, cfg, tick, partner=b), day_flags(b, cfg, tick, partner=a)
    skip_short = bool(get(cfg, "setup.skip_short_sessions"))
    skip_gap = bool(get(cfg, "setup.skip_gap_days"))

    def bad(f):
        out = f["spike_day"].copy()
        if skip_short:
            out |= f["short"]
        if skip_gap:
            out |= f["gap_day"]
        return out

    flags = fa.copy()
    flags["pair_bad"] = bad(fb).reindex(fa.index, fill_value=True)
    flags["tradeable"] = ~(bad(fa) | flags["pair_bad"])
    return flags, fa, fb


def build_dataset(cfg: dict, raw: dict[str, pd.DataFrame], dataset: str, report_path: Path | None = None) -> dict:
    traded, pair = get(cfg, "instruments.traded"), get(cfg, "instruments.pair")
    proxies = get(cfg, "instruments.proxies") or {}
    tick = float(get(cfg, "instruments.tick_size"))
    splice_date = get(cfg, "instruments.splice_date")

    raw_checks = {root: basic_checks(df, tick) for root, df in raw.items()}

    a, a_rolls, a_sched = build_continuous(raw[traded], cfg, root=traded)
    b, b_rolls, _ = build_continuous(raw[pair], cfg, root=pair, forced_schedule=a_sched)
    splices = {}
    pa_root, pb_root = proxies.get(traded), proxies.get(pair)
    if pa_root in raw and pb_root in raw:
        pa, pa_rolls, pa_sched = build_continuous(raw[pa_root], cfg, root=pa_root)
        pb, pb_rolls, _ = build_continuous(raw[pb_root], cfg, root=pb_root, forced_schedule=pa_sched)
        a, splices[traded] = splice(pa, a, splice_date, cfg)
        b, splices[pair] = splice(pb, b, splice_date, cfg)
        cut = pd.Timestamp(splice_date)
        a_rolls = pd.concat([pa_rolls[pa_rolls["roll_tdate"] < cut], a_rolls[a_rolls["roll_tdate"] >= cut]])
        b_rolls = pd.concat([pb_rolls[pb_rolls["roll_tdate"] < cut], b_rolls[b_rolls["roll_tdate"] >= cut]])

    a, b = to_ns_index(clean(a)), to_ns_index(clean(b))
    flags, fa, fb = combined_day_flags(a, b, cfg)
    pa_tbl = pair_alignment(a, b)

    frames = {traded: a, pair: b, "day_flags": flags, "rolls": a_rolls.reset_index(drop=True)}
    out_dir = save_processed(cfg, dataset, frames)

    if report_path is not None:
        parts = [
            f"# Data validation — dataset `{dataset}`",
            "",
            f"Continuous contracts: roll rule `{get(cfg, 'continuous.roll_rule')}`, "
            f"adjustment `{get(cfg, 'continuous.adjustment')}`. "
            f"Tradeable trading dates: **{int(flags['tradeable'].sum())} / {len(flags)}**.",
            "",
        ]
        if splices:
            parts += ["Splices (proxy → micro):", ""]
            for root, s in splices.items():
                parts.append(
                    f"- {root}: from trading date {s['splice_tdate'].date()}; raw price difference proxy vs micro "
                    f"{s['raw_price_diff']:+.2f} pts (should be ~0); applied offset {s['gap']:+.2f} pts "
                    f"(includes the micro series' own back-adjustment), measured at {s['gap_ts']}"
                )
            parts.append("")
        parts.append(validation_report(traded, raw_checks[traded], basic_checks(a, tick, check_grid=False), fa, a_rolls, pa_tbl, cfg))
        parts.append(validation_report(pair, raw_checks[pair], basic_checks(b, tick, check_grid=False), fb, b_rolls, None, cfg))
        for root in (pa_root, pb_root):
            if root in raw_checks:
                parts += [f"## Raw checks {root}", "", *(f"- {k}: {v:,}" for k, v in raw_checks[root].items()), ""]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(parts))
    log.info("dataset %s written to %s", dataset, out_dir)
    return frames
