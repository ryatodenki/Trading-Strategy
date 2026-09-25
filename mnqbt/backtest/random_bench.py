"""Random-entry benchmark matched to the strategy's own orders.

For every real trade we keep everything except the signal:
  * order type (limit or market) and, for limits, the distance of the limit
    price from the last close before placement, measured in daily ATRs;
  * direction, time of day of placement, how long the order may wait;
  * stop distance in ATRs and target in R; same flatten time, costs and
    fill rules (the benchmark calls the engine's own ``run_order``).
Each benchmark run moves every order to a random tradeable date in the same
period and places it at the same time of day.  Orders that do not fill are
redrawn on another random date (the strategy's trades are also conditional on
a fill), so every run has the same number of trades.

p-value = share of runs whose mean net R is >= the strategy's (with +1 smoothing).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.backtest.engine import EngineSettings, Market, run_order
from mnqbt.rules.features import Features

MAX_REDRAWS = 25


def _round(price: float, tick: float, up: bool) -> float:
    return float(np.ceil(price / tick - 1e-9) * tick) if up else float(np.floor(price / tick + 1e-9) * tick)


def random_benchmark(F: Features, cfg: dict, trades: pd.DataFrame, start, end, reps: int, st: EngineSettings, seed: int = 0) -> dict:
    if trades.empty:
        return {"dist": np.array([]), "p_value": np.nan, "strategy": np.nan}
    mk = Market.from_frame(F.a1)
    daily = F.daily(cfg)
    tdate_all = pd.DatetimeIndex(F.a1["tdate"].to_numpy())
    tod = F.a1["tod"].to_numpy().astype(int)
    bounds = np.flatnonzero(np.r_[True, tdate_all[1:] != tdate_all[:-1], True])
    day_rng = {tdate_all[s]: (s, e) for s, e in zip(bounds[:-1], bounds[1:])}
    flat = F.flatten_ns(cfg)
    ok = F.flags["tradeable"].reindex(daily.index).fillna(False) & daily["atr"].notna()
    ok &= (daily.index >= pd.Timestamp(start)) & (daily.index <= pd.Timestamp(end))
    eligible = [d for d in daily.index[ok] if d in day_rng]
    atr_by_day = daily["atr"]

    ip = np.searchsorted(mk.ts, trades["placed_ns"].to_numpy(), side="left")
    place_tod = tod[np.minimum(ip, len(tod) - 1)]
    ref_close = mk.close[np.maximum(ip - 1, 0)]
    d_arr = trades["dir"].to_numpy(int)
    atr = trades["atr"].to_numpy(float)
    is_limit = (trades["entry_type"] == "limit").to_numpy()
    offset_atr = d_arr * (ref_close - trades["entry"].to_numpy(float)) / atr
    stop_ref = np.where(is_limit, trades["entry"].to_numpy(float), ref_close)
    stop_atr = d_arr * (stop_ref - trades["stop"].to_numpy(float)) / atr
    tgt_r = (d_arr * (trades["target"] - trades["entry"]) / trades["risk_pts"]).to_numpy(float)
    wait = (trades["expire_ns"] - trades["placed_ns"]).to_numpy(np.int64)
    tick = st.tick

    rng = np.random.default_rng(seed)
    means = np.full(reps, np.nan)
    for r in range(reps):
        res = []
        for k in range(len(trades)):
            d = int(d_arr[k])
            for _ in range(MAX_REDRAWS):
                day = eligible[int(rng.integers(0, len(eligible)))]
                s, e = day_rng[day]
                g = s + int(np.searchsorted(tod[s:e], place_tod[k], side="left"))
                if g <= s or g >= e:
                    continue
                a = float(atr_by_day[day])
                placed = int(mk.ts[g])
                ref = float(mk.close[g - 1])
                if is_limit[k]:
                    entry = _round(ref - d * offset_atr[k] * a, tick, up=d < 0)
                    stop = _round(entry - d * stop_atr[k] * a, tick, up=d < 0)
                    risk = d * (entry - stop)
                    target = _round(entry + d * tgt_r[k] * risk, tick, up=d > 0)
                    order = {"entry_type": "limit", "entry": entry, "target_src": "abs", "target_r": tgt_r[k]}
                else:
                    stop = _round(ref - d * stop_atr[k] * a, tick, up=d < 0)
                    order = {"entry_type": "market", "entry": np.nan, "target_src": "r_multiple", "target_r": tgt_r[k]}
                    target = ref + d * tgt_r[k] * d * (ref - stop)
                order.update({"placed_ns": placed, "dir": d, "stop": stop, "target": target,
                              "expire_ns": min(placed + int(wait[k]), int(flat[day])), "flatten_ns": int(flat[day])})
                status, trade, _, _ = run_order(mk, st, order)
                if trade is not None:
                    res.append(trade["r_net"])
                    break
        if res:
            means[r] = float(np.mean(res))
    strat = float(trades["r_net"].mean())
    valid = means[~np.isnan(means)]
    p = (1 + (valid >= strat).sum()) / (1 + len(valid))
    return {"dist": valid, "p_value": float(p), "strategy": strat, "bench_mean": float(valid.mean()),
            "bench_p05": float(np.quantile(valid, 0.05)), "bench_p95": float(np.quantile(valid, 0.95))}
