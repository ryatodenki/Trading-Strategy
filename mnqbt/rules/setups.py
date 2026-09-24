"""Assemble order intents (the things the engine tries to trade) from features.

Sequence for one trigger (a confirmed MNQ swing, see rules/smt.py):

1. Required core conditions: key level (swing extreme within tolerance of a
   key level) and/or SMT divergence.
2. Entry zone: the first FVG in the trade direction whose first candle starts
   at or after the swing bar and which is confirmed no later than
   ``max_minutes_smt_to_fvg`` after the trigger.  It must still be fresh and
   untouched (price has not yet traded to the entry price) when the order is
   placed.  Order placement time = max(trigger known, FVG known).
   Without the FVG requirement: market order at the next bar open.
3. Stop beyond the swept swing extreme (or the far FVG edge) plus buffer.
   Setups whose risk is outside [min_risk, max_risk] are skipped.
4. Target: fixed R multiple, or the nearest opposing key level at least
   ``liquidity_min_r`` R away.
5. Filters evaluated with information available at placement time.
6. Order expiry: first of max_wait, FVG expiry, the next no-entry window,
   flatten time, and (structure filter on) a structure flip against the trade.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mnqbt.config import get, hhmm_to_minutes, resolve_dist
from mnqbt.data.sessions import et_parts, in_windows, session_labels, trading_dates
from mnqbt.rules.bars import tf_minutes
from mnqbt.rules.features import Features
from mnqbt.rules.fvg import entry_price
from mnqbt.rules.levels import level_columns
from mnqbt.rules.news import news_block_mask
from mnqbt.timeutil import NS_PER_MIN


def _round_away(price: np.ndarray, direction: np.ndarray, tick: float) -> np.ndarray:
    """Round in the trade's favour-less direction: long target up / long stop down, etc."""
    up = np.ceil(price / tick - 1e-9) * tick
    dn = np.floor(price / tick + 1e-9) * tick
    return np.where(direction > 0, up, dn)


def _next_state_change(state: np.ndarray) -> dict[int, np.ndarray]:
    """For d in (+1, -1): out[d][i] = first index k >= i with state[k] != d (len if none)."""
    out = {}
    n = len(state)
    for d in (1, -1):
        bad = np.flatnonzero(state != d)
        idx = np.searchsorted(bad, np.arange(n + 1), side="left")
        out[d] = np.r_[bad, n][idx]
    return out


def build_intents(F: Features, cfg: dict, start: str | None = None, end: str | None = None) -> tuple[pd.DataFrame, dict]:
    s = get(cfg, "setup")
    req, flt = s["require"], s["filters"]
    tick = float(get(cfg, "instruments.tick_size"))
    va_levels = bool(flt["value_area"]) and get(cfg, "rules.value_area.mode") == "levels"
    funnel: dict[str, int] = {}

    trig = F.triggers(cfg)
    funnel["triggers (all MNQ swings)"] = len(trig)
    prox = "sweep" if get(cfg, "rules.levels.mode") == "sweep" else "near"
    near = trig[f"{prox}_core"].to_numpy() | (va_levels & trig[f"{prox}_va"].to_numpy())
    keep = np.ones(len(trig), bool)
    if req["key_level"]:
        keep &= near
        funnel["at a key level"] = int(keep.sum())
    if req["smt"]:
        keep &= trig["smt"].to_numpy()
        funnel["with SMT"] = int(keep.sum())
    trig = trig[keep].reset_index(drop=True)
    near = near[keep]
    use_va_name = va_levels & (trig["dist_va"].fillna(np.inf).to_numpy() < trig["dist_core"].fillna(np.inf).to_numpy())
    level_name = np.where(use_va_name, trig["level_va"].to_numpy(), trig["level_core"].to_numpy())
    level_name = np.where(near, level_name, "")

    ts = F.ts
    lo1, hi1, cl1 = (F.a1[k].to_numpy(float) for k in ("low", "high", "close"))
    window_ns = int(s["max_minutes_smt_to_fvg"]) * NS_PER_MIN
    frac = float(s["entry"]["fvg_fraction"])

    # ---- 2. entry zone -----------------------------------------------------
    rows = []
    if req["fvg"]:
        fv = F.fvgs(cfg)
        width = tf_minutes(get(cfg, "rules.fvg.timeframe")) * NS_PER_MIN
        by_dir = {}
        for d in (1, -1):
            f = fv[fv["dir"] == d]
            by_dir[d] = {k: f[k].to_numpy() for k in ("known_ns", "c1_start_ns", "top", "bottom", "expire_ns", "size")}
        for t in trig.itertuples():
            A = by_dir[t.dir]
            c1_min = t.start_ns // width * width
            i_lo = np.searchsorted(A["known_ns"], c1_min + 3 * width, side="left")
            i_hi = np.searchsorted(A["known_ns"], t.known_ns + window_ns, side="right")
            for i in range(i_lo, i_hi):
                if A["c1_start_ns"][i] < c1_min:
                    continue
                placed = max(int(A["known_ns"][i]), int(t.known_ns))
                if placed >= A["expire_ns"][i]:
                    continue
                e = float(entry_price(A["top"][i], A["bottom"][i], np.array(t.dir), frac, tick))
                j0 = np.searchsorted(ts, A["known_ns"][i], side="left")
                j1 = np.searchsorted(ts, placed, side="left")
                if j1 > j0 and ((t.dir > 0 and lo1[j0:j1].min() <= e) or (t.dir < 0 and hi1[j0:j1].max() >= e)):
                    continue  # already traded to the entry before we could place the order
                rows.append((t.Index, placed, "limit", e, A["top"][i], A["bottom"][i], A["size"][i], A["known_ns"][i], A["expire_ns"][i]))
                break
        funnel["with an FVG entry"] = len(rows)
    else:
        for t in trig.itertuples():
            j = np.searchsorted(ts, t.known_ns, side="left") - 1
            if j >= 0:
                rows.append((t.Index, int(t.known_ns), "market", cl1[j], np.nan, np.nan, np.nan, np.nan, np.iinfo(np.int64).max))
        funnel["market-entry candidates (no FVG)"] = len(rows)

    cols = ["trig", "placed_ns", "entry_type", "entry", "fvg_top", "fvg_bottom", "fvg_size", "fvg_known_ns", "fvg_expire_ns"]
    it = pd.DataFrame(rows, columns=cols)
    if it.empty:
        return it, funnel
    tr = trig.loc[it["trig"].to_numpy()].reset_index(drop=True)
    for c in ("dir", "extreme", "start_ns", "known_ns", "smt", "smt_leader", "atr", "prev_extreme", "pair_now", "pair_prev", "pos", "prev_pos"):
        it[c if c not in ("start_ns", "known_ns", "pos", "prev_pos") else f"trig_{c}"] = tr[c].to_numpy()
    it["level"] = level_name[it["trig"].to_numpy()]
    d = it["dir"].to_numpy()
    e = it["entry"].to_numpy(float)
    atr = it["atr"].to_numpy(float)

    # ---- 3. stop -----------------------------------------------------------
    buf = resolve_dist(s["stop"]["buffer"], atr)
    if s["stop"]["mode"] == "fvg" and req["fvg"]:
        ref = np.where(d > 0, it["fvg_bottom"], it["fvg_top"])
    else:
        ref = it["extreme"].to_numpy(float)
    stop = _round_away(ref - d * buf, -d, tick)
    risk = d * (e - stop)
    it["stop"], it["risk"] = stop, risk
    rmin = resolve_dist(s["stop"]["min_risk"], atr)
    rmax = resolve_dist(s["stop"]["max_risk"], atr)
    risk_ok = (risk > 0) & (risk >= rmin) & (risk <= rmax)

    # ---- 4. target ---------------------------------------------------------
    r_mult = float(s["target"]["r_multiple"])
    it["target_r"] = r_mult
    target = _round_away(e + d * r_mult * risk, d, tick)
    it["target_src"] = "r_multiple"
    if s["target"]["mode"] == "liquidity":
        lt = F.levels(cfg, get(cfg, "rules.smt.timeframe"))
        lstart = F.bars("a", get(cfg, "rules.smt.timeframe"))["start_ns"].to_numpy()
        row = np.searchsorted(lstart, it["placed_ns"].to_numpy(), side="right") - 1
        min_r = float(s["target"]["liquidity_min_r"])
        liq = np.full(len(it), np.nan)
        liq_name = np.full(len(it), "", dtype=object)
        for side in (1, -1):
            m = (d == side) & (row >= 0)
            if not m.any():
                continue
            cc = level_columns(cfg, side, include_value_area=va_levels)
            vals = lt[cc].to_numpy(float)[row[m]]
            thresh = (e + side * min_r * risk)[m][:, None]
            ok = (vals > thresh) if side > 0 else (vals < thresh)
            cand = np.where(ok, vals, np.inf if side > 0 else -np.inf)
            pick = cand.argmin(axis=1) if side > 0 else cand.argmax(axis=1)
            best = cand[np.arange(len(pick)), pick]
            found = np.isfinite(best)
            liq[np.flatnonzero(m)[found]] = best[found]
            liq_name[np.flatnonzero(m)[found]] = np.array(cc, dtype=object)[pick[found]]
        has = ~np.isnan(liq)
        target = np.where(has, _round_away(np.nan_to_num(liq), d, tick), target)
        it["target_src"] = np.where(has, "liq:" + liq_name.astype(str), "fallback_r")
        with np.errstate(invalid="ignore", divide="ignore"):
            it["target_r"] = np.where(has, d * (target - e) / risk, r_mult)
        if s["target"]["liquidity_fallback"] == "skip":
            risk_ok &= has
    it["target"] = target

    # ---- 5. context & filters at placement time ----------------------------
    # Everything below is derived from the placement timestamp itself or from bars that STARTED
    # before it (ip - 1), never from the bar the order will first trade in.
    placed = it["placed_ns"].to_numpy(np.int64)
    ip = np.searchsorted(ts, placed, side="left")
    placed_idx = pd.DatetimeIndex(placed.view("datetime64[ns]")).tz_localize("UTC")
    et_min, _ = et_parts(placed_idx, get(cfg, "project.timezone"))
    tdate = trading_dates(placed_idx, cfg)
    it["tdate"] = tdate
    it["et_min"] = et_min
    it["session"] = session_labels(et_min, cfg)
    halt = [[get(cfg, "sessions.trading_day_end"), get(cfg, "sessions.trading_day_start")]]
    fresh = ~in_windows(et_min, halt) & np.isin(tdate.dayofweek, [0, 1, 2, 3, 4])
    daily = F.daily(cfg)
    flags = F.flags.reindex(tdate)
    day_ok = flags["tradeable"].fillna(False).to_numpy(bool)
    sess_ok = np.isin(it["session"].to_numpy(), list(s["sessions_allowed"]))
    win_ok = ~in_windows(et_min, s["no_entry_windows"])
    flat_ns = F.flatten_ns(cfg).reindex(tdate).to_numpy()
    before_flat = placed < flat_ns
    atr_ok = ~np.isnan(atr)

    it["vol_state"] = daily["vol_state"].reindex(tdate).fillna("").to_numpy()
    it["vol_ratio"] = daily["vol_ratio"].reindex(tdate).to_numpy()
    ch = F.chop(cfg)
    ci = np.searchsorted(ch["known_ns"].to_numpy(), placed, side="right") - 1
    it["chop"] = np.where(ci >= 0, ch["chop"].to_numpy()[np.maximum(ci, 0)], np.nan)
    it["choppy"] = np.where(ci >= 0, ch["choppy"].to_numpy()[np.maximum(ci, 0)], False)
    st = F.structure(cfg)
    st_known = st["known_ns"].to_numpy()
    si = np.searchsorted(st_known, placed, side="right") - 1
    state = np.where(si >= 0, st["state"].to_numpy()[np.maximum(si, 0)], 0)
    it["structure"] = state
    it["structure_aligned"] = state * d
    vw = F.vwap(cfg)
    vwap_now = np.where(ip - 1 >= 0, vw[np.maximum(ip - 1, 0)], np.nan)
    it["vwap"] = vwap_now
    it["vwap_side"] = np.where(e > vwap_now, "above", np.where(e < vwap_now, "below", "at"))
    vah = daily["vah_prior"].reindex(tdate).to_numpy()
    val = daily["val_prior"].reindex(tdate).to_numpy()
    it["va_loc"] = np.where(np.isnan(vah), "", np.where(e > vah, "above_vah", np.where(e < val, "below_val", "inside")))
    it["news_day"] = news_block_mask(tdate.values, et_min, cfg)

    base = [("risk within limits", risk_ok), ("placed inside trading hours", fresh), ("tradeable day (not short/gap/spike)", day_ok),
            ("allowed session", sess_ok), ("outside no-entry windows", win_ok), ("before flatten time", before_flat), ("ATR available", atr_ok)]
    mask = np.ones(len(it), bool)
    for name, m in base:
        mask &= m
        funnel[name] = int(mask.sum())

    mood = get(cfg, "rules.mood")
    if flt["mood"]:
        mask &= np.isin(it["vol_state"].to_numpy(), list(mood["allowed_vol"]))
        if mood["block_choppy"]:
            mask &= ~it["choppy"].to_numpy(bool)
        funnel["filter: mood"] = int(mask.sum())
    if flt["structure"]:
        mask &= state == d
        funnel["filter: structure"] = int(mask.sum())
    if flt["vwap"]:
        trend = get(cfg, "rules.vwap.mode") == "trend"
        want_above = (d > 0) == trend
        mask &= np.where(want_above, e > vwap_now, e < vwap_now)
        funnel["filter: vwap"] = int(mask.sum())
    if flt["value_area"] and get(cfg, "rules.value_area.mode") == "location":
        mid = (vah + val) / 2
        mask &= np.where(d > 0, e <= mid, e >= mid)
        funnel["filter: value area location"] = int(mask.sum())
    if flt["news"]:
        mask &= ~it["news_day"].to_numpy(bool)
        funnel["filter: news"] = int(mask.sum())
    if start is not None:
        mask &= tdate >= pd.Timestamp(start)
    if end is not None:
        mask &= tdate <= pd.Timestamp(end)
    funnel["in period"] = int(mask.sum())

    # ---- 6. expiry ---------------------------------------------------------
    wait_end = placed + int(s["entry"]["max_wait_minutes"]) * NS_PER_MIN
    next_win = np.full(len(it), np.iinfo(np.int64).max)
    for ws, _ in s["no_entry_windows"] or []:
        delta = (hhmm_to_minutes(ws) - et_min) % 1440
        next_win = np.minimum(next_win, placed + delta.astype(np.int64) * NS_PER_MIN)
    expire = np.minimum.reduce([wait_end, it["fvg_expire_ns"].to_numpy(np.int64), np.nan_to_num(flat_ns, nan=0).astype(np.int64), next_win])
    it["cancel_reason_at_expiry"] = "timeout"
    if flt["structure"]:
        nxt = _next_state_change(st["state"].to_numpy())
        first_after = np.searchsorted(st_known, placed, side="right")
        flip_ns = np.full(len(it), np.iinfo(np.int64).max)
        for side in (1, -1):
            m = d == side
            k = nxt[side][first_after[m]]
            flip_ns[m] = np.where(k < len(st_known), st_known[np.minimum(k, len(st_known) - 1)], np.iinfo(np.int64).max)
        it["cancel_reason_at_expiry"] = np.where(flip_ns < expire, "structure_flip", "timeout")
        expire = np.minimum(expire, flip_ns)
    it["expire_ns"] = expire
    it["flatten_ns"] = flat_ns

    out = it[mask].sort_values(["placed_ns", "trig_known_ns"], kind="stable").reset_index(drop=True)
    return out, funnel
