# Gamma study — stage `explore`

Pre-registered in [GAMMA.md](../../../GAMMA.md). 1R = 10% of the entry day's daily ATR. Costs as in the harness. p is one-sided (effect > 0), from 10,000 resamples of whole trading days. Every test is also in the shared log: [../patterns/README.md](../patterns/README.md).

## Days by gamma regime (entry-eligible days; description only)

| instrument / split | positive | negative | no regime | first day with a regime |
|---|---:|---:|---:|---|
| MNQ explore | 1,666 | 102 | 205 | 2011-05-03 |

## Main tests: does the rule make money on its matched days?

| # | hypothesis | instrument / split | days | trades | /yr | win % | avg R net | avg R gross | 95% CI (net) | PF | p | p adj. | deflated Sharpe | random-entry p | passes |
|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| G1 | Prior-day VAH/VAL sweep fade, positive gamma | MNQ explore | positive | 369 | 52 | 23.6 | -0.226 | +0.005 | [-0.351, -0.092] | 0.63 | 0.9991 | 1.0000 | 0.000 | — | no |
| G2 | Asia/London/prior-day sweep reversal, positive gamma | MNQ explore | positive | 2,214 | 305 | 24.1 | -0.219 | +0.011 | [-0.278, -0.157] | 0.70 | 1.0000 | 1.0000 | 0.000 | — | no |
| G3 | Open drive (09:35-10:00), negative gamma | MNQ explore | negative | 99 ⚠ | 15 | 51.5 | -0.119 | +0.029 | [-0.646, +0.368] | 1.03 | 0.6698 | 1.0000 | 0.094 | — | no |
| G4 | VWAP trend following, negative gamma | MNQ explore | negative | 1,843 | 270 | 14.4 | -0.104 | +0.042 | [-0.165, -0.033] | 0.76 | 0.9971 | 1.0000 | 0.000 | — | no |
| G5 | Key-level breakout FVG (15m over 5m), R:R > 1; fixed target (+gamma) / trailing stop (-gamma) | MNQ explore | every day with a regime | 190 | 27 | 15.3 | -0.223 | -0.102 | [-0.367, -0.052] | 0.42 | 0.9940 | 1.0000 | 0.002 | — | no |

⚠ fewer than 100 trades.

## Contrasts: does gamma help?

| # | contrast | instrument / split | matched trades | avg R matched | opposite trades | avg R opposite | Δ | 95% CI | p | p adj. |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|
| G1 | positive days − negative days | MNQ explore | 369 | -0.226 | 18 | -0.251 | +0.025 | [-0.608, +0.531] | 0.4429 | 1.0000 |
| G2 | positive days − negative days | MNQ explore | 2,214 | -0.219 | 139 | +0.001 | -0.220 | [-0.439, -0.015] | 0.9827 | 1.0000 |
| G3 | negative days − positive days | MNQ explore | 99 | -0.119 | 1,629 | -0.123 | +0.004 | [-0.532, +0.494] | 0.4842 | 1.0000 |
| G4 | negative days − positive days | MNQ explore | 1,843 | -0.104 | 28,375 | -0.214 | +0.110 | [+0.046, +0.183] | 0.0006 | 0.0060 |
| G5 | gamma-matched exits − swapped exits | MNQ explore | 190 | -0.223 | 515 | -0.202 | -0.022 | [-0.183, +0.157] | 0.6057 | 1.0000 |

## G5 by regime, FVG timeframe and FVG at the level (description only)

| group | trades | avg R net (gamma-matched exits) | avg R net (swapped exits) |
|---|---:|---:|---:|
| positive gamma | 116 | -0.059 | -0.215 |
| negative gamma | 74 | -0.482 | +0.125 |
| 15min FVG | 91 | -0.174 | -0.243 |
| 5min FVG | 99 | -0.269 | -0.169 |
| FVG at the level | 84 | -0.216 | -0.276 |
| FVG not at the level | 106 | -0.229 | -0.123 |

Multiple-testing adjustment: Holm across 10 tests. A hypothesis passes if its main test's adjusted p < 0.05 with avg R > 0, and its contrast Δ > 0.

**Nothing passed this stage.**
## Observations after the run (description only, not tests; nothing here changes a verdict)

- **Negative gamma is rare.** Only 102 of the 1,768 explore days with a regime (6%) had negative GEX, so G3 and the negative-day half of G5 rest on few trades.
- **G4's contrast is mostly costs, not gamma.** Its Δ = +0.110R has Holm-adjusted p = 0.006, but G4 still loses money on negative days, so it fails. Most of the Δ comes from the R unit:
  - Negative-gamma days have about twice the ATR, so the same ~1.1 points of costs are a smaller share of 1R (10% of ATR).
  - Before costs the two regimes differ by only 0.025R.

  | G4, VWAP trend | trades | median ATR | avg R gross | costs in R | avg R net |
  |---|---:|---:|---:|---:|---:|
  | negative gamma | 1,843 | 91 | +0.042 | 0.146 | −0.104 |
  | positive gamma | 28,375 | 49 | +0.017 | 0.231 | −0.214 |

- **G5 loses even before costs:** −0.10R gross, −0.22R net, over 190 trades (27 a year). 164 of the 190 exits were at the stop.
  - On negative days, trailing lost −0.48R net over 74 trades.
  - On positive days, fixed targets lost −0.06R net over 116 trades.
  - The swapped-exit numbers in the table above come from very different trade counts: fixed targets cancel many waiting orders when price reaches the target first. They are not a fair comparison of exit styles.
