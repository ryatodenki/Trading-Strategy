# Pattern search and gamma study — every test run

Generated from `test_log.jsonl`, which gets one line per test, appended and never edited. Hypotheses and rules: [PATTERNS.md](../../../PATTERNS.md) (H1–H9) and [GAMMA.md](../../../GAMMA.md) (G1–G5; each has a main test and a gamma contrast). "passes" is the hypothesis's verdict at that stage.

| time (UTC) | commit | study | stage | instrument | split | # | test | hypothesis | trades | effect (avg R or Δ) | 95% CI | p | p adj. | passes |
|---|---|---|---|---|---|---|---|---|---:|---:|---|---:|---:|---|
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | patterns | explore | MNQ | explore | H1 | rule | Open drive (09:35-10:00) | 1,929 | -0.102 | [-0.196, -0.012] | 0.9855 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | patterns | explore | MNQ | explore | H2 | rule | London -> NY overlap continuation (09:30-11:30) | 1,954 | -0.301 | [-0.474, -0.123] | 0.9996 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | patterns | explore | MNQ | explore | H3 | rule | Lunch reversal (12:00-13:30) | 1,960 | -0.211 | [-0.306, -0.119] | 1.0000 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | patterns | explore | MNQ | explore | H4 | rule | Close continuation (15:00-16:00) | 1,964 | -0.216 | [-0.305, -0.127] | 1.0000 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | patterns | explore | MNQ | explore | H5 | rule | Asia high/low sweep reversal | 1,105 | -0.240 | [-0.301, -0.177] | 1.0000 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | patterns | explore | MNQ | explore | H6 | rule | London high/low sweep reversal | 1,188 | -0.232 | [-0.330, -0.131] | 1.0000 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | patterns | explore | MNQ | explore | H7 | rule | Prior-day high/low sweep reversal | 462 | -0.314 | [-0.421, -0.203] | 1.0000 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | patterns | explore | MNQ | explore | H8 | filter | Skip CPI / FOMC / NFP days (filter on H1-H7) | 10,562 | +0.052 | [-0.070, +0.180] | 0.2044 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | patterns | explore | MNQ | explore | H9 | filter | Trade with the daily trend (filter on H1-H7) | 10,377 | +0.025 | [-0.089, +0.138] | 0.3318 | 1.0000 | no |
| 2026-09-25T13:46:48+00:00 | b41fa8a | gamma | explore | MNQ | explore | G1 | main | Prior-day VAH/VAL sweep fade, positive gamma | 369 | -0.226 | [-0.351, -0.092] | 0.9991 | 1.0000 | no |
| 2026-09-25T13:46:48+00:00 | b41fa8a | gamma | explore | MNQ | explore | G1 | contrast | Prior-day VAH/VAL sweep fade, positive gamma | 387 | +0.025 | [-0.608, +0.531] | 0.4429 | 1.0000 | no |
| 2026-09-25T13:46:48+00:00 | b41fa8a | gamma | explore | MNQ | explore | G2 | main | Asia/London/prior-day sweep reversal, positive gamma | 2,214 | -0.219 | [-0.278, -0.157] | 1.0000 | 1.0000 | no |
| 2026-09-25T13:46:48+00:00 | b41fa8a | gamma | explore | MNQ | explore | G2 | contrast | Asia/London/prior-day sweep reversal, positive gamma | 2,353 | -0.220 | [-0.439, -0.015] | 0.9827 | 1.0000 | no |
| 2026-09-25T13:46:48+00:00 | b41fa8a | gamma | explore | MNQ | explore | G3 | main | Open drive (09:35-10:00), negative gamma | 99 | -0.119 | [-0.646, +0.368] | 0.6698 | 1.0000 | no |
| 2026-09-25T13:46:48+00:00 | b41fa8a | gamma | explore | MNQ | explore | G3 | contrast | Open drive (09:35-10:00), negative gamma | 1,728 | +0.004 | [-0.532, +0.494] | 0.4842 | 1.0000 | no |
| 2026-09-25T13:46:48+00:00 | b41fa8a | gamma | explore | MNQ | explore | G4 | main | VWAP trend following, negative gamma | 1,843 | -0.104 | [-0.165, -0.033] | 0.9971 | 1.0000 | no |
| 2026-09-25T13:46:48+00:00 | b41fa8a | gamma | explore | MNQ | explore | G4 | contrast | VWAP trend following, negative gamma | 30,218 | +0.110 | [+0.046, +0.183] | 0.0006 | 0.0060 | no |
| 2026-09-25T13:46:48+00:00 | b41fa8a | gamma | explore | MNQ | explore | G5 | main | Key-level breakout FVG (15m over 5m), R:R > 1; fixed target (+gamma) / trailing stop (-gamma) | 190 | -0.223 | [-0.367, -0.052] | 0.9940 | 1.0000 | no |
| 2026-09-25T13:46:48+00:00 | b41fa8a | gamma | explore | MNQ | explore | G5 | contrast | Key-level breakout FVG (15m over 5m), R:R > 1; fixed target (+gamma) / trailing stop (-gamma) | 705 | -0.022 | [-0.183, +0.157] | 0.6057 | 1.0000 | no |
| 2026-09-25T15:31:12+00:00 | 1bdbfa8 | gamma | mnq | MNQ | mnq | G1 | main | Prior-day VAH/VAL sweep fade, positive gamma | 131 | -0.141 | [-0.338, +0.082] | 0.8970 | 1.0000 | no |
| 2026-09-25T15:31:12+00:00 | 1bdbfa8 | gamma | mnq | MNQ | mnq | G1 | contrast | Prior-day VAH/VAL sweep fade, positive gamma | 164 | -0.033 | [-0.418, +0.332] | 0.5560 | 1.0000 | no |
| 2026-09-25T15:31:12+00:00 | 1bdbfa8 | gamma | mnq | MNQ | mnq | G2 | main | Asia/London/prior-day sweep reversal, positive gamma | 919 | -0.056 | [-0.144, +0.033] | 0.8926 | 1.0000 | no |
| 2026-09-25T15:31:12+00:00 | 1bdbfa8 | gamma | mnq | MNQ | mnq | G2 | contrast | Asia/London/prior-day sweep reversal, positive gamma | 1,127 | -0.211 | [-0.492, +0.042] | 0.9447 | 1.0000 | no |
| 2026-09-25T15:31:12+00:00 | 1bdbfa8 | gamma | mnq | MNQ | mnq | G3 | main | Open drive (09:35-10:00), negative gamma | 154 | -0.096 | [-0.401, +0.212] | 0.7279 | 1.0000 | no |
| 2026-09-25T15:31:12+00:00 | 1bdbfa8 | gamma | mnq | MNQ | mnq | G3 | contrast | Open drive (09:35-10:00), negative gamma | 864 | -0.176 | [-0.530, +0.166] | 0.8414 | 1.0000 | no |
| 2026-09-25T15:31:12+00:00 | 1bdbfa8 | gamma | mnq | MNQ | mnq | G4 | main | VWAP trend following, negative gamma | 2,572 | -0.001 | [-0.050, +0.057] | 0.5162 | 1.0000 | no |
| 2026-09-25T15:31:12+00:00 | 1bdbfa8 | gamma | mnq | MNQ | mnq | G4 | contrast | VWAP trend following, negative gamma | 14,012 | -0.007 | [-0.064, +0.057] | 0.5815 | 1.0000 | no |
| 2026-09-25T15:31:12+00:00 | 1bdbfa8 | gamma | mnq | MNQ | mnq | G5 | main | Key-level breakout FVG (15m over 5m), stop beyond the latest swing, R:R > 1; fixed target (+gamma) / trailing stop (-gamma) | 44 | -0.331 | [-0.812, +0.180] | 0.8960 | 1.0000 | no |
| 2026-09-25T15:31:12+00:00 | 1bdbfa8 | gamma | mnq | MNQ | mnq | G5 | contrast | Key-level breakout FVG (15m over 5m), stop beyond the latest swing, R:R > 1; fixed target (+gamma) / trailing stop (-gamma) | 108 | -0.182 | [-0.737, +0.413] | 0.7254 | 1.0000 | no |

## Earlier tests on these dates (other rules, same data)

- Step 3 (results/real/step3_variants.md): the ICT setup and 18 variants plus 2 engine checks, 2010-06 → 2022-12. None had an edge.
- STRATEGIES.md (results/real/strategies_dev.md): 15 published strategies, 2010-06 → 2022-12. None qualified.
- Earlier breakdowns of those runs (by session, level type, year) were looked at; they are part of why validate is not fresh data.
