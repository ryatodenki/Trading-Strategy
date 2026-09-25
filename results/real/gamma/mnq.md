# Gamma study — stage `mnq`

Pre-registered in [GAMMA.md](../../../GAMMA.md). 1R = 10% of the entry day's daily ATR. Costs as in the harness. p is one-sided (effect > 0), from 10,000 resamples of whole trading days. Every test is also in the shared log: [../patterns/README.md](../patterns/README.md).

## Days by gamma regime (entry-eligible days; description only)

| instrument / split | positive | negative | no regime | first day with a regime |
|---|---:|---:|---:|---|
| MNQ mnq | 711 | 155 | 0 | 2019-07-01 |

## Main tests: does the rule make money on its matched days?

| # | hypothesis | instrument / split | days | trades | /yr | win % | avg R net | avg R gross | 95% CI (net) | PF | p | p adj. | deflated Sharpe | random-entry p | passes |
|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| G1 | Prior-day VAH/VAL sweep fade, positive gamma | MNQ mnq | positive | 131 | 38 | 16.8 | -0.141 | -0.082 | [-0.338, +0.082] | 0.85 | 0.8970 | 1.0000 | — | — | no |
| G2 | Asia/London/prior-day sweep reversal, positive gamma | MNQ mnq | positive | 919 | 263 | 23.7 | -0.056 | -0.001 | [-0.144, +0.033] | 0.86 | 0.8926 | 1.0000 | — | — | no |
| G3 | Open drive (09:35-10:00), negative gamma | MNQ mnq | negative | 154 | 45 | 48.7 | -0.096 | -0.063 | [-0.401, +0.212] | 0.93 | 0.7279 | 1.0000 | — | — | no |
| G4 | VWAP trend following, negative gamma | MNQ mnq | negative | 2,572 | 757 | 17.9 | -0.001 | +0.031 | [-0.050, +0.057] | 1.00 | 0.5162 | 1.0000 | — | — | no |
| G5 | Key-level breakout FVG (15m over 5m), stop beyond the latest swing, R:R > 1; fixed target (+gamma) / trailing stop (-gamma) | MNQ mnq | every day with a regime | 44 ⚠ | 13 | 29.5 | -0.331 | -0.292 | [-0.812, +0.180] | 0.63 | 0.8960 | 1.0000 | — | — | no |

⚠ fewer than 100 trades.

## Contrasts: does gamma help?

| # | contrast | instrument / split | matched trades | avg R matched | opposite trades | avg R opposite | Δ | 95% CI | p | p adj. |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|
| G1 | positive days − negative days | MNQ mnq | 131 | -0.141 | 33 | -0.107 | -0.033 | [-0.418, +0.332] | 0.5560 | 1.0000 |
| G2 | positive days − negative days | MNQ mnq | 919 | -0.056 | 208 | +0.155 | -0.211 | [-0.492, +0.042] | 0.9447 | 1.0000 |
| G3 | negative days − positive days | MNQ mnq | 154 | -0.096 | 710 | +0.080 | -0.176 | [-0.530, +0.166] | 0.8414 | 1.0000 |
| G4 | negative days − positive days | MNQ mnq | 2,572 | -0.001 | 11,440 | +0.006 | -0.007 | [-0.064, +0.057] | 0.5815 | 1.0000 |
| G5 | gamma-matched exits − swapped exits | MNQ mnq | 44 | -0.331 | 64 | -0.150 | -0.182 | [-0.737, +0.413] | 0.7254 | 1.0000 |

## G5 by regime, FVG timeframe and FVG at the level (description only)

| group | trades | avg R net (gamma-matched exits) | avg R net (swapped exits) |
|---|---:|---:|---:|
| positive gamma | 28 | -0.442 | +0.025 |
| negative gamma | 16 | -0.137 | -1.570 |
| 15min FVG | 20 | -0.094 | -0.287 |
| 5min FVG | 24 | -0.529 | -0.028 |
| FVG at the level | 28 | -0.150 | -0.271 |
| FVG not at the level | 16 | -0.648 | +0.027 |
| round-1 stop (beyond the FVG), same dates | 193 | -0.099 | — |

Multiple-testing adjustment: Holm across 10 tests. A hypothesis passes if its main test's adjusted p < 0.05 with avg R > 0, and its contrast Δ > 0.

**Nothing passed this stage.**

## Observations after the run (description only, not tests)

- **Wider stops leave few trades.** The round-2 stop has a median of 13% of ATR, and the nearest key level must be farther away than that. Only 44 setups in 3.5 years passed (13 a year), and they lost −0.29R per trade even before costs. On the same dates, the round-1 stop (beyond the FVG) gave 193 trades at −0.10R net.
- **Trade 6 of the explore charts (2015-08-24, long at 7,887.75) would not be taken under round 2.** The swing stop is 7,824.75 (63 points), and the nearest key level above the entry is 54 points away, so reward:risk is 0.86 and the rule passes on it. That day, only 1 of 8 setups had reward:risk above 1 with swing stops.
- **G4 (VWAP trend) broke even on MNQ's negative-gamma days:** −0.001R net, +0.031R before costs. Its contrast is about zero (Δ = −0.007), so here gamma made no difference.
- The deflated Sharpe ratio is computed only in the explore stage; nothing passed, so it is not needed here.
