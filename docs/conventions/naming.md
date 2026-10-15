# Naming conventions

Defaults for data projects. A project may override an item through an ADR.

## General

- `snake_case` for tables, columns, files, functions and variables; `PascalCase` for classes.
- English only, no abbreviations unless they are domain terms (`kwh`, `cpf`, `utc`).
- Names describe content, not technology: `meter_readings`, not `kafka_table`.

## Tables

| Item | Pattern | Example |
|---|---|---|
| Catalog | `<project>_<env>` or platform default | `smart_meter_dev` |
| Schema | Medallion layer or domain | `bronze`, `silver`, `gold`, `ml` |
| Bronze table | `<source>_<entity>` | `kafka_meter_readings`, `files_meter_readings` |
| Silver table | `<entity>` (plural noun) | `meter_readings`, `households` |
| Gold table | `<entity>_<grain>` or business name | `household_daily_consumption` |
| Feature table | `<entity>_features_<grain>` | `household_features_daily` |
| Prediction table | `<model>_predictions` | `consumption_spike_predictions` |
| Model (registry) | `<catalog>.<schema>.<purpose>_model` | `smart_meter_dev.ml.consumption_spike_model` |

## Columns

| Kind | Pattern | Example |
|---|---|---|
| Identifier | `<entity>_id` | `household_id` |
| Event timestamp (UTC) | `<event>_ts` | `reading_ts` |
| Date | `<event>_date` | `reading_date` |
| Boolean | `is_<state>` / `has_<thing>` | `is_complete_day` |
| Measure | `<measure>_<unit>` | `energy_kwh`, `temperature_c` |
| Aggregate | `<agg>_<measure>_<window>` | `avg_energy_kwh_7d` |
| Label (ML) | `label_<target>` | `label_consumption_spike` |
| Technical metadata | leading underscore | `_ingested_at`, `_source_file`, `_rescued_data` |

## Code and repository

| Item | Pattern | Example |
|---|---|---|
| Feature name in specs | UPPER_SNAKE_CASE | `SMART_METER_INGESTION` |
| Branch | `<type>/<feature-kebab>` | `feat/smart-meter-ingestion` |
| ADR file | `NNNN-kebab-title.md` | `0003-aiven-as-kafka-broker.md` |
| Job / pipeline | `<project>_<purpose>` | `smart_meter_ingestion` |
