# Rule definitions — please review before any real backtest

Every rule below is code in `mnqbt/rules/` with its parameters in
`config/default.yaml`. The descriptions are short on purpose. If one doesn't
match how you mark charts by hand, say which, and I'll change the code, not
just the wording.

## Conventions that apply to everything

- **Time.** All clock times are New York (ET). DST is handled automatically, so "09:30" is always the cash open.
- **Trading day.** Runs from 18:00 ET (previous evening) to 17:00 ET. Sunday evening belongs to Monday.
- **Sessions** (editable): Asia 18:00–03:00, London 03:00–09:30, NY 09:30–16:00.
- **When information counts.** A bar's values count only once the bar has **closed**. A 5-minute candle stamped 09:30 is usable from 09:35.
  - Swing points count only after they are **confirmed**.
  - A session's high and low count only once the session is **over**.
  - This is enforced by tests. They rebuild everything with the future deleted and require identical signals. Six deliberately injected lookahead bugs were each caught.
- **Distances.** Written as "X points or Y × ATR, whichever is larger".
  - ATR is the average daily range of the previous 14 full trading days.
  - This keeps a rule's meaning the same when NQ was at 2,000 (2010) and at 25,000 (2025).

## 0. Market mood

- **Volatility regime.** Fixed for the whole day, using only prior days. Ratio = average daily range of the last 5 days ÷ that of the last 20.
  - Below 0.80 = **calm**; above 1.25 = **volatile**; otherwise **normal**.
- **Chop.** Uses the efficiency ratio of the last 24 five-minute closes (2 hours): net move ÷ total distance travelled.
  - 1.0 is a straight line; near 0 is back-and-forth.
  - Below 0.20 = **choppy**. A random walk averages about 0.20, so this marks the choppier half of the time.
- **Mood filter (when switched on).** Trade only on normal or volatile days, and not while choppy.
  - ADX (< 20 = choppy) is available instead of the efficiency ratio.

## 1. Structure / order flow

- **Swing points.** A swing high is a candle whose high is higher than the 2 candles before it and not exceeded by the 2 after it. Swing lows mirror this.
  - Of two equal highs, only the first counts.
  - A swing is known only when the 2nd candle after it closes.
- **Structure.** Measured on the **1-hour chart**.
  - **Bullish** once a candle **closes** above the most recent confirmed swing high.
  - **Bearish** once one closes below the most recent swing low.
  - It stays that way until the opposite break.
- **Structure filter (when on).** Longs only while bullish, shorts only while bearish. A working order is cancelled if structure flips against it before it fills.

## 2. Key levels

At any moment, these are the levels that exist, all built from data before that moment:

| Level | Definition |
|---|---|
| Prior-day high / low | High / low of the previous **full** trading day (18:00–17:00). Holiday half-days are skipped. |
| Current-day high / low | Running high / low of today so far. The candle being tested is not included. |
| Asia / London / NY high & low | The most recent **completed** instance of each session. Today's Asia high becomes a level at 03:00; until then it's yesterday's. |
| Recent swing highs / lows | The 3 most recent confirmed 15-minute swing highs and lows. |
| Prior VAH / VAL | Only when the value-area piece is switched on (see §8). |

"**At a key level**" means an MNQ swing extreme is within **max(3 pts, 0.03 × ATR)** of one of these levels, about 10 points at 2025 prices. Swing highs are tested against high-type levels and swing lows against low-type levels.

An optional **sweep** mode is available: the swing must trade *through* the level by at least 1 tick and at most the tolerance.

## 3. Fair value gap (entry zone)

- **Definition.** Three consecutive candles on the 5-minute chart (15-minute as a variant), in the same trading day with no missing candle between.
  - **Bullish FVG:** candle 3's low is above candle 1's high. The zone runs from candle 1's high up to candle 3's low.
  - **Bearish FVG:** candle 3's high is below candle 1's low.
- **Minimum size.** max(1 pt, 0.01 × ATR), about 3.5 points at 2025 prices.
- **Known** when candle 3 closes. **Valid** for 12 candles after that (1 hour on 5m).

## 4. SMT divergence

For a **bearish** SMT:

- MNQ has a confirmed 5-minute swing high. Its previous swing high is 3 to 24 candles earlier (15 minutes to 2 hours).
- The two indices disagree:
  - MNQ's new high is above its previous one while MES's is not, **or**
  - MES makes the higher high while MNQ does not.
- MES's high is read within ±1 candle of each MNQ swing, so a one-candle timing difference doesn't count as divergence.
- Bullish SMT mirrors this with swing lows.
- The SMT is known when the MNQ swing is confirmed, 2 candles after it.

## 5. Setup assembly (the baseline)

1. **Trigger.** MNQ makes a confirmed 5m swing. That swing is **at a key level** and shows **SMT** with MES. A swing high means a short setup; a swing low means a long.
2. **Entry zone.** The first FVG in the trade direction that:
   - starts at or after the swing candle;
   - is confirmed within **60 minutes** of the SMT;
   - is still fresh when the order is placed, with price not having returned to the entry yet.
3. **Order.** Placed when both the SMT and the FVG are known.
   - Limit at the **50% level** of the FVG (a setting: 0 = near edge, 1 = far edge).
   - Rounded one tick deeper when it falls between ticks.
4. **Stop.** One buffer beyond the **swept swing extreme**, buffer = max(1 pt, 0.01 × ATR).
   - Setups are skipped when the risk is under max(2 pts, 0.02 × ATR) (costs would dominate) or over 0.4 × ATR.
   - Variant: stop beyond the far edge of the FVG.
5. **Target.** **2R** fixed.
   - Variant: the nearest opposing key level at least 1R away. If none exists, 2R is used, so both variants take identical entries.
6. **Cancel the order if:**
   - it isn't filled within **60 minutes**;
   - the FVG expires;
   - price reaches the target before filling;
   - a no-entry window starts;
   - (with the structure filter) structure flips against it.
7. **Position rules.**
   - One position or working order at a time. Setups that appear while busy are skipped and counted.
   - 1 contract.
   - Anything still open at **15:55 ET** is closed at market.

## 6. No-trade filters

- **No new orders** 15:30–18:00 ET (editable list of windows).
- **No trading on:**
  - holiday / half-day sessions;
  - days where either instrument has a data hole of 60+ minutes;
  - days with a suspect bad tick.
- **News days** (off by default):
  - FOMC and NFP dates are in `config/news_days.csv`. FOMC dates are from the Fed's calendars; NFP dates come from BLS scheduling rules.
  - Add CPI or anything else to the CSV.
  - Modes: skip the whole day, or ±30 minutes around the release.

## 7. VWAP

- **Anchoring.** Session-anchored: resets at the 18:00 trading-day open. A variant resets at each of Asia / London / NY.
- **Calculation.** Typical price × volume.
- **VWAP filter (when on, "trend" mode).** Longs only when the entry price is **above** VWAP, shorts only below.
  - "Discount" mode flips this. Every report also splits baseline trades by VWAP side, so you see both answers without extra tests.

## 8. Value area (VAH / VAL)

- **Source.** The prior full trading day's volume profile.
  - Without tick data, each 1-minute bar's volume is spread evenly across its high–low range. That's usually within a few ticks of a true tick profile.
- **Calculation.** Start at the highest-volume price (POC) and keep adding the busier neighbouring price until 70% of volume is covered.
- **Default use ("levels" mode).** When switched on, prior VAH and VAL **join the key-level list**, so setups at VAH/VAL count.
  - Alternative "location" mode: longs only below the value-area midpoint, shorts only above (buy discount / sell premium).

## 9. Fills and costs (engine)

- **Limit entries.**
  - Fill only if price trades **at least one tick through** the limit.
  - A "touch" setting exists so you can see the difference; it's in every report.
- **The candle the order fills in.**
  - A stop in that candle counts. Price had to pass the entry on its way to the stop, so the order is certain.
  - A target counts only if the candle closes beyond it.
- **Later candles.** If one candle hits both stop and target, the **stop is assumed first**. The optimistic opposite is reported as a bracket.
- **Stop exits.** Pay **1 tick** slippage, or fill at the open if price gaps through. Market exits (15:55 flatten) also pay 1 tick.
- **Costs.** **$0.60 per side** commission + fees. MNQ = $2 per point, $0.50 per tick.
- **Pre-2019 data.** MNQ didn't exist before May 2019, so NQ/ES prices are used (identical tick for tick). P&L is still MNQ's $2/pt with MNQ costs.
  - When prices were low (2010–2015), stops in points were small, so fixed costs are a bigger share of R. That's real, and it shows in the per-year table.

## 10. Data handling

- **Continuous contract.**
  - Roll 8 calendar days before the 3rd-Friday expiry (CME's roll Thursday). MNQ and MES roll on the same day.
  - Older data is **back-adjusted by the roll gap**, so every point distance is exact across rolls.
  - Trades never straddle a roll: rolls happen at 18:00 and all positions are flat by 15:55.
- **Proxies.** NQ/ES are used before 2019-07-01 and MNQ/MES after. The validation report shows the raw price difference at the splice, which should be about 0.
- **Validation report.** Covers missing weekdays (explained by holiday), short sessions, intraday holes, spike bars, duplicates, OHLC errors, MNQ–MES coverage and correlation, and every roll with its gap.

---

## Judgment calls I made — please confirm or change

1. **Key-level tolerance looks loose.** On synthetic data, about half of all 5m swings pass the key-level test, because with ~12 levels one is often nearby. Options:
   - require a **sweep** (`rules.levels.mode: sweep`);
   - shrink the tolerance;
   - drop the running day high/low and the 3 swing levels from the list.

   Which matches your marking?
2. **Which sessions to trade.** Default is all three, so the by-session table can show where it works. If you only trade London + NY, that should be the baseline from the start, not a finding after the fact.
3. **Structure timeframe.** Default is 1-hour swings (2 bars each side). Do you read order flow on 1h, 4h, or 15m?
4. **VWAP direction.** Is "long above VWAP" (trend) or "long below VWAP" (discount) the rule you use?
5. **VAH/VAL role.** Should they be extra key levels (current default) or a premium/discount location filter?
6. **Stop placement.** Default is beyond the swing that made the SMT. Do you use that, or beyond the FVG?
7. **SMT timeframe.** 5m swings with 2 bars each side, previous swing 15 min–2 h back. Do you look for SMT on 1m, 5m or 15m?
8. **One trade at a time.** Setups that appear while an order is working or a trade is open are skipped, not queued.
9. **Flatten at 15:55** every day. A trade opened in Asia can run into the NY session.
10. **Inducement** is not implemented, as requested.
