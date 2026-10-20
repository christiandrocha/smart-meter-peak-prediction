# Smart Meter Peak Prediction

Household-level consumption peak prediction on a Databricks lakehouse, with streaming ingestion and governed ML features

## Problem

Predicting when a household reaches its consumption peak needs clean, complete, point-in-time
correct half-hourly readings. Raw smart meter data arrives from two sources (historical files and a
stream), with malformed timestamps, non-numeric values, gaps, daylight saving artefacts and
duplicates. Without a governed ingestion layer, every model would have to rediscover and re-fix
these problems, and no result could be reproduced.

The first feature, **METER_INGESTION**, provides that layer for a 60-household sample of the London
smart meter data set: Bronze, Silver and Gold tables with data contracts, quality rules with a
quarantine, and per-household data quality facts. The follow-up feature, PEAK_MODEL, reads these
tables to build features and train models.

## Architecture

```text
[London smart meter data (Kaggle) — 60 households — 1,679,974 half-hourly readings]
                                │
                                ▼
                scripts/prepare_sample.py (seed 42)
                Study period 2012-07-01 → 2014-02-28 (UTC)
                Cutoff 2013-12-01T00:00:00Z
                                │
               ┌────────────────┴────────────────┐
               ▼                                 ▼
     Historical files                   Stream file
     1,432,405 readings                 247,569 readings
     17 monthly CSVs + households       readings_stream.csv
               │                                 │
               ▼                                 ▼
     Unity Catalog Volume landing       Replay producer (Docker)
     databricks fs cp                   Keyed by household_id, event-time order
               │                                 │
               │                                 ▼
               │                        Aiven Kafka — topic meter-readings
               │                        2 partitions, SASL_SSL (SCRAM)
               │                                 │
               ▼                                 ▼
     Auto Loader                        Structured Streaming (Kafka source)
     trigger(availableNow=True)         trigger(availableNow=True)
               │                                 │
               └────────────────┬────────────────┘
                                ▼
                Bronze — append-only Delta (3 tables)
                Raw payload + source metadata (file / topic, partition, offset)
                Bronze, not Kafka, is the replay source
                                │
                                ▼
                Lakeflow pipeline smart_meter_silver_gold
                Triggered, serverless, recomputed from Bronze
                Rules from rules.py as expectations
                                │
                     ┌──────────┼──────────┐
                     ▼          ▼          ▼
                  Silver   Quarantine     Gold
               (3 tables)   (1 table)  (3 tables)
                                │
                                ▼
                PEAK_MODEL (next feature) reads Gold and silver.households
```

- **Two ingestion paths, one cutoff.** Readings before `2013-12-01T00:00:00Z` come from files,
  later ones from Kafka. Both land in Bronze with their source metadata. Bronze, not Kafka, is the
  replay source.
- **Quality rules with a quarantine.** Rules are defined once (`rules.py`). Rows that fail a drop
  rule go to `silver.meter_readings_quarantine` with the failed rule ids. Duplicates are resolved
  first-ingested-wins. Rule counts are table totals computed from `silver.meter_readings_evaluated`.
- **Gold facts, no labels.** Daily consumption per household and a dense household-by-month quality
  table with coverage, zero readings and gaps. Thresholds and labels belong to PEAK_MODEL.
- **Contracts.** Every published table and the Kafka topic has a contract in `docs/contracts/`.
- **Idempotent and UTC.** Re-running with the same input gives the same output; all times are UTC,
  and event time (`reading_ts`) is kept apart from processing time (`_ingested_at`).
- **Deployment.** A Databricks Asset Bundle (`databricks.yml`, `resources/`) deploys a daily job
  (`setup_catalog`, `ingest_files`, `ingest_kafka`, `refresh_silver_gold`) and the pipeline to a
  `dev` target on Databricks Free Edition.

Specifications: active features in [`.claude/sdd/features/`](.claude/sdd/features); shipped
features (brainstorm, define, design, build report and the ship record) in
[`.claude/sdd/archive/`](.claude/sdd/archive), for example
[`METER_INGESTION`](.claude/sdd/archive/METER_INGESTION). Decisions:
[`docs/adr/`](docs/adr/README.md).

## Getting started

Local development (unit tests run on local Spark and need Java 17):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
cp .env.example .env   # fill in locally; never commit
pytest
```

Generate the sample (needs the Kaggle raw files in `data/raw`, which git ignores):

```bash
pip install -e ".[sample]"
python scripts/prepare_sample.py build --out data/sample/seed42
```

Deploy, load and verify on Databricks: follow the
[runbook](docs/runbooks/meter_ingestion.md). In short:

```bash
databricks bundle validate -t dev -p dev
databricks bundle deploy -t dev -p dev      # first time: deploy, run setup_catalog, deploy again
databricks bundle run -t dev -p dev smart_meter_ingestion
```

The integration tests target the deployed environment, carry the `integration` marker and are
excluded from the default run and from CI. Some are before/after pairs that need a real operation
in between, so run them per step as listed in the runbook ("Evidence order"):

```bash
pip install -e ".[dev,integration]"
pytest -m integration tests/integration/<file>::<test>
```

## Repository layout

| Path | Content |
|---|---|
| `src/smart_meter_peak_prediction/` | Library: sampling, producer, settings, rule catalog, Bronze, Silver, Gold, metrics (tested) |
| `pipelines/` | Lakeflow pipeline sources (Python wiring, SQL summary view) |
| `notebooks/` | Job notebooks: catalog setup, file ingestion, Kafka ingestion |
| `resources/`, `databricks.yml` | Asset Bundle: job, pipeline, variables, targets |
| `docker/producer/` | Replay producer image |
| `config/` | Sample plan, pinned household selection and reference manifest |
| `tests/` | Unit tests, `tests/local_data` (needs raw data), `tests/integration` (needs a deployed workspace) |
| `docs/contracts/` | Data contracts of the tables and the Kafka topic |
| `docs/runbooks/` | Operations runbook |
| `.claude/sdd/` | Feature specifications (brainstorm, define, design, build) |
| `docs/adr/` | Architecture decision records |
| `docs/profiling/` | Data profiles of the sources |
| `spikes/` | Feasibility checks; not part of the product |

## Design decisions

See [`docs/adr/`](docs/adr/README.md).

## Known limitations & roadmap

- Silver and Gold are recomputed in full on every update. This is fine at about 1.7 M rows; the
  revisit trigger (an update over 15 minutes, or Bronze over 50 M rows) is recorded in ADR 0005.
- The Kafka service is a free tier that powers off when idle, and the pipeline refresh waits for the
  Kafka task. An Aiven outage therefore stalls the refresh of Silver and Gold until the next
  successful run (see the runbook).
- Free Edition limits apply: one active pipeline per type, five concurrent tasks, a daily compute
  quota.
- Only the `dev` target is deployed; `prod` is documented.
- Roadmap: PEAK_MODEL (features, training sets, models), then monitoring of data quality trends.

## License

Released under the MIT License. See [LICENSE](LICENSE).
