"""Random-entry benchmark for the strategies: the harness's matched benchmark (backtest/random_bench.py)
extended to holding periods of any length.

Every trade keeps everything except its date: direction; entry time of day (or "the close"); holding
length in exchange trading days and exit time of day (or "the close"); stop distance in daily ATRs
from the last close before entry; target in R; and its R unit (1 ATR of the new day when there is no
stop).  Each run moves every trade to a random entry-eligible day of the same period and trades it
through the engine's own ``run_order``; a draw that does not trade is redrawn.
p = share of runs whose mean net R is >= the strategy's, with +1 smoothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.backtest.engine import EngineSettings, Market, run_order
from mnqbt.strategies.common import Ctx

MAX_REDRAWS = 25


def _round(x: np.ndarray, tick: float, up: np.ndarray) -> np.ndarray:
    return np.where(up, np.ceil(x / tick - 1e-9) * tick, np.floor(x / tick + 1e-9) * tick)


def profile(ctx: Ctx, mk: Market, trades: pd.DataFrame) -> pd.DataFrame:
    """What each trade keeps when it is moved to another day."""
    placed = trades["placed_ns"].to_numpy(np.int64)
    flat = trades["flatten_ns"].to_numpy(np.int64)
    td, xd = pd.DatetimeIndex(trades["tdate"]), pd.DatetimeIndex(trades["exit_tdate"])
    d = trades["dir"].to_numpy(int)
    ref = mk.close[np.maximum(np.searchsorted(mk.ts, placed, side="left") - 1, 0)]
    atr = trades["atr"].to_numpy(float)
    stop, target = trades["stop"].to_numpy(float), trades["target"].to_numpy(float)
    risk_ref = d * (ref - stop)
    with np.errstate(invalid="ignore", divide="ignore"):
        tgt_r = np.where(trades["target_src"] == "r_multiple", trades["target_r"].to_numpy(float), d * (target - ref) / risk_ref)
    return pd.DataFrame({
        "dir": d,
        "entry_close": placed == ctx.close_ns(td),
        "entry_min": ctx.et_minute(placed),
        "exit_close": flat == ctx.close_ns(xd),
        "exit_min": ctx.et_minute(flat),
        "hold": ctx.days_between(td, xd),
        "stop_atr": risk_ref / atr,
        "tgt_r": tgt_r,
        "r_multiple": (trades["target_src"] == "r_multiple").to_numpy(),
    })


def timed_r_net(mk: Market, st: EngineSettings, placed: np.ndarray, flatten: np.ndarray, d: np.ndarray,
                risk_unit: np.ndarray) -> np.ndarray:
    """Net R of market-in / market-out trades with no stop and no target, exactly as ``run_order``
    computes them (NaN where the engine would not trade)."""
    n = len(mk.ts)
    i0 = np.searchsorted(mk.ts, placed, side="left")
    ix = np.searchsorted(mk.ts, flatten, side="left")
    ok = (i0 < n) & (i0 < ix) & (ix < n)
    i0c, ixc = np.minimum(i0, n - 1), np.minimum(ix, n - 1)
    slip = st.slippage_ticks_market * st.tick
    entry = mk.open[i0c] + d * slip
    exit_px = mk.open[ixc] - d * slip
    rolls = np.searchsorted(mk.roll_ns, mk.ts[ixc], side="right") - np.searchsorted(mk.roll_ns, mk.ts[i0c], side="right")
    commission = 2 * (1 + rolls) * st.commission_per_side * st.contracts
    net_pts = d * (exit_px - entry) - 2 * rolls * slip
    pnl = net_pts * st.point_value * st.contracts - commission
    return np.where(ok, pnl / (risk_unit * st.point_value * st.contracts), np.nan)


def random_benchmark(ctx: Ctx, mk: Market, st: EngineSettings, trades: pd.DataFrame, start, end, reps: int,
                     seed: int = 0) -> dict:
    if trades.empty:
        return {"dist": np.array([]), "p_value": np.nan, "strategy": np.nan, "bench_mean": np.nan, "bench_p05": np.nan,
                "bench_p95": np.nan}
    pf = profile(ctx, mk, trades)
    days = ctx.trading_days()
    days = days[(days >= pd.Timestamp(start)) & (days <= pd.Timestamp(end))]
    eligible = days[ctx.can_enter(days)]
    pos = np.searchsorted(ctx.days.values, eligible.values)
    last_pos = np.searchsorted(ctx.days.values, days[-1].to_datetime64())
    atr_e = ctx.atr_on(eligible)
    close_all = pd.Series(ctx.close_ns(ctx.days[pos.min(): last_pos + 1]), index=ctx.days[pos.min(): last_pos + 1])
    allowed = {h: np.flatnonzero(pos + h <= last_pos) for h in np.unique(pf["hold"])}

    d, hold = pf["dir"].to_numpy(), pf["hold"].to_numpy()
    no_stop = np.isnan(pf["stop_atr"].to_numpy()) & np.isnan(pf["tgt_r"].to_numpy())
    tick = st.tick
    rng = np.random.default_rng(seed)

    def draw(k: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Random entry day for trades ``k``: (placed, flatten, ref close, ATR)."""
        pick = np.empty(len(k), dtype=int)
        for h in np.unique(hold[k]):
            m = hold[k] == h
            pick[m] = allowed[h][rng.integers(0, len(allowed[h]), size=int(m.sum()))]
        day = eligible[pick]
        xday = ctx.days[pos[pick] + hold[k]]
        placed = np.where(pf["entry_close"].to_numpy()[k], close_all.reindex(day).to_numpy(),
                          ctx.at_minutes(day, pf["entry_min"].to_numpy()[k]))
        flat = np.where(pf["exit_close"].to_numpy()[k], close_all.reindex(xday).to_numpy(),
                        ctx.at_minutes(xday, pf["exit_min"].to_numpy()[k]))
        ref = mk.close[np.maximum(np.searchsorted(mk.ts, placed, side="left") - 1, 0)]
        return placed.astype(np.int64), flat.astype(np.int64), ref, atr_e[pick]

    means = np.full(reps, np.nan)
    for r in range(reps):
        res = np.full(len(pf), np.nan)
        todo = np.arange(len(pf))
        for _ in range(MAX_REDRAWS):
            if len(todo) == 0:
                break
            placed, flat, ref, a = draw(todo)
            fast = no_stop[todo]
            if fast.any():
                k = todo[fast]
                res[k] = timed_r_net(mk, st, placed[fast], flat[fast], d[k], a[fast])
            for j in np.flatnonzero(~fast):
                k = todo[j]
                dk = int(d[k])
                stop = np.nan
                if not np.isnan(pf["stop_atr"].iat[k]):
                    stop = float(_round(ref[j] - dk * pf["stop_atr"].iat[k] * a[j], tick, np.array(dk < 0)))
                target, src = np.nan, "abs"
                if pf["r_multiple"].iat[k]:
                    src = "r_multiple"
                elif not np.isnan(pf["tgt_r"].iat[k]):
                    target = float(_round(ref[j] + dk * pf["tgt_r"].iat[k] * dk * (ref[j] - stop), tick, np.array(dk > 0)))
                order = {"placed_ns": int(placed[j]), "dir": dk, "expire_ns": int(flat[j]), "flatten_ns": int(flat[j]),
                         "stop": stop, "target": target, "entry_type": "market", "entry": np.nan, "target_src": src,
                         "target_r": pf["tgt_r"].iat[k], "risk_unit": float(a[j])}
                _, trade, _, _ = run_order(mk, st, order)
                if trade is not None:
                    res[k] = trade["r_net"]
            todo = todo[np.isnan(res[todo])]
        if np.isfinite(res).any():
            means[r] = float(np.nanmean(res))
    strat = float(trades["r_net"].mean())
    valid = means[~np.isnan(means)]
    p = (1 + (valid >= strat).sum()) / (1 + len(valid))
    return {"dist": valid, "p_value": float(p), "strategy": strat, "bench_mean": float(valid.mean()),
            "bench_p05": float(np.quantile(valid, 0.05)), "bench_p95": float(np.quantile(valid, 0.95))}
