# DESIGN: Peak Model

> Phase 2. How the requirements will be met, file by file.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | PEAK_MODEL |
| **Date** | 2026-10-21 |
| **Author** | Christian |
| **Source** | DEFINE_PEAK_MODEL.md (status Ready for Design); BRAINSTORM_PEAK_MODEL.md (Selected Approach, data flow, tasks 1 to 5); ADR 0001, 0003 to 0007; contracts in `docs/contracts/`; archived METER_INGESTION design, build report and SHIPPED record as the layout reference |
| **Status** | Ready for Build |

Allowed status values: `Draft`, `Ready for Build`.

---

## Overview

PEAK_MODEL adds a governed daily ML path on top of the shipped METER_INGESTION Gold tables, using
variant 1A of D-32 (ADR 0007). Two jobs are added to the same Asset Bundle. Neither the
METER_INGESTION job nor its pipeline changes, and no pipeline is added (ADR 0008).

- **Daily job `smart_meter_peak_model`.** It runs these steps on serverless notebook tasks:
  - run the existing Silver/Gold pipeline;
  - ingest the hourly weather file with Auto Loader and rebuild `silver.weather_hourly`;
  - recompute the dense feature table `ml.household_features_daily` (a UC Feature Engineering
    table, time-series column `feature_date`) and the label and eligibility table
    `ml.household_labels_daily`;
  - score the households eligible on `target_date` with the `champion` version through
    `fe.score_batch`.
- **On-demand job `smart_meter_peak_model_training`.** It does the following:
  - builds the point-in-time training set with `create_training_set`;
  - trains one deterministic `HistGradientBoostingClassifier`;
  - picks t at maximum validation F1 (ADR 0009) and evaluates overall, per ACORN group and per month;
  - registers the model with `fe.log_model`, stores t as a version tag and moves `champion`.

Every table is recomputed in full and written with a change-only MERGE, so reruns change 0 rows and
rebuilds give identical content (ADR 0011). The training set is kept as a run artifact with its
source table versions. All logic lives in `src/smart_meter_peak_prediction/` and is unit-tested on
local Spark and scikit-learn. Notebooks are thin wiring.

---

## Architecture

```text
 LOCAL MACHINE                         DATABRICKS FREE EDITION (serverless, target dev, catalog smart_meter_dev)
 -------------                         -------------------------------------------------------------------------
 data/raw/weather_hourly_darksky.csv
   -- databricks fs cp --> /Volumes/smart_meter_dev/bronze/landing/weather/   (runbook, once)

 METER_INGESTION (unchanged, tag v0.1.0)          read-only interface (C-08)
   job smart_meter_ingestion 06:00 UTC  --> pipeline smart_meter_silver_gold --> gold.household_daily_consumption
                                                                              --> gold.household_data_quality_monthly
                                                                              --> silver.households

 Job smart_meter_peak_model (daily 08:00 UTC, paused in development mode, max 1 concurrent run; ADR 0008)
 +--------------------------------------------------------------------------------------------------------+
 | [1] refresh_silver_gold (pipeline_task on smart_meter_silver_gold, full_refresh false, 1 retry / 10 min)|
 | [2] ingest_weather (notebook)   Auto Loader availableNow -> bronze.files_weather_hourly (append-only)   |
 |        |                                                                                               |
 | [3] build_weather_silver (notebook, after 2)  parse UTC (QR-16 fail), dedup (QR-17), QR-18 warn        |
 |        -> silver.weather_hourly (change-only MERGE)                                                    |
 |        |                                                                                               |
 | [4] build_features (notebook, after 1 and 3)  dense grid household x feature_date, D-28 + D-25         |
 |        -> ml.household_features_daily  (UC feature table, PK household_id, feature_date TIMESERIES)    |
 | [5] build_labels (notebook, after 1)  D-19 label of T = D + 1, D-27 eligibility over 3 months < T      |
 |        -> ml.household_labels_daily  (QR-19 fail; parameters as table properties)                      |
 |        |                                                                                               |
 | [6] score_predictions (notebook, after 4 and 5)  target_date (default: latest complete Gold day + 1)   |
 |        eligible households on T -> fe.score_batch(models:/...consumption_spike_model/<champion version>) |
 |        label = score >= t (version tag decision_threshold); QR-20 fail                                 |
 |        -> gold.consumption_spike_predictions (replaceWhere target_date in scored dates)                |
 +--------------------------------------------------------------------------------------------------------+
   widest level: 2 tasks ([1] with [2], [3] with [5])

 Job smart_meter_peak_model_training (no schedule, on demand, D-36)
 +--------------------------------------------------------------------------------------------------------+
 | [1] train_model (notebook)                                                                             |
 |   labels@VL (eligible, labelled, in D-29 ranges) + lookup_date = target_date - 1                       |
 |   fe.create_training_set(FeatureLookup ml.household_features_daily@VF, timestamp_lookup_key lookup_date)|
 |   guards G-02 (exact T - 1 row), G-03 (no empty month), G-04 (VF unchanged)                            |
 |   HistGradientBoostingClassifier(random_state=seed, early_stopping=False) on train                     |
 |   t = max F1 on validation (ties: highest t); metrics overall / ACORN / month + ratio rule             |
 |   MLflow run: params, metrics, training_set.parquet, scores, table versions, git commit                |
 |   fe.log_model -> smart_meter_dev.ml.consumption_spike_model vN -> tag decision_threshold              |
 |   -> reload check -> alias champion = vN                                                               |
 +--------------------------------------------------------------------------------------------------------+
```

---

## Components

Package path `src/smart_meter_peak_prediction/` is abbreviated `pkg/`.

| Component | Responsibility | Technology | Requirements covered |
|---|---|---|---|
| Parameters and names (`pkg/peak_config.py`) | `PeakParameters`: every FR-31 parameter with its default, parsed from job parameters (widgets), validated (ordered, disjoint split ranges; thresholds in range). Table, Volume, checkpoint, model and experiment names built on top of the existing `Settings` (unchanged). Pinned platform versions and the runtime version guard (G-01) | Python dataclasses | FR-31, NFR-13 |
| Delta write helpers (`pkg/delta_sync.py`) | SQL for the change-only MERGE (null-safe change condition, insert, delete by source), `replaceWhere` overwrite, table properties, and reading MERGE metrics from the Delta history | Spark SQL, Delta | NFR-10, NFR-11, AC-57, AC-66 |
| Table setup (`pkg/peak_setup.py`) | `CREATE TABLE IF NOT EXISTS` for `bronze.files_weather_hourly` (append-only), `silver.weather_hourly`, `ml.household_labels_daily` and `gold.consumption_spike_predictions`. Schema of the feature table for `fe.create_table`. Precondition that catalog and schemas exist (created by METER_INGESTION, ADR 0003) | Spark SQL | FR-18, FR-21, FR-29, AC-64 |
| Weather library (`pkg/weather.py`) | Source read schema (header names), Bronze projection, Silver transform: UTC parse with an explicit offset, QR-16 check, QR-17 ranked dedup with a loser count, QR-18 parse and range count; daily mean temperature with a fixed summation order | PySpark | FR-18, FR-19, NFR-16, AC-36 to AC-39 |
| Feature library (`pkg/features.py`) | Dense household x date grid, the shared same-weekday baseline, every D-28 and D-25 feature, density check (G-10), and the explicit lookup on `feature_date = target_date - 1` (1B fallback and test oracle) | PySpark | FR-20, FR-23, NFR-12, AC-39 to AC-42 |
| Label library (`pkg/labels.py`) | D-19 label of T, D-27 / D-34 eligibility window and reasons, QR-19 check, density check | PySpark | FR-21, FR-22, NFR-12, AC-41, AC-43 to AC-47 |
| Model wrapper (`pkg/model.py`) | Feature column order, fixed categorical codes (OD-10), classifier factory, MLflow pyfunc wrapper that returns the probability of the positive class | scikit-learn 1.3.0, MLflow pyfunc | FR-24, FR-29, AC-49, AC-54 |
| Training library (`pkg/training.py`) | Split assignment, training-frame guards (G-02, G-03), deterministic row order, fit, threshold rule (ADR 0009), evaluation and metric names, ratio-rule reference, the run parameter set, orchestration over a `Tracker` protocol | pandas, NumPy, scikit-learn | FR-23 to FR-26, NFR-10, AC-48 to AC-53 |
| Registry adapter (`pkg/registry.py`) | Thin layer over the Feature Engineering client and MLflow: ensure the feature table, build the training set, read Delta versions (G-04), `fe.log_model` with signature and `code_paths`, threshold tag, reload check, alias, champion resolution with named errors (G-07); `MlflowTracker` | databricks-feature-engineering 0.18.2, MLflow 3.17.2 (serverless) | FR-25, FR-27, NFR-18, AC-54, AC-55, AC-61 |
| Scoring library (`pkg/scoring.py`) | Target date resolution (default, single, range), feature-date and label-row check (G-06), eligible set, prediction assembly, QR-20, `replaceWhere` write | PySpark, FE client | FR-28, FR-29, NFR-11, AC-56 to AC-61 |
| Notebooks (`notebooks/ingest_weather.py`, `build_weather_silver.py`, `build_features.py`, `build_labels.py`, `score_predictions.py`, `train_model.py`) | Wiring only. They read widgets, set and assert the UTC session time zone, pin the ML libraries with `%pip`, call the library, and print counts and parameters into the notebook exit value. No try/except (I-14 rule of METER_INGESTION) | Databricks notebooks (serverless) | FR-18 to FR-29 |
| Bundle resources (`resources/smart_meter_peak_model.job.yml`, `resources/smart_meter_peak_model_training.job.yml`) | Daily job with six tasks, job parameters and schedule; training job with one task and no schedule. `databricks.yml` and the two METER_INGESTION resource files are not changed | Databricks Asset Bundles | FR-30, FR-31, NFR-13, NFR-14 |
| Data contracts (`docs/contracts/*.yaml`, five new files) | Bronze and Silver weather, features, labels, predictions (consumer-facing) | YAML, `check_specs.py` | AC-64 |
| Tests (`tests/`) | Unit tests (local Spark, scikit-learn), local-data tests on the seed-42 sample, integration tests on the `dev` workspace | pytest, pyspark, databricks-sdk, mlflow | All AC |
| Runbook and reset script (`docs/runbooks/peak_model.md`, `scripts/reset_peak_model_outputs.py`) | Weather upload, first-run order, training, backfill, evidence order, guarded user-run reset for AC-66, model cleanup order | Markdown, Python | NFR-17, AC-62, AC-66 |

---

## Data Model

All names are shown for the main layout (catalog `smart_meter_dev`, ADR 0003). With the A-09
fallback they follow the same variables. Event-time columns: `weather_ts`, `feature_date`,
`target_date`. Processing-time and source-metadata columns start with `_`: `_ingested_at`,
`_source_file`, `_rescued_data`, `_scored_at`. All dates are UTC calendar dates. Every notebook sets
`spark.sql.session.timeZone = UTC` and asserts it. Derivations that must not depend on the session
time zone (AC-37) use explicit-offset parsing and epoch arithmetic.

| Object | Layer | Grain | Key | Partitioning / clustering | Notes |
|---|---|---|---|---|---|
| Volume path `/Volumes/smart_meter_dev/bronze/landing/weather/` | bronze | One file | Path | - | Existing Volume `landing`, new folder. The file is uploaded once by the operator (runbook) |
| Volume path `/Volumes/smart_meter_dev/bronze/checkpoints/files_weather_hourly/` | bronze | One stream | Path | - | Auto Loader checkpoint |
| `smart_meter_dev.bronze.files_weather_hourly` | bronze | One row per CSV line ingested | `(_source_file, time_raw)` | None; `delta.appendOnly = true` | All 12 source columns as raw strings (`time_raw`, `temperature_raw`, `apparent_temperature_raw`, `dew_point_raw`, `humidity_raw`, `pressure_raw`, `visibility_raw`, `wind_bearing_raw`, `wind_speed_raw`, `precip_type_raw`, `icon_raw`, `summary_raw`), `_rescued_data`, `_source_file`, `_ingested_at`. Contract `bronze_files_weather_hourly.yaml` |
| `smart_meter_dev.silver.weather_hourly` | silver | One row per UTC hour present in the source | `weather_ts` | None (about 21,000 rows) | `weather_ts`, `temperature_c`, `_ingested_at` (of the winning Bronze row). Full time range of the file kept. Contract `silver_weather_hourly.yaml` |
| `smart_meter_dev.ml.household_features_daily` | ml | One row per `silver.households` household per feature date D, from `study_start` to the latest Gold `reading_date` | `(household_id, feature_date)`, `feature_date` TIMESERIES | None (36,480 rows for seed 42) | Created with `fe.create_table(primary_keys, timeseries_columns="feature_date", schema)`. History retention 90 days (ADR 0011). Table properties `smart_meter.baseline_day_count` and `smart_meter.label_lookback_weeks`. Contract `ml_household_features_daily.yaml` |
| `smart_meter_dev.ml.household_labels_daily` | ml | One row per `silver.households` household per target date T = D + 1 | `(household_id, target_date)` | None | Plain Delta table. History retention 90 days. Table properties hold the label and eligibility parameters of the build (`smart_meter.label_threshold`, `smart_meter.baseline_day_count`, `smart_meter.label_lookback_weeks`, `smart_meter.coverage_min`, `smart_meter.zero_share_max`, `smart_meter.eligibility_months`). Contract `ml_household_labels_daily.yaml` |
| Training set (per training run) | ml (artifact) | One row per eligible, labelled `(household_id, target_date)` in the three ranges | `(household_id, target_date)` | - | Not a table (OD-09). Artifact `training_set.parquet` of the MLflow run, plus `mlflow.log_input` of both source tables at their versions |
| `smart_meter_dev.ml.consumption_spike_model` | ml (registry) | One version per successful training run | `(name, version)`; alias `champion` | - | Logged by `fe.log_model` (pyfunc wrapper, signature, `feature_spec.yaml` naming the feature table). Version tag `decision_threshold` = `repr(t)` (ADR 0009) |
| `smart_meter_dev.gold.consumption_spike_predictions` | gold | One row per eligible household per `target_date` | `(household_id, target_date)` | None | `household_id`, `target_date`, `score`, `label`, `model_version`, `_scored_at`. Rows of a scored date are replaced as one transaction. Contract `gold_consumption_spike_predictions.yaml` (consumer-facing) |
| MLflow experiment `/Users/<deploying user>/smart_meter_peak_model` | - | One run per training run | run id | - | Parameters, metrics and artifacts listed in *MLflow run contents* |

### Column derivations

**Weather, Bronze (FR-18).** The Auto Loader read schema uses the source header names in file order
(`visibility`, `windBearing`, `temperature`, `time`, `dewPoint`, `pressure`, `apparentTemperature`,
`windSpeed`, `precipType`, `icon`, `humidity`, `summary`; profile `docs/profiling/weather_hourly_darksky.md`).
The read has `header = true` and the rescued data column. The projection renames each column to
snake_case with the `_raw` suffix and adds `_source_file = _metadata.file_path` and
`_ingested_at = current_timestamp()`. The existing `bronze.auto_loader_reader` and
`bronze.run_available_now` functions are reused unchanged.

**Weather, Silver (FR-19).**

| Column or step | Expression |
|---|---|
| `weather_ts` | `try_to_timestamp(concat(trim(time_raw), '+00:00'), 'yyyy-MM-dd HH:mm:ssXXX')`. The explicit offset makes the instant independent of the session time zone (AC-37, ADR 0001 DA-07 fallback form) |
| QR-16 | When any row has a non-null `time_raw` with null `weather_ts`, or a null `time_raw`, the step raises before any write and names the first offending raw values (count and up to 5 examples) |
| `temperature_c` | `try_cast(trim(temperature_raw) AS DOUBLE)`. A null result fails the step (QR-18 parse). Values outside [-30, 45] are kept and counted (QR-18 warn) |
| QR-17 rank | `row_number() OVER (PARTITION BY weather_ts ORDER BY _ingested_at, _source_file, time_raw, temperature_raw, <remaining raw columns in schema order>)`; rank 1 is kept. The ADR 0005 order, extended by the raw values so that two identical-time rows of one file and one batch (same `_ingested_at` and `_source_file`) still have a deterministic winner. The loser count is returned |
| `_ingested_at` | Of the winning Bronze row |

**Daily temperature (D-25, F-22).** For each feature date D:
- `weather_date = date_from_unix_date(CAST(floor(unix_seconds(weather_ts) / 86400) AS INT))`, which
  is the UTC date whatever the session time zone;
- `temperature_hour_count_1d = count(*)`, 0 when no row exists;
- `mean_temperature_c_1d = aggregate(array_sort(collect_list(temperature_c)), 0D, (acc, x) -> acc + x) / count(*)`,
  null when the count is 0. The sorted fold fixes the summation order, so recomputation is bitwise
  stable (ADR 0011).

**Feature grid and features (FR-20).**
- **Grid.** Every household of `silver.households`, crossed with every date D from `study_start` to
  `max(reading_date)` of `gold.household_daily_consumption`.
- **Gold join.** Left join of the Gold daily rows on `(household_id, reading_date = D)`. The join
  gives `total`, `max` and `complete`, where `complete = coalesce(is_complete_day, false)`.
- **Window.** `W = PARTITION BY household_id ORDER BY feature_date`, with ROWS frames. Because the
  grid is dense, a row offset equals a day offset.

| Feature | Expression |
|---|---|
| `total_energy_kwh_1d`, `max_energy_kwh_1d` | `total`, `max` of D as stored (null without a Gold row) |
| `avg_energy_kwh_7d` | `avg(IF(complete, total, NULL)) OVER (W ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)` |
| `avg_energy_kwh_28d` | the same with `27 PRECEDING` |
| `complete_day_share_28d` | `sum(IF(complete, 1, 0)) OVER (W ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) / 28.0`; days before the grid start count as not complete |
| Shared baseline (`features.same_weekday_baseline`) | Candidates `c_k = lag(IF(complete, total, NULL), 7k - 1) OVER W` for k = 1 to `label_lookback_weeks`; row D - (7k - 1) is T - 7k. `found = filter(array(c_1, ..., c_L), x -> x IS NOT NULL)`, which keeps the most recent first. `baseline_day_count = least(size(found), N)` with N = `baseline_day_count` parameter. Median of `array_sort(slice(found, 1, N))`: the middle element for odd N, the mean of the two middle elements for even N; null when `size(found) < N` |
| `median_energy_kwh_same_weekday_8w` | The shared baseline at D (the D-19 baseline of T = D + 1) |
| `target_weekday`, `target_month` | `weekday(date_add(D, 1)) + 1` (1 = Monday), `month(date_add(D, 1))` |
| `acorn_group`, `tariff` | From `silver.households` |
| `mean_temperature_c_1d`, `temperature_hour_count_1d` | Daily temperature of D, left-joined; count `coalesce(..., 0)` |

**Labels and eligibility (FR-21, FR-22).** The grid is the feature grid, with
`target_date = date_add(feature_date, 1)`.

| Column | Expression |
|---|---|
| `feature_date` | D |
| `total_energy_kwh` | Gold `total_energy_kwh` of T as stored; null without a row (for example T = max D + 1) |
| `baseline_energy_kwh`, `baseline_day_count` | The shared baseline at D, the same function as the feature |
| `label_consumption_spike` | `CASE WHEN coalesce(is_complete_day_T, false) AND baseline_day_count = N THEN IF(total_energy_kwh > label_threshold * baseline_energy_kwh, 1, 0) END`. An exact 1.3 x baseline gives 0, because the comparison is strict in IEEE doubles |
| Window months | Monthly rows with `reading_month` from `add_months(trunc(T, 'MM'), -E)` to `add_months(trunc(T, 'MM'), -1)`, E = `eligibility_months`. These are exactly the E latest study months whose last day is before T. T = 2012-10-01 gives 2012-07 to 2012-09, and T = 2012-09-30 gives only 2012-07 and 2012-08, because 2012-06 is not a study month |
| `eligibility_month_count` | Number of monthly rows found (0 to E), restricted to `silver.households` households |
| `coverage_ratio_3m` | `sum(observed_readings) / sum(expected_readings)` when the count = E, else null |
| `zero_share_3m` | `sum(zero_readings) / sum(observed_readings)` when the count = E and the observed sum > 0, else null |
| `ineligibility_reasons` | `filter(array(IF(cnt < E, 'insufficient_history', NULL), IF(cnt = E AND coverage_ratio_3m < coverage_min, 'low_coverage', NULL), IF(cnt = E AND (zero_share_3m IS NULL OR zero_share_3m >= zero_share_max), 'high_zero_share', NULL)), x -> x IS NOT NULL)`; fixed order, empty when eligible |
| `is_eligible` | `size(ineligibility_reasons) = 0` |

**Training set (FR-23).**
- **Source rows.** The labels table read at version VL. It keeps the rows where `is_eligible`,
  `label_consumption_spike IS NOT NULL` and `target_date` lies in one of the three ranges.
- **Label type.** `training.select_training_rows` casts the label to int after `toPandas`: a nullable
  int column arrives as float, and the lookup frame would then carry a double label (build
  deviation D-13). The filtering itself runs in pandas on the labels read at VL (build deviation
  D-06).
- **Columns.** `split` is assigned by `target_date` only, never shuffled, and
  `lookup_date = feature_date` (= `target_date - 1`).
- **Feature lookup.** `fe.create_training_set` with
  `FeatureLookup(table_name = features, lookup_key = "household_id", timestamp_lookup_key = "lookup_date", feature_names = FEATURE_COLUMNS)`,
  `label = "label_consumption_spike"` and `exclude_columns = ["lookup_date"]`. This is the spike 05
  shape.
- **Order.** The materialised frame is sorted by `(target_date, household_id)` before fitting.
  The order of the HGB input rows must not depend on Spark partitioning.

**Model (FR-24, OD-10).**
- **Classifier.** `HistGradientBoostingClassifier(random_state = random_seed, early_stopping = False, categorical_features = <mask>)`,
  with all other arguments at their scikit-learn 1.3.0 defaults. Every argument is logged.
- **Feature order (`FEATURE_COLUMNS`).**
  1. `total_energy_kwh_1d`
  2. `max_energy_kwh_1d`
  3. `avg_energy_kwh_7d`
  4. `avg_energy_kwh_28d`
  5. `median_energy_kwh_same_weekday_8w`
  6. `complete_day_share_28d`
  7. `target_weekday`
  8. `target_month`
  9. `acorn_group`
  10. `tariff`
  11. `mean_temperature_c_1d`
  12. `temperature_hour_count_1d`
- **Categorical codes.** The wrapper encodes with a fixed map, not a fitted encoder:
  - `acorn_group`: Affluent 0, Comfortable 1, Adversity 2;
  - `tariff`: Std 0, ToU 1;
  - `target_weekday`: value - 1;
  - `target_month`: value - 1;
  - any other value is NaN.

  These four columns are the categorical mask. Numeric nulls stay NaN and use the native missing
  value support. Nothing is imputed or scaled, so nothing is fitted outside train.
- **Wrapper.** The pyfunc class `ConsumptionSpikeModel` holds the classifier and the codes.
  `predict` selects `FEATURE_COLUMNS` from its input, encodes them and returns
  `predict_proba(...)[:, 1]`. The model is logged with `code_paths` set to the package folder, so the
  class loads outside the training task (DA-16).

**Predictions (FR-28, FR-29).**

| Column | Derivation |
|---|---|
| `household_id`, `target_date` | Labels rows of the scored dates with `is_eligible` |
| `score` | `prediction` of `fe.score_batch(model_uri = "models:/<model>/<v>", df, result_type = "double")`, where v is the version that `champion` resolves to at the start of the run (pinned, so an alias move during the run cannot mix versions). `df` holds `household_id`, `target_date` and `lookup_date = target_date - 1` |
| `label` | `CAST(score >= t AS INT)`, with t = `float(tag decision_threshold of v)` |
| `model_version` | v (int) |
| `_scored_at` | One UTC timestamp taken once per run |

### Data quality rules

QR-16 to QR-20 come from DEFINE. The G-NN guards are design-level checks that turn a failure path
of an AC into an explicit stop.

| Rule | Object | Action (`warn` / `drop` / `fail`) | Source finding |
|---|---|---|---|
| QR-16 raw `time` parses as `yyyy-MM-dd HH:mm:ss` read as UTC (explicit offset) | `silver.weather_hourly` step | `fail` before write (0 rows committed) | F-16, F-20 |
| QR-17 one row per `weather_ts`, first ingested wins (ADR 0005 order plus raw-value tie-break); losers counted in the task output | `silver.weather_hourly` step | `drop` as deduplication (counted) | F-15 |
| QR-18 `temperature_c` parses as a number | `silver.weather_hourly` step | `fail` before write | F-14 (no null-like temperature) |
| QR-18 `temperature_c BETWEEN -30 AND 45` | `silver.weather_hourly` | `warn` (kept, counted) | A-18 |
| QR-19 label in (null, 0, 1); non-null exactly when T is complete and `baseline_day_count = N`; `is_eligible` exactly when `ineligibility_reasons` is empty | `ml.household_labels_daily` step | `fail` before write | D-19, D-27 |
| QR-20 `(household_id, target_date)` unique; `score BETWEEN 0 AND 1`; `label = 1` exactly when `score >= t` | `gold.consumption_spike_predictions` step | `fail` before write | D-23, D-31 |
| G-01 `scikit-learn == 1.3.0` and `databricks-feature-engineering == 0.18.2` in the task. Every PEAK_MODEL notebook task runs on the job environment `peak_model_env` with serverless `environment_version: "2"` (Python 3.11, scikit-learn 1.3.0 preinstalled), the environment spike 05 validated; without it the bundle jobs get a Python 3.12 environment where 1.3.0 has no wheel (build deviation D-19) | features, training and scoring notebooks; both job files | `fail` | ADR 0007 (serverless environment 2 keeps 1.3.0, the FE client is installed by `%pip`) |
| G-02 every training row has a feature row with `feature_date = target_date - 1` (anti-join count 0), and no looked-up `complete_day_share_28d` is null | training set | `fail` | ADR 0007 as-of semantics |
| G-03 every calendar month of the validation and test ranges has at least 1 eligible labelled row; checked before an MLflow run starts | training | `fail`, naming the empty months | F-29 |
| G-04 feature-table Delta version equal before and after the training set is materialised | training | `fail` | ADR 0011 (logged version must be exact) |
| G-05 git commit parameter is non-empty | training | `fail` | NFR-18 |
| G-06 for every target date T to score, the feature table has one row per `silver.households` household at T - 1, and the labels table has one row per `silver.households` household at T (`scoring.check_inputs`; without label rows, `replaceWhere` over T would delete T's earlier predictions and write nothing) | scoring | `fail` before write, naming the missing feature date(s) or the target date(s) without label rows | FR-28, AC-60, build deviation D-07 |
| G-07 alias `champion` resolves and its version has a parseable `decision_threshold` tag | scoring | `fail`, naming the alias or the tag | AC-61, ADR 0009 |
| G-08 the reloaded new version (`models:/<model>/<v>`) reproduces the in-memory test scores exactly; checked before the alias moves | training | `fail` (champion unchanged) | AC-54 |
| G-09 split ranges ordered and disjoint; thresholds in (0, 1] for shares; label threshold > 0; integer parameters >= 1; `baseline_day_count <= label_lookback_weeks` (otherwise N baseline days can never be found and nothing would be labelled); `target_date_end` only with `target_date` and not before it | parameters | `fail` | FR-31, AC-59, build deviation D-03 |
| G-10 output density: rows = households x dates and unique keys, for features and labels | features and labels steps | `fail` before write | AC-41 |
| G-11 validation split has at least one positive row | training | `fail` before any metric | ADR 0009 |
| G-12 the recomputed `silver.weather_hourly` has at least 1 row (`build_weather_silver` raises "`<bronze table>` is empty: upload the weather file and run ingest_weather"; otherwise the change-only MERGE would delete every Silver row) | `silver.weather_hourly` step (notebook) | fail before write | FR-19, AC-66, build deviation D-17 |

### MLflow run contents

| Kind | Content |
|---|---|
| Parameters | Every FR-31 training-side parameter: the six split bounds and `random_seed`. The label and eligibility parameters are read from the labels table properties at version VL, and the baseline parameters are cross-checked against the feature table properties (a mismatch fails the run). `model_class = HistGradientBoostingClassifier`, `random_state`, `early_stopping = False` and every other classifier argument (`get_params()`). `features_table`, `features_table_version`, `labels_table`, `labels_table_version`. `git_commit`. `threshold_rule`. Library versions (`scikit_learn`, `mlflow`, `databricks_feature_engineering`, `python`). `feature_columns`, `categorical_codes` |
| Metrics | `validation_threshold`, `validation_f1_at_t`, `champion_reload_max_abs_diff`, and per split (`validation`, `test`) the scheme below. No wall-clock or duration metric, so two runs on the same input log equal metrics (AC-49) |
| Artifacts | `training_set.parquet` (keys, split, features, label), `validation_scores.parquet` and `test_scores.parquet` (keys, label, score), `training_set_manifest.json` (per-split rows, positives, order-independent checksum, table names and versions) |
| Inputs | `mlflow.log_input` of the labels and features tables at their versions (context `training`) |
| Model | `fe.log_model(model = ConsumptionSpikeModel, artifact_path = "model", flavor = mlflow.pyfunc, training_set, registered_model_name, signature = infer_signature(X_test, test scores), code_paths)` |

```text
<split>_<metric>                         test_pr_auc, validation_precision_at_t
<split>_acorn_<group>_<metric>           test_acorn_affluent_recall_at_t   (group in lower case)
<split>_month_<yyyy>_<mm>_<metric>       validation_month_2013_09_flag_count_at_t
<split>_ratio_rule_pr_auc                reference only (D-30)
metric in: pr_auc (average precision), precision_at_t, recall_at_t, flag_count_at_t, row_count, positive_count
precision_at_t is 0.0 when no row is flagged; pr_auc is not logged for a segment with 0 positives
ratio rule score: total_energy_kwh_1d / median_energy_kwh_same_weekday_8w, with a null total scored 0
                  and a zero baseline replaced by 1e-6 (labelled rows always have a baseline)
```

### Resolution of the open design items

| ID | Decision | Rationale |
|---|---|---|
| OD-07 | The first task of the daily job is a `pipeline_task` on the existing `smart_meter_silver_gold` pipeline (`full_refresh: false`). `build_features`, `build_labels` and `score_predictions` depend on it. The schedule is 08:00 UTC (ingestion runs at 06:00 UTC), and the pipeline task has 1 retry after 600 s (ADR 0008) | The dependency is explicit and testable from the YAML (AC-62). The job is independent of the Kafka service, which empties on power-off (DA-11). An update with no new input is cheap, because unchanged MVs skip the refresh. `run_job_task` would couple the job to Kafka, and table-update triggers on MVs are not spiked |
| OD-08 | t is stored as the version tag `decision_threshold` = `repr(t)` (authoritative, read by scoring), and also as the run metric `validation_threshold`. Candidates are the distinct validation scores, F1 is compared exactly on integer counts, and the highest t wins a tie (ADR 0009) | One registry read in scoring. Exact float round trip. The tag round-trip was shown by spike 05. Among equal F1 values, the highest t flags the fewest households |
| OD-09 | Not persisted as a Delta table. Logged with the run as `training_set.parquet`, plus `mlflow.log_input` of the source tables with their versions and a manifest with per-split checksums (ADR 0011) | No extra catalog object per run. The exact training data stays with its run after the tables move on. AC-48 and the AC-55 rebuild check read the artifact |
| OD-10 | Native categorical support (`categorical_features` mask) for `acorn_group`, `tariff`, `target_weekday` and `target_month`, encoded by a fixed code map inside the pyfunc wrapper; unknown values become NaN. Numeric nulls stay NaN (native missing value support); no imputation or scaling | scikit-learn 1.3.0 needs integer-coded categories (string categories arrived later). A fixed map has nothing fitted on data, so there is no leakage and no fit state. Encoding inside the wrapper keeps `fe.score_batch` working on the raw feature table |
| OD-11 | Landing path `/Volumes/<catalog>/bronze/landing/weather/`. Bronze by Auto Loader `availableNow` in the job task `ingest_weather` (checkpoint `checkpoints/files_weather_hourly`), reusing `bronze.auto_loader_reader` and `bronze.run_available_now`. The Silver weather step is the job task `build_weather_silver`: a batch recompute from Bronze with a change-only MERGE | The A-02 pattern is proven by spike 01 and METER_INGESTION (each file processed once, AC-36). A job task keeps the rule "no pipeline added". About 21,000 rows recompute in seconds |
| OD-12 | A separate on-demand job `smart_meter_peak_model_training` with one task `train_model`, no schedule and `max_retries: 0` (ADR 0008). Each successful run registers one version and moves `champion` (D-36) | No training task exists in the scheduled job, so AC-62 holds literally, and a wrong parameter on a scheduled run can never register a model. The second job name is recorded in DEFINE D-35 and D-37 (U-01 resolved) |
| OD-13 | Variant 1A of D-32 (ADR 0007, Accepted): UC feature table with time-series column, `create_training_set` with `timestamp_lookup_key`, `fe.log_model`, `fe.score_batch`. The 1B fallback stays documented: `features.explicit_lookup` exists as the test oracle and as the fallback join | Spike 05 passed every A-12 check, with 0 differences from the explicit join |

### Assumption dependencies

DA numbers continue after METER_INGESTION (DA-01 to DA-12). None of these is a new spike. Each is
checked by the first live step of PR 2 (the *Gate after PR 2* in the *Delivery Plan*). A failure
applies the listed fallback through `/iterate`.

| Assumption | Decisions depending on it | Check | Fallback |
|---|---|---|---|
| DA-13 A `pipeline_task` in a second job can start an update of the bundle pipeline. When an update is already running, the request fails rather than queueing, and the retry after 600 s succeeds | OD-07 | First daily run; one run started while the ingestion job runs | Keep the schedule offset and accept the failed run (the next daily run retries). Concurrent use is documented in the runbook |
| DA-14 Job-level `parameters` reach notebook tasks as widgets, an empty default (`target_date`) is accepted, and `bundle run --params` overrides them | FR-31, AC-58, AC-59, AC-63 | `bundle validate`, first run, AC-63 run | Task `base_parameters` per task, with overrides through `--notebook-params` documented in the runbook |
| DA-15 A plain Delta MERGE (including `WHEN NOT MATCHED BY SOURCE THEN DELETE`) into a table created by `fe.create_table` keeps it usable by `create_training_set` and `score_batch` | ADR 0011, `build_features` | First `build_features` run, then training | `fe.write_table(df = changed rows, mode = "merge")` for upserts, plus a SQL `DELETE` for removed keys |
| DA-16 `fe.log_model` forwards `code_paths` to the pyfunc flavor, and `models:/...` loads the wrapper outside the training task | Model wrapper, AC-54 | G-08 in the first training run | `cloudpickle.register_pickle_by_value(model module)` before logging |
| DA-17 The bundle substitution `bundle.git.commit` resolves to the HEAD commit at deploy time | G-05, AC-54 | `bundle validate` output and the first training run | A bundle variable `git_commit` set with `--var` at deploy. This would add a variable, so `tests/test_bundle_config.py::test_ac28_layout_variables_match_sample_plan` and `Settings` would need an `/iterate` |
| DA-18 UC honours `delta.deletedFileRetentionDuration` and `delta.logRetentionDuration` of 90 days on the feature and label tables (including predictive optimisation, if enabled) | ADR 0011, AC-55 rebuild | `SHOW TBLPROPERTIES` after the first run | Reproduction from `training_set.parquet` only; the runbook documents the limit |

### Bundle and job layout

`databricks.yml` is not changed. The PEAK_MODEL parameters are job parameters, not bundle
variables, so the variable set stays equal to `Settings` (an existing METER_INGESTION test asserts
this).

```yaml
# resources/smart_meter_peak_model.job.yml (sketch)
resources:
  jobs:
    smart_meter_peak_model:
      name: smart_meter_peak_model
      max_concurrent_runs: 1
      timeout_seconds: 7200
      schedule: { quartz_cron_expression: "0 0 8 * * ?", timezone_id: UTC }
      email_notifications: { on_failure: ["${workspace.current_user.userName}"] }
      parameters:                       # FR-31, label and scoring side; values are strings
        - { name: label_threshold,      default: "1.3" }
        - { name: baseline_day_count,   default: "4" }
        - { name: label_lookback_weeks, default: "8" }
        - { name: coverage_min,         default: "0.80" }
        - { name: zero_share_max,       default: "0.90" }
        - { name: eligibility_months,   default: "3" }
        - { name: target_date,          default: "" }   # empty: latest complete Gold day + 1
        - { name: target_date_end,      default: "" }   # set for a backfill range
      tasks:
        - task_key: refresh_silver_gold
          pipeline_task: { pipeline_id: "${resources.pipelines.smart_meter_silver_gold.id}", full_refresh: false }
          timeout_seconds: 2700
          max_retries: 1
          min_retry_interval_millis: 600000
        - task_key: ingest_weather          # notebook, timeout 900, max_retries 1
        - task_key: build_weather_silver    # depends_on ingest_weather; timeout 900, max_retries 1
        - task_key: build_features          # depends_on refresh_silver_gold, build_weather_silver; timeout 1800, max_retries 1
        - task_key: build_labels            # depends_on refresh_silver_gold; timeout 1800, max_retries 1
        - task_key: score_predictions       # depends_on build_features, build_labels; timeout 1800, max_retries 1
      # every notebook task: base_parameters src_path (${workspace.file_path}/src) and the catalog
      # and schema names from ${var.*}; the model name is derived from Settings, not passed in

# resources/smart_meter_peak_model_training.job.yml (sketch)
resources:
  jobs:
    smart_meter_peak_model_training:
      name: smart_meter_peak_model_training
      max_concurrent_runs: 1
      timeout_seconds: 3600
      # no schedule: on demand only (D-36)
      email_notifications: { on_failure: ["${workspace.current_user.userName}"] }
      parameters:                       # FR-31, training side
        - { name: train_start,      default: "2012-07-29" }
        - { name: train_end,        default: "2013-07-31" }
        - { name: validation_start, default: "2013-08-01" }
        - { name: validation_end,   default: "2013-11-30" }
        - { name: test_start,       default: "2013-12-01" }
        - { name: test_end,         default: "2014-02-27" }
        - { name: random_seed,      default: "42" }
      tasks:
        - task_key: train_model
          timeout_seconds: 3000
          max_retries: 0
          notebook_task:
            notebook_path: ../notebooks/train_model.py
            base_parameters:
              src_path: ${workspace.file_path}/src
              catalog: ${var.catalog}
              ml_schema: ${var.ml_schema}
              experiment_path: /Users/${workspace.current_user.userName}/smart_meter_peak_model
              git_commit: ${bundle.git.commit}
```

Notebooks that use the ML libraries start with the pinned install and a Python restart. These are
`build_features`, `train_model` and `score_predictions`. A unit test keeps the pins equal to
`peak_config.PINNED_REQUIREMENTS`:

```text
# MAGIC %pip install --quiet databricks-feature-engineering==0.18.2 scikit-learn==1.3.0
dbutils.library.restartPython()
```

MLflow is not reinstalled; the preinstalled 3.17.2 is logged as a run parameter. Each notebook
declares its widgets in a `_widget_names` tuple, as the METER_INGESTION notebooks do, so the bundle
test can match job and task parameters to widgets.

**Concurrency.** The widest level of the daily job has 2 tasks, and the training job has 1. When
the ingestion job (at most 2 concurrent tasks) overlaps either job, at most 4 tasks run at once,
within the Free Edition limit of 5.

**Change-only MERGE (ADR 0011)**, generated by `delta_sync.merge_sql`:

```sql
MERGE INTO <target> AS t
USING <recomputed source view> AS s
ON t.k1 = s.k1 AND t.k2 = s.k2
WHEN MATCHED AND NOT (t.c1 <=> s.c1 AND t.c2 <=> s.c2 AND ...) THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
WHEN NOT MATCHED BY SOURCE THEN DELETE
```

The notebook reads `operationMetrics` (`numTargetRowsInserted`, `numTargetRowsUpdated`,
`numTargetRowsDeleted`) from `DESCRIBE HISTORY ... LIMIT 1` and returns them in its exit value.
A rerun with no new input reports 0 for all three (NFR-11).

For `silver.weather_hourly`, `build_weather_silver` stops before the MERGE when the recomputed
Silver has 0 rows (G-12, build deviation D-17): with an empty source, `WHEN NOT MATCHED BY SOURCE
THEN DELETE` would remove every Silver row.

---

## Key Decisions (ADRs)

| ADR | Title | Status |
|---|---|---|
| 0007 | PEAK_MODEL runtime and data assumptions (A-04, A-12, A-16, A-17; variant 1A) | Accepted |
| 0008 | PEAK_MODEL jobs: the daily job runs the shared Silver/Gold pipeline first, training runs in a separate on-demand job (OD-07, OD-11, OD-12) | Proposed |
| 0009 | Decision threshold stored as a model version tag, highest threshold wins ties (OD-08) | Proposed |
| 0010 | Next-day consumption spike label: strictly above 1.3 x the median of the last 4 complete same-weekday days within 8 weeks (D-19 and the label analysis, as the DEFINE Self-Review asks) | Proposed |
| 0011 | Dense ML tables written by change-only MERGE; training sets kept as run artifacts, not tables (OD-09) | Proposed |

---

## Delivery Plan

The feature ships as three pull requests, each at or below about 25 files. The BUILD_REPORT has one
file for the whole feature. It stays `In Progress` until PR 3 and records which PR delivered each
file and each AC's evidence.

| PR | Scope | Manifest entries | Files |
|---|---|---|---|
| PR 1 | Libraries, contracts, unit tests | 1 to 23 | 23 |
| PR 2 | Notebooks, bundle resources, configuration and ADR tests, local-data tests | 24 to 35 | 12 |
| PR 3 | Integration tests, reset script, runbook, documentation | 36 to 44 | 9 |

**Gate after PR 2, before PR 3.** After PR 2 is deployed to `dev`, run the bootstrap sequence of the
runbook: a partial daily run up to `build_labels`, one training run, then one full daily run. It
checks DA-13 to DA-18. If any of them fails, this DESIGN is updated through `/iterate` with the
listed fallback before PR 3, as METER_INGESTION did after its spikes.

---

## File Manifest

Ordered by dependency. `/build` executes this list top to bottom. Package path
`src/smart_meter_peak_prediction/` is abbreviated `pkg/`. Agents:
- `ml-data-engineer`: feature, label, training, registry and scoring code;
- `pipeline-builder`: weather ingestion, Delta helpers, table setup, the bundle and the reset script;
- `build-agent`: everything else.

Existing inputs, read and not modified:
- `pkg/config.py`, `pkg/bronze.py`, `pkg/metrics.py` (reused: `Settings`, `auto_loader_reader`,
  `run_available_now`, `table_checksum_sql`);
- `resources/smart_meter_ingestion.job.yml`, `resources/smart_meter_silver_gold.pipeline.yml`,
  `databricks.yml` (must stay identical; AC-62);
- `tests/support/harness.py` (local-data tests build Gold through it);
- `spikes/local/a17_peak_labels_eligibility.py` (oracle for the seed-42 figures; never imported by
  `src/` or `tests/`; its logic is re-implemented in `pkg/labels.py`).

| # | PR | File | Action | Purpose | Agent | Depends on |
|---|---|---|---|---|---|---|
| 1 | 1 | `pyproject.toml` | Update | Dev extra adds `scikit-learn>=1.3,<1.4`, `numpy<2`, `mlflow-skinny>=2.16,<4` and `pyarrow>=15,<22` (pyarrow 22 and later require NumPy 2, which scikit-learn 1.3 cannot import; build deviation D-01). Integration extra adds `mlflow-skinny` and `pyarrow>=15,<22`. Ruff per-file ignore `S608` for `pkg/delta_sync.py`, `pkg/features.py`, `pkg/labels.py` (SQL from validated settings) | build-agent | - |
| 2 | 1 | `pkg/peak_config.py` | Create | Table, Volume, checkpoint, model and experiment names; `PeakParameters` with FR-31 defaults, parsing from widgets and G-09 validation; split ranges and calendar months; `PINNED_REQUIREMENTS` and `check_versions()` (G-01) (AC-50, AC-63) | ml-data-engineer | 1 |
| 3 | 1 | `pkg/delta_sync.py` | Create | `merge_sql` (change-only, insert, delete by source), `replace_where_write`, `set_properties_sql`, `last_merge_metrics` (AC-57, AC-66) | pipeline-builder | 2 |
| 4 | 1 | `pkg/peak_setup.py` | Create | DDL for Bronze and Silver weather, labels and predictions (append-only Bronze, 90-day retention on labels); feature table schema; schema-exists precondition (AC-64) | pipeline-builder | 2 |
| 5 | 1 | `pkg/weather.py` | Create | Source schema, Bronze projection, Silver transform with QR-16, QR-17, QR-18 and counts, daily temperature with sorted fold (AC-36 to AC-39) | pipeline-builder | 2 |
| 6 | 1 | `pkg/features.py` | Create | Dense grid, `same_weekday_baseline`, feature columns, G-10 density check, `explicit_lookup` (AC-39 to AC-42, AC-48) | ml-data-engineer | 2, 5 |
| 7 | 1 | `pkg/labels.py` | Create | Label of T, eligibility window and reasons, QR-19, G-10, parameter table properties (AC-41, AC-43 to AC-47, AC-63) | ml-data-engineer | 6 |
| 8 | 1 | `pkg/model.py` | Create | `FEATURE_COLUMNS`, `CATEGORY_CODES`, `encode`, `build_classifier`, `ConsumptionSpikeModel` pyfunc wrapper; no pyspark import (AC-49, AC-54) | ml-data-engineer | 2 |
| 9 | 1 | `pkg/training.py` | Create | Splits, G-02, G-03, G-11, deterministic order, fit, `choose_threshold` (ADR 0009), evaluation and metric names, ratio rule, run parameters, `run_training(frame, params, tracker)` over a `Tracker` protocol (AC-48 to AC-53) | ml-data-engineer | 8 |
| 10 | 1 | `pkg/registry.py` | Create | FE and MLflow adapters: `ensure_feature_table`, `build_training_set`, `table_version`, `MlflowTracker` (`fe.log_model` with signature and `code_paths`, tag, G-08 reload check, alias), `resolve_champion` (G-07); FE imported inside functions (AC-54, AC-55, AC-61) | ml-data-engineer | 8, 9 |
| 11 | 1 | `pkg/scoring.py` | Create | `resolve_target_dates`, G-06 check, eligible set, `assemble_predictions`, QR-20, write through `delta_sync.replace_where_write` (AC-56 to AC-61) | ml-data-engineer | 3, 7, 10 |
| 12 | 1 | `docs/contracts/bronze_files_weather_hourly.yaml` | Create | `kind: table`, owner PEAK_MODEL, inline Bronze schema of DEFINE, `primary_key: [_source_file, time_raw]` (AC-64) | build-agent | 5 |
| 13 | 1 | `docs/contracts/silver_weather_hourly.yaml` | Create | Silver weather schema, QR-16 to QR-18 with actions (AC-64) | build-agent | 5 |
| 14 | 1 | `docs/contracts/ml_household_features_daily.yaml` | Create | Feature table schema (`complete_day_share_28d` and `temperature_hour_count_1d` not null), grain and density rule, time-series column, point-in-time rule (AC-64) | build-agent | 6 |
| 15 | 1 | `docs/contracts/ml_household_labels_daily.yaml` | Create | Label table schema with `ineligibility_reasons` as `array<string>`, QR-19 `fail`, parameter table properties (AC-64) | build-agent | 7 |
| 16 | 1 | `docs/contracts/gold_consumption_spike_predictions.yaml` | Create | Consumer-facing contract: schema of D-35, QR-20 `fail`, consumer demand-response team (D-21), freshness daily with no deadline (D-24) (AC-64) | build-agent | 11 |
| 17 | 1 | `tests/support/peak_builders.py` | Create | Builders for Gold daily and monthly rows, households, Bronze weather rows; fixtures of AC-42 (2 households x 70 days), AC-43 (six label cases, with T = threshold x baseline built with the same double arithmetic) and AC-45 (late starter, dead meter, 0.80 / 0.7999 coverage, 0.90 zero share) | build-agent | 5, 6, 7 |
| 18 | 1 | `tests/test_weather.py` | Create | AC-36 (projection), AC-37 (session time zone), AC-38, AC-39 (fixture day without weather) | pipeline-builder | 5, 17 |
| 19 | 1 | `tests/test_features.py` | Create | AC-39, AC-40, AC-41 (density), AC-42 | ml-data-engineer | 6, 17 |
| 20 | 1 | `tests/test_labels.py` | Create | AC-41, AC-43, AC-45, AC-46, AC-47 (reason invariants on fixtures) | ml-data-engineer | 7, 17 |
| 21 | 1 | `tests/test_training.py` | Create | AC-48 to AC-53 on fixtures with a fake tracker; AC-54 wrapper round trip through `mlflow.pyfunc` save and load in a temp folder | ml-data-engineer | 8, 9, 17 |
| 22 | 1 | `tests/test_scoring.py` | Create | AC-56 to AC-61 on local Spark with a fake scorer and a fake registry (writer not called on failure) | ml-data-engineer | 11, 17 |
| 23 | 1 | `tests/test_peak_tables.py` | Create | AC-64 (library schemas equal the five contracts, `_` rule), AC-66 (MERGE text: change condition covers every non-key column, delete by source), DDL properties | pipeline-builder | 3, 4, 12 to 16 |
| 24 | 2 | `notebooks/ingest_weather.py` | Create | Precondition, weather DDL, Auto Loader `availableNow` into Bronze, row count in the exit value (AC-36) | pipeline-builder | 4, 5 |
| 25 | 2 | `notebooks/build_weather_silver.py` | Create | Recompute Silver from Bronze, QR-16 to QR-18, change-only MERGE, counts and MERGE metrics in the exit value (AC-37, AC-38, AC-66) | pipeline-builder | 3, 5, 24 |
| 26 | 2 | `notebooks/build_features.py` | Create | Pinned `%pip`, G-01, `ensure_feature_table`, compute, G-10, MERGE, table properties (AC-39 to AC-41, AC-66) | ml-data-engineer | 3, 6, 10 |
| 27 | 2 | `notebooks/build_labels.py` | Create | Parameters from widgets (printed), compute, QR-19, G-10, MERGE, table properties (AC-44 to AC-47, AC-63, AC-66) | ml-data-engineer | 3, 4, 7 |
| 28 | 2 | `notebooks/score_predictions.py` | Create | Pinned `%pip`, G-01, `scoring.run` for the resolved dates, exit value with dates, rows, version and t (AC-56 to AC-61) | ml-data-engineer | 11 |
| 29 | 2 | `notebooks/train_model.py` | Create | Pinned `%pip`, G-01, G-05, versions VL and VF, training set, `training.run_training` with `MlflowTracker`, exit value with run id and version (AC-48 to AC-55) | ml-data-engineer | 9, 10 |
| 30 | 2 | `resources/smart_meter_peak_model.job.yml` | Create | Daily job of the layout above (AC-62, AC-63) | pipeline-builder | 24 to 28 |
| 31 | 2 | `resources/smart_meter_peak_model_training.job.yml` | Create | Training job of the layout above (AC-62) | pipeline-builder | 29 |
| 32 | 2 | `tests/test_peak_bundle.py` | Create | AC-62: task graph, width <= 5, pipeline task, schedule, no training task in the scheduled job, exactly one pipeline resource, METER_INGESTION files unchanged (SHA-256 pinned from tag `v0.1.0`, plus `git show` when the tag is present). AC-63: parameters reach widgets. Pins equal `PINNED_REQUIREMENTS`. UTC set and asserted. No try/except | pipeline-builder | 30, 31 |
| 33 | 2 | `tests/test_peak_model_adr.py` | Create | AC-67: ADR 0007 is Accepted, records a result for A-04, A-12 and A-16 and names variant 1A; `check_specs.run` reports 0 errors | build-agent | - |
| 34 | 2 | `tests/test_secrets_hygiene.py` | Update | Add `test_ac65_tracked_files_contain_no_databricks_token` (the existing `dapi` pattern over `git ls-files`, including the new notebooks and job files) | build-agent | 30, 31 |
| 35 | 2 | `tests/local_data/test_peak_seed42.py` | Create | Marker `local_data`: Gold built by the METER_INGESTION harness from `data/sample/seed42`, then `pkg/features.py` and `pkg/labels.py`; the raw weather file through `pkg/weather.py` in UTC and Europe/London (AC-37, AC-39, AC-41, AC-44, AC-47, AC-63; figures of ADR 0007) | ml-data-engineer | 5, 6, 7, 17 |
| 36 | 3 | `tests/integration/conftest.py` | Update | Fixtures for the two PEAK_MODEL jobs (by base name), `run_now` with job parameters and `only`, task output reader, MLflow client and artifact download, registry reads, evidence snapshots | build-agent | 30, 31 |
| 37 | 3 | `tests/integration/test_peak_data.py` | Create | AC-36, AC-37, AC-39, AC-40, AC-41, AC-44, AC-47, AC-63, AC-64, AC-66 | pipeline-builder | 36 |
| 38 | 3 | `tests/integration/test_peak_training.py` | Create | AC-48 to AC-55 | ml-data-engineer | 36 |
| 39 | 3 | `tests/integration/test_peak_scoring.py` | Create | AC-56 to AC-60 | ml-data-engineer | 36 |
| 40 | 3 | `tests/integration/test_peak_deployment.py` | Create | AC-62 through the Jobs and Pipelines APIs; run durations saved as evidence | pipeline-builder | 36 |
| 41 | 3 | `scripts/reset_peak_model_outputs.py` | Create | User-run, guarded reset for AC-66: drops `silver.weather_hourly`, `ml.household_features_daily` and `ml.household_labels_daily` only after `--confirm` and a row-count check. It never touches Bronze, the model or predictions, and prints no secret | pipeline-builder | 4 |
| 42 | 3 | `docs/runbooks/peak_model.md` | Create | Weather upload, deploy, bootstrap order, training, backfill, evidence order, reset (user-run), model cleanup order (aliases, then versions, then the model; ADR 0007), concurrency with the ingestion job | build-agent | 30, 31, 41 |
| 43 | 3 | `docs/spikes/README.md` | Update | Record rows for A-17 and spike 05 (ADR 0007) | build-agent | - |
| 44 | 3 | `README.md` | Update | PEAK_MODEL architecture summary, links to the runbook, contracts and ADRs 0007 to 0011 | build-agent | 42 |

---

## Test Strategy

Every acceptance criterion from DEFINE appears here. Levels:
- **Unit:** pytest with local Spark, scikit-learn and MLflow skinny; runs in CI.
- **Local data:** marker `local_data`; needs `data/sample/seed42` and `data/raw`.
- **Integration:** marker `integration`; runs against the deployed `dev` target.
- **Manual / evidence:** a scripted operator step from the runbook whose output goes into the build
  report.

Every test name contains its AC id (golden rule 3). Integration tests that need a before and an
after state store a snapshot in `out/evidence/` in a `*_before` test and compare it in the
`*_after` test. The runbook gives the order and keeps each pair back to back (METER_INGESTION
lesson). Checksums use `metrics.table_checksum_sql`. Independent recomputations in tests are
written in the test itself and do not call the library function under test.

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-36 | Unit | `tests/test_weather.py::test_ac36_bronze_projection_keeps_raw_columns_and_metadata` | The source-header read becomes the 12 `*_raw` string columns plus `_rescued_data`, `_source_file` and `_ingested_at`, all non-null where expected |
| AC-36 | Integration | `tests/integration/test_peak_data.py::test_ac36_bronze_weather_has_21165_rows_and_rerun_adds_none` | After the first run: 21,165 rows, 0 null `_source_file` or `_ingested_at`. A rerun of task `ingest_weather` alone adds 0 rows |
| AC-37 | Unit | `tests/test_weather.py::test_ac37_weather_ts_is_independent_of_session_time_zone` | The same Bronze fixture with rows on the four DST days is transformed under UTC and under Europe/London: identical `weather_ts`, 24 rows per DST day |
| AC-37 | Local data | `tests/local_data/test_peak_seed42.py::test_ac37_raw_weather_file_same_in_utc_and_london` | The raw file through `pkg/weather.py` in both zones: 21,165 rows, unique `weather_ts`, min 2011-11-01T00:00:00Z, max 2014-03-31T22:00:00Z, identical values, 24 rows on each DST day |
| AC-37 | Integration | `tests/integration/test_peak_data.py::test_ac37_silver_weather_range_uniqueness_and_dst_days` | The deployed table has the same count, range, uniqueness and DST-day counts |
| AC-38 | Unit | `tests/test_weather.py::test_ac38_unparseable_time_fails_before_write` | `2013-13-01 00:00:00` raises the QR-16 error; the fake writer is never called |
| AC-38 | Unit | `tests/test_weather.py::test_ac38_duplicate_time_keeps_earlier_ingested_and_counts_one` | The earlier `_ingested_at` row is kept; the duplicate count is 1. A same-batch tie resolves the same way under reversed input order |
| AC-38 | Unit | `tests/test_weather.py::test_ac38_temperature_50_is_kept_and_warn_count_is_one` | The 50.0 row is in the output and the QR-18 warn count is 1 |
| AC-39 | Unit | `tests/test_weather.py::test_ac39_day_without_weather_has_count_0_and_null_mean` | A fixture day without weather rows gives count 0 and a null mean in the feature row |
| AC-39 | Unit | `tests/test_features.py::test_ac39_mean_temperature_matches_recomputation_and_is_order_stable` | A pandas recomputation is within 1e-9, and two different input partitionings give bitwise-equal means |
| AC-39 | Local data | `tests/local_data/test_peak_seed42.py::test_ac39_seed42_temperature_hour_counts` | Every date from 2012-07-01 to 2014-02-28 has 24 hours, except 2013-09-09 and 2013-09-10 with 23 |
| AC-39 | Integration | `tests/integration/test_peak_data.py::test_ac39_feature_temperature_matches_silver_weather` | A SQL recomputation from `silver.weather_hourly` per UTC date: mean within 1e-9 and hour counts as above |
| AC-40 | Unit | `tests/test_features.py::test_ac40_features_match_independent_recomputation` | A pandas oracle written from *Feature definitions* on a fixture with incomplete and missing days: numeric features within 1e-9 with nulls in the same places; categorical features equal |
| AC-40 | Integration | `tests/integration/test_peak_data.py::test_ac40_every_feature_matches_sql_recomputation` | An independent SQL recomputation from Gold, `silver.households` and `silver.weather_hourly` gives 0 differing rows over 100% of `ml.household_features_daily` |
| AC-41 | Unit | `tests/test_features.py::test_ac41_feature_grid_is_dense_and_density_check_fails_on_gap` | One row per household and date with unique keys; G-10 raises when a row is removed |
| AC-41 | Unit | `tests/test_labels.py::test_ac41_label_grid_is_dense_with_target_date_plus_one` | Label keys equal the feature keys shifted by one day |
| AC-41 | Local data | `tests/local_data/test_peak_seed42.py::test_ac41_seed42_tables_have_36480_rows` | 60 x 608 rows in each table, unique keys, the date ranges of AC-41 |
| AC-41 | Integration | `tests/integration/test_peak_data.py::test_ac41_deployed_feature_and_label_keys_are_complete` | 36,480 rows each and unique keys; the anti-join with `silver.households` x dates is 0 in both directions |
| AC-42 | Unit | `tests/test_features.py::test_ac42_changing_data_from_t_leaves_earlier_features_and_training_rows_unchanged` | 2 households x 70 days. Gold from T, monthly rows of months ending on or after T, and weather from T 00:00Z are replaced. Rebuilt features with `feature_date <= T - 1`, labels before T, and the training rows of T (explicit lookup) are identical |
| AC-43 | Unit | `tests/test_labels.py::test_ac43_hand_computed_label_cases` | The six cases give 0, 1, null, null, null and the hand-computed baseline within 1e-9 for the skipped incomplete day; 0 cases differ |
| AC-44 | Local data | `tests/local_data/test_peak_seed42.py::test_ac44_seed42_label_counts` | 33,093 labelled rows, positive share between 14.5% and 14.7%, first 2012-07-29, last 2014-02-27, 0 QR-19 violations (the ADR 0007 figures) |
| AC-44 | Integration | `tests/integration/test_peak_data.py::test_ac44_deployed_label_counts_and_qr19` | The same figures on `ml.household_labels_daily`, and QR-19 as SQL gives 0 violations |
| AC-45 | Unit | `tests/test_labels.py::test_ac45_eligibility_fixture_cases` | Late starter, dead meter, coverage 0.80 and 0.7999, zero share 0.90, T = 2012-09-30 (`insufficient_history`, month count 2) and T = 2012-10-01 (eligible) as stated in AC-45, including coverage 78 / 92 for January 2013 |
| AC-46 | Unit | `tests/test_labels.py::test_ac46_appending_later_months_keeps_eligibility_up_to_month_start` | Eligibility computed with monthly rows up to M, then with rows for M + 1 and later added: `is_eligible`, reasons, coverage and zero share are unchanged for every T on or before the first day of M + 1 |
| AC-47 | Unit | `tests/test_labels.py::test_ac47_ineligible_rows_have_reasons_and_eligible_rows_none` | The reason invariants on the fixture set |
| AC-47 | Local data | `tests/local_data/test_peak_seed42.py::test_ac47_seed42_eligible_rows_per_split` | Train 16,969, validation 7,170, test 5,116 at 14.0%, 15.8% and 13.6% (within 0.1 pp); no eligible labelled T before 2012-10-01; last ineligible labelled T 2013-10-31 |
| AC-47 | Integration | `tests/integration/test_peak_data.py::test_ac47_deployed_eligible_rows_per_split` | The same figures on the deployed label table |
| AC-48 | Unit | `tests/test_training.py::test_ac48_splits_are_ordered_disjoint_and_equal_the_eligible_labelled_rows` | Split ranges, ordering, 0 extra and 0 missing rows; G-02 fails when a T - 1 feature row is missing; G-09 fails on overlapping ranges (`test_ac48_overlapping_or_unordered_ranges_fail_guard_g09` also covers a label threshold of 0 and a share above 1) |
| AC-48 | Integration | `tests/integration/test_peak_training.py::test_ac48_logged_training_set_equals_labels_and_features_at_t_minus_1` | `training_set.parquet` of the latest run: the split maxima and minima are ordered, every row is inside its range, the rows equal the eligible labelled rows at `labels_table_version`, and 100% of feature values equal `ml.household_features_daily VERSION AS OF features_table_version` at `target_date - 1` |
| AC-48 | Unit | `tests/test_training.py::test_ac48_training_set_lookup_uses_date_keys_the_spike_shape_and_guard_g04` | `registry.build_training_set` with a stand-in Feature Engineering client: `target_date` and `lookup_date` are DATE columns, the `FeatureLookup` and `create_training_set` arguments are the spike 05 shape, and G-04 raises when the feature table version changes between the two reads |
| AC-49 | Unit | `tests/test_training.py::test_ac49_two_fits_give_identical_scores_threshold_and_metrics` | Two `run_training` calls on the same fixture frame with a shuffled input order: test scores bitwise equal, equal t, equal metric dictionaries |
| AC-49 | Integration | `tests/integration/test_peak_training.py::test_ac49_two_training_runs_are_identical` | Two runs of the training job on unchanged tables: `test_scores.parquet` max absolute difference 0, equal `validation_threshold`, and every metric equal |
| AC-50 | Unit | `tests/test_training.py::test_ac50_run_parameters_cover_model_seed_and_fr31` | The parameter set holds `model_class`, `random_state`, `early_stopping = False` and every FR-31 parameter except the scoring-only `target_date` (D-38; U-02 resolved) |
| AC-50 | Integration | `tests/integration/test_peak_training.py::test_ac50_logged_parameters` | The same set, read from the MLflow run |
| AC-51 | Unit | `tests/test_training.py::test_ac51_threshold_is_max_f1_with_highest_t_on_ties` | A brute-force oracle over all candidate thresholds with exact fraction comparison. It covers a constructed tie and a single positive; F1 at t is within 1e-9 |
| AC-51 | Integration | `tests/integration/test_peak_training.py::test_ac51_version_tag_equals_recomputed_threshold` | t recomputed from `validation_scores.parquet` with the oracle equals `float(decision_threshold)` exactly; the logged `validation_f1_at_t` is within 1e-9 |
| AC-52 | Unit | `tests/test_training.py::test_ac52_metric_names_cover_segments_with_counts_and_no_accuracy` | On a fixture with 3 groups and validation and test months: every metric of the scheme exists with row and positive counts; the ratio-rule PR-AUC exists; no metric name contains `accuracy` |
| AC-52 | Integration | `tests/integration/test_peak_training.py::test_ac52_seed42_metrics_and_signal` | Overall, 3 ACORN groups, 4 validation months and 3 test months present with counts; `test_pr_auc` greater than the test positive share; `test_ratio_rule_pr_auc` logged; no `accuracy` metric |
| AC-53 | Unit | `tests/test_training.py::test_ac53_empty_validation_month_fails_before_any_metric_or_registration` | Fixture label rows with 0 eligible rows in 2013-09: the error names `2013-09`. The fake tracker records no metric, no logged model, no tag and no alias call, and the fake registry's `champion` is unchanged |
| AC-54 | Unit | `tests/test_training.py::test_ac54_pyfunc_wrapper_round_trip_reproduces_scores` | Save and load through `mlflow.pyfunc` in a temp folder with `code_paths`: identical probabilities. The signature covers `FEATURE_COLUMNS` |
| AC-54 | Integration | `tests/integration/test_peak_training.py::test_ac54_registered_version_alias_reload_and_run_records` | The newest version has a signature; `champion` points to it; `champion_reload_max_abs_diff` is 0; the run has `features_table`, `labels_table`, both versions and a 40-hex `git_commit` equal to the deployed commit |
| AC-55 | Integration | `tests/integration/test_peak_training.py::test_ac55_uc_lineage_lists_feature_table_upstream_of_model` | Variant 1A: the UC table-lineage API of `ml.household_features_daily` lists the model downstream (polled up to 300 s, as in spike 05), and the model's `feature_spec.yaml` names the table |
| AC-55 | Integration | `tests/integration/test_peak_training.py::test_ac55_logged_versions_rebuild_the_same_training_set` | The 1B check, kept as extra evidence: an explicit join at the logged versions gives the row count and checksum of `training_set_manifest.json` |
| AC-56 | Unit | `tests/test_scoring.py::test_ac56_predictions_cover_exactly_eligible_households_with_label_rule` | Fixture labels with eligible and ineligible households and a fake scorer: one row per eligible household; `label` equals `score >= t` at the tie value; `model_version` is the champion version; QR-20 fails on a duplicate and on a score of 1.2 |
| AC-56 | Integration | `tests/integration/test_peak_scoring.py::test_ac56_predictions_for_t_match_eligibility_threshold_and_model` | For the scored T: the rows equal the eligible households, `score` is in [0, 1], `label = 1` exactly when `score >= decision_threshold` of `model_version`, and `model_version` is the `champion` version. After the backfill, every prediction of a test-range T equals the logged `test_scores.parquet` of that version (max absolute difference 0), which ties the score to the model applied to the feature row dated T - 1 |
| AC-57 | Unit | `tests/test_scoring.py::test_ac57_reassembly_is_identical_except_scored_at` | Two assemblies for the same T and version are equal on every column except `_scored_at`; the replace predicate covers only the scored dates |
| AC-57 | Integration | `tests/integration/test_peak_scoring.py::test_ac57_before_rescore_snapshot` and `::test_ac57_after_rescore_only_scored_at_changes` | The second scoring run for T leaves the count and the checksum without `_scored_at` equal, `_scored_at` later, and the checksum (with `_scored_at`) of every other date unchanged |
| AC-58 | Unit | `tests/test_scoring.py::test_ac58_default_target_date_is_day_after_latest_complete_day` | Gold fixture whose latest complete day is 2014-02-27, with an incomplete 2014-02-28: the default T is 2014-02-28 and the feature date is 2014-02-27 |
| AC-58 | Integration | `tests/integration/test_peak_scoring.py::test_ac58_run_without_target_date_scores_2014_02_28` | A daily run with the empty default writes rows for 2014-02-28, and the task exit value names feature date 2014-02-27 |
| AC-59 | Unit | `tests/test_scoring.py::test_ac59_range_resolves_to_89_dates` | `target_date = 2013-12-01` and `target_date_end = 2014-02-27` give 89 dates; an end before the start fails G-09 (`PeakParameters` raises "target_date_end must not be before target_date") |
| AC-59 | Unit | `tests/test_scoring.py::test_ac59_target_date_end_without_target_date_is_rejected` | `PeakParameters(target_date_end=...)` without `target_date`, directly and through `from_mapping` with an empty `target_date`, raises the G-09 error "target_date_end needs target_date"; a single date and a one-day range are accepted |
| AC-59 | Integration | `tests/integration/test_peak_scoring.py::test_ac59_backfill_covers_test_range_and_rerun_changes_only_scored_at` | For each of the 89 dates, the row count equals the eligible households. The 5,116 eligible labelled test rows all have a prediction. A second backfill changes no column except `_scored_at` |
| AC-60 | Unit | `tests/test_scoring.py::test_ac60_missing_feature_date_fails_before_write` | Features up to 2014-02-28 and T = 2014-03-05: the error names 2014-03-04, and the writer is not called |
| AC-60 | Unit | `tests/test_scoring.py::test_ac60_a_household_missing_from_the_feature_date_fails_before_write` | One household lacks its feature row at T - 1: G-06 error names that feature date (2014-02-27), and the writer is not called |
| AC-60 | Unit | `tests/test_scoring.py::test_ac60_missing_label_rows_fail_before_write` | The labels table has no rows for T = 2014-02-28: the error names the labels table and 2014-02-28, and the writer is not called (D-07) |
| AC-60 | Integration | `tests/integration/test_peak_scoring.py::test_ac60_target_beyond_features_fails_and_writes_nothing` | A daily run with `target_date = 2014-03-05` ends failed, the task error names 2014-03-04, and the predictions checksum is unchanged |
| AC-61 | Unit | `tests/test_scoring.py::test_ac61_missing_champion_alias_fails_before_write` | A fake registry without `champion` (and one with `champion` but no `decision_threshold` tag): the error names the alias (or the tag), and the writer is not called. Not run live, because removing the alias from the shared model is destructive; the runbook notes that the bootstrap order makes the first scoring step fail the same way when no model exists yet |
| AC-62 | Unit | `tests/test_peak_bundle.py::test_ac62_daily_job_graph_schedule_and_pipeline_dependency` | Job `smart_meter_peak_model`: 6 tasks with the dependencies above; widest level 2 (<= 5); `score_predictions` reaches `refresh_silver_gold` through its dependencies; the `pipeline_task` names `smart_meter_silver_gold`; schedule present; serverless (no cluster keys) |
| AC-62 | Unit | `tests/test_peak_bundle.py::test_ac62_training_is_on_demand_only` | Job `smart_meter_peak_model_training` (D-37) is serverless, has no schedule or trigger and at most 5 concurrent tasks; no task of the daily job uses `train_model.py` |
| AC-62 | Unit | `tests/test_peak_bundle.py::test_ac62_bundle_has_exactly_one_pipeline_and_meter_ingestion_files_unchanged` | Exactly one `pipelines` entry across `resources/*.yml`. The SHA-256 of `resources/smart_meter_ingestion.job.yml` and `resources/smart_meter_silver_gold.pipeline.yml` equals the values pinned from tag `v0.1.0`, also compared with `git show v0.1.0:<file>` when the tag is available |
| AC-62 | Integration | `tests/integration/test_peak_deployment.py::test_ac62_deployed_jobs_pipeline_and_run_durations` | After `bundle validate` and `bundle deploy -t dev` (exit codes as evidence): both PEAK_MODEL jobs exist by base name with the YAML settings; exactly one pipeline with the bundle pipeline name; the deployed METER_INGESTION job and pipeline settings equal their YAML. The latest successful daily and training runs have no quota termination, and their durations are saved as evidence |
| AC-63 | Unit | `tests/test_peak_bundle.py::test_ac63_label_and_eligibility_parameters_are_job_parameters` | `label_threshold` and `coverage_min` are job parameters of the daily job, read as widgets by `build_labels.py` and passed to `PeakParameters` without code change |
| AC-63 | Unit | `tests/test_peak_tables.py::test_ac63_baseline_day_count_above_lookback_weeks_is_rejected` | `baseline_day_count` above `label_lookback_weeks` (default and widget path) raises the G-09 error "baseline_day_count must not exceed label_lookback_weeks"; equal values are accepted |
| AC-63 | Local data | `tests/local_data/test_peak_seed42.py::test_ac63_threshold_1_5_and_coverage_0_90` | Positive share 7.91% (within 1 pp of 7.9% and below the default); 29,100 eligible labelled rows, not above 29,255 |
| AC-63 | Integration | `tests/integration/test_peak_data.py::test_ac63_before_parameter_run_snapshot` and `::test_ac63_after_parameter_run_and_restore` | Task `build_labels` run with `label_threshold = 1.5` and `coverage_min = 0.90`: the positive share and eligible count are as above, the values appear in the task exit value and the table properties, and a rerun with the defaults restores the snapshot checksum |
| AC-64 | Unit | `tests/test_peak_tables.py::test_ac64_library_schemas_equal_contracts_and_underscore_rule` | The outputs of `weather.py`, `features.py`, `labels.py` and `scoring.py` equal the five contracts in names and types (in order); the label column is `label_consumption_spike`; `_ingested_at`, `_source_file`, `_rescued_data` and `_scored_at` carry the prefix |
| AC-64 | Integration | `tests/integration/test_peak_data.py::test_ac64_deployed_columns_match_contracts` | `information_schema.columns` equals the five contracts (`full_data_type`, lower case) |
| AC-65 | Unit | `tests/test_secrets_hygiene.py::test_ac65_tracked_files_contain_no_databricks_token` | No `dapi` followed by 32 hex characters in any tracked file |
| AC-65 | Manual / evidence | `pre-commit run --all-files` | All hooks pass, including `detect-private-key`; the output goes into the build report |
| AC-66 | Unit | `tests/test_peak_tables.py::test_ac66_merge_updates_only_changed_rows_and_deletes_missing_keys` | The generated MERGE compares every non-key column with `<=>` and has insert and delete-by-source clauses. Local recomputation of weather, features and labels from the same inputs with another partitioning is bitwise equal |
| AC-66 | Integration | `tests/integration/test_peak_data.py::test_ac66_before_rebuild_snapshot` and `::test_ac66_after_rerun_and_rebuild_checksums_equal` | Rerun of `build_weather_silver`, `build_features` and `build_labels`: MERGE metrics 0 inserted, 0 updated, 0 deleted, and the checksums are equal. After the user-run reset script and a rerun, the counts and checksums of the three tables equal the snapshot |
| AC-67 | Unit | `tests/test_peak_model_adr.py::test_ac67_adr_0007_accepted_with_spike_05_outcomes_and_variant` | ADR 0007 has status Accepted, a non-pending result for A-04, A-12 and A-16, and names variant 1A |
| AC-67 | Unit | `tests/test_peak_model_adr.py::test_ac67_check_specs_reports_no_errors` | `check_specs.run(root)` returns 0 errors |

---

## Operational Concerns

| Concern | Approach |
|---|---|
| Deployment | METER_INGESTION must be deployed and the catalog must exist (ADR 0003). There is no first-deploy problem of the DA-06 kind, because PEAK_MODEL adds only jobs. Steps: `databricks bundle validate -t dev`, then `databricks bundle deploy -t dev` from a clean working tree (the runbook checks `git status --porcelain` is empty, so the logged commit is the code that runs). Upload the weather file once: `databricks fs cp data/raw/weather_hourly_darksky.csv dbfs:/Volumes/smart_meter_dev/bronze/landing/weather/`. Bootstrap: `databricks bundle run -t dev smart_meter_peak_model --only refresh_silver_gold,ingest_weather,build_weather_silver,build_features,build_labels`, then `databricks bundle run -t dev smart_meter_peak_model_training`, then a full daily run. CI keeps running `bundle validate` only |
| Scheduling and retries | Daily job at 08:00 UTC (paused in development mode), `max_concurrent_runs: 1`, job timeout 7200 s. Retries: pipeline task 1 after 600 s (DA-13); weather, features, labels and scoring 1 each (all idempotent). Training job: no schedule, `max_retries: 0`, timeout 3000 s; a serverless automatic retry (DA-12) would register a second identical version, which is harmless (AC-49). Run training only when no daily run is active; G-04 fails a run whose feature table changes underneath it |
| Monitoring and alerting | Failure email to the deploying user on both jobs. Every notebook returns a JSON exit value: row counts, QR-17 and QR-18 counts, MERGE metrics, parameters, scored dates, model version and t. MLflow holds the metrics per training run, including per-month flag counts, so the seasonal drift of flag volume (F-28) is visible. Drift monitoring and SLA alerts stay out of scope (v0.3, D-24) |
| Secrets | None needed. PEAK_MODEL uses workspace identity only: no secret scope, no token in YAML, notebooks or code. Integration tests use the local CLI profile. AC-65 scans tracked files for Databricks tokens |
| Cost | Seed-42 volumes: 21,165 weather rows, 36,480 rows per ML table, about 29,000 training rows, single-node scikit-learn. Each notebook task pays a serverless start. The pipeline task usually skips unchanged MVs. Expected durations are minutes per run, recorded in the build report (NFR-14); the job timeouts stop runaway runs before the daily quota does. Revisit trigger: one step longer than 10 minutes (ADR 0011) |
| Backfill / reprocessing | Scoring backfill: `databricks bundle run -t dev smart_meter_peak_model --params target_date=2013-12-01,target_date_end=2014-02-27`; reruns change only `_scored_at`. Feature and label rebuild: every run recomputes from Gold and Bronze weather; a full rebuild is the user-run reset script followed by a daily run. Weather replay: Bronze is the replay source (ADR 0006); a new file lands under a new name. Model rebuild: rerun the training job. Older models are reproducible by time travel within 90 days, and from `training_set.parquet` afterwards. Parameter changes (for example AC-63) rewrite labels and require a retrain before the next scoring run is meaningful |
| Cleanup | Removing the registered model needs its aliases deleted, then its versions, then the model (ADR 0007). The runbook gives the order. Tables are dropped with the reset script; Bronze weather and its checkpoint are dropped only together (ADR 0006 pattern) |

---

## Risks & Trade-offs

| Risk or trade-off | Impact | Mitigation |
|---|---|---|
| The daily job and the ingestion job can both start the pipeline (ADR 0008) | A refused update fails a PEAK_MODEL run | Schedule offset, 1 retry after 600 s, `max_concurrent_runs: 1`; DA-13 checked at the PR 2 gate |
| PEAK_MODEL scores on whatever Bronze holds; it does not ingest readings | Freshness depends on the ingestion job having run | Accepted (D-24 sets no deadline); the runbook orders ingestion before the PEAK_MODEL run |
| Automatic promotion on every training run (D-36) | A worse model replaces `champion` with no gate beyond G-03, G-08 and AC-52 | User decision D-36; per-segment and ratio-rule metrics are logged for review; the challenger flow is v0.3 |
| Determinism depends on the platform library versions and the CPU count (spike 05 had 4 CPUs) | AC-49 could fail after a serverless image change | G-01 pins and checks versions, and both jobs pin serverless environment version 2 (D-19); sorted training input; versions logged per run; AC-49 runs live. Environment version 2 will be retired eventually: moving to version 3 (Python 3.12, scikit-learn 1.4.2, numpy 1.26) means re-pinning and rerunning spike 05 |
| Local scikit-learn 1.3.x (Python 3.12 has no 1.3.0 wheel) differs from the platform 1.3.0 | A unit test could pass locally and the platform behave differently | CI runs Python 3.11; unit tests assert logic, not platform score values; platform behaviour is covered by the integration tests |
| `numpy<2` in the dev extra to keep scikit-learn 1.3 importable | Local environment constraint | Matches the serverless stack; revisit with a scikit-learn upgrade (an ADR 0007 revisit trigger) |
| The as-of lookup would hide a missing feature row (ADR 0007) | Silent use of an older feature row | Dense table (G-10) plus G-02 and G-06 |
| Delta history retention may be shortened by platform maintenance (DA-18) | Time travel to an older run's versions fails | Training set and scores kept as run artifacts; retention set explicitly |
| The version tag holding t is mutable (ADR 0009) | A manual edit changes labels | Write access stays with the deploying user; the run metric is the audit copy |
| Full recompute per step | Cost grows with history | Small at v0.1; revisit trigger in ADR 0011 |
| Notebook-level failures are not caught (no try/except) | An error shows as a task failure with its stack trace | Same policy as METER_INGESTION (I-14). Library functions raise errors that name the cause (month, date, alias) |

---

## Open Items for the User and Needed `/iterate` Changes

None of these blocks `/build`. U-01 and U-02 are resolved (2026-10-21) by user decisions D-37 and D-38 in DEFINE.

| ID | Item | Recommendation |
|---|---|---|
| U-01 | **Resolved by D-37.** OD-12 adds a second job, `smart_meter_peak_model_training`, which was not in the D-35 name list, while FR-30 and AC-62 spoke of one job | The user chose the second on-demand job. DEFINE D-35, FR-30 and AC-62 now name both jobs; the daily job has no training task and the training job has no schedule |
| U-02 | **Resolved by D-38.** AC-50 asked a training run to log "every FR-31 parameter", and FR-31 includes the scoring-only `target_date` | The user decided that the training run logs every FR-31 parameter except `target_date`. DEFINE AC-50, FR-27 and FR-31 now say so; `target_date` is recorded in the scoring task output |
| U-03 | The QR-17 order (earliest `_ingested_at`, then smallest `_source_file`) does not decide between two rows with the same time from one file in one Auto Loader batch | The design adds the raw values as a final tie-break (deterministic, F-15 says no such rows exist). An optional `/iterate` of QR-17 records it |
| U-04 | `median_energy_kwh_same_weekday_8w` keeps "8w" in its name while `label_lookback_weeks` is a parameter | Keep the name for v0.1. A non-default lookback is recorded in the table properties; renaming is a contract version change |
| U-05 | ADRs 0008 to 0011 are `Proposed` | Review and accept them (in particular the tie rule of ADR 0009 and the second job of ADR 0008) |

---

## Self-Review

- **Weak points:**
  - DA-13 to DA-18 are platform assumptions that no spike has covered: the second job starting the
    pipeline, job parameters as widgets, MERGE into a FE table, `code_paths` through
    `fe.log_model`, `bundle.git.commit`, and retention. Each has a configuration-level fallback,
    and the PR 2 gate checks them before the integration tests are written.
  - AC-61 has unit evidence only, because a live check would remove the alias of the shared model.
  - AC-46 has unit evidence only. Its platform counterpart is the METER_INGESTION point-in-time
    rule (AC-24, verified live).
  - AC-56's "model applied to the feature row dated T - 1" is proven live only for test-range
    dates, by comparing with the logged test scores. For other dates the same code path is trusted.
  - The second job (D-37, U-01) and the `target_date` exception of AC-50 (D-38, U-02) are now
    user decisions in DEFINE; ADR 0008 is still `Proposed`.
  - The design pins scikit-learn 1.3.0 because the serverless image keeps it, not because it is
    the version the project would choose.
- **Risks:**
  - A Free Edition image change could break determinism or the FE client (ADR 0007 revisit trigger).
    G-01 turns that into a clear failure instead of silent drift.
  - Automatic promotion (D-36) can install a weak model.
  - The max-F1 threshold tuned on a 15.8% validation period will flag differently in a 13.6% test
    period (F-28).
  - 60 households make the per-month and per-group metrics noisy.
  - Integration tests depend on a completed METER_INGESTION replay, including the Kafka months
    (F-29). G-03 catches an empty month but not a partial one.
- **Trade-offs:**
  - Full recompute with change-only MERGE instead of incremental logic: simple to prove (AC-66),
    with cost that grows with history.
  - A training set kept as a run artifact instead of a table: fewer catalog objects, but not
    queryable with SQL.
  - A separate training job instead of a run mode: AC-62 holds literally and a scheduled run can
    never register a model, at the price of one more job name.
  - A pipeline task in PEAK_MODEL instead of a trigger: explicit and Kafka-independent, but
    readings are only as fresh as the last ingestion run.
  - Fixed categorical codes instead of a fitted encoder: nothing to fit, but a new ACORN group or
    tariff needs a code change.
- **What I would do differently:** With more budget or time, I would spike DA-13 to DA-16 in one
  throwaway job before `/build`, as ADR 0007 did for A-12, instead of checking them at the PR 2 gate.
  I would also replace the pipeline task with a table-update trigger on
  `gold.household_daily_consumption` once a spike shows that MV refreshes fire it. Then PEAK_MODEL
  would follow real ingestion, and two jobs would no longer start the pipeline. On a paid
  workspace, I would add a challenger alias and a promotion gate against the ratio rule.
- **Next improvement:** The user reviews ADRs
  0008 to 0011. Then `/build` PR 1 (manifest entries 1 to 23), and the PR 2 gate for DA-13 to DA-18.

---

## Change Log

| Date | Change | Why | Downstream impact |
|---|---|---|---|
| 2026-10-21 | Created from DEFINE_PEAK_MODEL.md (Ready for Design): architecture, data model, guards G-01 to G-11, OD-07 to OD-13 resolved, DA-13 to DA-18, job layout, 44-file manifest in three PRs, test strategy for AC-36 to AC-67; ADRs 0008 to 0011 drafted (Proposed). Status `Ready for Build` | Phase 2 of the SDD workflow | `/build` starts at manifest entry 1; DEFINE `/iterate` items U-01 and U-02 recommended, not blocking |
| 2026-10-21 | U-01 and U-02 marked resolved by DEFINE D-37 and D-38 (user decisions); OD-12 note, AC-50 unit test row, AC-62 training-job unit test row, Self-Review and Next improvement aligned with the new DEFINE wording of D-35, FR-30, AC-50, AC-62. Status stays `Ready for Build` | `/iterate` of DEFINE_PEAK_MODEL.md after the user answered U-01 and U-02 | No manifest change (entries 30, 31, 32 already cover both jobs). Test names unchanged; `test_ac62_training_is_on_demand_only` also asserts serverless and <= 5 tasks for the training job. ADR 0008 (Proposed) agrees with D-37; its user-review gap (U-05) remains |
| 2026-10-21 | G-09 extended: also rejects `baseline_day_count > label_lookback_weeks` and a `target_date_end` set without `target_date` or before it. G-06 extended: `scoring.check_inputs` also fails when the labels table lacks one row per household at a target date. Edited the guards table (G-06, G-09), the scoring library row in the architecture table, and the test strategy (AC-48 note, AC-59 unit row, two AC-60 unit rows for the existing tests). Status stays `Ready for Build` | Build deviations D-03 and D-07 of PR 1 (BUILD_REPORT_PEAK_MODEL.md), already implemented and merged; DESIGN brought in line with the code (user request) | No manifest change (entries 2, 11, 22 already cover the files). DEFINE not affected: AC-59 and AC-60 wording holds, the new checks are guards only. Test gap: no test yet for `baseline_day_count > label_lookback_weeks` or `target_date_end` without `target_date`; the PR 1 tests cover the end-before-start and missing-label cases only |
| 2026-10-21 | Test Strategy rows added by build PR 2 for the two G-09 cases left untested by the previous entry (`test_ac63_baseline_day_count_above_lookback_weeks_is_rejected`, `test_ac59_target_date_end_without_target_date_is_rejected`) and for `registry.build_training_set` (`test_ac48_training_set_lookup_uses_date_keys_the_spike_shape_and_guard_g04`) | PR 2 build (BUILD_REPORT_PEAK_MODEL.md, deviation D-12): the test gap named above is closed | No manifest change |
| 2026-10-21 | Manifest entry 1 and the integration extra read `pyarrow>=15,<22` (matches `pyproject.toml`; the unrelated `profile` extra keeps `pyarrow>=15`). Training-set section gains a "Label type" bullet: `select_training_rows` casts the label to int. New guard G-12 (empty recomputed Silver weather: fail before write) in the guards table, and a note under the change-only MERGE | Build deviations D-01 (PR 1), D-13 and D-17 (PR 2) of BUILD_REPORT_PEAK_MODEL.md, already implemented; DESIGN brought in line with the code (user request) | No manifest change (entries 1, 9, 25 already cover the files). DEFINE not affected: no AC contradicts the changes (AC-66 and FR-19 hold; G-12 is a guard only). Test gap: no test covers G-12, because the check lives in the notebook `notebooks/build_weather_silver.py`, which no unit test executes (`tests/test_peak_bundle.py` only checks its job wiring); no Test Strategy row added. D-13 needs no new row: the existing AC-48 training-set lookup test already asserts a `bigint` label in the lookup frame. Build report rows D-01, D-13, D-17 marked updated |
| 2026-10-21 | Both PEAK_MODEL jobs declare the job environment `peak_model_env` (serverless `environment_version: "2"`) and every notebook task uses it; G-01 and the determinism risk row updated; new unit test `tests/test_peak_bundle.py::test_g01_every_notebook_task_runs_on_serverless_environment_version_2` | PR 2 gate: the unpinned bundle jobs ran on Python 3.12, where `scikit-learn==1.3.0` has no wheel, so `%pip` in `build_features` failed (build deviation D-19). Spike 05 and one-off runs default to environment 2 (Python 3.11). User chose to pin environment 2 (2026-10-21) | Manifest entries 30 and 31 changed; METER_INGESTION files unchanged; the gate restarts at step 3 |

---

## Next Step

`/build .claude/sdd/features/DESIGN_PEAK_MODEL.md`
