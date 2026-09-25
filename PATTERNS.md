# Pattern search in MNQ / MES — declared before any data was looked at

This file fixes the data split, the hypotheses, the statistics and the pass rules. It was committed before any of these hypotheses was run on any split. Nothing here is changed after results are seen. Every run is logged, failures included (`results/real/patterns/test_log.jsonl`).

## Data split, by trading date

| Split | Dates | Share of the 4,199 trading dates | Use |
|---|---|---:|---|
| **Explore** | 2010-06-07 → 2018-08-09 | 50% | test the hypotheses below |
| **Validate** | 2018-08-10 → 2022-12-30 | 27% | only hypotheses that pass explore |
| **Final test** | 2023-01-03 → 2026-09-24 | 23% | **locked** until you say so |

- **Why the final test starts at 2023-01-01, not at a strict 75% mark.** A strict 75% mark falls on 2022-09-02, but September–December 2022 was already used by earlier runs in this project. 2023 onward has never been loaded by any test. It is also the harness's standing holdout.
- **Loading.**
  - An explore run loads no bar after 2018-08-09.
  - A validate run loads no bar after 2022-12-30. It loads earlier bars only so that ATR and moving averages have history; its trades are the ones entered on or after 2018-08-10.
  - The final test needs an explicit `--unlock-final` flag. It will not be run without your say-so.
- **What was already used.** These dates are not untouched: explore and validate both lie inside 2010–2022, which earlier runs in this project used for different rules.
  - Step 3: the ICT setup and 21 variants of it.
  - The 15 published strategies in STRATEGIES.md.
  - None of those passed.
  - Two hypotheses below are relatives of earlier failures: #1 (open drive), a cousin of `orb5`, and #4 (close continuation), a cousin of `im_rest_of_day`.
  - The sweep hypotheses (#5–7) share the "liquidity sweep" idea with the ICT setup, but they are traded without SMT or FVG.
  - This makes validate weaker evidence than truly fresh data would be. **Only the final test is fresh.**

## Conventions (all hypotheses)

- **Data.** Continuous back-adjusted MNQ 1-minute bars, NQ before 2019-07-01. For the MES check: MES, with ES before 2019-07-01.
- **Costs.** The harness's costs, as in STRATEGIES.md:
  - $0.60 per side;
  - 1 tick of slippage on market entries, market exits and stops;
  - a stop and a target in the same bar count as the stop.
  - In points these costs are about 1.6× what an NQ trader paid in 2010–2019, so early years are penalised a little.
- **R, the unit of results.** 1R = **10% of the entry day's daily ATR** (the 14-day ATR from prior days). The ATR is MNQ's for MNQ trades and MES's for MES trades.
  - That is about 28–37 MNQ points at 2024–2025 volatility.
  - One unit for every hypothesis keeps results comparable and lets the filter tests (#8, #9) pool trades.
  - Where a rule has a stop, the stop is a real order; only the unit of results is fixed.
- **Entry days.** Only days the data validation marks tradeable (no half days, data holes or bad ticks), with an ATR available.
- **Timing.** Every decision uses only bars that started before the order time.
  - Orders are market orders at the open of the first 1-minute bar at or after the stated time.
  - Timed exits are market orders the same way.
- **Positions.** One position at a time per hypothesis.

## The hypotheses

Each hypothesis has a market reason stated before testing, and a direction fixed in advance. There are no free parameters beyond those written here.

### Time of day

| # | Name | Market reason | Rule |
|---|---|---|---|
| 1 | **Open drive** | Overnight order imbalances are released at the cash open. The first 5 minutes reveal the imbalance, and it keeps pushing for the rest of the first half hour. | Direction = sign(09:34 close − 09:30 open). Enter 09:35, exit 10:00. No stop. |
| 2 | **London → NY overlap continuation** | European flows set the direction during London. US participants join in the overlap and extend it until London closes (11:30 ET). | Direction = sign(09:29 close − 03:00 open), the London session's move. Enter 09:30, exit 11:30. No stop. |
| 3 | **Lunch reversal** | Liquidity is thin over lunch, and morning traders take profits, so part of the morning move gives back. | Direction = the opposite of sign(11:59 close − 09:30 open). Enter 12:00, exit 13:30. No stop. |
| 4 | **Close continuation** | End-of-day flows (market-on-close imbalances, dealer hedging) push in the direction of the day's move. | Direction = sign(14:59 close − 09:30 open). Enter 15:00, exit 16:00. No stop. |

In all four, no trade is taken if the sign is zero or a needed bar is missing.

### Sweeps of session and prior-day levels (reversal)

- **Market reason:** stop orders rest just beyond widely watched highs and lows. When price runs those stops but cannot hold beyond the level, the buying (selling) was exhausted, and price reverses.
- **Direction, fixed in advance:** reversal.

| # | Level | Known from | Sweep window (ET) |
|---|---|---|---|
| 5 | Asia high / low (18:00–03:00 session) | 03:00 | 03:00–12:00 |
| 6 | London high / low (03:00–09:30 session) | 09:30 | 09:30–15:00 |
| 7 | Prior-day high / low (previous full 18:00–17:00 day) | 18:00 | 03:00–15:00 |

The same rule applies to each level, on 5-minute bars (high side; the low side mirrors it):

- **The first trade-through.** Find the first 5-minute bar, after the level is known, whose high is at least 1 tick above the level.
  - If that bar starts outside the sweep window, the level was already taken, and there is no trade on it that day.
  - For #7, this means a prior-day high already taken in the Asia session gives no trade.
- **Sweep.** The trade-through bar must *close back below* the level; otherwise it is a breakout, and there is no trade.
- **Entry:** short at the next 5-minute bar's open (5 minutes after the sweep bar started).
- **Stop:** 1 tick above the sweep bar's high.
- **Exit:** 60 minutes after entry, or 16:00, whichever comes first.
- **Frequency:** at most one trade per level side per day.

### Filters, tested on the pooled trades of #1–7

| # | Name | Market reason | Test |
|---|---|---|---|
| 8 | **Skip scheduled news days** | CPI, FOMC and NFP releases cause jumps and whipsaws that stop out technical trades at random. | Δ = average R of trades on non-news days − average R of trades on news days > 0. A news day is a CPI (BLS schedule), FOMC or NFP day in `config/news_days.csv`. |
| 9 | **Trade with the daily trend** | Intraday moves in the direction of the daily trend have institutional flow behind them. | Δ = average R of trend-aligned trades − average R of counter-trend trades > 0. The daily trend is up if the previous trading day's 15:59 close is above the average of the last 50 such closes, down if below. |

## Statistics

- **For #1–7:**
  - trades, trades per year, win %, average net and gross R;
  - 95% CI of average net R from 10,000 bootstrap resamples of whole trading days;
  - profit factor;
  - one-sided p (H0: average net R ≤ 0), from the same bootstrap;
  - deflated Sharpe ratio (Bailey & López de Prado 2014), from the per-trade Sharpe ratio, with N = 7 trials and the spread of Sharpe ratios across them.
- **For #8–9:** Δ, its 95% CI, and one-sided p from resampling whole trading days (the pooled trades of one day move together).
- **Multiple testing:** Holm–Bonferroni across all **9** hypotheses in explore.
- **Random-entry benchmark:** for any hypothesis that passes explore, the matched random-entry p from `strategies/benchmark.py` (same direction, time of day, holding and stop distance, on random days) is reported as a warning sign for plain market drift. It is not a pass rule.

## Pass rules, fixed now

1. **Explore:** Holm-adjusted p < 0.05 across the 9 hypotheses. That means average net R > 0 for #1–7, and Δ > 0 for #8–9.
2. **Validate:** only explore passes are run. Each must have the same sign and one-sided p < 0.05, Holm-adjusted across the number of hypotheses taken to validate.
3. **MES check:** hypotheses that pass both are run on MES, using MES's own prices and levels.
   - It holds on MES if average net R (or Δ) is > 0 in both explore and validate, and one-sided p < 0.05 on the two combined.
   - This check is reported, not a gate.
4. **Final test:** only for hypotheses that pass 1 and 2, and only when you say so. Each is run once, and the run is logged.

If nothing passes explore, validate is not used, and it stays available for a future, better-founded hypothesis.
