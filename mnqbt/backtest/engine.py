"""Event-driven 1m backtest engine for order intents from rules/setups.py.

Fill model (all prices in index points; 1 contract unless configured):

Limit entry at E (long; short mirrors):
  * ``through``: fills in the first bar whose low < E (price traded at least one
    tick beyond the limit).  ``touch``: low <= E.  Fill price = E.
  * If the would-be target is reached (high >= target) in a bar before the
    fill bar, the order is cancelled ("move happened without us").
  * The order is live from the first bar starting at/after placement until
    ``expire_ns`` (timeout / FVG expiry / no-entry window / flatten / structure flip).

Fill bar (1m bar in which the limit filled), conservative:
  * stop is hit if low <= stop (price must pass E on its way down, so this is
    real, not a guess);
  * target only counts if the bar CLOSES beyond it (otherwise we cannot know
    whether the high came before or after the fill).

Later bars:
  * stop if low <= stop, target if high > target (through) / >= (touch).
  * both in the same bar -> ``same_bar: stop_first`` (conservative) unless a
    finer-data resolver says otherwise; ``target_first`` is the optimistic bound.
  * stop fill = min(open, stop) - slippage (a bar that opens through the stop
    fills at its open); target fill = target exactly (no improvement).
  * still open at ``flatten_ns``: market exit at that bar's open - slippage.

Market entry (no-FVG variant): next bar open + slippage; target = entry + R * risk.
Costs: commission+fees per contract per side, both sides.
One position at a time: an intent placed while an order is working or a
position is open is skipped (and counted).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from mnqbt.config import get
from mnqbt.timeutil import NS_PER_MIN

INT_MAX = np.iinfo(np.int64).max
TRADE_COLUMNS = [
    "intent", "dir", "placed_ns", "fill_ns", "exit_ns", "entry", "stop", "target", "risk_pts", "exit_price", "exit_reason",
    "ambiguous_bar", "bars_held", "mfe_r", "mae_r", "gross_pts", "net_pts", "commission", "pnl_usd", "gross_usd",
    "slippage_usd", "r_gross", "r_net", "fill_session",
]


@dataclass(frozen=True)
class EngineSettings:
    fill_mode: str
    same_bar: str
    commission_per_side: float
    slippage_ticks_stop: int
    slippage_ticks_market: int
    contracts: int
    tick: float
    point_value: float

    @classmethod
    def from_cfg(cls, cfg: dict) -> "EngineSettings":
        b = get(cfg, "backtest")
        return cls(
            fill_mode=b["fill_mode"],
            same_bar=b["same_bar"],
            commission_per_side=float(b["commission_per_side"]),
            slippage_ticks_stop=int(b["slippage_ticks_stop"]),
            slippage_ticks_market=int(b["slippage_ticks_market"]),
            contracts=int(b["contracts"]),
            tick=float(get(cfg, "instruments.tick_size")),
            point_value=float(get(cfg, "instruments.point_value")),
        )


@dataclass
class Market:
    ts: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    session: np.ndarray

    @classmethod
    def from_frame(cls, m1: pd.DataFrame) -> "Market":
        from mnqbt.timeutil import ns

        return cls(
            ts=ns(m1.index),
            open=m1["open"].to_numpy(float),
            high=m1["high"].to_numpy(float),
            low=m1["low"].to_numpy(float),
            close=m1["close"].to_numpy(float),
            session=m1["session"].astype(str).to_numpy() if "session" in m1 else np.full(len(m1), ""),
        )


Resolver = Callable[[int, int, float, float], str | None]


def _first(mask: np.ndarray) -> int:
    """Index of the first True, or INT_MAX."""
    if mask.size == 0:
        return INT_MAX
    i = int(np.argmax(mask))
    return i if mask[i] else INT_MAX


def exit_scan(
    mk: Market, g0: int, g_flat: int, d: int, stop: float, target: float, st: EngineSettings,
    limit_fill_bar: bool, resolver: Resolver | None = None,
) -> tuple[int, str, float, bool]:
    """Walk bars from the fill bar g0 until exit.  Returns (exit_bar, reason, raw_exit_price, ambiguous)."""
    h, l, c, o = mk.high, mk.low, mk.close, mk.open
    through = st.fill_mode == "through"
    g_flat = min(g_flat, len(mk.ts))
    start = g0
    if limit_fill_bar:
        if (l[g0] <= stop) if d > 0 else (h[g0] >= stop):
            return g0, "stop", stop, False
        if d > 0:
            tgt = c[g0] > target if through else c[g0] >= target
        else:
            tgt = c[g0] < target if through else c[g0] <= target
        if tgt:
            return g0, "target", target, False
        start = g0 + 1
    H, L = h[start:g_flat], l[start:g_flat]
    if d > 0:
        fs = _first(L <= stop)
        ft = _first(H > target if through else H >= target)
    else:
        fs = _first(H >= stop)
        ft = _first(L < target if through else L <= target)
    if fs == INT_MAX and ft == INT_MAX:
        if g_flat < len(mk.ts):
            return g_flat, "flatten", o[g_flat], False
        return len(mk.ts) - 1, "end_of_data", c[-1], False
    ambiguous = fs == ft
    if ambiguous:
        g = start + fs
        verdict = resolver(int(mk.ts[g]), d, stop, target) if resolver else None
        if verdict is None:
            verdict = "stop" if st.same_bar == "stop_first" else "target"
        take_stop = verdict == "stop"
    else:
        take_stop = fs < ft
    if take_stop:
        g = start + fs
        raw = min(o[g], stop) if d > 0 else max(o[g], stop)
        if limit_fill_bar and g == g0:
            raw = stop
        return g, "stop", raw, ambiguous
    g = start + ft
    return g, "target", target, ambiguous


def run_order(mk: Market, st: EngineSettings, o_: dict, resolver: Resolver | None = None) -> tuple[str, dict | None, int, int | None]:
    """Simulate ONE order from placement to exit.  Returns (status, trade or None, busy_until_ns, event_ns).

    ``o_`` keys: placed_ns, dir, expire_ns, flatten_ns, stop, target, entry_type ('limit'|'market'),
    entry, target_src, target_r, [cancel_reason_at_expiry].
    """
    ts, o, h, l = mk.ts, mk.open, mk.high, mk.low
    n = len(ts)
    through = st.fill_mode == "through"
    placed = int(o_["placed_ns"])
    d = int(o_["dir"])
    i0 = int(np.searchsorted(ts, placed, side="left"))
    i_exp = int(np.searchsorted(ts, int(o_["expire_ns"]), side="left"))
    i_flat = int(np.searchsorted(ts, int(o_["flatten_ns"]), side="left"))
    if i0 >= n:
        return "no_data", None, placed, None
    stop = float(o_["stop"])
    target = float(o_["target"])

    if o_["entry_type"] == "limit":
        e = float(o_["entry"])
        L, H = l[i0:i_exp], h[i0:i_exp]
        if d > 0:
            fill = L < e if through else L <= e
            reach = H >= target
        else:
            fill = H > e if through else H >= e
            reach = L <= target
        f = _first(fill)
        ct = _first(reach & ~fill)
        if ct < f:
            t = int(ts[i0 + ct])
            return "cancel_target_first", None, t + NS_PER_MIN, t
        if f == INT_MAX:
            return f"expired_{o_.get('cancel_reason_at_expiry', 'timeout')}", None, int(o_["expire_ns"]), int(o_["expire_ns"])
        g0 = i0 + f
        entry = e
        limit_bar = True
    else:
        g0 = i0
        if g0 >= i_flat:
            return "no_time_left", None, placed, None
        entry = o[g0] + d * st.slippage_ticks_market * st.tick
        if o_["target_src"] == "r_multiple":
            risk_now = d * (entry - stop)
            if risk_now <= 0:
                return "invalid_gap_through_stop", None, placed, int(ts[g0])
            raw_t = entry + d * float(o_["target_r"]) * risk_now
            target = np.ceil(raw_t / st.tick - 1e-9) * st.tick if d > 0 else np.floor(raw_t / st.tick + 1e-9) * st.tick
        limit_bar = False

    risk = d * (entry - stop)
    if risk <= 0 or d * (target - entry) <= 0:
        return "invalid_levels", None, placed, int(ts[g0])
    gx, reason, raw_exit, amb = exit_scan(mk, g0, i_flat, d, stop, target, st, limit_bar, resolver)
    if reason == "stop":
        exit_px = raw_exit - d * st.slippage_ticks_stop * st.tick
    elif reason in ("flatten", "end_of_data"):
        exit_px = raw_exit - d * st.slippage_ticks_market * st.tick
    else:
        exit_px = raw_exit
    seg_h, seg_l = h[g0:gx + 1], l[g0:gx + 1]
    mfe = (seg_h.max() - entry) if d > 0 else (entry - seg_l.min())
    mae = (entry - seg_l.min()) if d > 0 else (seg_h.max() - entry)
    commission = 2 * st.commission_per_side * st.contracts
    gross_pts = d * (raw_exit - (entry if limit_bar else o[g0]))
    net_pts = d * (exit_px - entry)
    pnl_usd = net_pts * st.point_value * st.contracts - commission
    risk_usd = risk * st.point_value * st.contracts
    trade = {
        "intent": -1,
        "dir": d,
        "placed_ns": placed,
        "fill_ns": int(ts[g0]),
        "exit_ns": int(ts[gx]),
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_pts": risk,
        "exit_price": exit_px,
        "exit_reason": reason,
        "ambiguous_bar": amb,
        "bars_held": gx - g0 + 1,
        "mfe_r": mfe / risk,
        "mae_r": mae / risk,
        "gross_pts": gross_pts,
        "net_pts": net_pts,
        "commission": commission,
        "pnl_usd": pnl_usd,
        "gross_usd": gross_pts * st.point_value * st.contracts,
        "slippage_usd": (gross_pts - net_pts) * st.point_value * st.contracts,
        "r_gross": gross_pts / risk,
        "r_net": pnl_usd / risk_usd,
        "fill_session": mk.session[g0],
    }
    return "filled", trade, int(ts[gx]) + NS_PER_MIN, int(ts[g0])


def simulate(mk: Market, intents: pd.DataFrame, st: EngineSettings, resolver: Resolver | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run intents through the engine, one position/working order at a time.  Returns (trades, order_log)."""
    trades, log = [], []
    busy_until = -1
    rows = intents.to_dict("records") if len(intents) else []
    for k, row in enumerate(rows):
        placed = int(row["placed_ns"])
        if placed < busy_until:
            log.append((k, "skipped_busy", placed, None))
            continue
        status, trade, busy, event = run_order(mk, st, row, resolver)
        if status in ("no_data", "no_time_left", "invalid_gap_through_stop", "invalid_levels"):
            log.append((k, status, placed, event))
            continue
        busy_until = busy
        if trade is not None:
            trade["intent"] = k
            trades.append(trade)
        log.append((k, status, placed, event))

    trades_df = pd.DataFrame(trades, columns=TRADE_COLUMNS)
    if trades_df.empty:
        ints = {"intent", "dir", "placed_ns", "fill_ns", "exit_ns", "bars_held"}
        trades_df = trades_df.astype({c: ("int64" if c in ints else "bool" if c == "ambiguous_bar" else "object"
                                          if c in ("exit_reason", "fill_session") else "float64") for c in TRADE_COLUMNS})
    tag_cols = [c for c in intents.columns if c not in trades_df.columns]
    if tag_cols:  # carry every intent tag (level, mood, VWAP side, ...) onto its trade, even for an empty result
        trades_df = trades_df.join(intents[tag_cols].reset_index(drop=True), on="intent")
    for c in ("placed_ns", "fill_ns", "exit_ns"):
        trades_df[c.replace("_ns", "_time")] = pd.to_datetime(trades_df[c].astype("int64"), utc=True)
    log_df = pd.DataFrame(log, columns=["intent", "status", "placed_ns", "event_ns"])
    return trades_df, log_df
