# Pattern search — every test run

Generated from `test_log.jsonl`, which gets one line per test, appended and never edited. Hypotheses and rules: [PATTERNS.md](../../../PATTERNS.md).

| time (UTC) | commit | stage | instrument | split | # | hypothesis | trades | effect (avg R or Δ) | 95% CI | p | p adj. | passes |
|---|---|---|---|---|---|---|---:|---:|---|---:|---:|---|
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | explore | MNQ | explore | H1 | Open drive (09:35-10:00) | 1,929 | -0.102 | [-0.196, -0.012] | 0.9855 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | explore | MNQ | explore | H2 | London -> NY overlap continuation (09:30-11:30) | 1,954 | -0.301 | [-0.474, -0.123] | 0.9996 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | explore | MNQ | explore | H3 | Lunch reversal (12:00-13:30) | 1,960 | -0.211 | [-0.306, -0.119] | 1.0000 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | explore | MNQ | explore | H4 | Close continuation (15:00-16:00) | 1,964 | -0.216 | [-0.305, -0.127] | 1.0000 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | explore | MNQ | explore | H5 | Asia high/low sweep reversal | 1,105 | -0.240 | [-0.301, -0.177] | 1.0000 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | explore | MNQ | explore | H6 | London high/low sweep reversal | 1,188 | -0.232 | [-0.330, -0.131] | 1.0000 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | explore | MNQ | explore | H7 | Prior-day high/low sweep reversal | 462 | -0.314 | [-0.421, -0.203] | 1.0000 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | explore | MNQ | explore | H8 | Skip CPI / FOMC / NFP days (filter on H1-H7) | 10,562 | +0.052 | [-0.070, +0.180] | 0.2044 | 1.0000 | no |
| 2026-09-25T11:12:48+00:00 | 27c2bc2 | explore | MNQ | explore | H9 | Trade with the daily trend (filter on H1-H7) | 10,377 | +0.025 | [-0.089, +0.138] | 0.3318 | 1.0000 | no |

## Earlier tests on these dates (other rules, same data)

- Step 3 (results/real/step3_variants.md): the ICT setup and 18 variants plus 2 engine checks, 2010-06 → 2022-12. None had an edge.
- STRATEGIES.md (results/real/strategies_dev.md): 15 published strategies, 2010-06 → 2022-12. None qualified.
- Earlier breakdowns of those runs (by session, level type, year) were looked at; they are part of why validate is not fresh data.
