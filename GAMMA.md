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

*Revised twice after your review, before any run. Earlier versions are in commits `9a1697c` and `27f7f93`.*

Your rules:
- Price breaks a key level in the direction of simple higher-high / higher-low structure, and the breaking move leaves an FVG. An FVG right at the level is better, but not required.
- Enter in that FVG. A 15-minute FVG is stronger and is used if there is one; otherwise a 5-minute one.
- Stop a little beyond the FVG.
- Take the trade only if reward:risk is more than 1:1.
- Exit by the day's gamma.
- Trade the London and NY sessions.

The long side is described; shorts mirror it.

1. **Key levels** (long side):
   - the latest confirmed 5-minute swing high;
   - the prior day's high and today's high so far;
   - the prior day's VAH and VAL (the harness's 70% value area of the prior full day);
   - VWAP (the harness's, anchored at the 18:00 start of the trading day).
2. **Structure.** Uptrend: the latest two 5-minute swing highs are rising and the latest two swing lows are rising. These are the harness's swings, 2 bars each side, confirmed before the FVG's first candle starts.
3. **Breakout FVG.** A bullish FVG on the 5-minute or the 15-minute chart whose three candles carried price through a key level: candle 1 opened at or below the level, and candle 3 closed above it.
   - It uses the harness rule: 3 up candles, gap ≥ max(1 pt, 3% of ATR), all in one trading day.
   - Levels are taken as known when candle 1 starts. VWAP is taken at the close of the bar before candle 1.
   - **At the level** means the gap itself contains the level: candle 1's high ≤ level ≤ candle 3's low. It is better but not required, and it is reported separately.
   - **Sessions:** London and NY. Candle 3 starts at or after 03:00 ET and closes before 15:30 ET.
4. **Entry.** When candle 3 closes, place a limit buy at the FVG's midpoint.
   - There is no time limit. The order waits until it fills, and fills only when price trades 1 tick through.
   - It is cancelled only in these cases:
     - price reaches the target first (positive-gamma days; the harness rule);
     - a 15-minute setup replaces it (rule 5);
     - it reaches 15:30, the harness's last time for new entries.
5. **15 minutes beats 5 minutes.**
   - If a bullish 15-minute setup is confirmed while a 5-minute order is still waiting, the 5-minute order is cancelled and the 15-minute one placed. The 15-minute setup must pass every rule here, including rule 7.
   - If both are confirmed at the same moment, the 15-minute one is used.
6. **Stop:** a buffer below the FVG's low edge (candle 1's high).
   - The buffer is **1% of ATR**, your "2 pips".
   - The setup is skipped if the stop distance is outside [max(2 pt, 2% of ATR), 40% of ATR].
7. **Reward:risk more than 1:1.**
   - The reward is the distance from the entry to the nearest key level beyond it, as of the order.
   - The key levels here are:
     - prior-day high and today's high so far;
     - the latest Asia, London and NY session highs;
     - the 3 latest 15-minute swing highs;
     - the prior day's VAH and VAL;
     - VWAP.
   - If that reward is 1× the stop distance or less, **pass**: no trade.
   - If no key level lies beyond the entry, the reward counts as 2× the stop distance.
   - This applies on both gamma regimes, so the contrast compares the same entries.
8. **Exit, by the day's gamma:**
   - **Positive gamma: fixed target and stop.** The target is that nearest key level, or 2× the stop distance if there is none.
   - **Negative gamma: trailing stop, no target.**
     - Every 5-minute swing low confirmed after the fill moves the stop up to that swing low minus the buffer.
     - The stop never moves down.
   - **Both:** flat at 15:55 if still open. Everything here is day trading.
9. **Positions.** One at a time. A setup while an order or position is live is skipped, except for the replacement in rule 5.

**Description only, not tests:** G5's results split by FVG timeframe (5 vs 15 minutes) and by FVG at the level vs not.

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
  - G5 split by regime, by FVG timeframe and by FVG at the level vs not.
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

1. **G5 limit orders on positive-gamma days** follow the harness's standard fill rule: a working limit order is cancelled if price reaches the target before the order fills. The move happened without the trade. (G5 itself was revised after your review; see its section.)
2. **Trailing stop timing (G5, negative gamma).** A swing is confirmed at the close of its 5-minute bar. The new stop applies from the next 1-minute bar. A bar that opens through the stop fills at its open, minus 1 tick.
3. **Pooled G2, two levels swept by the same bar.** The orders are identical except for the level name. The first in the order Asia, London, prior day is taken, and the others are skipped as "position already open".
4. **Fixed family size.** A test that cannot be computed (no trades) stays in the Holm family as p = 1, so the family is always the 10 tests declared above.

*Erratum, found while preparing round 2:* the 40%-of-ATR maximum stop in G5 rule 6 was never applied. The harness's `setup.stop.max_risk` is `{points: 1e9, atr_frac: 0.40}`, and the harness takes the larger of the two, so the limit is 1e9 points. No round-1 G5 trade had a stop over 40% of ATR (0 of 190), so the explore results are unchanged. *Fixed afterwards:* `max_risk` is now `{points: 0, atr_frac: 0.40}`, so the cap applies to round-1 G5 (`stop_at="fvg"`). Round 2 has no cap, so it is not affected.

---

## Round 2 — declared after the explore run, before any run on these dates

After the explore run (nothing passed) and after seeing its example charts, you asked for three changes:
- wider G5 stops, at the swing instead of just beyond the FVG;
- still skip any trade whose reward is not bigger than its risk;
- a rerun of everything on MNQ's own prices.

G5 is revised **because of** what the 2011–2018 charts showed. So round 2 must be judged only on data that neither round has touched.

### Data

- **MNQ only: 2019-07-01 → 2022-12-30.** The harness switches from NQ to MNQ prices at the 2019-07-01 trading day. This is the MNQ part of the validate split.
- No gamma test has used these dates. Earlier studies did (Step 3, STRATEGIES.md), as noted above.
- Bars before 2019-07-01 are loaded only for ATR and level history.
- Nothing after 2022-12-30 is loaded. **The final test (2023-01-03 onward) stays locked.**

### Hypotheses

- **G1–G4:** unchanged.
- **G5:** unchanged except the stop.
  - **Stop:** 1% of ATR beyond the latest 5-minute swing low (for longs; the latest swing high for shorts) confirmed by the time the order is placed.
    - That swing is always at or beyond the FVG's far edge, so the stop is never tighter than in round 1.
    - The minimum risk [max(2 pt, 2% of ATR)] still applies.
    - The 40%-of-ATR maximum is dropped. The reward:risk rule limits the stop instead.
  - **Reward:risk:** as before, the nearest key level beyond the entry must be more than 1× the (wider) stop distance away, or there is no trade. With no key level beyond the entry, the target is 2× the stop distance.
  - **Trailing stop (negative gamma):** starts at this stop, then moves as before.

### Tests and pass rule

- Same as explore: 10 tests (main + contrast for G1–G5), Holm across 10.
- A hypothesis passes if its main test has Holm-adjusted p < 0.05 with average R > 0, and its contrast Δ > 0.
- **Description only:** G5 with the round-1 stop (beyond the FVG) on the same dates, to show what the wider stop changed.

### What a pass would lead to

A pass here is new evidence, because these dates are unseen by both rounds. But it has used up validate.
- The next step would be the MES check on the same dates.
- After that comes the final test (2023+), run once and only when you say so.
