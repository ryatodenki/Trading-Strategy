"""YAML config loading, dotted-key overrides, and distance resolution."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "default.yaml"
VARIANTS_CONFIG = ROOT / "config" / "variants.yaml"


def load_yaml(path: str | Path) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def load_config(path: str | Path | None = None, overrides: Mapping[str, Any] | None = None) -> dict:
    cfg = load_yaml(path or DEFAULT_CONFIG)
    if overrides:
        cfg = apply_overrides(cfg, overrides)
    return cfg


def get(cfg: Mapping, dotted: str, default: Any = None) -> Any:
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return default
        node = node[part]
    return node


def apply_overrides(cfg: Mapping, overrides: Mapping[str, Any]) -> dict:
    """Return a deep copy of ``cfg`` with ``{"a.b.c": value}`` overrides applied."""
    out = copy.deepcopy(dict(cfg))
    for dotted, value in overrides.items():
        parts = dotted.split(".")
        node = out
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                raise KeyError(f"override path {dotted!r} does not exist in config")
            node = node[part]
        if parts[-1] not in node:
            raise KeyError(f"override key {dotted!r} does not exist in config")
        node[parts[-1]] = copy.deepcopy(value)
    return out


def resolve_dist(spec: Mapping | float | int, atr: np.ndarray | float) -> np.ndarray | float:
    """``{points, atr_frac}`` -> max(points, atr_frac * atr).  NaN ATR -> NaN."""
    if isinstance(spec, (int, float)):
        return np.full(np.shape(atr), float(spec)) if np.ndim(atr) else float(spec)
    pts = float(spec.get("points", 0.0))
    frac = float(spec.get("atr_frac", 0.0))
    atr_arr = np.asarray(atr, dtype=float)
    val = np.maximum(pts, frac * atr_arr)
    if frac > 0:
        val = np.where(np.isnan(atr_arr), np.nan, val)
    return val if np.ndim(val) else float(val)


def hhmm_to_minutes(text: str) -> int:
    hh, mm = text.split(":")
    return int(hh) * 60 + int(mm)
