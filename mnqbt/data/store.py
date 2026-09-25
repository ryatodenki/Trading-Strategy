"""On-disk layout for market data (everything under project.data_dir, git-ignored)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mnqbt.config import ROOT, get


def data_dir(cfg: dict) -> Path:
    p = Path(get(cfg, "project.data_dir"))
    return p if p.is_absolute() else ROOT / p


def raw_dir(cfg: dict, source: str, root: str) -> Path:
    return data_dir(cfg) / "raw" / source / root


def processed_dir(cfg: dict, dataset: str) -> Path:
    return data_dir(cfg) / "processed" / dataset


def results_dir(cfg: dict) -> Path:
    p = Path(get(cfg, "project.results_dir"))
    return p if p.is_absolute() else ROOT / p


def scratch_dir(cfg: dict) -> Path:
    p = Path(get(cfg, "project.scratch_dir"))
    return p if p.is_absolute() else ROOT / p


def load_raw(cfg: dict, source: str, root: str) -> pd.DataFrame:
    files = sorted(raw_dir(cfg, source, root).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no raw parquet files for {root} under {raw_dir(cfg, source, root)}")
    df = pd.concat([pd.read_parquet(f) for f in files]).sort_index()
    return df


def save_processed(cfg: dict, dataset: str, frames: dict[str, pd.DataFrame]) -> Path:
    out = processed_dir(cfg, dataset)
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.to_parquet(out / f"{name}.parquet")
    return out


def load_processed(cfg: dict, dataset: str, names: list[str]) -> dict[str, pd.DataFrame]:
    base = processed_dir(cfg, dataset)
    missing = [n for n in names if not (base / f"{n}.parquet").exists()]
    if missing:
        raise FileNotFoundError(f"dataset {dataset!r} is missing {missing} in {base}; run `python -m mnqbt build` first")
    return {n: pd.read_parquet(base / f"{n}.parquet") for n in names}
