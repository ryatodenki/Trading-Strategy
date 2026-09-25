# Candidate strategies — declared before any backtest

This file was committed before any of these strategies was run on real data.
Every rule and parameter below is fixed here. Nothing is tuned afterwards.

- **Where a paper publishes exact rules, they are used as published.** Deviations forced by the data or the contract are listed under each strategy.
- **Where no canonical rule exists, the plainest rule is used**, with every parameter stated, and it is marked as such.
- **Each strategy is run once**, on the development period only: **2010-06-07 → 2022-12-31**.
- **The 2023+ holdout is not touched.**

## Conventions shared by every strategy

- **Data and sizing.**
  - Continuous back-adjusted MNQ 1-minute bars, with NQ before 2019-07-01 (same prices, see DEFINITIONS §9–10).
  - 1 contract; P&L at MNQ's $2 per point.
- **Times** are New York time.
  - The cash session (RTH) runs 09:30–16:00.
  - "The open" is the open of the 09:30 bar.
  - "The close" is the open of the 16:00 bar, which is the 15:59 close to within a tick.
  - On early-close days the close is the open of the day's last bar.
- **Orders and costs** are the harness's (`backtest` in `config/default.yaml`).
  - Entries and timed exits are market orders at the open of the first 1m bar at or after the stated time, with 1 tick of slippage.
  - Stops fill at the stop, or at the open if a bar gaps through it, minus 1 tick.
  - Targets fill exactly at the target and only when price trades 1 tick through it.
  - A stop and a target in the same bar count as the stop.
  - Commission and fees: $0.60 per side.
- **Contract rolls.** A position held across a roll, or across the NQ→MNQ switch, pays a close and a reopen: $1.20 commission plus 2 ticks.
- **Entry days.** Only trading days the data validation marks tradeable: no half days, no data holes, no bad ticks. Multi-day positions simply hold through later days.
- **ATR** is the harness daily ATR: the mean true range of the prior 14 full days.
- **Minimum risk.** For strategies with a stop, a day is skipped when the stop distance is below max(2 pts, 0.02 × ATR). This is the harness's standing rule; below it, costs dominate.
- **R, the unit of results.**
  - With a stop: 1R = the entry-to-stop distance.
  - Without a stop, none is added, because the published rules have none. 1R = one daily ATR at entry, a volatility unit and not a loss limit. p-values, t-statistics and profit factors do not depend on this choice.
- **Positions.** One position at a time per strategy. Strategies are independent of each other.

## The candidates

| # | ID | Family | Source | Trades |
|---|---|---|---|---|
| 1 | `orb5` | Opening range | Zarattini, Barbon & Aziz (2023) | ≤ 1 a day |
| 2 | `orb15` | Opening range | same rules, 15-min range | ≤ 1 a day |
| 3 | `orb30` | Opening range | same rules, 30-min range | ≤ 1 a day |
| 4 | `im_first_half_hour` | Intraday momentum | Gao, Han, Li & Zhou (2018) | 1 a day |
| 5 | `im_rest_of_day` | Intraday momentum | Baltussen, Da, Lammers & Martens (2021) | 1 a day |
| 6 | `overnight` | Overnight drift | Cliff, Cooper & Gulen (2008); Kelly & Clark (2011); Boyarchenko, Larsen & Whelan (2023) | 1 a day |
| 7 | `gap_fade` | Gap | plainest rule (no canonical paper) | ≤ 1 a day |
| 8 | `gap_go` | Gap | plainest rule (no canonical paper) | ≤ 1 a day |
| 9 | `vwap_trend` | VWAP | Zarattini & Aziz (2023) | many a day |
| 10 | `vwap_reversion` | VWAP | plainest rule: 2σ / 3σ VWAP bands (practitioner default) | a few a day |
| 11 | `vwap_regime` | VWAP × volatility | #9 on volatile days, #10 on calm days | a few a day |
| 12 | `tsmom` | Trend following | Moskowitz, Ooi & Pedersen (2012) | 1 a month |
| 13 | `sma10m` | Trend following | Faber (2007) | ≤ 1 a month |
| 14 | `turn_of_month` | Calendar | Ariel (1987); Lakonishok & Smidt (1988); McConnell & Xu (2008) | 1 a month |
| 15 | `pre_holiday` | Calendar | Ariel (1990); Lakonishok & Smidt (1988) | ~9 a year |

### 1–3. Opening range, 5 / 15 / 30 minutes (`orb5`, `orb15`, `orb30`)

Zarattini, C., Barbon, A. & Aziz, A. (2023), *Can Day Trading Really Be Profitable? Evidence of Sustainable Long-term Profits from Opening Range Breakout (ORB) Day Trading Strategy vs. Benchmark in the US Stock Market*, SSRN working paper.

- **Opening range:** 09:30 to 09:30 + N minutes, with N = 5, 15 or 30.
  - Its open is the 09:30 open.
  - Its close is the close of its last 1m bar.
  - Its high and low come from all its bars.
- **Direction:** long if the range closed above its open, short if below; no trade if equal.
- **Entry:** market at 09:30 + N.
- **Stop:** the range low for a long, the range high for a short.
- **Target:** 10R.
- **Exit:** at the close if neither the stop nor the target is hit.
- **Deviations:**
  - The paper trades QQQ with risk-based sizing and a 4× leverage cap. Here it's 1 contract, and the minimum-risk rule skips tiny ranges.
  - The paper's parameters are for the 5-minute range. The 15- and 30-minute versions keep every rule and only lengthen the range.

### 4. Intraday momentum, first half-hour (`im_first_half_hour`)

Gao, L., Han, Y., Li, S. Z. & Zhou, G. (2018), *Market intraday momentum*, Journal of Financial Economics.

- **Signal:** r1 = the 09:59 close ÷ the previous trading day's 15:59 close − 1.
- **Entry:** market at 15:30. Long if r1 > 0, short if r1 < 0.
- **Exit:** at the close. No stop, no target.
- **Skipped** when the previous trading day has no 15:59 bar (early close).

### 5. Intraday momentum, rest of day (`im_rest_of_day`)

Baltussen, G., Da, Z., Lammers, S. & Martens, M. (2021), *Hedging demand and market intraday momentum*, Journal of Financial Economics.

- **Signal:** r = the 15:29 close ÷ the previous trading day's 15:59 close − 1.
- Everything else as in #4.
- The paper links this effect to options dealers' gamma hedging, so it is the closest published proxy for the gamma reading.

### 6. Overnight hold (`overnight`)

- **Sources:**
  - Cliff, M., Cooper, M. J. & Gulen, H. (2008), *Return differences between trading and non-trading hours: Like night and day*, SSRN working paper.
  - Kelly, M. A. & Clark, S. P. (2011), *Returns in trading versus non-trading hours: The difference is day and night*, Journal of Asset Management.
  - Boyarchenko, N., Larsen, L. C. & Whelan, P. (2023), *The overnight drift*, Review of Financial Studies.
- **Rules:**
  - **Entry:** long at the close of every tradeable day.
  - **Exit:** at the open of the next trading day. No stop, no target.

### 7. Gap fade (`gap_fade`)

No canonical published rule for index futures, so this is the plainest one, with no free parameter.

- **Gap** = the open − the previous trading day's 15:59 close. Skipped if there is no such bar.
- **Gap up:** short at the open.
  - Target: the previous close (gap filled).
  - Stop: the open + the gap, so the stop is as far as the target.
- **Gap down:** the mirror image.
- **Exit:** at the close if neither the stop nor the target is hit.
- R = the gap. Skipped when the gap is below the minimum risk.

### 8. Gap continuation (`gap_go`)

No canonical published rule; plainest rule.

- **Entry:** long at the open after a gap up, short after a gap down. The gap is as in #7.
- **Stop:** the previous close (gap fully filled).
- **Exit:** at the close. No target.
- R = the gap. Skipped when the gap is below the minimum risk.

### 9. VWAP trend following (`vwap_trend`)

Zarattini, C. & Aziz, A. (2023), *Volume Weighted Average Price (VWAP): The Holy Grail for Day Trading Systems*, SSRN working paper.

- **VWAP:** anchored at 09:30, from the typical price × volume of 1m bars (the harness `session` anchor).
- **Signal:** after each 1m close from 09:30 to 15:58, the wanted position is long if the close is above VWAP and short if below (unchanged if equal).
- **Trading:** a change of position happens at the next bar's open. A reversal is an exit plus a new entry at the same open. The first position is taken at 09:31.
- **Exit:** flat at the close. No stop, no target.

### 10. VWAP mean reversion (`vwap_reversion`)

No canonical paper. The plainest band rule uses practitioner-default bands (2σ entry, like Bollinger's, and 3σ stop).

- **σ:** the volume-weighted standard deviation of the typical price around VWAP since 09:30.
- **Signal:** a 1m close moves from inside the bands to above VWAP + 2σ (or below VWAP − 2σ).
- **Entry:** short (long) at the next bar's open. No new entries at or after 15:30.
- **Target:** VWAP at the signal bar. **Stop:** VWAP ± 3σ at the signal bar. Both are fixed at entry.
- **Exit:** at the close if neither the stop nor the target is hit.
- **Repeat signals:** one position at a time. After an exit, a new signal needs a new move from inside the bands to outside.
- R = the stop distance. Skipped when it is below the minimum risk.

### 11. VWAP by volatility regime (`vwap_regime`)

- **Regime:** the harness's, fixed for the day from prior days (5-day ÷ 20-day mean true range; DEFINITIONS §0).
- **Rules:** volatile days (> 1.25) trade #9's rules, calm days (< 0.80) trade #10's rules, normal days are not traded.
- **Hypothesis, stated in advance:** trends persist when volatility is high and deviations revert when it is low.
- The per-regime results of #9 and #10 are also reported, as description only; they are not extra tests.

### 12. Time-series momentum (`tsmom`)

Moskowitz, T. J., Ooi, Y. H. & Pedersen, L. H. (2012), *Time series momentum*, Journal of Financial Economics.

- **Decision:** at the close of the last trading day of each month. Long if the return since the close of the last trading day 12 months earlier is positive, short if negative.
- **Holding:** until the close of the next month's last trading day, then the decision is made again.
- **Costs:** each month is one trade, closed and reopened, which costs about $2.20 a month extra. The rolls it crosses are charged too.
- **Deviations:** the paper scales every position to 40% annual volatility; here it's 1 contract. No stop.
- The first trade needs 12 months of history, so it comes in mid-2011.

### 13. Ten-month moving average (`sma10m`)

Faber, M. T. (2007), *A Quantitative Approach to Tactical Asset Allocation*, Journal of Wealth Management.

- **Decision:** at the close of each month's last trading day. Long if that close is above the mean of the last 10 month-end closes, this one included; otherwise flat.
- **Holding:** one month, as in #12. Long or flat only; no stop.

### 14. Turn of the month (`turn_of_month`)

- **Sources:**
  - Ariel, R. A. (1987), *A monthly effect in stock returns*, Journal of Financial Economics.
  - Lakonishok, J. & Smidt, S. (1988), *Are seasonal anomalies real? A ninety-year perspective*, Review of Financial Studies.
  - McConnell, J. J. & Xu, W. (2008), *Equity returns at the turn of the month*, Financial Analysts Journal.
- **Rules:**
  - **Entry:** long at the close of the second-to-last trading day of the month.
  - **Exit:** at the close of the third trading day of the next month. This holds the published window, day −1 through day +3.
  - No stop.

### 15. Pre-holiday (`pre_holiday`)

- **Sources:**
  - Ariel, R. A. (1990), *High stock returns before holidays: Existence and evidence on possible causes*, Journal of Finance.
  - Lakonishok & Smidt (1988), as above.
- **Rules:**
  - **Entry:** long at the close of the trading day before the pre-holiday day.
  - **Exit:** at the close of the pre-holiday day, which is the last trading day before a scheduled full closure: New Year's Day, MLK Day, Presidents Day, Good Friday, Memorial Day, Juneteenth (from 2022), Independence Day, Labor Day, Thanksgiving or Christmas.
  - Unscheduled closures (Hurricane Sandy, national days of mourning) are excluded because they were not known in advance.
  - No stop.

## What is reported, for each strategy

- **Performance:** trades, trades per year, win %, average net and gross R per trade, 95% bootstrap CI of average net R, profit factor, net $, and max drawdown in $ and in R.
  - The CI is computed two ways: resampling trades, and resampling whole trading days.
- **Per year:** average net R per trade and number of trades.
- **p (edge):** one-sided test that average net R is > 0, from 10,000 bootstrap resamples of whole trading days.
- **p (random), matched random entries:**
  - Every trade is moved to a random tradeable day in the same period.
  - It keeps its direction, entry time of day, holding length (same number of trading days and exit time of day), stop distance in ATRs, target in R and R unit.
  - 1,000 runs. p = the share of runs whose average net R is at least the strategy's, with +1 smoothing.
  - This is the test that matters for long-only strategies, which gain from the 2010–2022 bull market whenever they happen to be invested.
- **Multiple testing across all 15 strategies:**
  - Holm–Bonferroni adjustment (5% family-wise error), applied separately to p (edge) and to p (random).
  - Benjamini–Hochberg q-values are shown alongside.
  - Per-year and per-regime numbers are description only; they are not tests.

## Finalists: the rule, fixed now

A strategy qualifies only if **all** of these hold:

1. Holm-adjusted p (edge) < 0.05.
2. Holm-adjusted p (random) < 0.05.
3. At least 100 trades in the development period.
4. Average net R is still positive after removing its single best year.

At most two finalists are recommended, ranked by the lower bound of the day-block 95% CI of average net R. If none qualifies, none is recommended. A finalist would then get one look at the 2023+ holdout, logged as the harness requires.
