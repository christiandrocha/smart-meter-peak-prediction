# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: SemVer.
Entries are added by `/ship`.

## [Unreleased]

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
