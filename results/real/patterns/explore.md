# Pattern search — stage `explore`

Pre-registered in [PATTERNS.md](../../../PATTERNS.md). 1R = 10% of the entry day's daily ATR. Costs as in the harness. p is one-sided (effect > 0), from 10,000 resamples of whole trading days.

## Rules

| # | hypothesis | instrument / split | trades | /yr | win % | avg R net | avg R gross | 95% CI | PF | p | p adj. | deflated Sharpe | random-entry p | passes |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| H1 | Open drive (09:35-10:00) | MNQ explore | 1,929 | 238 | 48.2 | -0.102 | +0.133 | [-0.196, -0.012] | 0.89 | 0.9855 | 1.0000 | 0.000 | — | no |
| H2 | London -> NY overlap continuation (09:30-11:30) | MNQ explore | 1,954 | 241 | 45.9 | -0.301 | -0.065 | [-0.474, -0.123] | 0.81 | 0.9996 | 1.0000 | 0.000 | — | no |
| H3 | Lunch reversal (12:00-13:30) | MNQ explore | 1,960 | 242 | 43.7 | -0.211 | +0.025 | [-0.306, -0.119] | 0.78 | 1.0000 | 1.0000 | 0.000 | — | no |
| H4 | Close continuation (15:00-16:00) | MNQ explore | 1,964 | 242 | 44.1 | -0.216 | +0.020 | [-0.305, -0.127] | 0.82 | 1.0000 | 1.0000 | 0.000 | — | no |
| H5 | Asia high/low sweep reversal | MNQ explore | 1,105 | 136 | 23.8 | -0.240 | -0.008 | [-0.301, -0.177] | 0.57 | 1.0000 | 1.0000 | 0.000 | — | no |
| H6 | London high/low sweep reversal | MNQ explore | 1,188 | 146 | 23.9 | -0.232 | +0.004 | [-0.330, -0.131] | 0.80 | 1.0000 | 1.0000 | 0.000 | — | no |
| H7 | Prior-day high/low sweep reversal | MNQ explore | 462 | 57 | 22.1 | -0.314 | -0.068 | [-0.421, -0.203] | 0.54 | 1.0000 | 1.0000 | 0.000 | — | no |

## Filters (pooled trades of H1–H7)

| # | hypothesis | instrument / split | trades | kept | avg R kept | removed | avg R removed | Δ | 95% CI | p | p adj. | passes |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| H8 | Skip CPI / FOMC / NFP days (filter on H1-H7) | MNQ explore | 10,562 | 9,229 | -0.212 | 1,333 | -0.264 | +0.052 | [-0.070, +0.180] | 0.2044 | 1.0000 | no |
| H9 | Trade with the daily trend (filter on H1-H7) | MNQ explore | 10,377 | 5,209 | -0.205 | 5,168 | -0.230 | +0.025 | [-0.089, +0.138] | 0.3318 | 1.0000 | no |

Multiple-testing adjustment: Holm across 9.

**Nothing passed this stage.**

## Observation after the run (description, not a test)

- **H1 (open drive) is positive before costs:** +0.133R per trade gross, 95% CI [+0.038, +0.224], positive in 7 of 9 years.
- **Costs are what sink it here.** They average 0.236R per trade in these years: the daily ATR was 35–60 points, so 1R was only 3.5–6 points against about 1.1 points of costs per round trip.
- **The same observation holds for every rule:** costs are about 0.23–0.25R per trade across H1–H7, and no other rule is positive before costs with a CI above zero.
- **This does not pass the pre-declared rule,** which is judged after costs. Pursuing it would be a new hypothesis formed from explore results. The best evidence for it is the final test; validate is not clean for it, because the earlier `orb5` run (a close relative) already showed its 2018–2022 results.
