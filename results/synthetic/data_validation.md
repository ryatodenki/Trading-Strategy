# Data validation — dataset `synthetic`

Continuous contracts: roll rule `calendar`, adjustment `additive`. Tradeable trading dates: **1627 / 1675**.

Splices (proxy → micro):

- MNQ: from trading date 2020-07-01; raw price difference proxy vs micro +0.00 pts (should be ~0); applied offset +2194.50 pts (includes the micro series' own back-adjustment), measured at 2020-06-30 20:59:00+00:00
- MES: from trading date 2020-07-01; raw price difference proxy vs micro +0.00 pts (should be ~0); applied offset +585.50 pts (includes the micro series' own back-adjustment), measured at 2020-06-30 20:59:00+00:00

## MNQ

- Trading dates with data: **1675**  (2018-01-02 → 2024-06-28)
- 1m bars: 2,300,070; median per full day: 1380
- Weekdays with no data: 19 (19 are known holidays; **0 unexplained**)
- Short / holiday sessions (not traded): 48 (of which early close before 16:00 ET: 48)
- Days with an intraday hole ≥ 60 min (not traded): 0
- Days with suspect spikes (not traded): 0 (0 bars)

Row checks (raw contracts → continuous):

| check | raw | continuous |
|---|---:|---:|
| rows | 1,571,788 | 2300070 |
| duplicate_rows | 0 | 0 |
| bad_ohlc_rows | 0 | 0 |
| nonpositive_or_nan_rows | 0 | 0 |
| zero_volume_rows | 0 | 0 |
| off_tick_grid_rows | 0 |  |

Rolls (additive back-adjustment gap measured at the last minute both contracts traded):

| roll trading date | old | new | gap (pts) | measured at (UTC) | method |
|---|---|---|---:|---|---|
| 2018-03-08 | NQH8 | NQM8 | +136.50 | 2018-03-07 21:59:00+00:00 | last_common_minute |
| 2018-06-07 | NQM8 | NQU8 | +147.00 | 2018-06-06 20:59:00+00:00 | last_common_minute |
| 2018-09-13 | NQU8 | NQZ8 | +136.50 | 2018-09-12 20:59:00+00:00 | last_common_minute |
| 2018-12-13 | NQZ8 | NQH9 | +126.00 | 2018-12-12 21:59:00+00:00 | last_common_minute |
| 2019-03-07 | NQH9 | NQM9 | +147.00 | 2019-03-06 21:59:00+00:00 | last_common_minute |
| 2019-06-13 | NQM9 | NQU9 | +136.50 | 2019-06-12 20:59:00+00:00 | last_common_minute |
| 2019-09-12 | NQU9 | NQZ9 | +136.50 | 2019-09-11 20:59:00+00:00 | last_common_minute |
| 2019-12-12 | NQZ9 | NQH0 | +136.50 | 2019-12-11 21:59:00+00:00 | last_common_minute |
| 2020-03-12 | NQH0 | NQM0 | +136.50 | 2020-03-11 20:59:00+00:00 | last_common_minute |
| 2020-06-11 | NQM0 | NQU0 | +136.50 | 2020-06-10 20:59:00+00:00 | last_common_minute |
| 2020-09-10 | MNQU0 | MNQZ0 | +136.50 | 2020-09-09 20:59:00+00:00 | last_common_minute |
| 2020-12-10 | MNQZ0 | MNQH1 | +136.50 | 2020-12-09 21:59:00+00:00 | last_common_minute |
| 2021-03-11 | MNQH1 | MNQM1 | +136.50 | 2021-03-10 21:59:00+00:00 | last_common_minute |
| 2021-06-10 | MNQM1 | MNQU1 | +136.50 | 2021-06-09 20:58:00+00:00 | last_common_minute |
| 2021-09-09 | MNQU1 | MNQZ1 | +136.50 | 2021-09-08 20:59:00+00:00 | last_common_minute |
| 2021-12-09 | MNQZ1 | MNQH2 | +136.50 | 2021-12-08 21:59:00+00:00 | last_common_minute |
| 2022-03-10 | MNQH2 | MNQM2 | +136.50 | 2022-03-09 21:59:00+00:00 | last_common_minute |
| 2022-06-09 | MNQM2 | MNQU2 | +136.50 | 2022-06-08 20:59:00+00:00 | last_common_minute |
| 2022-09-08 | MNQU2 | MNQZ2 | +136.50 | 2022-09-07 20:59:00+00:00 | last_common_minute |
| 2022-12-08 | MNQZ2 | MNQH3 | +136.50 | 2022-12-07 21:59:00+00:00 | last_common_minute |
| 2023-03-09 | MNQH3 | MNQM3 | +136.50 | 2023-03-08 21:59:00+00:00 | last_common_minute |
| 2023-06-08 | MNQM3 | MNQU3 | +136.50 | 2023-06-07 20:58:00+00:00 | last_common_minute |
| 2023-09-07 | MNQU3 | MNQZ3 | +136.50 | 2023-09-06 20:59:00+00:00 | last_common_minute |
| 2023-12-07 | MNQZ3 | MNQH4 | +136.50 | 2023-12-06 21:59:00+00:00 | last_common_minute |
| 2024-03-07 | MNQH4 | MNQM4 | +147.00 | 2024-03-06 21:59:00+00:00 | last_common_minute |
| 2024-06-13 | MNQM4 | MNQU4 | +136.50 | 2024-06-12 20:59:00+00:00 | last_common_minute |

Short sessions (first 40):

| date | bars | last bar ET | holiday |
|---|---:|---|---|
| 2018-01-15 | 1140 | 12:59 | MLK Day |
| 2018-02-19 | 1140 | 12:59 | Presidents Day |
| 2018-05-28 | 1140 | 12:59 | Memorial Day |
| 2018-07-04 | 1140 | 12:59 | Independence Day |
| 2018-09-03 | 1140 | 12:59 | Labor Day |
| 2018-11-22 | 1140 | 12:59 | Thanksgiving |
| 2018-11-23 | 1155 | 13:14 | Day after Thanksgiving (early close) |
| 2019-01-21 | 1140 | 12:59 | MLK Day |
| 2019-02-18 | 1140 | 12:59 | Presidents Day |
| 2019-05-27 | 1140 | 12:59 | Memorial Day |
| 2019-07-04 | 1140 | 12:59 | Independence Day |
| 2019-09-02 | 1140 | 12:59 | Labor Day |
| 2019-11-28 | 1140 | 12:59 | Thanksgiving |
| 2019-11-29 | 1155 | 13:14 | Day after Thanksgiving (early close) |
| 2020-01-20 | 1140 | 12:59 | MLK Day |
| 2020-02-17 | 1140 | 12:59 | Presidents Day |
| 2020-05-25 | 1140 | 12:59 | Memorial Day |
| 2020-07-03 | 1140 | 12:59 | Independence Day |
| 2020-09-07 | 1140 | 12:59 | Labor Day |
| 2020-11-26 | 1140 | 12:59 | Thanksgiving |
| 2020-11-27 | 1155 | 13:14 | Day after Thanksgiving (early close) |
| 2021-01-18 | 1140 | 12:59 | MLK Day |
| 2021-02-15 | 1140 | 12:59 | Presidents Day |
| 2021-05-31 | 1140 | 12:59 | Memorial Day |
| 2021-07-05 | 1140 | 12:59 | Independence Day |
| 2021-09-06 | 1140 | 12:59 | Labor Day |
| 2021-11-25 | 1140 | 12:59 | Thanksgiving |
| 2021-11-26 | 1155 | 13:14 | Day after Thanksgiving (early close) |
| 2022-01-17 | 1140 | 12:59 | MLK Day |
| 2022-02-21 | 1140 | 12:59 | Presidents Day |
| 2022-05-30 | 1140 | 12:59 | Memorial Day |
| 2022-06-20 | 1140 | 12:59 | Juneteenth |
| 2022-07-04 | 1140 | 12:59 | Independence Day |
| 2022-09-05 | 1140 | 12:59 | Labor Day |
| 2022-11-24 | 1140 | 12:59 | Thanksgiving |
| 2022-11-25 | 1155 | 13:14 | Day after Thanksgiving (early close) |
| 2023-01-16 | 1140 | 12:59 | MLK Day |
| 2023-02-20 | 1140 | 12:59 | Presidents Day |
| 2023-05-29 | 1140 | 12:59 | Memorial Day |
| 2023-06-19 | 1140 | 12:59 | Juneteenth |

Pair alignment (share of traded-instrument minutes that also have a partner bar; 1m change correlation):

| year | bars | coverage | corr |
|---|---:|---:|---:|
| 2018 | 354,375 | 1.000 | 0.894 |
| 2019 | 354,375 | 1.000 | 0.897 |
| 2020 | 355,755 | 1.000 | 0.898 |
| 2021 | 352,995 | 1.000 | 0.898 |
| 2022 | 354,135 | 1.000 | 0.897 |
| 2023 | 352,755 | 1.000 | 0.898 |
| 2024 | 175,680 | 1.000 | 0.897 |

## MES

- Trading dates with data: **1675**  (2018-01-02 → 2024-06-28)
- 1m bars: 2,300,070; median per full day: 1380
- Weekdays with no data: 19 (19 are known holidays; **0 unexplained**)
- Short / holiday sessions (not traded): 48 (of which early close before 16:00 ET: 48)
- Days with an intraday hole ≥ 60 min (not traded): 0
- Days with suspect spikes (not traded): 0 (0 bars)

Row checks (raw contracts → continuous):

| check | raw | continuous |
|---|---:|---:|
| rows | 1,571,923 | 2300070 |
| duplicate_rows | 0 | 0 |
| bad_ohlc_rows | 0 | 0 |
| nonpositive_or_nan_rows | 0 | 0 |
| zero_volume_rows | 0 | 0 |
| off_tick_grid_rows | 0 |  |

Rolls (additive back-adjustment gap measured at the last minute both contracts traded):

| roll trading date | old | new | gap (pts) | measured at (UTC) | method |
|---|---|---|---:|---|---|
| 2018-03-08 | ESH8 | ESM8 | +36.25 | 2018-03-07 21:59:00+00:00 | last_common_minute |
| 2018-06-07 | ESM8 | ESU8 | +39.25 | 2018-06-06 20:58:00+00:00 | last_common_minute |
| 2018-09-13 | ESU8 | ESZ8 | +36.50 | 2018-09-12 20:59:00+00:00 | last_common_minute |
| 2018-12-13 | ESZ8 | ESH9 | +33.50 | 2018-12-12 21:59:00+00:00 | last_common_minute |
| 2019-03-07 | ESH9 | ESM9 | +39.25 | 2019-03-06 21:59:00+00:00 | last_common_minute |
| 2019-06-13 | ESM9 | ESU9 | +36.25 | 2019-06-12 20:59:00+00:00 | last_common_minute |
| 2019-09-12 | ESU9 | ESZ9 | +36.50 | 2019-09-11 20:59:00+00:00 | last_common_minute |
| 2019-12-12 | ESZ9 | ESH0 | +36.50 | 2019-12-11 21:59:00+00:00 | last_common_minute |
| 2020-03-12 | ESH0 | ESM0 | +36.25 | 2020-03-11 20:59:00+00:00 | last_common_minute |
| 2020-06-11 | ESM0 | ESU0 | +36.50 | 2020-06-10 20:59:00+00:00 | last_common_minute |
| 2020-09-10 | MESU0 | MESZ0 | +36.50 | 2020-09-09 20:59:00+00:00 | last_common_minute |
| 2020-12-10 | MESZ0 | MESH1 | +36.25 | 2020-12-09 21:59:00+00:00 | last_common_minute |
| 2021-03-11 | MESH1 | MESM1 | +36.25 | 2021-03-10 21:59:00+00:00 | last_common_minute |
| 2021-06-10 | MESM1 | MESU1 | +36.50 | 2021-06-09 20:59:00+00:00 | last_common_minute |
| 2021-09-09 | MESU1 | MESZ1 | +36.50 | 2021-09-08 20:59:00+00:00 | last_common_minute |
| 2021-12-09 | MESZ1 | MESH2 | +36.50 | 2021-12-08 21:59:00+00:00 | last_common_minute |
| 2022-03-10 | MESH2 | MESM2 | +36.50 | 2022-03-09 21:59:00+00:00 | last_common_minute |
| 2022-06-09 | MESM2 | MESU2 | +36.50 | 2022-06-08 20:59:00+00:00 | last_common_minute |
| 2022-09-08 | MESU2 | MESZ2 | +36.25 | 2022-09-07 20:58:00+00:00 | last_common_minute |
| 2022-12-08 | MESZ2 | MESH3 | +36.50 | 2022-12-07 21:59:00+00:00 | last_common_minute |
| 2023-03-09 | MESH3 | MESM3 | +36.25 | 2023-03-08 21:59:00+00:00 | last_common_minute |
| 2023-06-08 | MESM3 | MESU3 | +36.50 | 2023-06-07 20:59:00+00:00 | last_common_minute |
| 2023-09-07 | MESU3 | MESZ3 | +36.25 | 2023-09-06 20:58:00+00:00 | last_common_minute |
| 2023-12-07 | MESZ3 | MESH4 | +36.50 | 2023-12-06 21:59:00+00:00 | last_common_minute |
| 2024-03-07 | MESH4 | MESM4 | +39.25 | 2024-03-06 21:59:00+00:00 | last_common_minute |
| 2024-06-13 | MESM4 | MESU4 | +36.50 | 2024-06-12 20:59:00+00:00 | last_common_minute |

Short sessions (first 40):

| date | bars | last bar ET | holiday |
|---|---:|---|---|
| 2018-01-15 | 1140 | 12:59 | MLK Day |
| 2018-02-19 | 1140 | 12:59 | Presidents Day |
| 2018-05-28 | 1140 | 12:59 | Memorial Day |
| 2018-07-04 | 1140 | 12:59 | Independence Day |
| 2018-09-03 | 1140 | 12:59 | Labor Day |
| 2018-11-22 | 1140 | 12:59 | Thanksgiving |
| 2018-11-23 | 1155 | 13:14 | Day after Thanksgiving (early close) |
| 2019-01-21 | 1140 | 12:59 | MLK Day |
| 2019-02-18 | 1140 | 12:59 | Presidents Day |
| 2019-05-27 | 1140 | 12:59 | Memorial Day |
| 2019-07-04 | 1140 | 12:59 | Independence Day |
| 2019-09-02 | 1140 | 12:59 | Labor Day |
| 2019-11-28 | 1140 | 12:59 | Thanksgiving |
| 2019-11-29 | 1155 | 13:14 | Day after Thanksgiving (early close) |
| 2020-01-20 | 1140 | 12:59 | MLK Day |
| 2020-02-17 | 1140 | 12:59 | Presidents Day |
| 2020-05-25 | 1140 | 12:59 | Memorial Day |
| 2020-07-03 | 1140 | 12:59 | Independence Day |
| 2020-09-07 | 1140 | 12:59 | Labor Day |
| 2020-11-26 | 1140 | 12:59 | Thanksgiving |
| 2020-11-27 | 1155 | 13:14 | Day after Thanksgiving (early close) |
| 2021-01-18 | 1140 | 12:59 | MLK Day |
| 2021-02-15 | 1140 | 12:59 | Presidents Day |
| 2021-05-31 | 1140 | 12:59 | Memorial Day |
| 2021-07-05 | 1140 | 12:59 | Independence Day |
| 2021-09-06 | 1140 | 12:59 | Labor Day |
| 2021-11-25 | 1140 | 12:59 | Thanksgiving |
| 2021-11-26 | 1155 | 13:14 | Day after Thanksgiving (early close) |
| 2022-01-17 | 1140 | 12:59 | MLK Day |
| 2022-02-21 | 1140 | 12:59 | Presidents Day |
| 2022-05-30 | 1140 | 12:59 | Memorial Day |
| 2022-06-20 | 1140 | 12:59 | Juneteenth |
| 2022-07-04 | 1140 | 12:59 | Independence Day |
| 2022-09-05 | 1140 | 12:59 | Labor Day |
| 2022-11-24 | 1140 | 12:59 | Thanksgiving |
| 2022-11-25 | 1155 | 13:14 | Day after Thanksgiving (early close) |
| 2023-01-16 | 1140 | 12:59 | MLK Day |
| 2023-02-20 | 1140 | 12:59 | Presidents Day |
| 2023-05-29 | 1140 | 12:59 | Memorial Day |
| 2023-06-19 | 1140 | 12:59 | Juneteenth |

## Raw checks NQ

- rows: 991,115
- duplicate_rows: 0
- bad_ohlc_rows: 0
- nonpositive_or_nan_rows: 0
- zero_volume_rows: 0
- off_tick_grid_rows: 0

## Raw checks ES

- rows: 991,550
- duplicate_rows: 0
- bad_ohlc_rows: 0
- nonpositive_or_nan_rows: 0
- zero_volume_rows: 0
- off_tick_grid_rows: 0
