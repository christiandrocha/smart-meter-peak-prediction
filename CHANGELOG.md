# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: SemVer.
Entries are added by `/ship`.

## [Unreleased]

## [0.2.0] - 2026-10-22

### Added

- PEAK_MODEL: a daily job predicts, for each eligible household, whether the next day's consumption
  is a spike (strictly above 1.3 times the median of the last four complete same-weekday days within
  eight weeks, ADR 0010). It writes `gold.consumption_spike_predictions` for the target date; the
  default target is the day after the latest complete day (2014-02-28 on the seed-42 sample).
- Weather ingestion from a Unity Catalog Volume into `bronze.files_weather_hourly` and
  `silver.weather_hourly`, with a change-only MERGE and a guard against an empty source.
- ML tables `ml.household_features_daily` and `ml.household_labels_daily`: dense per household and
  date, point-in-time (features as of the day before the target), with the parameters recorded as
  table properties (ADR 0011).
- On-demand training job `smart_meter_peak_model_training`: a gradient boosting model logged to MLflow
  with Unity Catalog feature lookups, registered as `smart_meter_dev.ml.consumption_spike_model`.
  Promotion uses the `champion` alias; the decision threshold is a version tag (ADR 0009).
- Daily job `smart_meter_peak_model` (08:00 UTC) that runs the shared Silver and Gold pipeline first.
- Operations runbook `docs/runbooks/peak_model.md` and a guarded, user-run reset script
  `scripts/reset_peak_model_outputs.py`.
- Data contracts for the five PEAK_MODEL tables in `docs/contracts/` and ADRs 0007 to 0011.

### Changed

- Contract header comments and the PEAK_MODEL runbook point to the archived design documents under
  `.claude/sdd/archive/`. No schema changed.

### Known limits

- The peak job and the ingestion job share one pipeline. An update requested while the other one
  runs is refused and the task ends `INTERNAL_ERROR`, which the job does not retry; the next daily
  run is the retry (runbook, Concurrency).
- Training runs on demand only, without retries. Retry-sensitive steps depend on the idempotent
  writes and on the alias, not on single-attempt execution.

## [0.1.0] - 2026-10-20

### Added

- Meter ingestion (METER_INGESTION): a deterministic 60-household seed-42 sample and a replay
  producer that publishes post-cutoff readings to the Aiven Kafka topic `meter-readings`.
- Bronze ingestion of historical CSV files (Auto Loader, `availableNow`) and of the Kafka topic
  (raw payload with topic, partition and offset). Both are idempotent and do not advance on failure.
- Silver tables `meter_readings`, `meter_readings_quarantine`, `meter_readings_evaluated` and
  `households`: first-ingested-wins deduplication, rule-based quarantine, and table-total rule
  counts. A replay of the stream leaves Silver unchanged; a full refresh from Bronze reproduces
  identical Silver and Gold contents.
- Gold tables `household_daily_consumption`, `household_data_quality_monthly` and the
  `household_data_quality` view, the input contract for PEAK_MODEL.
- Asset Bundle for the `dev` target: daily job `smart_meter_ingestion` and the Lakeflow pipeline
  `smart_meter_silver_gold` (serverless, Unity Catalog `smart_meter_dev`).
- Data contracts for the topic and every published table in `docs/contracts/`, and 33 integration
  tests (`pytest -m integration`) that check 25 acceptance criteria against the workspace.
- Operations runbook `docs/runbooks/meter_ingestion.md` (deploy, evidence order, outage and reset
  procedures) and ADRs 0001 to 0006.

### Known limits

- Live verification ran on Databricks Free Edition with Aiven free-tier Kafka. AC-28 (a first deploy
  on a fresh workspace) is partial; the exit codes of that run are not recorded.
- Powering off the Aiven free service empties the topic; recovery needs a Kafka reset (runbook).
- The four pull requests (#1 to #4) are stacked and not merged at the time of this entry.
