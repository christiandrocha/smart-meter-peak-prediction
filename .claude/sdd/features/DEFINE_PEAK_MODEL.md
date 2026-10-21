# DEFINE: Peak Model

> Phase 1. Requirements that can be tested. No implementation choices here.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | PEAK_MODEL |
| **Date** | 2026-10-21 |
| **Author** | Christian |
| **Source** | `BRAINSTORM_PEAK_MODEL.md` (status Ready for Define), decisions D-05, D-16, D-19 to D-34 and findings F-14 to F-31; shipped `METER_INGESTION` (`.claude/sdd/archive/METER_INGESTION/`) and its contracts in `docs/contracts/` for the interface |
| **Status** | Ready for Design |

Allowed status values: `Draft`, `Ready for Design`.

Target release: v0.1, second of the two features of the end-to-end thin slice.

**User decisions taken in this phase:** Q-18 (object names and the predictions schema, including
`_scored_at` in place of the Q-08 wording `scored_at`) is decided as D-35, and Q-19 (training
cadence: on demand, each successful run moves `champion`) is decided as D-36. Both were confirmed
by the user on 2026-10-21.

**Hard gate before `/design` (separate from this document's status):** spike 05
(`spikes/databricks/05_spike_mlflow_uc.py`) must pass for A-04 (MLflow UC registry and alias),
A-12 (Feature Engineering on serverless) and A-16 (deterministic training), or the D-32 fallback
(plain Delta tables with an explicit join) must be chosen. Its outcome is recorded in an ADR
(FR-32, AC-67). A failed A-12 changes tasks 2, 4 and 5. It does not change any requirement here,
because every FR and AC below is written to hold under both variants.

**ID numbering.** Decision, finding, assumption and question IDs (D-, F-, A-, Q-) continue the
project-wide series of the brainstorms. FR, NFR, AC, constraint, quality-rule and design-question
IDs continue after `METER_INGESTION` (FR-01 to FR-17, NFR-01 to NFR-09, AC-01 to AC-35, C-01 to
C-07, QR-01 to QR-15, OD-01 to OD-06). This document therefore starts at FR-18, NFR-10, AC-36,
C-08, QR-16 and OD-07, so that test names that cite an AC (golden rule 3) stay unique in the
shared `tests/` folder. `METER_INGESTION` constraints C-01 to C-07 apply here under their original
IDs. Q-12 and Q-13 in this document mean the PEAK_MODEL brainstorm questions, not the
`METER_INGESTION` DEFINE items with the same IDs.

---

## Problem Statement

A demand-response team (hypothetical, D-21) wants a once-per-day list of the households likely to
consume well above their usual level on the next day. The governed daily consumption and the
monthly quality facts already exist (`METER_INGESTION`). What is missing is a reproducible ML data
path from those facts to a daily score. Without it, nobody can show that a prediction for day T
used only data available at the end of day T - 1, that the training households were chosen
without looking at the future, or which data and code produced a given model version. Without that
evidence the scores cannot be trusted or audited.

---

## Users & Stakeholders

| User or consumer | Need | How they consume the output |
|---|---|---|
| Demand-response team (hypothetical, D-21) | Once per day, a score and a yes/no flag per eligible household for the next day; ranking by score stays possible (D-23) | `gold.consumption_spike_predictions` (D-35), one `target_date` per daily run |
| ML or data platform operator | One-command deployment, idempotent daily runs, a training run that can be repeated and gives the same model, within Free Edition limits | Asset Bundle `dev` target, PEAK_MODEL job (D-33), MLflow experiment, UC model with alias `champion` |
| Reviewer or auditor | Trace a prediction to its model version, the version to its training run, and the run to the feature and label data and their versions; see why a household-date was not eligible | UC lineage (variant 1A) or MLflow-logged table names and Delta versions (fallback 1B); `ml.household_labels_daily` eligibility reasons |
| Later releases (v0.2, v0.3) | A feature table and a label table that can be extended without breaking the v0.1 model | `ml.household_features_daily`, `ml.household_labels_daily` |

---

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| Label follows D-19 exactly | Fixture cases that differ from a hand-computed expectation | 0 (AC-43) |
| No leakage from the target day | Feature or training-set values that change when data dated T or later is altered | 0 (AC-42) |
| Point-in-time eligibility | Eligibility decisions for T that change when readings after T are appended | 0 (AC-46) |
| Reproducible training | Max absolute difference of test scores between two training runs on the same input and seed | 0 (AC-49) |
| Model adds signal | Test PR-AUC compared with the test positive rate; ratio-rule PR-AUC logged next to it | PR-AUC > positive rate (AC-52) |
| Idempotent scoring | Columns other than `_scored_at` that change when scoring for the same `target_date` and model version is re-run | 0 (AC-57) |
| Shipped feature untouched | Differences in the `METER_INGESTION` job and pipeline definitions against tag `v0.1.0` | 0 (AC-62) |
| Auditable model | Registered versions whose run does not record the feature and label tables with versions, parameters and code commit | 0 (AC-54, AC-55) |

---

## Scope

**In scope:**
- Bronze and Silver hourly weather from `weather_hourly_darksky.csv`, parsed as UTC (D-25, F-20).
- A daily feature table, one row per household per feature date D, with the D-28 feature set and
  the mean temperature of D (D-25, D-32).
- A label and eligibility table, one row per household per target date T = D + 1, with the D-19
  label and the D-27 / D-34 point-in-time eligibility and its reasons.
- A point-in-time training set with temporal splits (D-29). One scikit-learn
  `HistGradientBoostingClassifier` with a fixed seed (D-30). Operating threshold at max F1 on
  validation (D-23). Evaluation overall, per ACORN group and per month, with the ratio-rule
  reference.
- Registration in Unity Catalog with alias `champion` and lineage to the training data (D-32).
- Batch scoring per `target_date` into a Gold predictions table, plus one backfill over the test
  range (D-31).
- A separate PEAK_MODEL job in the same Asset Bundle that runs after the Silver/Gold pipeline
  update (D-33).
- Spike 05 and an ADR with its outcome (A-04, A-12, A-16), and the choice of variant 1A or the
  1B fallback (D-32).

**Out of scope:**
- Ingestion, Silver readings, daily Gold and quality measurement, and any change to the
  `METER_INGESTION` job, pipeline or contracts (owned by `METER_INGESTION`; D-33).
- Bank-holiday ingestion and a holiday flag (D-26). v0.2, with a corrected calendar (F-24).
- Target-day weather as a forecast stand-in (Topic 3C). v0.2 as a labelled experiment, or never.
- `weather_daily_darksky.csv`, `daily_dataset`, `hhblock_dataset`, `acorn_details.csv` (not
  planned; F-21).
- Richer features (weather sensitivity, half-hourly shape, calendar effects) and point-in-time
  joins against an SCD Type 2 household dimension. v0.2.
- Comparison models, hyper-parameter search, the `challenger` alias flow, forecasting, rolling
  backtests, drift monitoring and retraining triggers. v0.3.
- Real-time serving and online features. v0.4, or documented only (Free Edition limits).
- Operating points tied to business numbers (minimum precision, daily capacity), and any scoring
  deadline or SLA monitoring (D-23, D-24). When a real consumer appears.

---

## Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-18 | The system shall ingest `weather_hourly_darksky.csv` from the landing Volume into `bronze.files_weather_hourly`. Every source column is kept as raw text under a snake_case name, plus `_rescued_data`, `_source_file` and `_ingested_at`, and each file is processed once. | Must |
| FR-19 | The system shall publish `silver.weather_hourly` with one row per UTC hour: `weather_ts` parsed from the raw `time` as UTC whatever the session time zone (A-07, F-20), and `temperature_c` parsed as a number. Rules QR-16 to QR-18 apply. The whole time range of the file is kept. | Must |
| FR-20 | The system shall publish the feature table `ml.household_features_daily` with exactly one row per household in `silver.households` per feature date D, from the study start (2012-07-01) to the latest `reading_date` in `gold.household_daily_consumption`. Every row holds the D-28 features and the D-25 temperature, as defined in *Feature definitions*, computed only from data dated D or earlier. Under variant 1A it is a UC feature table with primary key `(household_id, feature_date)` and time-series column `feature_date`. Under the 1B fallback it is a Delta table with the same unique key. | Must |
| FR-21 | The system shall publish `ml.household_labels_daily` (D-35) with exactly one row per household in `silver.households` per target date T = D + 1 for every feature date D of FR-20. It holds `label_consumption_spike` per D-19: 1 when the total consumption of T is strictly greater than 1.3 x the median total of the last 4 complete days with the weekday of T in the 8 weeks before T, otherwise 0, and null when T is not a complete day or fewer than 4 such days exist. | Must |
| FR-22 | The system shall decide, for every row of FR-21, whether the household is eligible on T (D-27, D-34, D-20). This uses only `gold.household_data_quality_monthly` rows of the 3 latest study months whose last day is before T. The household is eligible when all 3 months exist, their coverage (sum observed / sum expected) is >= 0.80 and their zero share (sum zero / sum observed) is < 0.90. Every ineligible row lists all its reasons from `insufficient_history`, `low_coverage` and `high_zero_share`. Eligible rows list none. | Must |
| FR-23 | The system shall build the training set from the FR-21 rows that are eligible and have a non-null label. Each row is assigned to train, validation or test by `target_date` only (D-29: train 2012-07-29 to 2013-07-31, validation 2013-08-01 to 2013-11-30, test 2013-12-01 to 2014-02-27, never shuffled) and joined to the feature row dated exactly T - 1. The join is a point-in-time lookup under variant 1A and an explicit join on `feature_date = target_date - 1` under the 1B fallback. | Must |
| FR-24 | The system shall train one scikit-learn `HistGradientBoostingClassifier` on the train split, with a fixed `random_state` and no internal random early-stopping split (D-30). | Must |
| FR-25 | The system shall choose the operating threshold t that maximises F1 on the validation split and store t with the registered model version, so that it can be read back from the registry for that version (D-23). | Must |
| FR-26 | The system shall evaluate the model on validation and test and log to the MLflow run: PR-AUC, and precision, recall and number of flags at t, overall, per ACORN group and per calendar month, each with its row and positive counts. It shall also log the PR-AUC of the ratio rule (total of D divided by the same-weekday baseline for D + 1) as a reference only, and log no accuracy metric. Before it logs metrics or registers a model, it shall stop with an error when any calendar month of the validation or test range has 0 eligible labelled rows (F-29). | Must |
| FR-27 | The system shall register the trained model in `smart_meter_dev.ml.consumption_spike_model` (D-35) with a signature, set alias `champion` to the new version, and record lineage from the version to its training run and data. Under variant 1A that is UC lineage to the feature table. Under the 1B fallback the run records the feature and label table names with their Delta versions. In both variants the run records all FR-31 parameters and the code commit. | Must |
| FR-28 | The system shall score households for one `target_date` T per run. T is a job parameter whose default is the day after the latest complete Gold day (the latest `reading_date` with at least one `is_complete_day = true` row). Scoring covers exactly the households eligible on T (FR-22), uses the features dated T - 1 and the model version behind alias `champion`, and replaces only the prediction rows of T. It shall support one backfill run over every T of the test range. | Must |
| FR-29 | The system shall write predictions to `gold.consumption_spike_predictions` (D-35) with columns `household_id`, `target_date`, `score` (probability of the positive class), `label` (`score >= t` of the model version used), `model_version` and `_scored_at` (D-35). | Must |
| FR-30 | The system shall deploy from the same Asset Bundle (`dev` target) a separate PEAK_MODEL job, `smart_meter_peak_model` (D-35). Its daily run ingests weather and refreshes features, labels and eligibility, then scores, and the scoring step runs only after a Silver/Gold pipeline update of `METER_INGESTION` (D-33). Training is not on the daily schedule; it runs on demand (D-36). The `METER_INGESTION` job and pipeline definitions are not changed, and no Lakeflow pipeline is added. | Must |
| FR-31 | The system shall expose as parameters, changeable without code changes: the label threshold (1.3), the baseline day count (4), the label lookback (8 weeks), the eligibility thresholds (0.80, 0.90), the eligibility window (3 months), the three split ranges, the random seed and `target_date`. | Must |
| FR-32 | The project shall record the outcome of spike 05 for A-04, A-12 and A-16, and the resulting variant (1A or 1B fallback, D-32), in an ADR before `/design` starts. | Must |

---

## Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-10 | Reproducibility | Two training runs on the same input, parameters and seed give identical test scores (max absolute difference 0) and the same t (AC-49). Rebuilding weather, features and labels from Bronze weather and the `METER_INGESTION` Gold tables gives identical contents (AC-66). |
| NFR-11 | Idempotency | Re-running weather ingestion, the feature step or the label step with no new input changes 0 rows. Re-running scoring for the same `target_date` and model version changes nothing except `_scored_at` and touches 0 rows of other target dates (AC-36, AC-57, AC-66). |
| NFR-12 | Point-in-time correctness | 0 feature values for target date T depend on data dated T or later (AC-42). 0 eligibility decisions for T depend on readings dated T or later (AC-46). Splits are disjoint and ordered by `target_date` (AC-48). |
| NFR-13 | Platform limits | Serverless only. No job allows more than 5 concurrent tasks. No Lakeflow pipeline is added and the `METER_INGESTION` pipeline and job definitions are unchanged. No model serving endpoint or online table (AC-62). |
| NFR-14 | Cost | On the seed-42 sample, one daily run and one training run each finish without a stop by the Free Edition daily quota, and their wall-clock durations are recorded in the build report (AC-62). D-24 sets no deadline. |
| NFR-15 | Security | 0 credentials or tokens in tracked files, bundle YAML or notebooks (AC-65). |
| NFR-16 | Time handling | All timestamps are UTC. Event-time columns (`weather_ts`, `feature_date`, `target_date`) and processing-time columns (`_ingested_at`, `_scored_at`) are separate, and every processing-time column starts with `_` (AC-37, AC-64). |
| NFR-17 | Recoverability | Weather, features, labels, model and predictions can be rebuilt from the repository, the raw weather file and the `METER_INGESTION` tables alone (AC-66, AC-49). |
| NFR-18 | Auditability | 100% of prediction rows name a registered model version, and 100% of registered versions record their training data, parameters and code commit (AC-54, AC-55, AC-56). |

---

## Data Contracts

Catalog `smart_meter_dev` (ADR 0003). Object names follow D-35. `ml.household_features_daily` comes from brainstorm Topic 1A. Contract files in
`docs/contracts/` are added in `/build` for every new table, following `_template.yaml`, following
D-35. The predictions table is consumer-facing, so its contract file is required. The rest
are owned by this feature and get one so that AC-64 can compare deployed schemas with them.

| Dataset / topic | Owner | Grain | Key | Freshness | Contract file |
|---|---|---|---|---|---|
| `gold.household_daily_consumption` (read) | METER_INGESTION | One row per household per UTC day with at least one reading | `(household_id, reading_date)` | Daily, <= 24 h | `docs/contracts/gold_household_daily_consumption.yaml` |
| `gold.household_data_quality_monthly` (read) | METER_INGESTION | One row per household per UTC study month, dense | `(household_id, reading_month)` | Daily, <= 24 h; a month row is final once the month is ingested | `docs/contracts/gold_household_data_quality_monthly.yaml` |
| `silver.households` (read) | METER_INGESTION | One row per sampled household | `household_id` | On file arrival | `docs/contracts/silver_households.yaml` |
| `gold.household_data_quality` (not read for eligibility or training) | METER_INGESTION | One row per household | `household_id` | Daily | `docs/contracts/gold_household_data_quality.yaml`; whole-period view, not point-in-time safe (A-15) |
| `weather_hourly_darksky.csv` (source file) | External (Kaggle, Dark Sky) | One row per hour, single location (London) | `time` | Static file | Profile `docs/profiling/weather_hourly_darksky.md` |
| `bronze.files_weather_hourly` (D-35) | PEAK_MODEL | One row per CSV line ingested | `(_source_file, time_raw)` | On file arrival | Inline; file in `/build` |
| `silver.weather_hourly` | PEAK_MODEL | One row per UTC hour present in the source | `weather_ts` | On file arrival, checked daily | Inline; file in `/build` |
| `ml.household_features_daily` | PEAK_MODEL | One row per household in `silver.households` per feature date D, dense from 2012-07-01 to the latest Gold `reading_date` | `(household_id, feature_date)`; time-series column `feature_date` under 1A | Daily, after the Silver/Gold pipeline update | Inline; file in `/build` |
| `ml.household_labels_daily` (D-35) | PEAK_MODEL | One row per household in `silver.households` per target date T = D + 1 | `(household_id, target_date)` | Daily, after the feature step | Inline; file in `/build` |
| Training set (per training run) | PEAK_MODEL | One row per eligible, labelled `(household_id, target_date)` in the three split ranges | `(household_id, target_date)` | Per training run (on demand, D-36) | Inline; whether it is persisted or only logged with the run is OD-09 |
| `smart_meter_dev.ml.consumption_spike_model` (D-35) | PEAK_MODEL | One registered version per successful training run | `(name, version)`; alias `champion` | Per training run | Inline |
| `gold.consumption_spike_predictions` (D-35) | PEAK_MODEL | One row per eligible household per `target_date` | `(household_id, target_date)` | Daily, one `target_date` per run; no deadline (D-24) | Inline; `docs/contracts/gold_consumption_spike_predictions.yaml` in `/build` (consumer-facing) |

### Inline schemas

Names follow `docs/conventions/naming.md`: aggregates are `<agg>_<measure>_<window>` and
processing-time columns start with `_`. All dates are UTC calendar dates.

| Table | Columns (type) |
|---|---|
| `bronze.files_weather_hourly` | `time_raw`, `temperature_raw`, `apparent_temperature_raw`, `dew_point_raw`, `humidity_raw`, `pressure_raw`, `visibility_raw`, `wind_bearing_raw`, `wind_speed_raw`, `precip_type_raw`, `icon_raw`, `summary_raw` (all string, as in the source), `_rescued_data` (string), `_source_file` (string), `_ingested_at` (timestamp) |
| `silver.weather_hourly` | `weather_ts` (timestamp, UTC, not null), `temperature_c` (double, not null), `_ingested_at` (timestamp) |
| `ml.household_features_daily` | `household_id` (string), `feature_date` (date), `total_energy_kwh_1d` (double, nullable), `max_energy_kwh_1d` (double, nullable), `avg_energy_kwh_7d` (double, nullable), `avg_energy_kwh_28d` (double, nullable), `median_energy_kwh_same_weekday_8w` (double, nullable), `complete_day_share_28d` (double, not null), `target_weekday` (int, 1 = Monday to 7 = Sunday), `target_month` (int, 1 to 12), `acorn_group` (string), `tariff` (string), `mean_temperature_c_1d` (double, nullable), `temperature_hour_count_1d` (int, not null) |
| `ml.household_labels_daily` | `household_id` (string), `target_date` (date), `feature_date` (date, = `target_date` - 1), `total_energy_kwh` (double, nullable; total of T), `baseline_energy_kwh` (double, nullable; D-19 baseline of T), `baseline_day_count` (int; complete same-weekday days found, 0 to 4), `label_consumption_spike` (int, nullable; 0 or 1), `eligibility_month_count` (int, 0 to 3), `coverage_ratio_3m` (double, nullable), `zero_share_3m` (double, nullable), `is_eligible` (boolean, not null), `ineligibility_reasons` (array of string, empty when eligible) |
| Training set | `household_id`, `target_date`, `split` (string: `train`, `validation`, `test`), the feature columns of `ml.household_features_daily` dated `target_date` - 1, `label_consumption_spike` (int, not null) |
| `smart_meter_dev.ml.consumption_spike_model` | MLflow model with signature over the feature columns; the threshold t is stored with each version (how: OD-08); alias `champion` |
| `gold.consumption_spike_predictions` | `household_id` (string, not null), `target_date` (date, not null), `score` (double, not null, 0 to 1), `label` (int, not null, 0 or 1), `model_version` (int, not null), `_scored_at` (timestamp, not null) |

### Feature definitions (D-28, D-25)

For a household and feature date D, predicting target date T = D + 1. "Complete day" means
`is_complete_day = true` in `gold.household_daily_consumption`. A day without a Gold row counts as
not complete.

| Feature | Definition |
|---|---|
| `total_energy_kwh_1d`, `max_energy_kwh_1d` | `total_energy_kwh` and `max_energy_kwh` of the Gold row of D, as stored (also when D is incomplete); null when D has no Gold row |
| `avg_energy_kwh_7d`, `avg_energy_kwh_28d` | Mean `total_energy_kwh` over the complete days among the 7 (28) days ending at D, D included; null when there are none |
| `median_energy_kwh_same_weekday_8w` | The D-19 baseline of T: median `total_energy_kwh` of the last 4 complete days with the weekday of T among T - 7, T - 14, ..., T - 56 (all on or before D); null when fewer than 4 exist |
| `complete_day_share_28d` | Number of complete days among the 28 days ending at D, divided by 28 |
| `target_weekday`, `target_month` | ISO weekday (1 = Monday) and month of T |
| `acorn_group`, `tariff` | From `silver.households` (static in v0.1) |
| `mean_temperature_c_1d`, `temperature_hour_count_1d` | Mean `temperature_c` over the rows of `silver.weather_hourly` with `weather_ts` in [D 00:00Z, D + 1 00:00Z), and the number of those rows; the mean is null when the count is 0 (F-22) |

### Quality rules (continuing the QR series of `METER_INGESTION`)

| ID | Layer and table | Rule | Action | Evidence |
|---|---|---|---|---|
| QR-16 | Silver `weather_hourly` | Raw `time` parses as a timestamp in `yyyy-MM-dd HH:mm:ss`, read as UTC | fail | F-16, F-20 |
| QR-17 | Silver `weather_hourly` | Deduplicate on `weather_ts`, first ingested wins (earliest `_ingested_at`, then smallest `_source_file`; ADR 0005 pattern); losers are counted | dedup (counted) | F-15 |
| QR-18 | Silver `weather_hourly` | `temperature_c` parses as a number and lies in [-30, 45] | fail when it does not parse; warn when out of range | F-14 (no null-like temperature), A-18 |
| QR-19 | `ml.household_labels_daily` | `label_consumption_spike` is null, 0 or 1. It is non-null only when T is complete and `baseline_day_count = 4`. `is_eligible` is true exactly when `ineligibility_reasons` is empty | fail | D-19, D-27 |
| QR-20 | `gold.consumption_spike_predictions` | `(household_id, target_date)` unique; `score` in [0, 1]; `label = 1` exactly when `score >= t` of `model_version` | fail | D-23, D-31 |

### Eligibility definitions (D-27, D-34, D-20)

- The window of T is the 3 latest study months (rows of `gold.household_data_quality_monthly`)
  whose last day is before T. For T = 2012-10-01 these are 2012-07 to 2012-09. For T = 2012-09-30
  only 2012-07 and 2012-08 qualify, so T has `insufficient_history`.
- `coverage_ratio_3m` = sum of `observed_readings` / sum of `expected_readings` over the window.
  `zero_share_3m` = sum of `zero_readings` / sum of `observed_readings`, null when the observed sum
  is 0.
- Reasons: `insufficient_history` (fewer than 3 months in the window). The monthly table is dense
  from 2012-07 for every household, so this applies only to T before 2012-10-01. A late starter's
  months before its first reading exist with `observed_readings = 0` and show up as
  `low_coverage`. Other reasons: `low_coverage`
  (`coverage_ratio_3m < 0.80`), `high_zero_share` (`zero_share_3m >= 0.90`, or null). When the
  history is insufficient, coverage and zero share are not evaluated and that is the only reason.
- The household set of features, labels and eligibility is `silver.households`. Orphan households
  (`has_household_record = false` in the monthly table) have no ACORN group or tariff and are not
  scored. Seed 42 has 0 orphans (METER_INGESTION AC-35).

### Added in this document

The column names above, the density rule (one row for every household and date, so that the
lookup for T always finds the row dated exactly T - 1 and never an older one), and the following
definitions are specified here. The brainstorm did not fix them:

- the averages use complete days only;
- `total_energy_kwh_1d` and `max_energy_kwh_1d` are taken as stored for incomplete days;
- the temperature hour count is a feature column;
- orphans are left out;
- the "latest complete Gold day" that sets the default `target_date` is defined in FR-28;
- the evaluation stops early when a month has no labels (FR-26, from the F-29 mitigation).

Each of these is open to change through `/iterate`.

---

## Acceptance Criteria

Seed-42 figures (AC-44, AC-47) were first computed by the brainstorm's scratch script (F-28, F-30)
and are reproduced by `spikes/local/a17_peak_labels_eligibility.py` from the definitions in this
document (A-17, validated 2026-10-21, ADR 0007). If it gives other numbers, the ACs change
through `/iterate`. They are not quietly corrected in `/build`.

| ID | Given | When | Then |
|---|---|---|---|
| AC-36 | `weather_hourly_darksky.csv` in the landing Volume and an empty `bronze.files_weather_hourly` | Weather ingestion runs, then runs again with no new file | After the first run the table has exactly 21,165 rows and 0 rows with null `_source_file` or `_ingested_at`; the second run adds 0 rows |
| AC-37 | `silver.weather_hourly` built from AC-36, and the same Bronze rows processed again with the Spark session time zone set to `Europe/London` | Both outputs are queried | Both have 21,165 rows, unique `weather_ts`, minimum 2011-11-01T00:00:00Z and maximum 2014-03-31T22:00:00Z, and identical `weather_ts` values; each of 2012-03-25, 2012-10-28, 2013-03-31 and 2013-10-27 has exactly 24 rows (F-20) |
| AC-38 | Fixture Bronze weather rows: one with `time` = `2013-13-01 00:00:00`, two rows with the same `time` and different `_ingested_at`, one with temperature `50.0` | The Silver weather step runs on each fixture | The unparseable time fails the step with 0 rows committed (QR-16); the duplicate pair leaves the earlier-ingested row and a duplicate count of 1 (QR-17); the 50.0 row is kept and the QR-18 warn count is 1 |
| AC-39 | `silver.weather_hourly` for seed 42, and a fixture day with no weather rows | `mean_temperature_c_1d` and `temperature_hour_count_1d` are recomputed independently | For every feature date from 2012-07-01 to 2014-02-28 the mean differs from the recomputation by <= 1e-9. The hour count is 24 on every day except 2013-09-09 and 2013-09-10, which have 23 each (F-22). The fixture day has count 0 and a null mean |
| AC-40 | `ml.household_features_daily` for seed 42 | Every feature column is recomputed independently from the Gold tables, `silver.households` and `silver.weather_hourly` using *Feature definitions* | For 100% of rows each numeric feature differs by <= 1e-9 (nulls in the same places), and `target_weekday`, `target_month`, `acorn_group` and `tariff` are equal |
| AC-41 | `ml.household_features_daily` and `ml.household_labels_daily` for seed 42 | Keys and counts are queried | Each table has exactly 60 x 608 = 36,480 rows and unique keys. Features cover every pair of a `silver.households` household with a date from 2012-07-01 to 2014-02-28, and labels the same households with T from 2012-07-02 to 2014-03-01. 0 pairs are missing |
| AC-42 | A fixture with 2 households over 70 days and a chosen target date T | All Gold rows with `reading_date >= T`, all monthly quality rows for months ending on or after T and all weather hours at or after T 00:00Z are replaced by different values, and features, labels for dates before T, and the training set are rebuilt | Every feature row with `feature_date <= T - 1` is identical to before, and the training-set rows of target date T have identical feature values (0 differences) |
| AC-43 | A hand-computed fixture with, for one household: T exactly 1.3 x its baseline; T at 1.3 x baseline + 0.001; an incomplete T; a T with only 3 complete same-weekday days in the 8 weeks; a T whose fourth complete same-weekday day lies 9 weeks back; a T whose baseline skips an incomplete same-weekday day | Labels are computed | Labels are 0, 1, null, null and null for the first five cases. The sixth uses the next older complete same-weekday day within the 8 weeks and matches the hand-computed baseline within 1e-9. 0 cases differ from the hand-computed table |
| AC-44 | `ml.household_labels_daily` for seed 42 | Labels are counted | 33,093 rows have a non-null label, with a positive share between 14.5% and 14.7%. The earliest labelled T is 2012-07-29 and the latest 2014-02-27. QR-19 reports 0 violations (F-28) |
| AC-45 | A fixture with: a late starter whose first reading is 2012-10-15; a dead meter (zero share 0.95 over its window); a household with window coverage exactly 0.80 and another with 0.7999; a household with window zero share exactly 0.90; and T = 2012-09-30 and T = 2012-10-01 for a full-history household | Eligibility is computed | Late starter: `insufficient_history` for T before 2012-10-01. `low_coverage` for T from 2012-10-01 to 2012-12-31, because the dense monthly table gives its months before 2012-10-15 `observed_readings = 0`. Eligible for T in 2013-01, with window 2012-10 to 2012-12 and coverage 78 / 92 days, about 0.848. Dead meter: `high_zero_share`. Coverage 0.80 is eligible and 0.7999 is `low_coverage`. Zero share 0.90 is `high_zero_share`. T = 2012-09-30 is `insufficient_history` with `eligibility_month_count = 2`, and T = 2012-10-01 is eligible |
| AC-46 | Eligibility computed from `gold.household_data_quality_monthly` built up to the end of month M | Readings dated in month M + 1 or later are appended, the `METER_INGESTION` pipeline runs and eligibility is recomputed | For every T on or before the first day of M + 1, `is_eligible`, `ineligibility_reasons`, `coverage_ratio_3m` and `zero_share_3m` are unchanged |
| AC-47 | `ml.household_labels_daily` for seed 42 with the default parameters | Eligible labelled rows are counted per split | Train has 16,969, validation 7,170 and test 5,116, with positive shares 14.0%, 15.8% and 13.6% (each within 0.1 pp). No eligible labelled row has `target_date` before 2012-10-01. The last ineligible labelled T is 2013-10-31. Every ineligible row has at least one reason and every eligible row none (F-30) |
| AC-48 | A training set built for seed 42 | Splits and joins are queried | Max train `target_date` < min validation `target_date` and max validation < min test. Every row lies inside its D-29 range. The set equals the eligible rows with non-null labels in the three ranges (0 extra, 0 missing). For 100% of rows the joined features equal the feature row with `feature_date = target_date - 1` |
| AC-49 | The same training set, parameters and seed | Training runs twice | Test scores of the two runs have a max absolute difference of 0, t is equal and every logged metric is equal |
| AC-50 | A completed training run | Its logged parameters are read | The run logs the model class `HistGradientBoostingClassifier`, the fixed `random_state` and `early_stopping = False`, and every FR-31 parameter with its value |
| AC-51 | A completed training run and its validation scores | t is recomputed independently as the score threshold that maximises F1 on validation | The stored t of the registered version equals the recomputation (tie rule from OD-08). The validation F1 at t logged in the run equals the recomputed F1 within 1e-9 |
| AC-52 | A completed training run on seed 42 | Its metrics are read | PR-AUC, precision, recall and flag count at t exist for overall, for each of the 3 ACORN groups and for each month of validation (4) and test (3), each with row and positive counts. Test PR-AUC is greater than the test positive share. The ratio-rule test PR-AUC is logged. No metric named like `accuracy` exists |
| AC-53 | A fixture label table where the validation month 2013-09 has 0 eligible labelled rows, and a model with an existing `champion` version | Training runs | The run ends failed and names the empty month. 0 new model versions are registered, and `champion` still points to the previous version |
| AC-54 | A completed training run | The registry and the run are read | A new version of `smart_meter_dev.ml.consumption_spike_model` exists with a signature. Alias `champion` points to it. `models:/smart_meter_dev.ml.consumption_spike_model@champion` loads and reproduces the logged test scores with a max absolute difference of 0. The run records the feature and label table names with their Delta versions and the git commit |
| AC-55 | The registered version from AC-54, under the variant chosen in the spike 05 ADR | Lineage is read (variant 1A: UC lineage for the model version; 1B: the run's logged table names and versions) | 1A: `ml.household_features_daily` appears upstream of the model version. 1B: reading the logged tables at the logged Delta versions rebuilds a training set with the same row count and content checksum as the run's |
| AC-56 | A `champion` version with threshold t, and a target date T with eligible households | Scoring runs for T | `gold.consumption_spike_predictions` has, for T, exactly one row per household eligible on T and 0 rows for others. `score` is in [0, 1]. `label = 1` exactly when `score >= t` for 100% of rows. `model_version` is the `champion` version. Every score equals the model applied to the feature row dated T - 1 (max absolute difference 0) |
| AC-57 | Predictions for T written by AC-56, and rows of other target dates present | Scoring runs again for T with the same `champion` version | Rows for T have the same count and the same content checksum over all columns except `_scored_at`, which is later. Rows of every other target date are unchanged (checksum including `_scored_at`) |
| AC-58 | Seed-42 Gold tables whose latest complete day is 2014-02-27 | Scoring runs without a `target_date` parameter | It scores `target_date` = 2014-02-28 using features dated 2014-02-27 |
| AC-59 | An empty predictions table and the `champion` version | The backfill runs over 2013-12-01 to 2014-02-27, then runs again | For each of the 89 target dates the row count equals the eligible households on that date. The 5,116 eligible labelled test rows of AC-47 all have a prediction. The second run changes no column except `_scored_at` |
| AC-60 | Gold data whose latest `reading_date` is 2014-02-28 | Scoring runs with `target_date` = 2014-03-05, whose feature date has no row | The run ends failed with a message naming the missing feature date, and 0 prediction rows are written or changed |
| AC-61 | A registered model without alias `champion` | Scoring runs | The run ends failed with a message naming the missing alias, and 0 prediction rows are written or changed |
| AC-62 | A workspace with the `dev` profile and the repository at the feature commit | `databricks bundle validate -t dev` then `databricks bundle deploy -t dev` run, and the deployed jobs are read | Both exit 0. Job `smart_meter_peak_model` exists, serverless, with no more than 5 concurrent tasks. Its scoring task depends, directly or through other tasks, on a step that runs or waits for the Silver/Gold pipeline update. No training task is on the daily schedule. The bundle deploys exactly the one Lakeflow pipeline it already deployed. The `METER_INGESTION` job and pipeline resource definitions are identical to tag `v0.1.0`. One daily run and one training run on seed 42 succeed without a quota stop, and their durations are recorded |
| AC-63 | Seed-42 inputs | The label step runs with label threshold 1.5 and the eligibility step with coverage threshold 0.90, set as job parameters with no code change | The positive share of labelled rows is below the default run's share and within 1 pp of 7.9% (label analysis at 1.5x). The count of eligible labelled rows is no higher than with the defaults. The parameter values appear in the run logs |
| AC-64 | The deployed tables and the contract files | Column names and types are listed from Unity Catalog | Every table and column in *Data Contracts* exists with that name and type. The label column is `label_consumption_spike`. Every processing-time or source-metadata column (`_ingested_at`, `_source_file`, `_rescued_data`, `_scored_at`) starts with `_` |
| AC-65 | The repository at the feature commit | `pre-commit run --all-files` and a scan of tracked files for Databricks tokens (`dapi` followed by hex) run | All hooks pass, including `detect-private-key`, and the scan finds 0 matches |
| AC-66 | Weather, features and labels built once | The weather Silver step, the feature step and the label step run again with no new input, then rebuild from Bronze weather and the `METER_INGESTION` tables after their outputs are dropped | Row counts and content checksums of `silver.weather_hourly`, `ml.household_features_daily` and `ml.household_labels_daily` are equal to the first build after each run |
| AC-67 | Spike 05 has run | `docs/adr/` is read | An Accepted ADR records the outcome of A-04, A-12 and A-16 with evidence, and the chosen variant (1A, or the 1B fallback of D-32). `scripts/check_specs.py` reports 0 errors |

### Traceability (FR to AC)

| FR | Covered by |
|---|---|
| FR-18 | AC-36, AC-66 |
| FR-19 | AC-37, AC-38, AC-66 |
| FR-20 | AC-39, AC-40, AC-41, AC-42, AC-66 |
| FR-21 | AC-41, AC-43, AC-44, AC-66 |
| FR-22 | AC-45, AC-46, AC-47 |
| FR-23 | AC-42, AC-48 |
| FR-24 | AC-49, AC-50 |
| FR-25 | AC-51, AC-56 |
| FR-26 | AC-52, AC-53 |
| FR-27 | AC-53, AC-54, AC-55 |
| FR-28 | AC-56, AC-57, AC-58, AC-59, AC-60, AC-61 |
| FR-29 | AC-56, AC-64 |
| FR-30 | AC-62 |
| FR-31 | AC-50, AC-63 |
| FR-32 | AC-67 |

Coverage of the required kinds: correctness AC-39, AC-40, AC-43, AC-44, AC-47, AC-51, AC-56;
idempotency and reprocessing AC-36, AC-57, AC-59, AC-66; data quality AC-38, AC-41, AC-44
(QR-19); point-in-time AC-42, AC-46, AC-48; failure paths AC-38, AC-53, AC-60, AC-61.

---

## Decisions and Open Items

### Decided by the user (carried from the brainstorm, not reopened)

| ID | Decision | Where it is used |
|---|---|---|
| D-05, D-16, D-19 | Binary next-day spike label: total of T strictly greater than 1.3 x the median of the last 4 complete same-weekday days within 8 weeks before T; no label otherwise; all three numbers are parameters | FR-21, FR-31, AC-43, AC-44 |
| D-20, D-27, D-34 | Eligibility per target date over the 3 complete months before T from the monthly table; coverage >= 0.80 and zero share < 0.90; strict window, no shorter fallback | FR-22, AC-45 to AC-47 |
| D-21 | Hypothetical demand-response team reading daily batch predictions | Users, FR-28 |
| D-22, D-33 | Separate PEAK_MODEL job in the same bundle, after the Silver/Gold pipeline update; `METER_INGESTION` unchanged | FR-30, AC-62 |
| D-23 | `label = score >= t`, t at max F1 on validation, stored with the model version; `score` always written | FR-25, FR-29, AC-51, AC-56 |
| D-24 | No deadline beyond running after the Gold refresh | NFR-14 |
| D-25 | Mean temperature of feature day D over UTC hours of the hourly file; PEAK_MODEL owns Bronze and Silver hourly weather | FR-18 to FR-20, AC-36 to AC-39 |
| D-26 | No holidays in v0.1 | Scope |
| D-28 | Feature set | FR-20, *Feature definitions* |
| D-29 | Splits train 2012-07-29 to 2013-07-31, validation 2013-08-01 to 2013-11-30, test 2013-12-01 to 2014-02-27, by `target_date`, parameters | FR-23, AC-48 |
| D-30 | `HistGradientBoostingClassifier`, fixed seed, no internal random early stopping; ratio rule as reference metric only | FR-24, FR-26, AC-49, AC-50, AC-52 |
| D-31 | Scoring per `target_date` (default: day after the latest complete Gold day), overwrite of that date only, one test-range backfill | FR-28, AC-56 to AC-59 |
| D-32 | UC feature table with point-in-time lookup in serverless job tasks; fallback plain Delta with explicit join if spike 05 fails A-12 | FR-20, FR-23, FR-27, AC-55, AC-67 |
| D-35 (Q-18, 2026-10-21) | Names: predictions `smart_meter_dev.gold.consumption_spike_predictions`, model `smart_meter_dev.ml.consumption_spike_model`, labels `ml.household_labels_daily`, weather `bronze.files_weather_hourly` and `silver.weather_hourly`, job `smart_meter_peak_model`. Predictions columns `household_id`, `target_date`, `score`, `label`, `model_version`, `_scored_at` (leading underscore for processing time, METER_INGESTION Q-13) | FR-21, FR-27, FR-29, FR-30, Data Contracts, AC-54, AC-56, AC-62, AC-64 |
| D-36 (Q-19, 2026-10-21) | Training runs on demand, not on the daily schedule; each successful training run registers one version and moves `champion` to it, with no challenger comparison in v0.1 | FR-27, FR-30, AC-53, AC-62 |

### Open questions for the user

None. Q-18 and Q-19 are decided as D-35 and D-36.

### Open questions for `/design`

| ID | Question |
|---|---|
| OD-07 | How the PEAK_MODEL job depends on the Silver/Gold pipeline update: a first task that triggers the existing pipeline, or a trigger that follows the `METER_INGESTION` job or the Gold table update (D-33 allows both) |
| OD-08 | Where t is stored with the version (version tag, logged parameter, or both), and the tie rule when several thresholds reach the same validation F1 |
| OD-09 | Whether the training set is persisted as a Delta table or only logged with the run (`mlflow.log_input`) |
| OD-10 | Encoding of `acorn_group`, `tariff`, `target_weekday` and `target_month` for the classifier (native categorical support or ordinal codes), and handling of null features |
| OD-11 | Weather file landing path and Bronze mechanism (incremental file ingestion or batch read), and where the Silver weather step runs, given that no pipeline is added |
| OD-12 | How on-demand training is started (separate job or a run-mode parameter of the PEAK_MODEL job), under D-36 |
| OD-13 | Variant 1A or 1B, from the spike 05 ADR (FR-32) |

---

## Constraints & Assumptions

| ID | Type | Statement | Validated? |
|---|---|---|---|
| C-01 to C-07 | Constraint | Inherited from `METER_INGESTION` unchanged: Free Edition serverless only; at most 5 concurrent job tasks, one active pipeline per type, daily quota; Kafka limits (not used here); no secrets in code; UTC end to end; raw data out of git; study period 2012-07-01 to 2014-02-28 with cutoff 2013-12-01 | Yes |
| C-08 | Constraint | The `METER_INGESTION` interface (`gold.household_daily_consumption`, `gold.household_data_quality_monthly`, `silver.households`) is read only; changes go through `/iterate` on both features; its job and pipeline are not modified (D-33) | Yes (user, 2026-10-20) |
| C-09 | Constraint | Single-node scikit-learn; no ML dependency beyond scikit-learn, MLflow and the Databricks Feature Engineering client | Yes (brainstorm constraints) |
| C-10 | Constraint | Batch only: no model serving endpoint and no online tables (Free Edition) | Yes (KB, verified 2026-10-06) |
| A-04 | Assumption | MLflow registers models in UC and resolves aliases on Free Edition serverless; a scikit-learn model with a signature loads by `models:/...@champion` | **Pending, spike 05 (hard gate before `/design`)** |
| A-07 | Assumption | Hourly weather timestamps are UTC | Validated 2026-10-20 on the file (F-20); kept true in Bronze by AC-37 |
| A-12 | Assumption | Feature Engineering in UC works on Free Edition serverless: client installs in the job environment, `create_table` with `timeseries_columns`, `create_training_set` with `timestamp_lookup_key`, `fe.log_model`, `fe.score_batch`, lineage graph from model to feature table | **Pending, spike 05 (hard gate before `/design`)**; failure selects the 1B fallback (D-32) |
| A-15 | Assumption | The monthly quality table supports a point-in-time window per target date | Validated 2026-10-20 (contracts, METER_INGESTION AC-24) |
| A-16 | Assumption | Training is deterministic on serverless: two runs on the same input and seed give identical scores | **Pending, spike 05 (hard gate before `/design`)**; then AC-49 |
| A-17 | Assumption | The seed-42 label and eligibility figures of F-28, F-30 and F-31 (33,093 labels; 16,969 / 7,170 / 5,116 eligible) are reproduced by a committed script | Validated 2026-10-21: `spikes/local/a17_peak_labels_eligibility.py` recomputes every AC-41, AC-44 and AC-47 figure from the written definitions; the AC-63 run gives 7.91% positive and 29,100 eligible labelled rows (default 29,255) (ADR 0007) |
| A-18 | Assumption | Dark Sky `temperature` is in degrees Celsius | Pending; the profile samples (9.46 to 10.24 on a November night in London) support it; QR-18 range counts confirm it in `/build` |

---

## Clarity Score

| Dimension | Score (0-3) | Note |
|---|---|---|
| Problem | 3 | Concrete consumer need and a concrete gap: point-in-time evidence and lineage from governed facts to a daily score |
| Users | 2 | The consumer is hypothetical (D-21) with no service-level expectations; operator and auditor needs are concrete |
| Scope | 3 | Boundary with `METER_INGESTION` fixed (C-08, D-33); every out-of-scope item has a release |
| Acceptance criteria | 2 | 32 numbered, measurable criteria covering every FR, with correctness, idempotency, data quality, point-in-time and failure paths. Not 3: the t tie rule waits on OD-08 |
| Constraints | 2 | Platform limits and fallbacks are documented, but three platform assumptions (A-04, A-12, A-16) wait on spike 05, which can change tasks 2, 4 and 5 |
| **Total** | **12/15** | Gate: 12 or more |

---

## Self-Review

- **Weak points:**
  - `_scored_at` (D-35) departs from the original Q-08 wording; the user confirmed it, but any
    consumer written against Q-08 must use the new name.
  - On-demand training with automatic promotion (D-36) means a bad run replaces `champion` with no
    gate beyond AC-52's weak bar and AC-53's empty-month check.
  - AC-44, AC-47 and AC-63 rest on one local recomputation (A-17, ADR 0007). It is independent of
    the scratch script but written by the same project, so `/build` tests on the platform remain the
    real check.
  - Several definitions were added here, not decided upstream (*Added in this document*):
    complete-days-only averages, as-stored values for an incomplete D, orphans left out, early stop
    on empty months. Each one is plausible, but none was confirmed by the user.
  - AC-52 requires test PR-AUC above the test positive share, a weak bar. A model that clears it can
    still be worse than the ratio rule. The comparison is logged, not gated.
  - AC-62's "identical to tag `v0.1.0`" assumes the tag holds the shipped definitions and no
    follow-up has changed them on `main` since.
- **Risks:**
  - Spike 05 may fail A-12 (FE on Free Edition) or A-16 (determinism on serverless). The first
    switches to the 1B fallback. The second would make AC-49 unachievable and needs `/iterate`.
  - The max-F1 threshold is tuned on validation months with a 15.8% positive share and applied to
    a 13.6% test period, so flag volume and precision at t will drift by month (F-28). AC-52 only
    makes that visible.
  - D-34 removes August and September 2012 from training (F-30, F-31); its effect on quality is
    unmeasured.
  - Test labels depend on the completed Kafka replay of `METER_INGESTION` (F-29). AC-53 guards the
    empty-month case but not a partially replayed month.
  - 60 households give noisy per-group and per-month metrics.
- **Trade-offs:**
  - Dense feature and label tables (one row per household and date, nulls allowed) cost more rows
    than sparse ones, but they make the point-in-time lookup exact and the eligibility reasons
    complete.
  - Requirements written to hold under both D-32 variants keep this document stable through
    spike 05, at the cost of an AC (AC-55) with two branches.
  - Taking incomplete-day totals as stored keeps the feature honest to Gold but lets partial days
    look like low-consumption days.
- **What I would do differently:** Commit the label and eligibility script before writing numeric
  ACs, as `METER_INGESTION` did with A-13, and settle object names during the brainstorm.
- **Next improvement:** Run spike 05 and record it in an ADR (AC-67). Record the label threshold choice and the label
  analysis table in an ADR, as the brainstorm risk table asks.

---

## Next Step

1. **Hard gate:** spike 05 (`spikes/databricks/05_spike_mlflow_uc.py`, A-04, A-12, A-16) passes or
   the D-32 fallback is chosen, recorded in ADR 0007 (FR-32).
2. `/design .claude/sdd/features/DEFINE_PEAK_MODEL.md`

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-10-21 | Created from `BRAINSTORM_PEAK_MODEL.md` (Ready for Define): FR-18 to FR-32, NFR-10 to NFR-18, AC-36 to AC-67, QR-16 to QR-20, C-08 to C-10, A-17, A-18, Q-19 and OD-07 to OD-13 added; Q-18 answered with a proposal pending the user's confirmation. Status `Draft` | Phase 1 of the SDD workflow | `/design` blocked until Q-18 and Q-19 are confirmed and spike 05 passes or the fallback is chosen |
| 2026-10-21 | Q-18 and Q-19 decided by the user as D-35 and D-36 (proposals accepted unchanged, including `_scored_at`); proposal markers removed; status `Ready for Design` | User confirmation | None on requirements; `/design` still gated on A-17 and spike 05 |
| 2026-10-21 | A-17 Validated; AC intro, Self-Review and Next Step updated | Local spike `spikes/local/a17_peak_labels_eligibility.py` reproduces the AC-41, AC-44, AC-47 and AC-63 figures (ADR 0007) | None; AC figures unchanged |
