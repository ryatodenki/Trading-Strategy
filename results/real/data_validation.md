# Data validation — dataset `real`

Continuous contracts: roll rule `calendar`, adjustment `additive`. Tradeable trading dates: **3994 / 4199**.

Splices (proxy → micro):

- MNQ: from trading date 2019-07-01; raw price difference proxy vs micro +0.75 pts (should be ~0); applied offset +3599.25 pts (includes the micro series' own back-adjustment), measured at 2019-06-28 20:59:00+00:00
- MES: from trading date 2019-07-01; raw price difference proxy vs micro +0.00 pts (should be ~0); applied offset +795.75 pts (includes the micro series' own back-adjustment), measured at 2019-06-28 20:59:00+00:00

## MNQ

- Trading dates with data: **4199**  (2010-06-07 → 2026-09-24)
- 1m bars: 5,507,257; median per full day: 1363
- Weekdays with no data: 56 (50 are known holidays; **6 unexplained**)
- Short / holiday sessions (not traded): 196 (of which early close before 16:00 ET: 136)
- Days with an intraday hole ≥ 60 min (not traded): 4
- Days with suspect spikes (not traded): 8 (16 bars); 235 more spike bars were matched by the other index within ±1 min and kept as real moves

Row checks (raw contracts → continuous):

| check | raw | continuous |
|---|---:|---:|
| rows | 3,953,539 | 5507257 |
| duplicate_rows | 0 | 0 |
| bad_ohlc_rows | 0 | 0 |
| nonpositive_or_nan_rows | 8,556 | 0 |
| zero_volume_rows | 0 | 0 |
| off_tick_grid_rows | 49,907 |  |

Rolls (additive back-adjustment gap measured at the last minute both contracts traded):

| roll trading date | old | new | gap (pts) | measured at (UTC) | method |
|---|---|---|---:|---|---|
| 2010-06-10 | NQM0 | NQU0 | -2.00 | 2010-06-09 21:19:00+00:00 | last_common_minute |
| 2010-09-09 | NQU0 | NQZ0 | -3.25 | 2010-09-08 21:27:00+00:00 | last_common_minute |
| 2010-12-09 | NQZ0 | NQH1 | -1.75 | 2010-12-08 22:24:00+00:00 | last_common_minute |
| 2011-03-10 | NQH1 | NQM1 | -2.50 | 2011-03-09 22:29:00+00:00 | last_common_minute |
| 2011-06-09 | NQM1 | NQU1 | -3.75 | 2011-06-08 21:24:00+00:00 | last_common_minute |
| 2011-09-08 | NQU1 | NQZ1 | -5.25 | 2011-09-07 21:00:00+00:00 | last_common_minute |
| 2011-12-08 | NQZ1 | NQH2 | -3.50 | 2011-12-07 22:24:00+00:00 | last_common_minute |
| 2012-03-08 | NQH2 | NQM2 | -6.00 | 2012-03-07 22:27:00+00:00 | last_common_minute |
| 2012-06-07 | NQM2 | NQU2 | -5.25 | 2012-06-06 21:17:00+00:00 | last_common_minute |
| 2012-09-13 | NQU2 | NQZ2 | -6.50 | 2012-09-12 21:29:00+00:00 | last_common_minute |
| 2012-12-13 | NQZ2 | NQH3 | -5.50 | 2012-12-12 22:09:00+00:00 | last_common_minute |
| 2013-03-07 | NQH3 | NQM3 | -3.75 | 2013-03-06 22:14:00+00:00 | last_common_minute |
| 2013-06-13 | NQM3 | NQU3 | -5.50 | 2013-06-12 21:14:00+00:00 | last_common_minute |
| 2013-09-12 | NQU3 | NQZ3 | -6.75 | 2013-09-11 21:14:00+00:00 | last_common_minute |
| 2013-12-12 | NQZ3 | NQH4 | -4.75 | 2013-12-11 22:14:00+00:00 | last_common_minute |
| 2014-03-13 | NQH4 | NQM4 | -7.50 | 2014-03-12 21:12:00+00:00 | last_common_minute |
| 2014-06-16 | NQM4 | NQU4 | -6.50 | 2014-06-11 21:11:00+00:00 | last_common_minute |
| 2014-09-11 | NQU4 | NQZ4 | -7.00 | 2014-09-10 21:14:00+00:00 | last_common_minute |
| 2014-12-11 | NQZ4 | NQH5 | -5.50 | 2014-12-10 22:02:00+00:00 | last_common_minute |
| 2015-03-12 | NQH5 | NQM5 | -6.50 | 2015-03-11 21:06:00+00:00 | last_common_minute |
| 2015-06-11 | NQM5 | NQU5 | -5.50 | 2015-06-10 21:11:00+00:00 | last_common_minute |
| 2015-09-10 | NQU5 | NQZ5 | -8.75 | 2015-09-09 21:14:00+00:00 | last_common_minute |
| 2015-12-10 | NQZ5 | NQH6 | -4.25 | 2015-12-09 21:14:00+00:00 | last_common_minute |
| 2016-03-10 | NQH6 | NQM6 | -9.25 | 2016-03-09 21:41:00+00:00 | last_common_minute |
| 2016-06-09 | NQM6 | NQU6 | -7.25 | 2016-06-08 20:45:00+00:00 | last_common_minute |
| 2016-09-08 | NQU6 | NQZ6 | -4.00 | 2016-09-07 20:59:00+00:00 | last_common_minute |
| 2016-12-08 | NQZ6 | NQH7 | -1.75 | 2016-12-07 21:59:00+00:00 | last_common_minute |
| 2017-03-09 | NQH7 | NQM7 | +3.75 | 2017-03-08 21:59:00+00:00 | last_common_minute |
| 2017-06-08 | NQM7 | NQU7 | +8.75 | 2017-06-07 20:59:00+00:00 | last_common_minute |
| 2017-09-07 | NQU7 | NQZ7 | +7.25 | 2017-09-06 20:59:00+00:00 | last_common_minute |
| 2017-12-07 | NQZ7 | NQH8 | +19.00 | 2017-12-06 21:59:00+00:00 | last_common_minute |
| 2018-03-08 | NQH8 | NQM8 | +22.50 | 2018-03-07 21:59:00+00:00 | last_common_minute |
| 2018-06-07 | NQM8 | NQU8 | +23.75 | 2018-06-06 20:59:00+00:00 | last_common_minute |
| 2018-09-13 | NQU8 | NQZ8 | +28.25 | 2018-09-12 20:59:00+00:00 | last_common_minute |
| 2018-12-13 | NQZ8 | NQH9 | +25.75 | 2018-12-12 21:59:00+00:00 | last_common_minute |
| 2019-03-07 | NQH9 | NQM9 | +29.00 | 2019-03-06 21:59:00+00:00 | last_common_minute |
| 2019-06-13 | NQM9 | NQU9 | +26.00 | 2019-06-12 20:56:00+00:00 | last_common_minute |
| 2019-09-12 | MNQU9 | MNQZ9 | +22.75 | 2019-09-11 20:56:00+00:00 | last_common_minute |
| 2019-12-12 | MNQZ9 | MNQH0 | +22.25 | 2019-12-11 21:44:00+00:00 | last_common_minute |
| 2020-03-12 | MNQH0 | MNQM0 | -5.25 | 2020-03-11 20:59:00+00:00 | last_common_minute |
| 2020-06-11 | MNQM0 | MNQU0 | -9.50 | 2020-06-10 20:57:00+00:00 | last_common_minute |
| 2020-09-10 | MNQU0 | MNQZ0 | -16.50 | 2020-09-09 20:58:00+00:00 | last_common_minute |
| 2020-12-10 | MNQZ0 | MNQH1 | +1.75 | 2020-12-09 21:59:00+00:00 | last_common_minute |
| 2021-03-11 | MNQH1 | MNQM1 | -9.00 | 2021-03-10 21:59:00+00:00 | last_common_minute |
| 2021-06-10 | MNQM1 | MNQU1 | -15.00 | 2021-06-09 20:59:00+00:00 | last_common_minute |
| 2021-09-09 | MNQU1 | MNQZ1 | -9.25 | 2021-09-08 20:59:00+00:00 | last_common_minute |
| 2021-12-09 | MNQZ1 | MNQH2 | -2.50 | 2021-12-08 21:59:00+00:00 | last_common_minute |
| 2022-03-10 | MNQH2 | MNQM2 | -2.00 | 2022-03-09 21:59:00+00:00 | last_common_minute |
| 2022-06-09 | MNQM2 | MNQU2 | +31.50 | 2022-06-08 20:58:00+00:00 | last_common_minute |
| 2022-09-08 | MNQU2 | MNQZ2 | +75.00 | 2022-09-07 20:59:00+00:00 | last_common_minute |
| 2022-12-08 | MNQZ2 | MNQH3 | +117.50 | 2022-12-07 21:59:00+00:00 | last_common_minute |
| 2023-03-09 | MNQH3 | MNQM3 | +137.25 | 2023-03-08 21:59:00+00:00 | last_common_minute |
| 2023-06-08 | MNQM3 | MNQU3 | +172.75 | 2023-06-07 20:59:00+00:00 | last_common_minute |
| 2023-09-07 | MNQU3 | MNQZ3 | +195.50 | 2023-09-06 20:59:00+00:00 | last_common_minute |
| 2023-12-07 | MNQZ3 | MNQH4 | +198.00 | 2023-12-06 21:59:00+00:00 | last_common_minute |
| 2024-03-07 | MNQH4 | MNQM4 | +245.50 | 2024-03-06 21:59:00+00:00 | last_common_minute |
| 2024-06-13 | MNQM4 | MNQU4 | +254.00 | 2024-06-12 20:59:00+00:00 | last_common_minute |
| 2024-09-12 | MNQU4 | MNQZ4 | +240.00 | 2024-09-11 20:59:00+00:00 | last_common_minute |
| 2024-12-12 | MNQZ4 | MNQH5 | +271.75 | 2024-12-11 21:59:00+00:00 | last_common_minute |
| 2025-03-13 | MNQH5 | MNQM5 | +209.00 | 2025-03-12 20:59:00+00:00 | last_common_minute |
| 2025-06-12 | MNQM5 | MNQU5 | +221.25 | 2025-06-11 20:59:00+00:00 | last_common_minute |
| 2025-09-11 | MNQU5 | MNQZ5 | +230.50 | 2025-09-10 20:58:00+00:00 | last_common_minute |
| 2025-12-11 | MNQZ5 | MNQH6 | +261.75 | 2025-12-10 21:59:00+00:00 | last_common_minute |
| 2026-03-12 | MNQH6 | MNQM6 | +211.50 | 2026-03-11 20:59:00+00:00 | last_common_minute |
| 2026-06-11 | MNQM6 | MNQU6 | +259.25 | 2026-06-10 20:59:00+00:00 | last_common_minute |
| 2026-09-10 | MNQU6 | MNQZ6 | +288.75 | 2026-09-09 20:59:00+00:00 | last_common_minute |

Unexplained missing weekdays (first 30):

2014-06-12, 2014-06-13, 2014-09-23, 2014-09-24, 2014-09-25, 2014-12-31

Short sessions (first 40):

| date | bars | last bar ET | holiday |
|---|---:|---|---|
| 2010-06-10 | 836 | 17:29 |  |
| 2010-07-05 | 834 | 11:29 | Independence Day |
| 2010-08-06 | 1003 | 16:14 |  |
| 2010-09-06 | 729 | 11:29 | Labor Day |
| 2010-09-09 | 691 | 17:28 |  |
| 2010-11-25 | 784 | 11:29 | Thanksgiving |
| 2010-11-26 | 984 | 13:14 | Day after Thanksgiving (early close) |
| 2010-12-09 | 853 | 17:28 |  |
| 2010-12-23 | 960 | 16:14 |  |
| 2010-12-28 | 992 | 17:29 |  |
| 2010-12-29 | 988 | 17:29 |  |
| 2010-12-31 | 824 | 16:14 |  |
| 2011-01-17 | 842 | 11:29 | MLK Day |
| 2011-02-21 | 872 | 11:29 | Presidents Day |
| 2011-03-10 | 916 | 17:27 |  |
| 2011-04-25 | 1022 | 17:29 |  |
| 2011-05-20 | 1054 | 16:14 |  |
| 2011-05-30 | 640 | 11:29 | Memorial Day |
| 2011-06-09 | 769 | 17:26 |  |
| 2011-07-04 | 838 | 11:29 | Independence Day |
| 2011-09-05 | 892 | 11:29 | Labor Day |
| 2011-09-08 | 704 | 17:29 |  |
| 2011-11-24 | 964 | 11:29 | Thanksgiving |
| 2011-11-25 | 1084 | 13:14 | Day after Thanksgiving (early close) |
| 2011-12-08 | 900 | 17:29 |  |
| 2011-12-27 | 639 | 17:23 |  |
| 2011-12-30 | 1079 | 16:14 |  |
| 2012-01-03 | 646 | 17:29 |  |
| 2012-01-16 | 903 | 11:29 | MLK Day |
| 2012-02-20 | 913 | 11:29 | Presidents Day |
| 2012-03-08 | 834 | 17:29 |  |
| 2012-04-06 | 483 | 09:14 | Good Friday |
| 2012-05-28 | 930 | 11:29 | Memorial Day |
| 2012-06-07 | 784 | 17:26 |  |
| 2012-07-03 | 1087 | 17:27 |  |
| 2012-07-04 | 845 | 11:29 | Independence Day |
| 2012-09-03 | 900 | 11:29 | Labor Day |
| 2012-09-13 | 771 | 17:29 |  |
| 2012-10-29 | 857 | 09:14 | Hurricane Sandy |
| 2012-10-30 | 867 | 09:14 | Hurricane Sandy |

Pair alignment (share of traded-instrument minutes that also have a partner bar; 1m change correlation):

| year | bars | coverage | corr |
|---|---:|---:|---:|
| 2010 | 176,781 | 0.994 | 0.798 |
| 2011 | 318,821 | 0.997 | 0.855 |
| 2012 | 317,873 | 0.994 | 0.778 |
| 2013 | 309,973 | 0.993 | 0.771 |
| 2014 | 310,789 | 0.989 | 0.827 |
| 2015 | 328,480 | 0.994 | 0.878 |
| 2016 | 334,616 | 0.997 | 0.873 |
| 2017 | 340,693 | 0.989 | 0.709 |
| 2018 | 348,472 | 0.997 | 0.892 |
| 2019 | 346,580 | 0.989 | 0.893 |
| 2020 | 348,651 | 0.997 | 0.881 |
| 2021 | 353,069 | 0.998 | 0.853 |
| 2022 | 354,014 | 0.999 | 0.937 |
| 2023 | 352,912 | 0.998 | 0.891 |
| 2024 | 354,733 | 0.998 | 0.903 |
| 2025 | 352,175 | 0.999 | 0.943 |
| 2026 | 258,625 | 0.998 | 0.903 |

## MES

- Trading dates with data: **4199**  (2010-06-07 → 2026-09-24)
- 1m bars: 5,682,932; median per full day: 1368
- Weekdays with no data: 56 (50 are known holidays; **6 unexplained**)
- Short / holiday sessions (not traded): 171 (of which early close before 16:00 ET: 136)
- Days with an intraday hole ≥ 60 min (not traded): 4
- Days with suspect spikes (not traded): 0 (0 bars); 111 more spike bars were matched by the other index within ±1 min and kept as real moves

Row checks (raw contracts → continuous):

| check | raw | continuous |
|---|---:|---:|
| rows | 3,747,652 | 5682932 |
| duplicate_rows | 0 | 0 |
| bad_ohlc_rows | 0 | 0 |
| nonpositive_or_nan_rows | 15,556 | 0 |
| zero_volume_rows | 0 | 0 |
| off_tick_grid_rows | 71,138 |  |

Rolls (additive back-adjustment gap measured at the last minute both contracts traded):

| roll trading date | old | new | gap (pts) | measured at (UTC) | method |
|---|---|---|---:|---|---|
| 2010-06-10 | ESM0 | ESU0 | -4.50 | 2010-06-09 21:28:00+00:00 | last_common_minute |
| 2010-09-09 | ESU0 | ESZ0 | -5.00 | 2010-09-08 21:29:00+00:00 | last_common_minute |
| 2010-12-09 | ESZ0 | ESH1 | -5.00 | 2010-12-08 22:25:00+00:00 | last_common_minute |
| 2011-03-10 | ESH1 | ESM1 | -4.50 | 2011-03-09 22:28:00+00:00 | last_common_minute |
| 2011-06-09 | ESM1 | ESU1 | -5.25 | 2011-06-08 21:25:00+00:00 | last_common_minute |
| 2011-09-08 | ESU1 | ESZ1 | -6.00 | 2011-09-07 21:29:00+00:00 | last_common_minute |
| 2011-12-08 | ESZ1 | ESH2 | -6.00 | 2011-12-07 22:29:00+00:00 | last_common_minute |
| 2012-03-08 | ESH2 | ESM2 | -5.75 | 2012-03-07 22:29:00+00:00 | last_common_minute |
| 2012-06-07 | ESM2 | ESU2 | -6.75 | 2012-06-06 21:29:00+00:00 | last_common_minute |
| 2012-09-13 | ESU2 | ESZ2 | -7.00 | 2012-09-12 21:29:00+00:00 | last_common_minute |
| 2012-12-13 | ESZ2 | ESH3 | -6.00 | 2012-12-12 22:13:00+00:00 | last_common_minute |
| 2013-03-07 | ESH3 | ESM3 | -5.00 | 2013-03-06 22:14:00+00:00 | last_common_minute |
| 2013-06-13 | ESM3 | ESU3 | -5.50 | 2013-06-12 21:14:00+00:00 | last_common_minute |
| 2013-09-12 | ESU3 | ESZ3 | -6.75 | 2013-09-11 21:14:00+00:00 | last_common_minute |
| 2013-12-12 | ESZ3 | ESH4 | -7.00 | 2013-12-11 22:14:00+00:00 | last_common_minute |
| 2014-03-13 | ESH4 | ESM4 | -7.00 | 2014-03-12 21:14:00+00:00 | last_common_minute |
| 2014-06-16 | ESM4 | ESU4 | -7.25 | 2014-06-11 21:14:00+00:00 | last_common_minute |
| 2014-09-11 | ESU4 | ESZ4 | -7.50 | 2014-09-10 21:14:00+00:00 | last_common_minute |
| 2014-12-11 | ESZ4 | ESH5 | -7.00 | 2014-12-10 22:14:00+00:00 | last_common_minute |
| 2015-03-12 | ESH5 | ESM5 | -7.75 | 2015-03-11 21:14:00+00:00 | last_common_minute |
| 2015-06-11 | ESM5 | ESU5 | -7.75 | 2015-06-10 21:14:00+00:00 | last_common_minute |
| 2015-09-10 | ESU5 | ESZ5 | -9.00 | 2015-09-09 21:14:00+00:00 | last_common_minute |
| 2015-12-10 | ESZ5 | ESH6 | -8.25 | 2015-12-09 21:59:00+00:00 | last_common_minute |
| 2016-03-10 | ESH6 | ESM6 | -9.00 | 2016-03-09 21:59:00+00:00 | last_common_minute |
| 2016-06-09 | ESM6 | ESU6 | -9.25 | 2016-06-08 20:59:00+00:00 | last_common_minute |
| 2016-09-08 | ESU6 | ESZ6 | -7.00 | 2016-09-07 20:59:00+00:00 | last_common_minute |
| 2016-12-08 | ESZ6 | ESH7 | -5.00 | 2016-12-07 21:59:00+00:00 | last_common_minute |
| 2017-03-09 | ESH7 | ESM7 | -3.00 | 2017-03-08 21:59:00+00:00 | last_common_minute |
| 2017-06-08 | ESM7 | ESU7 | -2.75 | 2017-06-07 20:59:00+00:00 | last_common_minute |
| 2017-09-07 | ESU7 | ESZ7 | -2.25 | 2017-09-06 20:59:00+00:00 | last_common_minute |
| 2017-12-07 | ESZ7 | ESH8 | +2.75 | 2017-12-06 21:59:00+00:00 | last_common_minute |
| 2018-03-08 | ESH8 | ESM8 | +4.50 | 2018-03-07 21:59:00+00:00 | last_common_minute |
| 2018-06-07 | ESM8 | ESU8 | +4.00 | 2018-06-06 20:59:00+00:00 | last_common_minute |
| 2018-09-13 | ESU8 | ESZ8 | +5.25 | 2018-09-12 20:59:00+00:00 | last_common_minute |
| 2018-12-13 | ESZ8 | ESH9 | +4.00 | 2018-12-12 21:59:00+00:00 | last_common_minute |
| 2019-03-07 | ESH9 | ESM9 | +5.00 | 2019-03-06 21:59:00+00:00 | last_common_minute |
| 2019-06-13 | ESM9 | ESU9 | +4.00 | 2019-06-12 20:59:00+00:00 | last_common_minute |
| 2019-09-12 | MESU9 | MESZ9 | +1.25 | 2019-09-11 20:59:00+00:00 | last_common_minute |
| 2019-12-12 | MESZ9 | MESH0 | +2.50 | 2019-12-11 21:57:00+00:00 | last_common_minute |
| 2020-03-12 | MESH0 | MESM0 | -12.50 | 2020-03-11 20:59:00+00:00 | last_common_minute |
| 2020-06-11 | MESM0 | MESU0 | -11.25 | 2020-06-10 20:59:00+00:00 | last_common_minute |
| 2020-09-10 | MESU0 | MESZ0 | -9.25 | 2020-09-09 20:59:00+00:00 | last_common_minute |
| 2020-12-10 | MESZ0 | MESH1 | -7.50 | 2020-12-09 21:57:00+00:00 | last_common_minute |
| 2021-03-11 | MESH1 | MESM1 | -10.25 | 2021-03-10 21:59:00+00:00 | last_common_minute |
| 2021-06-10 | MESM1 | MESU1 | -9.00 | 2021-06-09 20:59:00+00:00 | last_common_minute |
| 2021-09-09 | MESU1 | MESZ1 | -9.75 | 2021-09-08 20:59:00+00:00 | last_common_minute |
| 2021-12-09 | MESZ1 | MESH2 | -6.75 | 2021-12-08 21:59:00+00:00 | last_common_minute |
| 2022-03-10 | MESH2 | MESM2 | -10.00 | 2022-03-09 21:59:00+00:00 | last_common_minute |
| 2022-06-09 | MESM2 | MESU2 | +1.50 | 2022-06-08 20:59:00+00:00 | last_common_minute |
| 2022-09-08 | MESU2 | MESZ2 | +17.00 | 2022-09-07 20:59:00+00:00 | last_common_minute |
| 2022-12-08 | MESZ2 | MESH3 | +31.25 | 2022-12-07 21:59:00+00:00 | last_common_minute |
| 2023-03-09 | MESH3 | MESM3 | +38.00 | 2023-03-08 21:59:00+00:00 | last_common_minute |
| 2023-06-08 | MESM3 | MESU3 | +42.75 | 2023-06-07 20:59:00+00:00 | last_common_minute |
| 2023-09-07 | MESU3 | MESZ3 | +49.50 | 2023-09-06 20:59:00+00:00 | last_common_minute |
| 2023-12-07 | MESZ3 | MESH4 | +50.25 | 2023-12-06 21:59:00+00:00 | last_common_minute |
| 2024-03-07 | MESH4 | MESM4 | +61.75 | 2024-03-06 21:59:00+00:00 | last_common_minute |
| 2024-06-13 | MESM4 | MESU4 | +65.00 | 2024-06-12 20:59:00+00:00 | last_common_minute |
| 2024-09-12 | MESU4 | MESZ4 | +59.75 | 2024-09-11 20:59:00+00:00 | last_common_minute |
| 2024-12-12 | MESZ4 | MESH5 | +66.25 | 2024-12-11 21:59:00+00:00 | last_common_minute |
| 2025-03-13 | MESH5 | MESM5 | +51.25 | 2025-03-12 20:59:00+00:00 | last_common_minute |
| 2025-06-12 | MESM5 | MESU5 | +53.25 | 2025-06-11 20:59:00+00:00 | last_common_minute |
| 2025-09-11 | MESU5 | MESZ5 | +53.75 | 2025-09-10 20:59:00+00:00 | last_common_minute |
| 2025-12-11 | MESZ5 | MESH6 | +60.50 | 2025-12-10 21:59:00+00:00 | last_common_minute |
| 2026-03-12 | MESH6 | MESM6 | +51.25 | 2026-03-11 20:59:00+00:00 | last_common_minute |
| 2026-06-11 | MESM6 | MESU6 | +60.00 | 2026-06-10 20:59:00+00:00 | last_common_minute |
| 2026-09-10 | MESU6 | MESZ6 | +65.25 | 2026-09-09 20:59:00+00:00 | last_common_minute |

Unexplained missing weekdays (first 30):

2014-06-12, 2014-06-13, 2014-09-23, 2014-09-24, 2014-09-25, 2014-12-31

Short sessions (first 40):

| date | bars | last bar ET | holiday |
|---|---:|---|---|
| 2010-07-05 | 1039 | 11:29 | Independence Day |
| 2010-09-06 | 1005 | 11:29 | Labor Day |
| 2010-09-09 | 1111 | 17:29 |  |
| 2010-11-25 | 1005 | 11:29 | Thanksgiving |
| 2010-11-26 | 1117 | 13:14 | Day after Thanksgiving (early close) |
| 2010-12-09 | 1145 | 17:29 |  |
| 2011-01-17 | 1016 | 11:29 | MLK Day |
| 2011-02-21 | 1034 | 11:29 | Presidents Day |
| 2011-05-30 | 941 | 11:29 | Memorial Day |
| 2011-06-09 | 1144 | 17:29 |  |
| 2011-07-04 | 1005 | 11:29 | Independence Day |
| 2011-09-05 | 1042 | 11:29 | Labor Day |
| 2011-11-24 | 1046 | 11:29 | Thanksgiving |
| 2011-11-25 | 1155 | 13:14 | Day after Thanksgiving (early close) |
| 2011-12-27 | 667 | 17:29 |  |
| 2012-01-03 | 673 | 17:29 |  |
| 2012-01-16 | 1041 | 11:29 | MLK Day |
| 2012-02-20 | 1046 | 11:29 | Presidents Day |
| 2012-04-06 | 724 | 09:14 | Good Friday |
| 2012-05-28 | 1030 | 11:29 | Memorial Day |
| 2012-07-04 | 1021 | 11:29 | Independence Day |
| 2012-09-03 | 1041 | 11:29 | Labor Day |
| 2012-09-13 | 1129 | 17:29 |  |
| 2012-10-29 | 909 | 09:14 | Hurricane Sandy |
| 2012-10-30 | 910 | 09:14 | Hurricane Sandy |
| 2012-11-23 | 1082 | 13:14 | Day after Thanksgiving (early close) |
| 2012-12-13 | 1120 | 17:14 |  |
| 2012-12-24 | 1139 | 13:14 |  |
| 2012-12-26 | 660 | 17:14 |  |
| 2013-01-02 | 660 | 17:14 |  |
| 2013-03-07 | 1076 | 17:14 |  |
| 2013-07-03 | 1150 | 13:14 |  |
| 2013-09-12 | 1081 | 17:14 |  |
| 2013-11-29 | 1064 | 13:14 | Day after Thanksgiving (early close) |
| 2013-12-24 | 1066 | 13:14 |  |
| 2013-12-26 | 657 | 17:14 |  |
| 2014-01-02 | 660 | 17:14 |  |
| 2014-05-26 | 998 | 12:59 | Memorial Day |
| 2014-07-03 | 1092 | 13:14 |  |
| 2014-07-04 | 1009 | 12:59 | Independence Day |

## Raw checks NQ

- rows: 3,660,491
- duplicate_rows: 0
- bad_ohlc_rows: 0
- nonpositive_or_nan_rows: 88,420
- zero_volume_rows: 0
- off_tick_grid_rows: 133,105

## Raw checks ES

- rows: 4,665,655
- duplicate_rows: 0
- bad_ohlc_rows: 0
- nonpositive_or_nan_rows: 245,114
- zero_volume_rows: 0
- off_tick_grid_rows: 301,181
