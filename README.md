# MNQ ICT/SMC setup — honest backtest harness

This turns a discretionary MNQ (Micro Nasdaq-100) setup into exact, testable
rules and measures which parts, if any, have an edge after costs:
key level + fair value gap, confirmed by SMT vs MES on session levels or by a
trending market, plus mood, structure,
VWAP and value area.

**Research only.** Nothing here connects to a broker or places orders.

| Stage | Status |
|---|---|
| Step 0 — data pipeline (download / import, rolls, sessions, validation) | done: Databento 2010 → 2026-09 → [results/real/data_validation.md](results/real/data_validation.md) |
| Step 1 — rule definitions + example charts | built; **definitions awaiting your review** → [DEFINITIONS.md](DEFINITIONS.md) |
| Step 2 — backtest engine (fills, costs, no lookahead) | built and tested |
| Step 3 — baseline, add-one, remove-one variants | **run on real data (2010–2022): every variant loses about 0.15–0.2R per trade after costs; the baseline does no better than random entries (p = 0.73)** → [results/real/step3_variants.md](results/real/step3_variants.md). *Erratum:* run without the 0.4 × ATR maximum stop (1.5% of trades across all runs had wider stops; 43 of 3,686 in the baseline). The cap is now fixed; these numbers are not rerun yet → [DEFINITIONS.md §5](DEFINITIONS.md#5-setup-assembly-the-baseline) |
| Step 4 — tuning grid, walk-forward, one-shot holdout, random benchmark, CIs | built; not run on real data (nothing to tune yet); **holdout untouched** |
| Published-strategy candidates ([STRATEGIES.md](STRATEGIES.md)) | **15 declared strategies run once on 2010–2022: none qualifies as a finalist**; holdout untouched → [results/real/strategies_dev.md](results/real/strategies_dev.md) |
| Pattern search ([PATTERNS.md](PATTERNS.md)): explore / validate / final split | **9 hypotheses on explore (2010-06 → 2018-08): nothing passed**; validate and final test unused → [results/real/patterns/](results/real/patterns/README.md) |
| Gamma regime study ([GAMMA.md](GAMMA.md)): SqueezeMetrics GEX as a regime switch, same splits | **5 hypotheses (10 tests) on explore: nothing passed** → [explore.md](results/real/gamma/explore.md); **round 2 (wider G5 stops) on MNQ 2019-07 → 2022-12: nothing passed** → [mnq.md](results/real/gamma/mnq.md); final test unused |

Everything under `results/synthetic/` comes from a **random walk**. It proves the
pipeline runs and has no lookahead: a random walk shows no edge, and it
doesn't here. **It says nothing about your setup.**

## Quick start

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,databento]"
pytest -q                                   # ~70 tests, ~1 min
python -m mnqbt synth --start 2018-01-02 --end 2024-06-28 --splice 2020-07-01 --dataset synthetic
python -m mnqbt suite --dataset synthetic   # Step 3 report -> results/synthetic/step3_variants.md
python -m mnqbt walkforward --dataset synthetic
python -m mnqbt charts --dataset synthetic  # example charts -> results/synthetic/examples/
```

## Step 0 — getting real data

### Options

Costs are approximate; check before buying.

| Source | Cost | History | Finer than 1m? | Fit |
|---|---|---|---|---|
| **Databento** (recommended) | Pay per use. **$125 free credit** at sign-up (a card is required at sign-up; it is only billed beyond the credit). | CME Globex from June 2010: NQ/ES all of it, MNQ/MES since May 2019 | Yes: 1-second bars, trades (tick) | Exchange data with real volume; the downloader here quotes the price first and refuses anything over your budget |
| FirstRate Data | One-time purchase (see site); updates $99.95/yr after 1 month | MNQ/MES 1m since May 2019; NQ/ES much longer | 1m only for these | CSV files; importer included |
| NinjaTrader (free account) | Free | Minute history varies by feed; tick typically ~1 year | Tick (recent only) | Manual export per quarterly contract; importer included |
| Yahoo Finance | Free | 1m for the last few weeks only | No | Useless for a backtest |

You chose the best free route, so the plan is **Databento within the free
credit** for NQ/ES (2010 → mid-2019) + MNQ/MES (2019 → today), 1-minute bars.
If you'd rather not put a card on file, export from NinjaTrader instead;
expect much less history.

### One-time setup for Databento in this cloud environment

This container can't reach Databento yet: the network policy blocks
`hist.databento.com`. In the environment settings (cloud environment menu →
Edit):

1. **Network access**: add `hist.databento.com` to allowed domains, or choose a broader access level.
2. **Environment variable**: `DATABENTO_API_KEY=<your key>` (from databento.com → API keys). Don't paste the key into chat.
3. Start a new session on this branch; the new settings apply to new sessions.

Then:

```bash
python -m mnqbt db-quote                     # asks Databento for a price; downloads nothing, costs nothing
python -m mnqbt db-download --max-cost 100   # refuses if the quote is over $100 (stay under your $125 credit)
python -m mnqbt build --source databento --dataset real   # -> results/real/data_validation.md
```

The download uses parent symbology (`MNQ.FUT`, `NQ.FUT`, …), i.e. every
contract, so rolls are built here instead of trusting a vendor's continuous
series. Files go to `datastore/` (git-ignored; market data is licensed and big).

### Importing files instead

```bash
python -m mnqbt import --format ninjatrader --root MNQ "MNQ 03-24.Last.txt" "MNQ 06-24.Last.txt" ...
python -m mnqbt import --format ninjatrader --root MES "MES 03-24.Last.txt" ...
python -m mnqbt import --format firstrate --root MNQ --symbol MNQH4 MNQH24.txt
python -m mnqbt build --source import --dataset real --no-proxies
```

NinjaTrader stamps bars at their **close**, in the time zone set in
NinjaTrader; the importer corrects to bar-open UTC (`--tz` if yours isn't ET).
FirstRate stamps bar **open** in ET.

### Contract rolls — the choice and why

- **When:** 8 calendar days before the 3rd-Friday expiry (CME's roll Thursday), the same day for MNQ and MES. `continuous.roll_rule: volume` rolls the session after the next contract's volume exceeds the front's, using the previous day only; MES then copies MNQ's dates.
- **How:** **additive back-adjustment.** The gap at the last minute both contracts traded is added to all older bars.
  - Every rule here works in points (FVG size, level distance, stop, P&L), and back-adjustment keeps every point distance exact, including prior-day levels across a roll.
  - Unadjusted data would put the prior-day high ~100–250 NQ points off on the day after each roll.
  - The cost: absolute prices far in the past are shifted. No rule uses round numbers or % returns, so nothing depends on that.
- **Trades never straddle a roll:** rolls occur at the 18:00 open and positions are flat by 15:55.
- **Before MNQ/MES existed:** NQ/ES are spliced in (default from 2019-07-01). The report shows the raw price difference at the splice (should be ~0). P&L is always MNQ's $2/point and MNQ costs.

### Sessions and validation

Session times live in `config/default.yaml` (ET; DST via zoneinfo). The
validation report lists:

- missing weekdays, explained by the built-in US holiday calendar;
- short/holiday sessions;
- intraday holes;
- suspect spike bars: a wick over 15× the usual 1m range that reverts within the bar, **and** no move of 5×+ its usual range in the other index within ±1 minute. A data release or crash moves MNQ and MES together; a bad tick shows up in one only. Spikes the other index matched are counted and kept;
- duplicates and OHLC errors;
- MNQ↔MES minute coverage and correlation per year;
- every roll with its gap.

Short sessions, 60-minute holes and spike days are excluded from trading.
These day flags use the whole day. That's harmless for holiday half-days
(they're announced in advance). For data-quality exclusions it would bias
results if data problems happened to coincide with extreme days, so their
count is always reported.

## Steps 1–4 — commands

```bash
python -m mnqbt charts --dataset real --variant baseline --n 9   # Step 1: check signals by eye
python -m mnqbt suite --dataset real                              # Step 3 (development period only)
python -m mnqbt walkforward --dataset real                        # Step 4 (development period only)
python -m mnqbt holdout --dataset real --variant baseline --note "final"   # Step 4: ONE look at recent data
python -m mnqbt strategies --dataset real                         # STRATEGIES.md candidates, development period only
python -m mnqbt gex-download                                     # SqueezeMetrics daily GEX, once, into datastore/gex/ (git-ignored)
python -m mnqbt gamma --stage explore                            # GAMMA.md study; then validate / mes; final needs --unlock-final
```

Variant definitions live in [config/variants.yaml](config/variants.yaml). Every
parameter lives in [config/default.yaml](config/default.yaml).

## Research protocol (how this avoids fooling you)

- **Development period** (default up to 2022-12-31): all variant comparisons, the tuning grid and the walk-forward.
- **Holdout** (2023-01-01 → today): used only by `mnqbt holdout`.
  - Each use is appended to `results/<dataset>/holdout_log.jsonl`.
  - A second use refuses to run without `--i-understand`, so the count of looks is always visible.
- **Tuning grid:** pre-declared and small (12 combinations, listed in config). Every combination is reported, not just the best.
- **Anchored walk-forward:** each year is tested with the combination that looked best on all earlier years.
- **Confidence intervals:** 95% bootstrap on average R, both per-trade and by whole trading days.
- **Warnings:** any variant with < 100 trades is flagged.
- **Matched random benchmark:** each real order is replayed on a random day at the same time of day. It keeps the same order type, limit distance (ATR), wait, stop (ATR), target (R), fill rules and costs. The p-value says how often luck does as well.
- **Breakdowns:** every variant is broken down by session, weekday and year. Baseline and full setups add direction, vol regime, key level type, SMT leader, VWAP side, value-area location, structure alignment, news day and target type.

## How lookahead is tested

`tests/test_no_lookahead.py`:

1. Rebuilds every feature on data truncated at 15 random intraday times. Everything known before the cut must be identical.
2. Cuts the data exactly at the placement time of sampled orders and requires the same order to come out.
3. Runs the strategy on random walks, where gross R must not be significantly positive.

The tests were checked by injecting six realistic bugs; each one made them fail:

- swing known at its own bar;
- FVG known at the 3rd candle's open;
- SMT peeking at later MES bars;
- running day-high including the current bar;
- ATR including today;
- VWAP read at the placement bar's close.

The first version of the test only caught one of the first three. That's why it's now this thorough.

## Layout

```
config/            default.yaml (all parameters), variants.yaml (Step 3), news_days.csv
mnqbt/data/        databento_fetch, importers, continuous (rolls), sessions, calendar, validate, build, synthetic, gex (gamma)
mnqbt/rules/       bars, swings, structure, levels, fvg, smt, mood, vwap, profile, news, features, setups
mnqbt/backtest/    engine (fills/costs), research (variants, grid, walk-forward, holdout), random_bench
mnqbt/reports/     metrics (stats, bootstrap CIs, multiple-testing corrections, breakdowns), charts, report (markdown)
mnqbt/strategies/  published-research candidates (STRATEGIES.md): rules, random-entry benchmark, runner; pattern search (PATTERNS.md) and gamma study (GAMMA.md)
tests/             FVG, swings/structure, sessions/levels, SMT, fills, rolls, profile/VWAP, no-lookahead
results/           committed reports (synthetic demo now; real data later)
```

## Known limitations

- The value area comes from 1m bars (volume spread evenly over each bar), not tick data. With Databento 1-second or trades data this can be upgraded.
- A stop and target inside the same 1m bar are resolved stop-first. The engine accepts a finer-data resolver (`resolver=`) if 1-second bars are downloaded for those minutes. The share of trades affected is shown in every table.
- Queue position isn't modelled; the trade-through rule is the stand-in.
- Inducement is not implemented (by request).
