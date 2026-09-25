# Options gamma as a regime switch — declared before any gamma data was downloaded

This file fixes the gamma data, the regime rule, the hypotheses, the statistics and the pass rules. It was committed before the gamma series was downloaded, so before any hypothesis here could be run. Nothing here is changed after results are seen. Every run is logged, failures included, in the same append-only log as the pattern search (`results/real/patterns/test_log.jsonl`, with `study: gamma`).

## The idea, stated in advance

- **Positive dealer gamma.** Option dealers hedge against the move: they sell into rallies and buy into dips. The market tends to **mean-revert**, so moves should be **faded**.
- **Negative dealer gamma.** Dealers hedge with the move: they sell into falling prices and buy into rising ones. The market tends to **trend**, so traders should **go with** moves.
- **The question:** do these setups make money when they are matched to the right regime, and do they do better on matched days than on opposite days?

## Gamma data

- **Series:** SqueezeMetrics' free daily GEX (`gex` column of `https://squeezemetrics.com/monitor/static/DIX.csv`).
  - GEX is the dollar gamma exposure of S&P 500 index (SPX) options.
  - SqueezeMetrics assumes dealers are long the calls and short the puts that investors trade (white paper *Gamma Exposure*, 2016, revised 2017).
  - It is the S&P 500, not the Nasdaq-100. It stands in for market-wide dealer positioning.
- **History:** from 2011-05-02. The file is kept in `datastore/gex/` (git-ignored). It is never committed, because of the site's terms.
- **Publication:** after the cash close. On 2026-09-24 the file was last modified at 17:52 ET; earlier years' publication times are not known.
- **Point in time:** the file is one current snapshot. If SqueezeMetrics has ever revised past values, that can't be seen or undone here.

### Regime rule

- **Which value a day uses.** Futures trading day T runs from 18:00 ET the day before to 17:00 ET on T. It uses the GEX dated on the latest cash date **strictly before T**.
  - Example: Tuesday's futures day, which starts Monday 18:00 ET, uses Monday's GEX, published Monday evening.
  - No hypothesis trades before 03:00 ET on T, which leaves about 9 hours after a publication time like today's.
- **Stale values.** If that GEX date is more than 7 calendar days before T, the day has no regime. It is not traded and not counted.
- **Positive-gamma day:** GEX > 0. **Negative-gamma day:** GEX < 0. GEX = 0 counts as neither.
- **No news layer** in this study.

## Data split (same as PATTERNS.md)

| Split | Dates | Gamma available | Use |
|---|---|---|---|
| **Explore** | 2010-06-07 → 2018-08-09 | from 2011-05-03 | test all hypotheses below |
| **Validate** | 2018-08-10 → 2022-12-30 | yes | only hypotheses that pass explore |
| **Final test** | 2023-01-03 → 2026-09-24 | yes | **locked** until you say so (`--unlock-final`) |

- **Loading.** An explore run loads no bar after 2018-08-09 and no GEX value dated after it. The same holds for validate at 2022-12-30.
- **Explore trades** start on 2011-05-03, the first day with a regime. Earlier bars are loaded only for ATR and level history.
- **What was already used.** G1–G4 apply a gamma switch to rules whose unconditional explore results are already known, and all of those were negative:
  - G2 is H5–H7 of PATTERNS.md, and G3 is H1.
  - G4 is STRATEGIES.md #9, run on 2010–2022.
  - G1 (value-area sweeps) and G5 (your breakout setup) are new rules, but G5 uses the same pieces as the Step 3 ICT setup: swings, FVGs and key levels.
  - Only the gamma split is new information. Validate has been used by earlier runs (see PATTERNS.md), so **only the final test is fresh.**

## Conventions (all hypotheses; as PATTERNS.md)

- **Data.** Continuous back-adjusted MNQ 1-minute bars, NQ before 2019-07-01. For the MES check: MES, with ES before 2019-07-01.
- **Costs.** The harness's costs:
  - $0.60 per side;
  - 1 tick of slippage on market entries, market exits and stops;
  - limit orders fill only when price trades 1 tick through;
  - a stop and a target in the same bar count as the stop.
- **R, the unit of results.** 1R = **10% of the entry day's daily ATR**, the 14-day ATR from prior days. Where a rule has a stop, the stop is a real order; only the unit of results is fixed.
- **Entry days.** Only days the data validation marks tradeable, with an ATR and a gamma regime.
- **Timing.** Every decision uses only bars that started before the order time. Market orders fill at the open of the first 1-minute bar at or after the stated time.
- **Positions.** One position at a time per hypothesis.

## The hypotheses

Each hypothesis has a market reason and a direction fixed in advance. There are no free parameters beyond those written here.

| # | Rule | Traded on | Market reason |
|---|---|---|---|
| **G1** | Prior-day value-area sweep-and-reject **fade** | positive-gamma days | Probes outside the prior day's value area find no acceptance, and dealers selling rallies and buying dips push price back into value. |
| **G2** | Asia / London / prior-day high-low sweep **reversal** (PATTERNS.md H5–H7, pooled) | positive-gamma days | Stop runs beyond obvious highs and lows are absorbed by dealer hedging flow and reverse. |
| **G3** | **Open drive**, go with the first 5 minutes (PATTERNS.md H1) | negative-gamma days | Dealers hedging with the move extend the opening imbalance. |
| **G4** | **VWAP trend following** (STRATEGIES.md #9) | negative-gamma days | Intraday trends persist when hedging flow adds to moves. |
| **G5** | **Your breakout setup:** structure breakout with FVG entry; **exits chosen by gamma** | every day with a regime | Positive gamma caps moves, so take a fixed profit. Negative gamma lets moves run, so trail the stop. |

### G1 — prior-day value-area sweep fade

- **Level:** the prior full trading day's (18:00–17:00) volume profile, with a **70% value area** (the harness's `value_area` with `source: prior_day`). VAH is the high side, VAL the low side.
- **Rule:** exactly the PATTERNS.md sweep rule (H5–H7) with VAH/VAL as the levels. The high side is described; the low side mirrors it.
  - **Level known from** 18:00, the start of the trading day. The **sweep window** is 03:00–15:00.
  - **The first trade-through.** Find the first 5-minute bar after 18:00 whose high is at least 1 tick above VAH. If it starts outside the window, there is no trade on that side that day.
  - **Sweep:** that bar must close back below VAH.
  - **Entry:** short at the next 5-minute open.
  - **Stop:** 1 tick above the sweep bar's high.
  - **Exit:** 60 minutes after entry or at 16:00, whichever comes first.

### G2 — session and prior-day sweep reversal

- **Rules:** the trades of H5 (Asia high/low), H6 (London high/low) and H7 (prior-day high/low) of PATTERNS.md, with every rule unchanged.
- **Pooled into one hypothesis,** one position at a time across the three: an order placed while another G2 position is open is skipped.

### G3 — open drive

- **Rule:** PATTERNS.md H1, unchanged.
- **Direction** = sign(09:34 close − 09:30 open). Enter at 09:35 and exit at 10:00, with no stop.

### G4 — VWAP trend following

- **Rule:** STRATEGIES.md #9, unchanged.
  - VWAP is anchored at 09:30.
  - After each 1-minute close from 09:30 to 15:58, the position is long above VWAP and short below it.
  - Changes happen at the next open, and the position is flat at the close.
  - No stop and no target.
- **R** = 10% of ATR, not the one ATR used in STRATEGIES.md.

### G5 — your breakout setup, exits chosen by gamma

This is your description turned into exact rules: 5-minute chart, daily and swing highs/lows, trade the breakout in the direction of simple higher-high/higher-low structure, FVG for a better entry, key levels for stop and target, a trailing stop on negative gamma and a fixed target on positive gamma. The long side is described; shorts mirror it.

1. **Bars and swings.** 5-minute bars. Swings are the harness's: 2 bars each side, known 2 bars after the swing bar.
2. **Structure.** Use the swings confirmed by the start of the breakout bar. The **uptrend** needs higher highs and higher lows: the latest swing high is above the one before it, and the latest swing low is above the one before it.
3. **Breakout.** A 5-minute bar that starts between 03:00 and 15:00 ET closes above a **breakout level**, while the bar before it (same trading day) closed at or below that level. The breakout levels are:
   - the latest confirmed 5-minute swing high;
   - the prior day's high.
4. **15-minute FVG present.** A bullish 15-minute FVG must exist when the breakout bar closes. It uses the harness rule: 3 up candles, gap ≥ max(1 pt, 3% of ATR), same trading day, known by the close of the breakout bar, and no older than 12 bars (3 hours).
5. **Entry, "FVG for better entry".** Use the most recent bullish 5-minute FVG, with the same harness rule and no older than 12 bars (60 minutes).
   - **Untouched:** no 5-minute bar after its third candle has traded down to the entry price.
   - **Entry:** a limit buy at the FVG's midpoint, placed at the close of the breakout bar.
   - **Order lifetime:** 60 minutes, and never past 15:30. It fills only when price trades 1 tick below the limit.
6. **Stop, a key level.** 1 buffer below the latest confirmed 5-minute swing low, the higher low that made the uptrend.
   - The buffer is max(1 pt, 1% of ATR), the harness's `setup.stop.buffer`.
   - The setup is skipped if the stop distance is outside [max(2 pt, 2% of ATR), 40% of ATR], the harness's minimum and maximum risk.
7. **Exit, by the day's gamma:**
   - **Positive gamma: fixed target and stop.**
     - The target is the nearest key level at least 1× the stop distance above the entry.
     - If there is none, the target is 2× the stop distance.
     - The key levels are the harness set as of the start of the breakout bar: prior-day high, today's high so far, the latest Asia, London and NY session highs, and the 3 latest 15-minute swing highs.
   - **Negative gamma: trailing stop, no target.**
     - Every 5-minute swing low confirmed after the fill moves the stop up to that swing low minus the buffer.
     - The stop never moves down.
   - **Both:** flat at 15:55 if still open.
8. **Positions.** One at a time. A breakout while an order or position is live is skipped.

## Tests, the contrasts and the family

Each hypothesis has **two tests**. That makes **10 tests** in one Holm family.

| Test | G1, G2 | G3, G4 | G5 |
|---|---|---|---|
| **Main (`Gk`)**: average net R > 0 | trades on positive-gamma days | trades on negative-gamma days | all trades, each with its regime's exit |
| **Contrast (`Gk-c`)**: Δ > 0 | Δ = avg R on positive days − avg R on negative days (same rule) | Δ = avg R on negative days − avg R on positive days (same rule) | Δ = avg R with gamma-matched exits − avg R with swapped exits (trailing on positive days, fixed target on negative days), same entry signals |

## Statistics

- **For each main test:**
  - trades, trades per year, win %, average net and gross R;
  - 95% CI of average net R from 10,000 resamples of whole trading days;
  - profit factor;
  - one-sided p (H0: average net R ≤ 0) from the same bootstrap;
  - deflated Sharpe ratio (Bailey & López de Prado 2014), with N = 5 trials (the main tests).
- **For each contrast:** Δ, its 95% CI and one-sided p, resampling whole trading days. Both groups' trades on a day move together.
- **Multiple testing:** Holm–Bonferroni across all **10** tests in explore.
- **Random-entry benchmark:** for a main test that passes, the matched random-entry p is reported as a warning sign, on random days of the same regime. It is not a pass rule. It is not computed for G5, whose limit entries and trailing stops the benchmark does not replay.
- **Description only, not tests:**
  - the number of positive-, negative- and no-regime days in each split;
  - G5 split by regime.
  - Fewer than 100 trades in a main test is flagged, not excluded.

## Pass rules, fixed now

1. **Explore:** a hypothesis passes if its **main test has Holm-adjusted p < 0.05** (across the 10 tests) and its **contrast Δ > 0**. The contrast must point the right way, but it does not have to be significant: the minority regime makes it low-powered.
2. **Validate:** only explore passes are run. Each must again have average net R > 0 with one-sided p < 0.05, Holm-adjusted across the number of hypotheses taken to validate, and Δ > 0.
3. **MES check:** hypotheses that pass both are run on MES, with MES's own prices and levels and the same GEX.
   - It holds on MES if average net R is > 0 in both explore and validate and the combined one-sided p is < 0.05.
   - This check is reported, not a gate.
4. **Final test:** only for hypotheses that pass 1 and 2, and only when you say so. Each is run once, and the run is logged.

If nothing passes explore, validate is not used.

---

### Implementation notes, made before any run (no rule above is changed)

1. **G5 limit orders on positive-gamma days** follow the harness's standard fill rule: a working limit order is cancelled if price reaches the target before the order fills. The move happened without the trade.
2. **Trailing stop timing (G5, negative gamma).** A swing is confirmed at the close of its 5-minute bar. The new stop applies from the next 1-minute bar. A bar that opens through the stop fills at its open, minus 1 tick.
3. **Pooled G2, two levels swept by the same bar.** The orders are identical except for the level name. The first in the order Asia, London, prior day is taken, and the others are skipped as "position already open".
4. **Fixed family size.** A test that cannot be computed (no trades) stays in the Holm family as p = 1, so the family is always the 10 tests declared above.
